# Root-text API batch — linter + parser

Runs `linter-root-text` then `parser-root-text` on every root text in `1-SOURCES/Text/`. How to run: the docstring of `0-INBOX/temp/api-lint/run_lint_batch.py`.

Updated 2026-10-15 · 1 texts (small 0 · medium 1 · large 0) · done 1 · failed 0 · **held 0** · to do 0 · **uploaded 1**

| What | Path |
|---|---|
| Status (one entry per text) | `0-INBOX/temp/api-lint/lint-status.json` |
| **Held texts — never run** (edit to release) | `0-INBOX/temp/api-lint/holds.json` |
| Log per text | `0-INBOX/temp/api-lint/logs/<id>.log` |
| Lint result | `4-SYSTEM/scripts/linter-root-text/output/<id>.lint.json` (or `.lint.errors.json`) |
| API payloads | `4-SYSTEM/scripts/parser-root-text/output/<id>/` (text, edition, toc, yigchungs, durchens) |
| Why the durchen texts are held | `0-INBOX/durchen-outliers-report.md` |
| Upload (script; ledger with every id) | `0-INBOX/temp/api-lint/run_upload_batch.py` · `0-INBOX/temp/api-lint/upload-status.json` |
| Titles changed to clear a title clash | `0-INBOX/temp/api-lint/retitled.json` |

`lint` OK = no errors · `err` / `warn` = linter errors / warnings (the language-list notice not counted) · `dur. warn` = footnote warnings (lemma not matched) · `src changed` = the linter rewrote the source frontmatter. Size from `0-INBOX/ROOT-WORKFLOW-BATCH.md`.

Upload columns: `upload` = uploaded / partial / failed · `text_id` = the id written into the source frontmatter · `ed.` / `toc` ✓ = created (`edition_id` / `toc_id` in the frontmatter) · `dur. up` / `yig. up` = notes sent / notes in the payload.

| # | id | size | chars | status | lint | err | warn | dur. warn | parse | segments | durchens | toc nodes | src changed | upload | text_id | ed. | toc | dur. up | yig. up | note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | མདོ་སྡེ་རྒྱན། | medium | 118,495 | done | OK | 0 | 6 | 0 | OK | 837 | 0 | 26 | no | uploaded | yNYUB52TDy6TpQqt5gjjV | ✓ | ✓ | 0/0 |  |  |

## Failures

Every text that failed lint, parse or upload. `error` is what the script recorded; `verified reason` is what investigating it found (kept in `0-INBOX/temp/api-lint/failure-reasons.json`). A text leaves this list, and its reason is removed, as soon as it succeeds.

None.
