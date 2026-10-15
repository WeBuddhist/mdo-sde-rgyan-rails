# Parser — Commentary

Takes a commentary file and its linter output and writes the API payloads for the text, edition, table of contents and alignment to the root text.

Forked from `parser-root-text`. Content segments default to **`paragraph`**, and `alignment.json` is always written. Run `linter-commentary` first.

## What it does

1. **extract_text_input** — takes `text_input` from the lint JSON (or `resolved` from a `.lint.errors.json`), drops empty fields and contributors without an id, writes `text.json` (includes `commentary_of` when set)
2. **build_edition** — builds the edition content and its segments with character spans from the body text (headings left out), writes `edition.json`, the yigchung annotations found in `<small>…</small>`, writes `yigchungs.json`, and the durchens (variant readings) written as footnotes, writes `durchens.json`
3. **build_toc** — builds a nested table of contents from the headings (headings are used only here), writes `toc.json`
4. **build_alignment** — links commentary segments to root-text segments through transclusions, writes `alignment.json`

The parser stops if the file's `file_type` is set to anything other than `commentary`.

## Output

```
output/
  <stem>/                  # one folder per source file, named after it
    <stem>.text.json        # text_input payload (with commentary_of)
    <stem>.edition.json     # edition metadata, content and segments
    <stem>.yigchungs.json   # yigchung (small-script) annotation spans — only when the text has <small>
    <stem>.durchens.json    # durchen (variant-reading) notes with their spans
    <stem>.toc.json         # nested TOC with character spans
    <stem>.alignment.json   # commentary → root-text alignments
```

## Edition

Same as `parser-root-text` (see its README): headings add no segment and no text to `content` (they are used only for the TOC), one segment per content block, the block ID as `reference`, `metadata.source` from `source` or `source_url`, `metadata.type` from `edition_type` (default `critical`).

### Segment types

The shape of the block is checked first, then its ID:

| Test | Type | Example |
|------|------|---------|
| **Two or more lines with no empty line between them** | `verse` | a quoted verse, one line per unit |
| ID starts with `T` or `t` | `top_segment` | `^T-1` |
| Any part is an uppercase Roman numeral | `front_matter` | `^I-1`, `^2-I-3` |
| Any part is lowercase letters only | `back_matter` | `^a-1` |
| Anything else | `paragraph` | `^1-1`, `^1-2x3`, `^1-U4` |

**Verse wins over the ID.** A verse in the intro or the colophon is `verse`, not `front_matter` or `back_matter`: those mark where a block sits, and the block's shape says what it is. The ID types only blocks that are not verse.

An empty line inside a block — including a line holding only an invisible character such as a zero-width space — stops it being verse, and the parser warns about it. Such a block is usually two paragraphs that each need their own block ID, and Obsidian shows no gap there, so the warning is the only sign.

A block of prose that was hard-wrapped onto several lines without a blank line between them reads as verse to this rule. Keep a paragraph on one line.

## Durchens

Built exactly as in `parser-root-text`.

A durchen (variant-reading note) is written as an Obsidian footnote: a marker right after the text it is about, and a definition at the end of the file.

```
རྣམ་དག་ཆོས་ཀྱི་དབྱིངས་ལ༌[^1]རོལ་མཛད་ཅིང་། །

[^1]: ལ་ ༼སྣར། པེ།༽ ལས་
```

The note reads `<lemma> ༼<witness sigla>༽ <variant>`. `durchens.json` holds one item per marker, sorted by span. Each item is exactly the body of `POST /v2/editions/{edition_id}/durchens`, which takes **one object per request**, so post the items one at a time:

```json
{"durchens": [{"span": {"start": 412, "end": 414}, "text": "ལ་ ༼སྣར། པེ།༽ ལས་"}]}
```

- The marker is dropped from `content`, and the definition lines are not content at all
- `text` is the whole note, as written
- **The span is the lemma**: the text before `༼`, matched backwards from the marker. Matching ignores whitespace, because verse lines are joined with no separator, and treats `༌` as `་`. Trailing tsheg and shad are inside the span, and trailing spaces are not. In the example above the span is `ལ༌`
- A lemma of shad only (`།། །།`) spans the shad just before the marker
- **Fallback (warning):** when the lemma does not end at the marker, or the note has no `༼` (an editorial note), the span is the syllable just before the marker. The marker position is certain, but the start of the span is then a guess, so check those notes
- Spans are half-open `[start, end)` absolute code-point offsets into `content`, like yigchungs, and never empty: the API stores an empty span but never returns it
- Markers left on their own after a block (`…། །` followed by a blank line and `[^5]`) mark the end of the text before them
- A marker in a heading, or in a block that is skipped, gets no durchen (warning). So does a marker with no definition, or with an empty note
- Every payload is checked against the API rules before it is written: integer offsets, `start < end <= len(content)`, non-blank `text`, and no keys besides `span` and `text`. `metadata` is never sent, since the API never returns it
- The file is written even when there are no footnotes (`{"durchens": []}`)
- The API does not check for duplicates: before re-uploading an edition, delete or check its existing durchens

The span logic is in `durchen.py`. The same file sits in `linter-root-text`, `linter-commentary`, `parser-root-text` and `parser-commentary`: change one, copy it to the other three.

## Alignment

Transclusions in the commentary (`![[1-SOURCES/Text/<lang>-<title>.md#^1-1]]`) say which root-text segment the commentary is discussing.

- `source_segment_reference` — segment in the commentary
- `target_segment_reference` — segment in the root text

A transclusion, or a group of consecutive transclusions, opens a scope. Transclusions written one after another count as one group even when blank lines separate them (keep them on separate lines — the parser joins them). Every commentary block that follows is aligned to those root-text segments until the scope ends, at either:

- the next transclusion group, or
- any heading — commentary after a heading must carry its own transclusion to be aligned

Headings are never aligned. Transclusions that point to a heading in the `root_text` file are skipped with a warning, since headings are not segments. Alignment can be many-to-one (several paragraphs on one verse) or many-to-many (several paragraphs on a group of verses).

## Requirements

```
pip install PyYAML pyewts
```

Python 3.8+.

## How to run

Run from the vault root (the folder that contains `1-SOURCES/` and `4-SYSTEM/`):

```bash
python3 4-SYSTEM\scripts\parser-commentary\parser.py "1-SOURCES\Commentaries\<lang>-<title>.md" "4-SYSTEM\scripts\linter-commentary\output\<lang>-<title>.lint.json"
```

## Notes

- If the lint JSON has no alt titles or contributors, the parser warns and carries on
- Blocks without a block ID are skipped with a warning; so are content blocks whose ID has more than 3 parts
- Inline formatting for interlinear glosses (`<small>…</small>`) is dropped from `content`: the gloss text stays, the tags do not. Each run becomes a yigchung annotation in `yigchungs.json`: one `{"span": {"start", "end"}}` POST body per unbroken run, absolute code-point offsets into the edition `content`, built exactly as in `parser-root-text` (see its README, *Yigchungs*). Stray `<small>` / `</small>` tags are reported by `linter-commentary`; the parser also stops on one (no edition or yigchung payload, exit status 1) as a safety net. The source file is never changed.
- Non-breaking spaces (U+00A0) become ordinary spaces in `content`.
- Headings deeper than level 6 (7+ `#`) are often written in bold, since Obsidian renders only six levels. For those, the `**` markers are dropped from the TOC title.
- Blocks that contain only transclusions are left out of the edition content; they feed alignment only
- TOC spans are offsets into the edition `content` (which has no heading text), built the same way as in `parser-root-text`
- Tibetan TOC titles in Wylie are converted to Unicode
