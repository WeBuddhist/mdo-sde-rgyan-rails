from __future__ import annotations

import re
import unicodedata

import durchen
from constants import (
    LICENSE_VALUES, ROLE_VALUES, LANGUAGE_VALUES, LANGUAGE_NAME_MAP,
    LANGUAGE_CODE_TO_NAME, LANG_TAG_MAP,
)

SEGMENT_TYPES = frozenset({"paragraph", "verse", "title", "back_matter", "front_matter", "top_segment"})
EDITION_TYPES = frozenset({"diplomatic", "critical", "collated"})

# Headers: ^n, ^n-n, ^n-n-n, ^n-n-n-… (any depth). Verses/segments: max ^n-n-n (3 parts).
REF_RE = re.compile(r'(\^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*$')
VERSE_REF_MAX_PARTS = 3
TRANSCLUSION_RE = re.compile(r'^\s*!\[\[.*?#\^.*?\]\]\s*$')


def _ref_part_count(ref):
    """Count hyphen-separated parts in a ^ref (caret stripped)."""
    return len(ref.lstrip("^").split("-")) if ref else 0


def is_nonempty_string(value):
    return isinstance(value, str) and len(value) >= 1


def resolve_language(value):
    v = value.strip()
    if v in LANGUAGE_VALUES:
        return v, None
    mapped = LANGUAGE_NAME_MAP.get(v.lower())
    if mapped:
        return mapped, f'"{v}" resolved to code "{mapped}"'
    return None, (
        f'"{v}" is not a valid language code or name. '
        f'Valid codes: {sorted(LANGUAGE_VALUES)}. '
        f'Valid names: {sorted(LANGUAGE_NAME_MAP)}'
    )


def validate_nullable_string(value, field, items):
    if value is None:
        return
    if not is_nonempty_string(value):
        items.append(("ERROR", f"{field}: expected string (>=1 char) or null"))


def validate_localized_object(value, field, items):
    if not isinstance(value, dict) or not value:
        items.append(("ERROR", f"{field}: expected object with at least one property"))
        return
    for key, item in value.items():
        if not is_nonempty_string(key):
            items.append(("ERROR", f"{field}: property names must be non-empty strings"))
        if not is_nonempty_string(item):
            items.append(("ERROR", f"{field}.{key}: expected string with at least one character"))


def _resolved_lang_code(data):
    raw = data.get("language")
    if is_nonempty_string(raw):
        code, _ = resolve_language(raw)
        if code:
            return code
    vault_tag = data.get("lang_tag")
    if vault_tag and vault_tag in LANGUAGE_VALUES:
        return vault_tag
    return None


def _is_roman(text):
    """True if every letter in text is Latin (IAST diacritics included)."""
    return all(
        not ch.isalpha() or "LATIN" in unicodedata.name(ch, "")
        for ch in text
    )


def _assert_roman(text, field, items):
    if isinstance(text, str) and not _is_roman(text):
        items.append((
            "ERROR",
            f"{field}: Pali titles must be in Roman script (e.g. IAST), got {text!r}",
        ))


def _is_pali_key(key):
    return isinstance(key, str) and key.split("-", 1)[0] == "pi"


def _lang_key_base(key):
    """The plain language code behind a title key.

    A script-suffixed key ("sa-x-iast") is reduced to its base ("sa"), the
    same way build.py normalizes it before upload.
    """
    if isinstance(key, str) and "-x-" in key:
        return key.split("-x-", 1)[0]
    return key


def _check_lang_key(key, field, items):
    """The key of a title / alt_titles entry must be a language code the API
    knows (the list fetched from /v2/languages)."""
    if not isinstance(key, str) or not key.strip():
        items.append(("ERROR", f"{field}: language key must be a non-empty string"))
        return
    base = _lang_key_base(key)
    if base not in LANGUAGE_VALUES:
        name = LANGUAGE_CODE_TO_NAME.get(base)
        items.append((
            "ERROR",
            f'{field}: "{key}" is not a valid language code'
            + (f' (did you mean "{name}"?)' if name else "")
            + f". Valid codes (from the languages API): {sorted(LANGUAGE_VALUES)}",
        ))


def _validate_title_lang_keys(data, items):
    """Every language key used in title / alt_titles must be a known code."""
    title = data.get("title")
    if isinstance(title, dict):
        for key in title:
            _check_lang_key(key, f"title.{key}", items)

    alt = data.get("alt_titles")
    if isinstance(alt, list):
        for i, item in enumerate(alt):
            if isinstance(item, dict):
                for key in item:
                    _check_lang_key(key, f"alt_titles[{i}].{key}", items)


