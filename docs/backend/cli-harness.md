# Cross-vault CLI harness

Requires Python 3.9+, Agentero CLI 0.11.7+ and `pip install pymupdf pikepdf numpy Pillow`. Keep `scripts/agentero-harness.py` and `scripts/pdf_optimizer.py` together.

```sh
python scripts/agentero-harness.py --vault /path/to/vault native paper list
python scripts/agentero-harness.py --vault /path/to/vault paper-text '{"ref":"papers/demo","pages":[1]}'
python scripts/agentero-harness.py --vault /path/to/vault notes-write '{"ref":"papers/demo","mode":"append","content":"Finding"}'
```

Helpers take one JSON object: `file-list/read/write` (`path`, optional `limit` or `content`/`mode`); `notes-get/write` (`ref`, optional `content`/`mode`); `paper-text` (`ref`, optional `pages`/`maxChars`); `page-read` (`ref`, `page`); `search` (`query`, optional `limit`, `year`, `publication`, `doi`, `isRead`); `import-pdf` (`files`, optional `parent`/`no_recognize`); `import-id` (`text`, optional `parent`); `download` (`ref`). Each call selects a vault; `--cli PATH` overrides the executable. Output is `{ok,data}` or `{ok:false,error}` (exit 1).

Imports/downloads use the existing PDF optimizer, retaining the smallest verified candidate and recoverable originals outside the vault (`--state`, default `~/.local/state/agentero-harness`). Local inputs stay unchanged; downloads are optimized after native import and before return. Raw native imports/downloads are blocked by the harness.

Limits/follow-up: no desktop or MCP required, but no MCP schema/resource parity. PDF text uses PyMuPDF; page reading needs existing v3 layout analysis; search uses path order rather than MCP ranking/page mapping. ID/download paths still need a live integration run. Run `python scripts/test-agentero-harness.py` with dependencies installed and `agentero` on PATH (or `AGENTERO_CLI`).
