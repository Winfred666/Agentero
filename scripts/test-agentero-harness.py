"""Run with the harness dependencies and agentero on PATH (or AGENTERO_CLI)."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pymupdf

SCRIPT = Path(__file__).with_name('agentero-harness.py')
harness = runpy.run_path(str(SCRIPT))
CLI = os.environ.get('AGENTERO_CLI', 'agentero')

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory).resolve()
    source = root / 'test-paper.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((72, 72), 'Cross vault paper text')
        doc.save(source)
    def call(op, **args):
        return harness['run'](config, op, args)
    for index in range(2):
        vault = root / f'vault-{index}'
        config = SimpleNamespace(cli=CLI, vault=vault, state=root / 'backups')
        harness['cli'](CLI, root, 'vault', 'create', str(vault))
        report = call('import-pdf', files=[str(source)], no_recognize=True)['compression'][0]
        assert report['final_bytes'] < report['original_bytes'], report
        assert Path(report['backup']).read_bytes() == source.read_bytes()
        reference = harness['cli'](CLI, vault, 'paper', 'list')[0]['path']
        call('file-write', path='notes/guide.md', content=f'vault {index} cross research')
        assert call('file-read', path='notes/guide.md')['content'].startswith(f'vault {index}')
        assert any(e['name'] == 'guide.md' for e in call('file-list', path='notes')['entries'])
        front = harness['frontmatter'](call('notes-get', ref=reference)['content'])[0]
        call('notes-write', ref=reference, content='Research body')
        call('notes-write', ref=reference, mode='append', content='more')
        notes = call('notes-get', ref=reference)['content']
        assert front and notes.startswith(front) and 'Research body' in notes and 'more' in notes
        assert 'Cross vault paper text' in call('paper-text', ref=reference)['pages'][0]['text']
        folder = vault / reference / 'source'
        folder.mkdir(exist_ok=True)
        shutil.copyfile(SCRIPT.parent.parent / 'test/fixtures/mcp-search/papers/alpha/source/layout.json', folder / 'layout.json')
        assert call('page-read', ref=reference, page=2)['textRegions'][0]['id'] == 'page2-body'
        assert call('search', query='cross research')['hits']
        assert call('search', query='cross research', path='notes', maxDepth=0)['hits']
        assert not call('search', query='cross research', maxDepth=0)['hits']
        call('file-write', path=reference + '/scope.md', content='scope regression')
        rows = harness['cli'](CLI, vault, 'paper', 'list', '--full')
        record = next(row for row in rows if row['path'] == reference)
        for key, value in [('isRead', record['is_read']), ('year', record.get('year')),
                           ('publication', record.get('publication') or ''), ('doi', record.get('doi') or '')]:
            hits = call('search', query='scope regression', path=reference, maxDepth=0, **{key: value})['hits']
            assert len(hits) == 1 and hits[0]['paperPath'] == reference
        assert not call('search', query='scope regression', path=reference, isRead=not record['is_read'])['hits']
        call('file-write', path='notes/second.md', content='cross research')
        assert call('search', query='cross research', path='notes', limit=1)['truncated']
    command = [sys.executable, str(SCRIPT), '--vault', str(vault)]
    result = subprocess.run([*command, 'file-read', '{"path":"notes/guide.md"}'], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['data']['content'].startswith('vault 1')
    for args in [('paper', 'list', '--help'), ('paper', 'get', '-h'), ('paper', 'help', 'list'), ('--version',)]:
        result = subprocess.run([*command, 'native', *args], capture_output=True, text=True, check=True)
        assert json.loads(result.stdout)['data']['text'].strip()
    result = subprocess.run([*command, 'native', 'paper', 'not-a-command'], capture_output=True, text=True)
    assert result.returncode == 1 and 'unrecognized subcommand' in json.loads(result.stdout)['error']['message']
    rejected = subprocess.run([*command, 'file-write', '{"path":"../escape.md","content":"no"}'], capture_output=True)
    assert rejected.returncode == 1 and not (root / 'escape.md').exists()
    print('PASS: eight helpers, compressed local imports, two vaults, frontmatter, CLI entry, containment')