def _validate_pali_roman_titles(data, items):
    """Titles keep the text's own language and script, except Pali:
    Pali title/alt_titles must be in Roman script (still keyed "pi")."""
    is_pali = _resolved_lang_code(data) == "pi"

    title = data.get("title")
    if isinstance(title, str):
        if is_pali:
            _assert_roman(title, "title", items)
    elif isinstance(title, dict):
        for key, val in title.items():
            if _is_pali_key(key):
                _assert_roman(val, f"title.{key}", items)

    alt = data.get("alt_titles")
    if isinstance(alt, str):
        if is_pali:
            _assert_roman(alt, "alt_titles", items)
    elif isinstance(alt, list):
        for i, item in enumerate(alt):
            if isinstance(item, str):
                if is_pali:
                    _assert_roman(item, f"alt_titles[{i}]", items)
            elif isinstance(item, dict):
                for key, val in item.items():
                    if _is_pali_key(key):
                        _assert_roman(val, f"alt_titles[{i}].{key}", items)


def validate_contribution(value, field, index, items):
    item_field = f"{field}[{index}]"
    if not isinstance(value, dict):
        items.append(("ERROR", f"{item_field}: expected object"))
        return
    keys = set(value)
    if "ai_id" in keys:
        extra = keys - {"ai_id", "role"}
        if extra:
            items.append(("ERROR", f"{item_field}: additional properties forbidden: {sorted(extra)}"))
        if not is_nonempty_string(value.get("ai_id")):
            items.append(("ERROR", f"{item_field}.ai_id: expected string with at least one character"))
        if value.get("role") not in ROLE_VALUES:
            items.append(("ERROR", f"{item_field}.role: expected one of {sorted(ROLE_VALUES)}"))
        return
    extra = keys - {"type", "id", "bdrc_id", "role"}
    if extra:
        items.append(("ERROR", f"{item_field}: additional properties forbidden: {sorted(extra)}"))
    validate_nullable_string(value.get("id"), f"{item_field}.id", items)
    validate_nullable_string(value.get("bdrc_id"), f"{item_field}.bdrc_id", items)
    if value.get("role") not in ROLE_VALUES:
        items.append(("ERROR", f"{item_field}.role: expected one of {sorted(ROLE_VALUES)}"))


