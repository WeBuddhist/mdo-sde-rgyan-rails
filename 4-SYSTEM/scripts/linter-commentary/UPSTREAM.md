# Upstream

| | |
|---|---|
| Source repository | https://github.com/WeBuddhist/21-taras-rails |
| Path | `4-SYSTEM/scripts/linter-commentary/` |
| Pinned commit | `2d14cddf9bdd207e34da4eff58b1d0fa98141a5f` (2026-10-01, "Add support for yigchungs in linter and parser") |
| Copied | 2026-10-12 |

Copied byte-identical, without upstream's `output/` folder. Every later commit here is a local delta.

**Why vendored:** this vault needs the same API lint → parse step for its root texts and commentaries.

## Local changes

- 2026-10-12: **durchens** (variant readings written as footnotes `[^n]`). Added `durchen.py`, shared by all four tools. The linter takes footnote definitions out before the block-ID check, which used to fail on them, and checks each marker against its definition and lemma. Not Nalanda-specific: offer it back to 21-taras-rails.

## Ported to mdo-sde-rgyan-rails

| | |
|---|---|
| Ported from | https://github.com/WeBuddhist/Nalanda-texts-rails |
| Path | `4-SYSTEM/scripts/linter-commentary/` |
| Pinned commit | `fd801eb3a522a5e0622b431e5db4b25bbbd1237a` (2026-10-14, "update the name") |
| Copied | 2026-10-15 |

Copied byte-identical from Nalanda-texts-rails (which already carries the local changes above), without its `output/` folder and `__pycache__/`. Every later commit here is a delta against that copy.
