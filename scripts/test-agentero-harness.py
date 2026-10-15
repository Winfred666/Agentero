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
    command = [sys.executable, str(SCRIPT), '--vault', str(vault)]
    result = subprocess.run([*command, 'file-read', '{"path":"notes/guide.md"}'], capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['data']['content'].startswith('vault 1')
    rejected = subprocess.run([*command, 'file-write', '{"path":"../escape.md","content":"no"}'], capture_output=True)
    assert rejected.returncode == 1 and not (root / 'escape.md').exists()
    print('PASS: eight helpers, compressed local imports, two vaults, frontmatter, CLI entry, containment')
