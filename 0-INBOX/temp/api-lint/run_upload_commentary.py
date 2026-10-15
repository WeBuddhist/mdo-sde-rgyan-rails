#!/usr/bin/env python3
"""Upload a commentary's parser-commentary payloads to the library API (dry run by default).

Reads 4-SYSTEM/scripts/parser-commentary/output/<stem>/ (text, edition, toc, durchens,
alignment, and yigchungs when present), checks them offline, then makes read-only GET calls
to the live API (category exists; no live text already has the same BDRC id).

Without --execute it SENDS NOTHING. With --execute it posts, in order:

    1. POST /v2/texts                          <- text.json       -> text_id
    2. POST /v2/texts/{text_id}/editions       <- edition.json    -> edition_id
    3. POST /v2/editions/{edition_id}/table-of-contents <- toc.json -> toc_id
    4. POST /v2/editions/{edition_id}/durchens <- durchens.json   (one atomic request)
    5. POST /v2/editions/{edition_id}/yigchungs <- yigchungs.json (only when present)

and after each step writes the id into the commentary's own frontmatter (the file in
0-INBOX/temp/segmented-commentary-with-toc/<stem>.md): text_id, edition_id, toc_id,
durchen_count, yigchung_count. A step whose id is already in the frontmatter is skipped, so an
interrupted run resumes. Ids are also kept in commentary-upload-status.json next to this script.

--execute needs --confirm <stem> (the same name again). Only run it after a human has approved
the dry-run plan.

    py -3 0-INBOX/temp/api-lint/run_upload_commentary.py Ar_3CBb_.toc
    py -3 0-INBOX/temp/api-lint/run_upload_commentary.py Ar_3CBb_.toc --no-live
    py -3 0-INBOX/temp/api-lint/run_upload_commentary.py Ar_3CBb_.toc --execute --confirm Ar_3CBb_.toc

Run from the vault root. Credentials as in run_upload_batch.py (WEBUDDHIST_* in env or .env).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import time as _time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_upload_batch as ub  # noqa: E402  (shares call / BASE / ApiError / env loading)

VAULT = ub.VAULT
OUT = VAULT / "4-SYSTEM" / "scripts" / "parser-commentary" / "output"
FILES = ("text", "edition", "toc", "durchens", "alignment", "yigchungs")
LEDGER = HERE / "commentary-upload-status.json"


def find_source(stem):
    for d in (VAULT / "0-INBOX" / "temp" / "segmented-commentary-with-toc",
              VAULT / "0-INBOX" / "processed" / "commentaries",
              VAULT / "1-SOURCES" / "Commentaries"):
        p = d / f"{stem}.md"
        if p.exists():
            return p
    return None


def check(stem, live):
    d = OUT / stem
    problems, warnings = [], []
    paths = {k: d / f"{stem}.{k}.json" for k in FILES}
    for k in ("text", "edition", "toc", "durchens", "alignment"):
        if not paths[k].exists():
            problems.append(f"missing payload {paths[k].name}")
    if problems:
        return None, problems, warnings
    p = {k: json.loads(paths[k].read_text(encoding="utf-8")) for k in FILES if paths[k].exists()}

    t = p["text"]
    if not t.get("title"):
        problems.append("text has no title")
    if not t.get("language"):
        problems.append("text has no language")
    for k in ("commentary_of", "translation_of"):
        if k in t and t[k] is None:
            problems.append(f"{k} is null in the text payload")
    if not t.get("commentary_of"):
        warnings.append("no commentary_of: the commentary will not be linked to a root text")

    ed = p["edition"]
    content = ed.get("content", "")
    n = len(content)
    if not content.strip():
        problems.append("edition content is empty")
    segs = (ed.get("segmentation") or {}).get("segments", [])
    refs = [s["reference"] for s in segs]
    if len(refs) != len(set(refs)):
        problems.append("duplicate segment references")
    empty = [s["reference"] for s in segs if not s.get("lines")]
    if empty:
        problems.append(f"{len(empty)} segment(s) have no lines (the API rejects the edition): "
                        f"{', '.join(empty[:5])}{' ...' if len(empty) > 5 else ''}")
    for s in segs:
        for sp in s.get("lines", []):
            if not 0 <= sp["start"] <= sp["end"] <= n:
                problems.append(f"segment {s['reference']} span out of range")
                break
    if not p["toc"].get("sections"):
        problems.append("toc has no sections")
    notes = p["durchens"].get("durchens", [])
    for dn in notes:
        sp = dn["span"]
        if not (0 <= sp["start"] < sp["end"] <= n) or not dn.get("text", "").strip():
            problems.append(f"durchen span {sp} out of range or empty text")
            break
    for y in (p.get("yigchungs") or {}).get("yigchungs", []):
        sp = y["span"]
        if not 0 <= sp["start"] < sp["end"] <= n:
            problems.append(f"yigchung span {sp} out of range")
            break
    if p["alignment"].get("alignments") == []:
        warnings.append("alignment is empty: nothing is aligned to a root text")

    src = find_source(stem)
    if src:
        text = src.read_text(encoding="utf-8")
        m = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.S)
        for key in ("text_id", "edition_id", "toc_id"):
            if m and re.search(rf"^{key}\s*:\s*\"?\S", m.group(1), re.M):
                warnings.append(f"source frontmatter already has {key}: a previous upload may exist")
        foot = len(re.findall(r"^\[\^\w+\]:", text, re.M))
        if foot != len(notes):
            problems.append(f"source has {foot} footnote definitions, payload has {len(notes)} durchens")

    if live:
        try:
            cat = t.get("category_id")
            if cat:
                try:
                    ub.call("GET", f"/v2/categories/{cat}", app=True)
                except ub.ApiError as exc:
                    if " 404 " in str(exc):
                        problems.append(f"category_id {cat} does not exist on the live API")
                    else:
                        raise
            if t.get("bdrc"):
                hits = ub.call("GET", f"/v2/texts?bdrc={t['bdrc']}&limit=5").get("items", [])
                if hits:
                    problems.append(f"a live text already has bdrc {t['bdrc']}: {[h.get('id') for h in hits]}")
        except ub.ApiError as exc:
            warnings.append(f"live check skipped: {exc}")
    return p, problems, warnings


def execute(stem, p, src):
    """Send the payloads; after each step write the id into the commentary's frontmatter."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    entry = ledger.setdefault(stem, {})
    ids = ub.read_fm_ids(src)

    def save():
        entry["updated"] = _dt.datetime.now().isoformat(timespec="seconds")
        text = json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        for attempt in range(10):  # the file can be briefly locked on Windows (indexer, sync)
            try:
                LEDGER.write_text(text, encoding="utf-8")
                return
            except OSError:
                if attempt == 9:
                    raise
                _time.sleep(0.5)

    def done(step, key, value, **kw):
        entry[key] = value
        entry.setdefault("log", []).append(
            {"step": step, "ts": _dt.datetime.now().isoformat(timespec="seconds"), **kw})
        save()
        ub.patch_fm(src, key, value)
        print(f"    {step:<9} {key} = {value}")

    if ids.get("text_id"):
        print(f"    text      skipped, text_id = {ids['text_id']} (already in the frontmatter)")
        text_id = ids["text_id"]
    else:
        text_id = ub.call("POST", "/v2/texts", p["text"])["id"]
        done("text", "text_id", text_id)

    if ids.get("edition_id"):
        print(f"    edition   skipped, edition_id = {ids['edition_id']}")
        eid = ids["edition_id"]
    else:
        ed = p["edition"]
        eid = ub.call("POST", f"/v2/texts/{text_id}/editions", ed)["id"]
        done("edition", "edition_id", eid, chars=len(ed["content"]),
             segments=len((ed.get("segmentation") or {}).get("segments", [])))

    if ids.get("toc_id"):
        print(f"    toc       skipped, toc_id = {ids['toc_id']}")
    else:
        done("toc", "toc_id", ub.call("POST", f"/v2/editions/{eid}/table-of-contents", p["toc"])["id"])

    notes = p["durchens"].get("durchens", [])
    if ids.get("durchen_count"):
        print(f"    durchens  skipped, durchen_count = {ids['durchen_count']}")
    elif notes:
        res = ub.call("POST", f"/v2/editions/{eid}/durchens", notes)
        if len(res) != len(notes):
            raise RuntimeError(f"durchens: sent {len(notes)}, got {len(res)} ids back")
        entry["durchen_ids"] = [r["id"] for r in res]
        done("durchens", "durchen_count", len(notes))

    marks = (p.get("yigchungs") or {}).get("yigchungs", [])
    if marks and not ids.get("yigchung_count"):
        got = []
        for start in range(0, len(marks), 500):
            got += [r["id"] for r in ub.call("POST", f"/v2/editions/{eid}/yigchungs", marks[start:start + 500])]
        entry["yigchung_ids"] = got
        done("yigchungs", "yigchung_count", len(marks))

    entry["status"] = "uploaded"
    entry["date"] = _dt.date.today().isoformat()
    save()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stem", help="parser output folder name, e.g. Ar_3CBb_.toc")
    ap.add_argument("--no-live", action="store_true", help="skip the read-only GET checks")
    ap.add_argument("--execute", action="store_true", help="send the requests (default: dry run)")
    ap.add_argument("--confirm", default="", help="with --execute: the stem again, as a deliberate second step")
    args = ap.parse_args()
    if args.execute and args.confirm != args.stem:
        ap.error(f"--execute needs --confirm {args.stem}")

    p, problems, warnings = check(args.stem, live=not args.no_live)
    print(f"== DRY RUN: {args.stem} -> {ub.BASE} ==")
    if p:
        ed = p["edition"]
        segs = (ed.get("segmentation") or {}).get("segments", [])
        print(f"  title        : {p['text'].get('title')}")
        print(f"  language     : {p['text'].get('language')}   category: {p['text'].get('category_id')}")
        print(f"  edition      : {len(ed.get('content', '')):,} chars, {len(segs)} segments")
        print(f"  toc          : {len(p['toc'].get('sections', []))} top section(s)")
        print(f"  durchens     : {len(p['durchens'].get('durchens', []))}")
        print(f"  yigchungs    : {len((p.get('yigchungs') or {}).get('yigchungs', []))}")
        print(f"  alignments   : {len(p['alignment'].get('alignments', []))}")
        print("\nPlan (nothing is sent):")
        print("  1. POST /v2/texts                          <- text.json       -> text_id")
        print("  2. POST /v2/texts/{text_id}/editions       <- edition.json    -> edition_id")
        print("  3. POST /v2/editions/{edition_id}/table-of-contents <- toc.json -> toc_id")
        print("  4. POST /v2/editions/{edition_id}/durchens <- durchens.json   (one atomic request)")
        if p.get("yigchungs"):
            print("  5. POST /v2/editions/{edition_id}/yigchungs <- yigchungs.json")
        print("  alignment    : skipped (no root edition to align to)" if not p["alignment"].get("alignments")
              else "  alignment    : PUT to the root edition (not implemented here)")
    for w in warnings:
        print(f"  WARN    {w}")
    for q in problems:
        print(f"  PROBLEM {q}")
    if problems:
        print("\nFAIL: fix the problems above before any upload.")
        return 1
    if not args.execute:
        print("\ndry run OK: payloads are consistent. Nothing was sent.")
        return 0
    src = find_source(args.stem)
    if not src:
        print("\nFAIL: cannot find the commentary .md to write the ids into.")
        return 1
    print(f"\n== EXECUTE: ids are written into {src.relative_to(VAULT)} ==")
    execute(args.stem, p, src)
    print("\nuploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