def _validate_line(line, field, items):
    if not isinstance(line, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(line) - {"start", "end"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "start" not in line:
        items.append(("ERROR", f"{field}.start: required"))
    elif not isinstance(line["start"], int) or isinstance(line["start"], bool) or line["start"] < 0:
        items.append(("ERROR", f"{field}.start: expected integer >= 0, got {line['start']!r}"))
    if "end" not in line:
        items.append(("ERROR", f"{field}.end: required"))
    elif not isinstance(line["end"], int) or isinstance(line["end"], bool) or line["end"] < 1:
        items.append(("ERROR", f"{field}.end: expected integer >= 1, got {line['end']!r}"))


def _validate_annotation_metadata(meta, field, items):
    if not isinstance(meta, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(meta) - {"name"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "name" in meta:
        validate_nullable_string(meta["name"], f"{field}.name", items)


def _validate_segment(seg, field, items):
    if not isinstance(seg, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(seg) - {"lines", "type", "reference"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "lines" not in seg:
        items.append(("ERROR", f"{field}.lines: required"))
    else:
        lines = seg["lines"]
        if not isinstance(lines, list) or len(lines) < 1:
            items.append(("ERROR", f"{field}.lines: expected array with >= 1 items"))
        else:
            for i, line in enumerate(lines):
                _validate_line(line, f"{field}.lines[{i}]", items)
    seg_type = seg.get("type", "paragraph")
    if seg_type not in SEGMENT_TYPES:
        items.append(("ERROR", f"{field}.type: expected one of {sorted(SEGMENT_TYPES)}, got {seg_type!r}"))
    if "reference" in seg:
        validate_nullable_string(seg["reference"], f"{field}.reference", items)


def _validate_page(page, field, items):
    if not isinstance(page, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(page) - {"lines", "reference"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "lines" not in page:
        items.append(("ERROR", f"{field}.lines: required"))
    else:
        lines = page["lines"]
        if not isinstance(lines, list) or len(lines) < 1:
            items.append(("ERROR", f"{field}.lines: expected array with >= 1 items"))
        else:
            for i, line in enumerate(lines):
                _validate_line(line, f"{field}.lines[{i}]", items)
    if "reference" not in page:
        items.append(("ERROR", f"{field}.reference: required"))
    elif not is_nonempty_string(page["reference"]):
        items.append(("ERROR", f"{field}.reference: expected string >= 1 character"))


def _validate_volume(vol, field, items):
    if not isinstance(vol, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(vol) - {"index", "pages", "metadata"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "index" in vol and vol["index"] is not None:
        idx = vol["index"]
        if not isinstance(idx, int) or isinstance(idx, bool) or idx < 1:
            items.append(("ERROR", f"{field}.index: expected integer >= 1 or null, got {idx!r}"))
    if "pages" not in vol:
        items.append(("ERROR", f"{field}.pages: required"))
    else:
        pages = vol["pages"]
        if not isinstance(pages, list) or len(pages) < 1:
            items.append(("ERROR", f"{field}.pages: expected array with >= 1 items"))
        else:
            for i, page in enumerate(pages):
                _validate_page(page, f"{field}.pages[{i}]", items)
    if "metadata" in vol and vol["metadata"] is not None:
        _validate_annotation_metadata(vol["metadata"], f"{field}.metadata", items)


def _validate_pagination(pag, items):
    field = "pagination"
    if not isinstance(pag, dict):
        items.append(("ERROR", f"{field}: expected object"))
        return
    extra = set(pag) - {"volumes", "metadata"}
    if extra:
        items.append(("ERROR", f"{field}: additional properties forbidden: {sorted(extra)}"))
    if "volumes" not in pag:
        items.append(("ERROR", f"{field}.volumes: required"))
    else:
        vols = pag["volumes"]
        if not isinstance(vols, list) or len(vols) < 1:
            items.append(("ERROR", f"{field}.volumes: expected array with >= 1 items"))
        else:
            for i, vol in enumerate(vols):
                _validate_volume(vol, f"{field}.volumes[{i}]", items)
    if "metadata" in pag and pag["metadata"] is not None:
        _validate_annotation_metadata(pag["metadata"], f"{field}.metadata", items)


def _extract_ref(lines):
    for line in reversed(lines):
        stripped = line.rstrip()
        if stripped:
            m = REF_RE.search(stripped)
            return m.group(1) if m else None
    return None


def _validate_segmentation_refs(body, items):
    blocks = re.split(r'\n[ \t]*\n', body.strip())
    header_seen = {}
    segment_seen = {}
    block_num = 0
    for raw in blocks:
        block = raw.strip()
        if not block:
            continue
        block_num += 1
        lines = block.split('\n')
        content_lines = [l for l in lines if not TRANSCLUSION_RE.match(l)]
        if not any(l.strip() for l in content_lines):
            continue
        is_header = lines[0].lstrip().startswith('#')
        ref = _extract_ref(lines)
        kind = "header" if is_header else "segment"
        if ref is None:
            expected = "^n-n-n-…" if is_header else "^n-n-n (max 3 parts)"
            items.append(("ERROR", f"{kind} {block_num}: missing reference ({expected})"))
            continue
        if not is_header and _ref_part_count(ref) > VERSE_REF_MAX_PARTS:
            items.append(("ERROR",
                f"{kind} {block_num}: reference {ref!r} has {_ref_part_count(ref)} parts; "
                f"verses allow at most ^n-n-n ({VERSE_REF_MAX_PARTS} parts)"))
            continue
        bucket = header_seen if is_header else segment_seen
        if ref in bucket:
            items.append(("ERROR",
                f"{kind} {block_num}: duplicate reference {ref!r} "
                f"(first seen at {kind} {bucket[ref]})"))
        else:
            bucket[ref] = block_num


# Yigchung (small-script gloss) markup: <small>…</small>. The parser turns
# each run into a yigchung annotation span, so a stray tag would put marks on
# the wrong text. A run may continue onto the next line of the same block,
# but never past the end of the block (or of a heading line).
SMALL_TAG_RE = re.compile(r"<(/?)small>", re.IGNORECASE)


def _tag_context(line, m, width=12):
    """A short piece of the line around a tag, for messages."""
    a, b = max(0, m.start() - width), min(len(line), m.end() + width)
    return ("…" if a else "") + line[a:b] + ("…" if b < len(line) else "")


def _validate_yigchung_tags(body, items):
    """ERROR for every stray <small> / </small>: a </small> with no open run,
    a <small> inside an open run, or a run not closed by the end of its block
    (for a heading, by the end of the heading line)."""
    blocks = re.split(r'\n[ \t]*\n', body.strip())
    block_num = 0
    for raw in blocks:
        block = raw.strip()
        if not block:
            continue
        block_num += 1
        lines = [l.rstrip('\r') for l in block.split('\n')]
        content_lines = [l for l in lines if not TRANSCLUSION_RE.match(l)]
        if not any(l.strip() for l in content_lines):
            continue
        is_header = lines[0].lstrip().startswith('#')
        kind = "header" if is_header else "segment"
        ref = _extract_ref(lines)
        where = f"{kind} {block_num}" + (f" ({ref})" if ref else "")
        # A heading is one line; content may span several.
        check_lines = [lines[0]] if is_header else content_lines
        in_small = False
        for n, line in enumerate(check_lines, start=1):
            at = where if is_header else f"{where}, line {n}"
            for m in SMALL_TAG_RE.finditer(line):
                if not m.group(1):
                    if in_small:
                        items.append(("ERROR",
                            f"{at}: stray <small> (a <small> run is already open): "
                            f"{_tag_context(line, m)!r}"))
                    in_small = True
                else:
                    if not in_small:
                        items.append(("ERROR",
                            f"{at}: stray </small> (no <small> is open): "
                            f"{_tag_context(line, m)!r}"))
                    in_small = False
        if in_small:
            end = "the heading line" if is_header else "the block"
            items.append(("ERROR", f"{where}: stray <small> (not closed by the end of {end})"))


# Durchen (variant-reading notes) are footnotes: a marker [^n] right after the
# text, a definition "[^n]: lemma ༼sigla༽ variant" at the end of the file. The
# parser makes one durchen per marker, spanning the lemma before it.
INLINE_MARK_RE = re.compile(
    SMALL_TAG_RE.pattern + "|" + durchen.FOOTNOTE_MARK_RE.pattern, re.IGNORECASE
)


def _validate_durchens(body, notes, items):
    """Check every footnote marker against its definition and the text before
    it, building the edition content the way the parser does (headings and
    transclusions left out, markup and block IDs dropped, lines joined)."""
    parts, marks, pos = [], [], 0
    blocks = re.split(r'\n[ \t]*\n', body.strip())
    block_num = 0
    for raw in blocks:
        block = raw.strip()
        if not block:
            continue
        block_num += 1
        lines = [l.rstrip('\r') for l in block.split('\n')]
        content_lines = [l for l in lines if not TRANSCLUSION_RE.match(l)]
        if not any(l.strip() for l in content_lines):
            continue
        is_header = lines[0].lstrip().startswith('#')
        ref = _extract_ref(lines)
        if is_header:
            labels = [m.group(1) for m in durchen.FOOTNOTE_MARK_RE.finditer(lines[0])]
            for label in labels:
                items.append(("WARN",
                    f"header {block_num} ({ref}): footnote [^{label}] in a heading — headings "
                    f"are not edition content, so it gets no durchen"))
                marks.append({"label": label, "pos": None, "where": f"header {block_num}"})
            continue
        if not any(durchen.FOOTNOTE_MARK_RE.sub("", l).strip() for l in content_lines):
            # Markers left on their own: they mark the end of the text before them.
            for l in content_lines:
                for m in durchen.FOOTNOTE_MARK_RE.finditer(l):
                    marks.append({"label": m.group(1), "pos": pos, "where": f"segment {block_num}"})
            continue
        if ref is None or _ref_part_count(ref) > VERSE_REF_MAX_PARTS:
            continue  # reported by _validate_segmentation_refs; the parser skips it
        where = f"segment {block_num} ({ref})"
        last = max(i for i, l in enumerate(content_lines) if l.strip())
        for i, line in enumerate(content_lines):
            out, line_marks, prev = [], [], 0
            for m in INLINE_MARK_RE.finditer(line.rstrip()):
                out.append(line[prev:m.start()])
                prev = m.end()
                if m.group(2) is not None:
                    line_marks.append((sum(map(len, out)), m.group(2)))
            out.append(line.rstrip()[prev:])
            text = "".join(out)
            if i == last:
                idx = text.rfind(ref)
                if idx != -1:
                    text = text[:idx].rstrip()
            for off, label in line_marks:
                marks.append({"label": label, "pos": pos + min(off, len(text)), "where": where})
            parts.append(text)
            pos += len(text)

    content = "".join(parts)
    seen = set()
    placed = 0
    for mk in marks:
        label, where = mk["label"], mk["where"]
        if label in seen:
            items.append(("WARN",
                f"{where}: footnote [^{label}] is marked more than once — one durchen for each"))
        seen.add(label)
        note = notes.get(label)
        if note is None:
            items.append(("ERROR", f"{where}: footnote [^{label}] has no definition"))
            continue
        if mk["pos"] is None or not note["text"]:
            continue
        start, end, how = durchen.locate(content, mk["pos"], note["text"])
        if how is None:
            items.append(("ERROR",
                f"{where}: footnote [^{label}] has no text before it to attach the durchen to"))
            continue
        placed += 1
        if how == "mismatch":
            items.append(("WARN",
                f"{where}: footnote [^{label}] lemma {durchen.lemma_of(note['text'])!r} does not "
                f"end at the marker — the durchen will span the syllable before it, "
                f"{content[start:end]!r}"))
        elif how == "no-lemma":
            items.append(("WARN",
                f"{where}: footnote [^{label}] has no ༼…༽ witness, so no lemma — the durchen "
                f"will span the syllable before it, {content[start:end]!r}"))
    for label, note in notes.items():
        if label not in seen:
            items.append(("WARN",
                f"footnote [^{label}] (line {note['line']}) is defined but never marked in the "
                f"text — no durchen"))
    if notes or marks:
        items.append(("INFO", f"durchens: {placed} from {len(notes)} footnote definition(s)"))


def _extract_headers(body):
    headers = []
    for line in body.split('\n'):
        stripped = line.rstrip('\r').rstrip()
        if not stripped.startswith('#'):
            continue
        level = len(stripped) - len(stripped.lstrip('#'))
        text_with_ref = stripped.lstrip('#').strip()
        m = REF_RE.search(text_with_ref)
        ref = m.group(1) if m else None
        text = text_with_ref[:m.start()].rstrip() if m else text_with_ref
        headers.append((level, text, ref))
    return headers


def validate_edition(data, body):
    items = []

    URL_SOURCE_FIELDS = ("source", "source_url")
    matched_url = next((f for f in URL_SOURCE_FIELDS if data.get(f)), None)
    if not matched_url:
        items.append(("ERROR",
            "source: required; add a `source` (or `source_url`) field with the text's URL "
            "(e.g. source: https://...)"))
    else:
        val = str(data[matched_url]).strip()
        if not (val.startswith("http://") or val.startswith("https://")):
            items.append(("ERROR",
                f"source ({matched_url}): value must be a URL (http/https), got {val!r}"))
        else:
            items.append(("INFO", f"source: {matched_url} = {val!r}"))

    if not data.get("lang_tag") and not data.get("language"):
        items.append(("ERROR", "lang_tag or language: at least one required"))

    if not data.get("file_type"):
        items.append(("INFO", "file_type: not set"))

    edition_type = data.get("edition_type")
    if edition_type and edition_type not in EDITION_TYPES:
        items.append(("ERROR",
            f"edition_type: expected one of {sorted(EDITION_TYPES)}, got {edition_type!r}"))
    elif edition_type and edition_type != "critical":
        items.append(("WARN", f"edition_type: expected 'critical' for now, got {edition_type!r}"))

    if not body or not body.strip():
        items.append(("ERROR", "content body is empty"))
    else:
        # Footnote definitions are not edition blocks: take them out first.
        body, notes, note_problems = durchen.split_definitions(body)
        items.extend(note_problems)
        _validate_segmentation_refs(body, items)
        _validate_yigchung_tags(body, items)
        _validate_durchens(body, notes, items)

    return items


def validate_toc(data, body):
    items = []
    headers = _extract_headers(body)

    if not headers:
        items.append(("ERROR", "toc: no headers found in document"))
        return items

    items.append(("INFO", f"toc: {len(headers)} headers found"))

    first_level = headers[0][0]
    if first_level != 1:
        items.append(("ERROR",
            f"toc: first header must be level 1 (#), got level {first_level}"))

    prev_level = None
    for level, text, ref in headers:
        if ref is None:
            items.append(("ERROR",
                f"toc: header missing reference marker: {text!r}"))
        if prev_level is not None and level > prev_level + 1:
            ref_str = ref or repr(text)
            items.append(("ERROR",
                f"toc: heading level skip at {ref_str}: "
                f"h{level} after h{prev_level} (max allowed: h{prev_level + 1})"))
        prev_level = level

    return items


def validate_text_input(data):
    items = []

    # Vault YAML uses bdrc_work_id; build.py maps it to API field bdrc.
    bdrc_val = data.get("bdrc") or data.get("bdrc_work_id")
    if "bdrc" in data or "bdrc_work_id" in data:
        source_key = "bdrc" if data.get("bdrc") else "bdrc_work_id"
        validate_nullable_string(bdrc_val, source_key, items)
    else:
        items.append(("INFO", "bdrc_work_id: not set (optional)"))

    for field in ("wiki", "date", "commentary_of", "translation_of"):
        if field in data:
            validate_nullable_string(data[field], field, items)
        else:
            items.append(("INFO", f"{field}: not set (optional)"))

    if data.get("file_type") == "translation":
        if not data.get("root_text"):
            items.append(("ERROR", "root_text: required for file_type 'translation'"))
        else:
            items.append(("INFO", f"root_text: {data['root_text']!r}"))

    title_val = data.get("title")
    if "title" not in data:
        items.append(("ERROR", "title: required field missing"))
    elif isinstance(title_val, str):
        if not title_val.strip():
            items.append(("ERROR", "title: value must be non-empty"))
    else:
        validate_localized_object(title_val, "title", items)

    if "alt_titles" in data and data["alt_titles"] is not None:
        alt = data["alt_titles"]
        if isinstance(alt, str):
            if not alt.strip():
                items.append(("ERROR", "alt_titles: value must be non-empty"))
        elif isinstance(alt, list):
            if not alt:
                items.append(("ERROR", "alt_titles: expected a non-empty list"))
            for i, item in enumerate(alt):
                if isinstance(item, str):
                    if not item.strip():
                        items.append(("ERROR", f"alt_titles[{i}]: expected non-empty string"))
                elif isinstance(item, dict):
                    # legacy {lang: title} objects still accepted
                    validate_localized_object(item, f"alt_titles[{i}]", items)
                else:
                    items.append(("ERROR", f"alt_titles[{i}]: expected string (or legacy localized object)"))
        else:
            items.append(("ERROR", "alt_titles: expected string or list of strings"))

    _validate_title_lang_keys(data, items)
    _validate_pali_roman_titles(data, items)

    vault_tag = data.get("lang_tag")
    if "language" not in data:
        if vault_tag and vault_tag in LANGUAGE_VALUES:
            inferred_name = LANGUAGE_CODE_TO_NAME.get(vault_tag, vault_tag)
            items.append(("INFO", f'language: not set -- inferred "{inferred_name}" from lang_tag "{vault_tag}"'))
        elif vault_tag:
            items.append(("ERROR", f'language: missing and lang_tag "{vault_tag}" is not a canonical code -- set language explicitly'))
        else:
            items.append(("ERROR", "language: required field missing"))
    elif not is_nonempty_string(data["language"]):
        items.append(("ERROR", "language: expected string with at least one character"))
    else:
        code, note = resolve_language(data["language"])
        if code is None:
            items.append(("ERROR", f"language: {note}"))

    if vault_tag and vault_tag not in LANG_TAG_MAP:
        items.append(("ERROR", f'lang_tag: "{vault_tag}" is not a known tag. Known: {sorted(LANG_TAG_MAP)}'))

    if "category_id" not in data:
        items.append(("ERROR", "category_id: required field missing"))
    elif not is_nonempty_string(data["category_id"]):
        items.append(("ERROR", "category_id: expected string with at least one character"))

    if "license" not in data:
        items.append(("ERROR", f'license: required; set one of {sorted(LICENSE_VALUES)}'))
    elif data["license"] not in LICENSE_VALUES:
        items.append(("ERROR", f"license: expected one of {sorted(LICENSE_VALUES)}, got {data['license']!r}"))

    _contrib_fields = ("contributions", "author", "author in English", "author_in_english",
                      "translator", "translator in English", "translator_in_english")
    if not any(data.get(f) for f in _contrib_fields):
        items.append(("WARN", "contributions: author/translator missing — ignored for now"))
    elif "contributions" in data:
        contribs = data["contributions"]
        if not isinstance(contribs, list):
            items.append(("ERROR", "contributions: expected array"))
        else:
            for i, item in enumerate(contribs):
                validate_contribution(item, "contributions", i, items)

    if "tag_ids" not in data:
        items.append(("INFO", "tag_ids: not set (optional)"))
    else:
        tag_ids = data["tag_ids"]
        if not isinstance(tag_ids, list):
            items.append(("ERROR", "tag_ids: expected array"))
        else:
            for i, item in enumerate(tag_ids):
                if not is_nonempty_string(item):
                    items.append(("ERROR", f"tag_ids[{i}]: expected string with at least one character"))

    return items
