#!/usr/bin/env python3
"""Headless, per-vault CLI harness. Native operations pass through to agentero."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

LIMIT = 2 * 1024 * 1024
BINARY = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'gz', 'sqlite', 'db', 'exe', 'bin'}


def cli(binary, vault, *args):
    result = subprocess.run([binary, '--vault', str(vault), '--json', *args],
                            capture_output=True, text=True, timeout=300)
    if result.returncode and not result.stdout.strip():
        raise ValueError(result.stderr.strip() or 'native command failed')
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        if not result.returncode and any(arg in ('--help', '-h', '--version', '-V', 'help') for arg in args):
            return {'text': result.stdout}
        raise
    if result.returncode or not payload.get('ok'):
        raise ValueError(payload.get('error', {}).get('message', result.stderr))
    return payload['data']


def path_in(vault, relative):
    parts = Path(relative.replace('\\', '/'))
    if parts.is_absolute() or '..' in parts.parts:
        raise ValueError('path must be vault-relative')
    if any(p.startswith('.') and p != '.agents' for p in parts.parts):
        raise ValueError('hidden paths are not available')
    path = (vault / parts).resolve()
    if not path.is_relative_to(vault):
        raise ValueError('path escapes vault')
    return path


def read(path):
    if path.suffix.lower().lstrip('.') in BINARY:
        raise ValueError('use paper-text for PDFs, not file-read')
    if path.stat().st_size > LIMIT:
        raise ValueError('text exceeds 2 MiB')
    text = path.read_text(encoding='utf-8')
    if '\0' in text:
        raise ValueError('binary content')
    return text


def write(path, content):
    if len(content.encode()) > LIMIT or '\0' in content:
        raise ValueError('invalid or oversized text')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


def paper(config, reference):
    data = cli(config.cli, config.vault, 'paper', 'get', reference)
    record = data['paper']
    return record, path_in(config.vault, record['path'])


def frontmatter(text):
    lines = text.splitlines(keepends=True)
    if lines and lines[0].strip() == '---':
        for index, line in enumerate(lines[1:], 1):
            if line.strip() == '---':
                return ''.join(lines[:index + 1]), ''.join(lines[index + 1:])
    return '', text


def compress(config, source, destination):
    """Bounded worker; backup outside the vault; original on worker failure."""
    state = config.state
    state.mkdir(parents=True, exist_ok=True)
    if state.is_relative_to(config.vault):
        raise ValueError('backup directory must be outside vault')
    backup_dir = Path(tempfile.mkdtemp(prefix='original-', dir=state))
    backup = backup_dir / source.name
    shutil.copy2(source, backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('pdf_optimizer.py')),
                                 str(source), str(destination)], capture_output=True, text=True, timeout=120)
        if result.returncode:
            raise ValueError('PDF worker failed')
        report = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        shutil.copy2(backup, destination)
        report = {'original_bytes': backup.stat().st_size, 'final_bytes': backup.stat().st_size,
                  'fallback': 'original retained'}
    report['backup'] = str(backup)
    return report


def run(config, op, args):
    vault = config.vault
    mode = args.get('mode', 'replace')
    if op in ('file-write', 'notes-write') and mode not in ('replace', 'append'):
        raise ValueError('mode must be replace or append')
    if op in ('file-list', 'file-read', 'file-write'):
        relative = args.get('path', '')
        path = path_in(vault, relative)
        if op == 'file-list':
            entries = []
            for item in sorted(path.iterdir()):
                if item.name.startswith('.') or item.name in ('target', 'node_modules'):
                    continue
                resolved = item.resolve()
                if resolved.is_relative_to(vault):
                    entries.append({'name': item.name, 'path': str(item.relative_to(vault)),
                                    'kind': 'directory' if item.is_dir() else 'file'})
            limit = max(1, min(int(args.get('limit', 200)), 500))
            return {'path': relative, 'entries': entries[:limit], 'truncated': len(entries) > limit}
        if op == 'file-read':
            content = read(path)
            return {'path': relative, 'content': content, 'bytes': len(content.encode())}
        if path.name in ('NOTES.md', 'catalog.sqlite', 'annotations.json', 'layout.json', 'layout-index.json'):
            raise ValueError('managed file; use dedicated operation')
        if path.suffix.lower().lstrip('.') in BINARY:
            raise ValueError('binary file')
        content = args['content']
        if mode == 'append' and path.exists():
            content = read(path) + content
        write(path, content)
        return {'path': relative, 'mode': mode, 'bytes': len(content.encode())}
    if op in ('notes-get', 'notes-write', 'paper-text', 'page-read'):
        record, folder = paper(config, args['ref'])
        if op.startswith('notes-'):
            path = path_in(vault, str((folder / 'NOTES.md').relative_to(vault)))
            existing = read(path) if path.exists() else ''
            if op == 'notes-get':
                return {'path': str(path.relative_to(vault)), 'content': existing}
            content = args['content']
            front, _ = frontmatter(existing)
            if mode == 'append' and existing.strip():
                content = existing.rstrip() + '\n\n' + content.rstrip() + '\n'
            elif not frontmatter(content)[0]:
                # JSON strings are valid YAML scalar aliases, including punctuation in IDs.
                front = front or '---\naliases: [' + json.dumps(record['id']) + ']\n---\n'
                content = front.rstrip() + '\n\n' + content.strip() + '\n'
            write(path, content)
            return {'path': str(path.relative_to(vault)), 'mode': mode}
        if op == 'page-read':
            path = path_in(vault, str((folder / 'source/layout.json').relative_to(vault)))
            layout = json.loads(path.read_text(encoding='utf-8'))
            page = int(args['page'])
            if page < 1:
                raise ValueError('page must be 1-based')
            if layout.get('schemaVersion') != 3:
                raise ValueError('page-read requires schemaVersion 3 layout analysis')
            regions = sorted(layout['regions'], key=lambda r: (r['pageIndex'], r['bbox']['y'], r['bbox']['x'], r['id']))
            count = max((r['pageIndex'] + 1 for r in regions), default=0)
            selected = [{k: r[k] for k in ('id', 'kind', 'title', 'text', 'bbox') if k in r}
                        for r in regions if r['pageIndex'] == page - 1]
            non_text = ('figure', 'image', 'chart', 'table', 'formula', 'algorithm')
            return {'paperPath': record['path'], 'page': page, 'pageCount': count,
                    'regionCount': len(selected), 'regions': selected,
                    'textRegions': [r for r in selected if r.get('text', '').strip()
                                    and not any(k in r['kind'].lower() for k in non_text)]}
        import pymupdf
        primary = folder / (folder.name + '.pdf')
        pdf = primary if primary.is_file() else next(iter(sorted(folder.glob('*.pdf'))), None)
        if pdf is None:
            raise ValueError('no PDF in paper folder')
        pdf = path_in(vault, str(pdf.relative_to(vault)))
        with pymupdf.open(pdf) as document:
            pages = args.get('pages', list(range(1, len(document) + 1)))
            budget = max(1, min(int(args.get('maxChars', 20000)), 50000))
            result = []
            for number in pages:
                if not isinstance(number, int) or not 1 <= number <= len(document):
                    raise ValueError('invalid 1-based page')
                text = document[number - 1].get_text()
                result.append({'page': number, 'charCount': len(text), 'text': text[:budget]})
            return {'path': record['path'], 'pageCount': len(document), 'pages': result}
    if op == 'search':
        terms = args['query'].lower().split()
        if not terms:
            raise ValueError('query must not be empty')
        scope = path_in(vault, args.get('path', ''))
        if not scope.is_dir():
            raise ValueError('search path must be a directory')
        max_depth = args.get('maxDepth')
        if max_depth is not None and (type(max_depth) is not int or max_depth < 0):
            raise ValueError('maxDepth must be a nonnegative integer')
        records = cli(config.cli, vault, 'paper', 'list', '--full')
        filters = {k: args[k] for k in ('year', 'publication', 'doi', 'isRead') if k in args}
        limit = max(1, min(int(args.get('limit', 60)), 200))
        hits = []
        for root, dirs, files in os.walk(scope, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in ('target', 'node_modules'))
            if max_depth is not None and len(Path(root).relative_to(scope).parts) >= max_depth:
                dirs.clear()
            for name in sorted(files):
                if not name.lower().endswith('.md'):
                    continue
                try:
                    path = path_in(vault, str((Path(root) / name).relative_to(vault)))
                    text = read(path)
                except (ValueError, UnicodeError, OSError):
                    continue
                if not all(term in text.lower() for term in terms):
                    continue
                relative = str(path.relative_to(vault))
                record = next((r for r in records if relative.startswith(r['path'] + '/')), None)
                if filters:
                    if record is None:
                        continue
                    if any((record.get('is_read') != value if key == 'isRead' else
                            record.get(key) != value if key == 'year' else
                            str(value).lower() not in str(record.get(key) or '').lower())
                           for key, value in filters.items()):
                        continue
                lines = text.splitlines()
                line = next((i for i, s in enumerate(lines, 1) if any(t in s.lower() for t in terms)), 1)
                hits.append({'path': relative, 'paperPath': record['path'] if record else None,
                             'line': line, 'snippet': lines[line-1][:200] if lines else ''})
                if len(hits) > limit:
                    return {'hits': hits[:limit], 'truncated': True}
        return {'hits': hits[:limit], 'truncated': len(hits) > limit}
    if op == 'import-pdf':
        with tempfile.TemporaryDirectory() as tmp:
            files, reports = [], []
            for index, name in enumerate(args['files']):
                source = Path(name).expanduser().resolve(strict=True)
                target = Path(tmp) / str(index) / source.name
                reports.append(compress(config, source, target))
                files.append(str(target))
            command = ['import', 'pdf', *files, '--parent', args.get('parent', 'papers')]
            if args.get('no_recognize'):
                command.append('--no-recognize')
            return {'import': cli(config.cli, vault, *command), 'compression': reports}
    if op in ('import-id', 'download'):
        command = ['import', 'id', args['text'], '--parent', args.get('parent', 'papers')] if op == 'import-id' else ['paper', 'download', args['ref']]
        data = cli(config.cli, vault, *command)
        if op == 'import-id':
            folder = path_in(vault, data['path'])
        else:
            _, folder = paper(config, args['ref'])
        reports = [compress(config, pdf, pdf) for pdf in folder.glob('*.pdf')]
        return {'result': data, 'compression': reports}
    raise ValueError('unknown helper operation: ' + op)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', required=True)
    parser.add_argument('--cli', default=shutil.which('agentero') or 'agentero')
    parser.add_argument('--state', default=str(Path.home() / '.local/state/agentero-harness'))
    parser.add_argument('operation', help='file-list/read/write, notes-get/write, paper-text, page-read, search, import-pdf/id, download, or native')
    parser.add_argument('arguments', nargs=argparse.REMAINDER, help='one JSON object for helpers; CLI arguments for native')
    config = parser.parse_args()
    config.vault = Path(config.vault).expanduser().resolve(strict=True)
    config.state = Path(config.state).expanduser().resolve()
    if config.operation == 'native':
        # Imports/downloads must pass through compression, not the raw native escape hatch.
        if not config.arguments or config.arguments[0] == 'import' or config.arguments[:2] == ['paper', 'download']:
            raise ValueError('use import-id, import-pdf or download helpers')
        result = cli(config.cli, config.vault, *config.arguments)
    else:
        result = run(config, config.operation, json.loads(config.arguments[0]) if config.arguments else {})
    print(json.dumps({'ok': True, 'data': result}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'ok': False, 'error': {'message': str(error)}}))
        sys.exit(1)
