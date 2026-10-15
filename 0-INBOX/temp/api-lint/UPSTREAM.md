# Upstream

`run_lint_batch.py`, `run_upload_batch.py` and `run_upload_commentary.py` copied 2026-10-15 from
https://github.com/WeBuddhist/Nalanda-texts-rails `0-INBOX/temp/api-lint/` at commit
`fd801eb3a522a5e0622b431e5db4b25bbbd1237a`. Kept at the same relative path so `VAULT = HERE.parents[2]`
and every path inside them resolve unchanged.

Local changes:
- `run_lint_batch.py` `_sizes()`: returns early when `0-INBOX/ROOT-WORKFLOW-BATCH.md` is absent
  (this vault has no workflow batch table); size classes then come from the character count.
