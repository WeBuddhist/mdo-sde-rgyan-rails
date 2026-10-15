"""Durchen (མཆན་འགྲེལ་ / variant-reading notes) written as Obsidian footnotes.

Shared by linter-root-text, linter-commentary, parser-root-text and
parser-commentary: the same file sits in each folder, byte-identical, so every
tool stays self-contained. Change one copy, copy it to the other three.

In the source a durchen is a footnote marker placed right after the text it
annotates, and a definition at the end of the file:

    རྣམ་དག་ཆོས་ཀྱི་དབྱིངས་ལ༌[^1]རོལ་མཛད་ཅིང་། །
    [^1]: ལ་ ༼སྣར། པེ།༽ ལས་

The note reads "<lemma> ༼<witness sigla>༽ <variant>": the lemma is the base
reading the note is about. The durchen span is that lemma, found by matching it
backwards from the marker in the edition content. When the lemma cannot be
matched (or the note has no ༼ at all, e.g. an editorial note), the span falls
back to the syllable before the marker, and the caller is told so.

Spans are half-open [start, end), absolute code-point offsets into the edition
content, and always non-empty: the API stores an empty span but never returns it.
"""

from __future__ import annotations

import re

# A definition is a whole line: "[^label]: note". Anything else that looks
# like "[^label]" is a marker.
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:[ \t]?(.*?)\s*$")
FOOTNOTE_MARK_RE = re.compile(r"\[\^([^\]\s]+)\]")

WITNESS_OPEN = "༼"     # ༼ opens the witness sigla; the lemma comes before it
TSHEG = "་"            # ་
TSHEG_NB = "༌"         # ༌ non-breaking tsheg, written before many markers
# Characters that end a syllable or a phrase: tsheg, shad and their variants.
PUNCT = set("་༌།༎༑༔")
# Whitespace, including the invisible characters the parsers treat as blank.
BLANK = set(" \t\r\n ​‌‍﻿")


def split_definitions(body):
    """Take the footnote definitions out of the body.

    Returns (body, defs, problems). Each definition line is replaced by an
    empty line, so line numbers and block boundaries stay where they were.
    defs maps label -> {"text", "line"} (1-based line in body). problems is a
    list of (level, message) for duplicate labels and blank notes.
    """
    lines = body.split("\n")
    defs, problems = {}, []
    for i, line in enumerate(lines):
        m = FOOTNOTE_DEF_RE.match(line.rstrip("\r"))
        if not m:
            continue
        label, text = m.group(1), m.group(2)
        lines[i] = ""
        if label in defs:
            problems.append(("ERROR",
                f"durchen [^{label}]: defined twice (lines {defs[label]['line']} and {i + 1})"))
            continue
        if not text.strip():
            problems.append(("ERROR",
                f"durchen [^{label}] (line {i + 1}): empty note — the API needs some text"))
        defs[label] = {"text": text.strip(), "line": i + 1}
    return "\n".join(lines), defs, problems


def lemma_of(note):
    """The base reading the note is about: the text before ༼, or None."""
    if WITNESS_OPEN not in note:
        return None
    lemma = note.split(WITNESS_OPEN, 1)[0].strip().rstrip("]").strip()
    return lemma or None


def _norm(c):
    return TSHEG if c == TSHEG_NB else c


def _span_end(content, end):
    """Where the span ends: after the trailing tsheg/shad before the marker,
    but not after trailing spaces ("ཏེ། [^1]" ends after ། )."""
    while end > 0 and content[end - 1] in BLANK:
        end -= 1
    return end


def _core_end(content, end):
    """End of the last letter before the marker (trailing tsheg, shad and
    spaces skipped)."""
    while end > 0 and (content[end - 1] in BLANK or content[end - 1] in PUNCT):
        end -= 1
    return end


def _match_lemma(content, core_end, lemma):
    """Start offset if the lemma ends at core_end, else None.

    Compared letter by letter going backwards, ignoring whitespace on both
    sides (the content joins verse lines with no separator) and treating ༌
    as ་.
    """
    want = [_norm(c) for c in lemma if c not in BLANK]
    while want and want[-1] in PUNCT:
        want.pop()
    if not want:
        return None
    i = core_end
    for c in reversed(want):
        while i > 0 and content[i - 1] in BLANK:
            i -= 1
        if i == 0 or _norm(content[i - 1]) != c:
            return None
        i -= 1
    return i


def _syllable_start(content, core_end):
    """Start of the syllable that ends at core_end."""
    i = core_end
    while i > 0 and content[i - 1] not in PUNCT and content[i - 1] not in BLANK:
        i -= 1
    return i


def locate(content, pos, note):
    """Span for a durchen whose marker sits at offset pos of content.

    Returns (start, end, how): how is "lemma" when the lemma matched,
    "no-lemma" when the note has no ༼ (fallback span), "mismatch" when the
    lemma did not match (fallback span), or None when there is no text before
    the marker at all (start and end are None too).
    """
    end = _span_end(content, pos)
    core = _core_end(content, pos)
    if core == 0:
        return None, None, None
    lemma = lemma_of(note)
    if lemma and all(c in PUNCT or c in BLANK for c in lemma):
        # A lemma of shad only ("།། །།"): the punctuation right before the marker.
        def bare(s):
            return [_norm(c) for c in s if c not in BLANK]
        if core < end and bare(content[core:end]) == bare(lemma):
            return core, end, "lemma"
    elif lemma:
        start = _match_lemma(content, core, lemma)
        if start is not None:
            return start, end, "lemma"
    return _syllable_start(content, core), end, ("mismatch" if lemma else "no-lemma")


def payload(durchens, content_length):
    """The POST bodies, sorted by span, after checking each against the API
    rules. durchens: dicts with start, end, text. Raises ValueError on the
    first bad one."""
    out = []
    for d in sorted(durchens, key=lambda d: (d["start"], d["end"])):
        start, end, text = d["start"], d["end"], d["text"]
        if not (isinstance(start, int) and isinstance(end, int)
                and not isinstance(start, bool) and not isinstance(end, bool)):
            raise ValueError(f"durchen span offsets must be integers: {d}")
        if not (0 <= start < end <= content_length):
            raise ValueError(f"durchen span out of range (content is {content_length}): {d}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"durchen text must be a non-blank string: {d}")
        out.append({"span": {"start": start, "end": end}, "text": text})
    return out
