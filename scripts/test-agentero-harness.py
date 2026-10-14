"""Run with the harness Python environment; uses real CLI and disposable vaults."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pymupdf

SCRIPT = Path(__file__).with_name('agentero-harness.py')
CLI = '/home/openclaw-svc/.local/bin/agentero'

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'test-paper.pdf'
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), 'Cross vault paper text')
    doc.save(source)
    doc.close()
    def call(vault, op, args):
        result = subprocess.run([sys.executable, str(SCRIPT), '--vault', str(vault), '--cli', CLI,
            '--state', str(root / 'backups'), op, json.dumps(args)], capture_output=True, text=True)
        payload = json.loads(result.stdout)
        assert result.returncode == 0, payload
        return payload['data']
    for index in range(2):
        vault = root / f'vault-{index}'
        subprocess.run([CLI, '--json', 'vault', 'create', str(vault)], check=True, capture_output=True)
        call(vault, 'import-pdf', {'files': [str(source)], 'no_recognize': True})
        rows = json.loads(subprocess.check_output([CLI, '--vault', str(vault), '--json', 'paper', 'list']))['data']
        reference = rows[0]['path']
        call(vault, 'file-write', {'path': 'notes/guide.md', 'content': f'vault {index} cross research'})
        assert call(vault, 'file-read', {'path': 'notes/guide.md'})['content'].startswith(f'vault {index}')
        assert any(e['name'] == 'guide.md' for e in call(vault, 'file-list', {'path': 'notes'})['entries'])
        before = call(vault, 'notes-get', {'ref': reference})['content']
        call(vault, 'notes-write', {'ref': reference, 'content': 'Research body'})
        call(vault, 'notes-write', {'ref': reference, 'mode': 'append', 'content': 'more'})
        notes = call(vault, 'notes-get', {'ref': reference})['content']
        assert 'aliases:' in notes and 'Research body' in notes and 'more' in notes
        text = call(vault, 'paper-text', {'ref': reference})
        assert 'Cross vault paper text' in text['pages'][0]['text']
        folder = vault / reference / 'source'
        folder.mkdir(exist_ok=True)
        (folder / 'layout.json').write_text(json.dumps({'schemaVersion': 3, 'regions': [
            {'id': 'p', 'kind': 'paragraph', 'pageIndex': 0, 'text': 'Cross vault paper text',
             'bbox': {'x': 0, 'y': 1, 'w': 10, 'h': 2}}]}))
        page = call(vault, 'page-read', {'ref': reference, 'page': 1})
        assert page['regionCount'] == 1 and page['textRegions'][0]['id'] == 'p'
        assert call(vault, 'search', {'query': 'cross research'})['hits']
        rejected = subprocess.run([sys.executable, str(SCRIPT), '--vault', str(vault),
            'file-write', '{"path":"../escape.md","content":"no"}'], capture_output=True)
        assert rejected.returncode == 1 and not (root / 'escape.md').exists()
    print('PASS: eight file/reading helpers, compressed local imports, two vaults, containment')
