"""Object-preserving PDF optimizer worker. Never overwrites until verified."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np
import pikepdf
import pymupdf as fitz


def annotations(page):
    return [(a.type, tuple(a.rect), a.info, a.colors, a.flags, a.vertices,
             a.border, a.opacity) for a in (page.annots() or [])]


def validate(source, candidate):
    with fitz.open(source) as before, fitz.open(candidate) as after:
        if len(before) != len(after) or before.metadata != after.metadata:
            return False
        if before.get_xml_metadata() != after.get_xml_metadata() or before.get_toc() != after.get_toc():
            return False
        for old, new in zip(before, after):
            if old.rect != new.rect or old.rotation != new.rotation or old.get_text() != new.get_text():
                return False
            def links(page):
                return [{k: str(v) for k, v in item.items() if k not in ('xref', 'id')}
                        for item in page.get_links()]
            if links(old) != links(new) or annotations(old) != annotations(new):
                return False
            # Drawing commands remain vector paths, not rasterized page images.
            if old.get_drawings() != new.get_drawings():
                return False
            a, b = (p.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False) for p in (old, new))
            if (a.width, a.height, a.n) != (b.width, b.height, b.n):
                return False
            delta = np.abs(np.frombuffer(a.samples, np.uint8).astype(np.int16)
                           - np.frombuffer(b.samples, np.uint8).astype(np.int16))
            if delta.mean() > 0.8 or np.mean(delta > 20) > 0.005:
                return False
    return True


def candidate(source, output, quality):
    with pikepdf.open(source) as pdf:
        if pdf.is_encrypted or any(isinstance(o, pikepdf.Dictionary) and
            (o.get('/Type') == '/Sig' or '/ByteRange' in o) for o in pdf.objects):
            raise ValueError('encrypted/signed PDF retained')
        if quality is not None:
            for obj in pdf.objects:
                if not isinstance(obj, pikepdf.Stream) or obj.get('/Subtype') != '/Image':
                    continue
                if obj.get('/ColorSpace') not in (pikepdf.Name.DeviceRGB, pikepdf.Name.DeviceGray):
                    continue
                if int(obj.get('/BitsPerComponent', 0)) != 8 or any(k in obj for k in ('/SMask', '/Mask', '/Decode')):
                    continue
                if obj.get('/Filter') in (pikepdf.Name.DCTDecode, pikepdf.Name.JPXDecode):
                    continue
                if len(obj.read_raw_bytes()) < 100000:
                    continue
                try:
                    image = pikepdf.PdfImage(obj).as_pil_image()
                    if image.mode not in ('RGB', 'L'):
                        continue
                    buffer = io.BytesIO()
                    image.save(buffer, format='JPEG', quality=quality, optimize=True, subsampling=0)
                    if len(buffer.getvalue()) < len(obj.read_raw_bytes()):
                        obj.write(buffer.getvalue(), filter=pikepdf.Name.DCTDecode)
                        if '/DecodeParms' in obj:
                            del obj['/DecodeParms']
                except Exception:
                    continue
        pdf.save(output, compress_streams=True, recompress_flate=True,
                 object_stream_mode=pikepdf.ObjectStreamMode.generate, fix_metadata_version=False)
    with pikepdf.open(output) as check:
        if check.check_pdf_syntax():
            raise ValueError('PDF syntax warnings')


def optimize(source, destination):
    source, destination = Path(source), Path(destination)
    original = source.stat().st_size
    trials = []
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        best, size = source, original
        for quality in (None, 90, 85):
            output = Path(folder) / f'{quality}.pdf'
            try:
                candidate(source, output, quality)
                accepted = output.stat().st_size < size and validate(source, output)
                trials.append({'quality': quality, 'bytes': output.stat().st_size, 'accepted': accepted})
                if accepted:
                    best, size = output, output.stat().st_size
            except Exception as error:
                trials.append({'quality': quality, 'accepted': False, 'reason': str(error)})
        if best != source or destination != source:
            staging = Path(folder) / 'selected.pdf'
            shutil.copy2(best, staging)
            os.replace(staging, destination)
    return {'original_bytes': original, 'final_bytes': size, 'saved_bytes': original-size,
            'candidates': trials, 'path': str(destination)}


if __name__ == '__main__':
    print(json.dumps(optimize(sys.argv[1], sys.argv[2])))
