# Cross-vault CLI harness

No MCP or desktop required. Reuses installed Agentero CLI for domain operations; adds file/notes, PDF text, layout-page and Markdown search helpers. No Rust/backend changes.

```sh
python3 -m venv ~/.local/share/agentero-harness/venv
~/.local/share/agentero-harness/venv/bin/pip install pymupdf pikepdf numpy Pillow
cp scripts/agentero-harness.py scripts/pdf_optimizer.py ~/.local/share/agentero-harness/
```

Entry: `~/.local/share/agentero-harness/venv/bin/python ~/.local/share/agentero-harness/agentero-harness.py --vault PATH OP ARGS`.

```sh
# Native commands use ordinary CLI arguments.
python scripts/agentero-harness.py --vault /path/to/vault native paper list
# Helpers take one JSON object.
python scripts/agentero-harness.py --vault /path/to/vault paper-text '{"ref":"papers/1706.03762","pages":[1]}'
python scripts/agentero-harness.py --vault /path/to/vault notes-write '{"ref":"papers/1706.03762","mode":"append","content":"Finding"}'
python scripts/agentero-harness.py --vault /path/to/vault import-id '{"text":"1706.03762"}'
```

Helpers: `file-list/read/write` (`path`, optional `limit` or `content`/`mode`); `notes-get/write` (`ref`, optional `content`/`mode`); `paper-text` (`ref`, optional `pages`/`maxChars`); `page-read` (`ref`, `page`); `search` (`query`, optional `limit`, `year`, `publication`, `doi`, `isRead`); `import-pdf` (`files`, optional `parent`/`no_recognize`); `import-id` (`text`, optional `parent`); `download` (`ref`). Every invocation selects its vault explicitly. Outputs `{ok,data}` or `{ok:false,error}`; failures exit 1. `--cli PATH` selects the installed binary.

Imports/downloads optimize PDFs before harness return, with recoverable originals outside the vault in `~/.local/state/agentero-harness`. Local PDF inputs are unchanged and optimized before copying. Downloaded PDFs enter the vault before optimization; no claim of reduced publisher traffic. Native passthrough blocks ordinary raw imports/downloads. Callers can still bypass the harness by invoking the CLI directly.

Scope: helper functionality, not identical MCP protocol/schema or PDFium output. PDF text uses PyMuPDF; `page-read` requires existing schemaVersion 3 layout analysis and does not generate it. Search uses deterministic path order, not MCP's ranking/page mapping. Notes preserve existing frontmatter for body replacement and append. Existing CLI operations remain unchanged. MCP resources have no protocol analogue; use CLI catalog/help and project context.

Verification: `python scripts/test-agentero-harness.py` in the dependency environment exercises all eight helpers, compressed local import, note preservation, two disposable vaults and path containment. Test CLI path currently targets the Pop!_OS runtime. Use installed CLI 0.11.7+ (local PDF import required).
