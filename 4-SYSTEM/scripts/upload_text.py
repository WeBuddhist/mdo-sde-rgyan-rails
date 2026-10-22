#!/usr/bin/env python3
"""upload_text.py — upload one linted + parsed root text or commentary to the WeBuddhist
library. A commentary is linked to its root text and aligned to the root edition.

Run the matching linter + parser first (linter-root-text + parser-root-text, or
linter-commentary + parser-commentary). This sends the parser payloads in
4-SYSTEM/scripts/parser-<kind>/output/<stem>/ in this order:

    1. POST /v2/texts                          <- <stem>.text.json      -> text_id
                                                  (a commentary carries commentary_of = the root's text_id;
                                                   settable only at creation, so the text is
                                                   never re-created when the file has a text_id)
    2. POST /v2/texts/{text_id}/editions       <- <stem>.edition.json   -> edition_id
    3. POST /v2/editions/{edition_id}/table-of-contents
                                               <- <stem>.toc.json       -> toc_id
    4. POST /v2/editions/{edition_id}/durchens <- <stem>.durchens.json  all notes as ONE list (atomic;
                                                  one id back per note, kept in the ledger)
    5. POST /v2/editions/{edition_id}/yigchungs <- <stem>.yigchungs.json lists of 500
    6. PUT  /v2/editions/{root_edition}/alignments/{edition_id}        (commentary only)
                                               <- <stem>.alignment.json, re-oriented so the ROOT
                                                  edition is the source (as translation-upload does)

After each successful step the id is written into the commentary's frontmatter (text_id,
edition_id, toc_id, durchen_count, yigchung_count, aligned_to_edition_id) and a receipt goes to the ledger
0-INBOX/temp/api-upload/upload-ledger.json. A step already recorded is skipped, so an
interrupted run resumes instead of duplicating.

Dry run is the default: it checks the payloads and (GET only) the live root, and prints the
plan. Nothing is sent without --execute, and --execute is run only after a human has
confirmed the plan in the conversation.

    python 4-SYSTEM/scripts/upload_text.py "<file.md>"             # dry run
    python 4-SYSTEM/scripts/upload_text.py "<file.md>" --execute   # after confirmation
    python 4-SYSTEM/scripts/upload_text.py "<file.md>" --verify    # read everything back

Credentials come from the environment, or from a WEBUDDHIST_* line in a git-ignored .env at
the vault root or 4-SYSTEM/scripts/.env, and are never printed:
    WEBUDDHIST_API_KEY    X-API-Key   (sent when set)
    WEBUDDHIST_API_BASE   default https://library.webuddhist.com

API helpers adapted from Nalanda-texts-rails 0-INBOX/temp/api-lint/run_upload_batch.py (root
texts, no alignment; durchens/yigchungs posted the same way) and the alignment step from
4-SYSTEM/Skills/translation-upload.
Run from the vault root.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VAULT = Path.cwd()
LEDGER = VAULT / "0-INBOX" / "temp" / "api-upload" / "upload-ledger.json"


def _load_env():
    for env in (VAULT / ".env", VAULT / "4-SYSTEM" / "scripts" / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                m = re.match(r"^\s*(?:export\s+)?(WEBUDDHIST_[A-Z_]+)\s*=\s*(.*?)\s*$", line)
                if m and m.group(1) not in os.environ:
                    os.environ[m.group(1)] = m.group(2).strip("'\"")


_load_env()
BASE = os.environ.get("WEBUDDHIST_API_BASE", "https://library.webuddhist.com").rstrip("/")


class ApiError(RuntimeError):
    pass


def call(method, path, body=None, timeout=300, retries=3):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("WEBUDDHIST_API_KEY", "")
    if key:
        h["X-API-Key"] = key
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            # only GETs are retried: a write may have been applied, and a retry would duplicate it
            if exc.code >= 500 and method == "GET" and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"HTTP {exc.code} {method} {path}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if method == "GET" and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"network error {method} {path}: {getattr(exc, 'reason', exc)}") from None


def paged(path):
    out, off = [], 0
    sep = "&" if "?" in path else "?"
    while True:
        d = call("GET", f"{path}{sep}limit=200&offset={off}")
        items = d.get("items", []) if isinstance(d, dict) else (d or [])
        out += items
        if not (isinstance(d, dict) and d.get("has_more")) or not items:
            return out
        off += len(items)


# ---------------------------------------------------------------- frontmatter

FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def read_fm(path):
    m = FM_RE.match(path.read_text(encoding="utf-8"))
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k = re.match(r"^([A-Za-z_]+)\s*:\s*\"?(.*?)\"?\s*$", line)
        if k:
            out[k.group(1)] = k.group(2)
    return out


def patch_fm(path, key, value):
    """Set `key: value` in the frontmatter (replace, or insert after commentary_of/category_id)."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text[:2000] else "\n"
    lines = text.split(nl)
    close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    new = f"{key}: {value}"
    for i in range(1, close):
        if re.match(rf"^{re.escape(key)}\s*:", lines[i]):
            lines[i] = new
            break
    else:
        anchors = [i for i in range(1, close)
                   if re.match(r"^(category_id|commentary_of|text_id|edition_id|toc_id)\s*:", lines[i])]
        lines.insert((max(anchors) if anchors else close - 1) + 1, new)
    tmp = path.with_suffix(".md.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(lines))
    os.replace(tmp, path)


def load_ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}


def save_ledger(ledger):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main

ID_KEYS = ("text_id", "edition_id", "toc_id", "durchen_count", "yigchung_count", "aligned_to_edition_id")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", help="a root-text or commentary file in 1-SOURCES/")
    ap.add_argument("--execute", action="store_true", help="send the requests (default: dry run)")
    ap.add_argument("--verify", action="store_true", help="GET the uploaded records back")
    args = ap.parse_args(argv)

    path = Path(args.file)
    fm = read_fm(path)
    ftype = fm.get("file_type")
    if ftype not in ("commentary", "root-text"):
        sys.exit(f"{path.name}: file_type is {ftype!r}; this uploads 'root-text' or 'commentary'")
    is_comm = ftype == "commentary"
    root_tid = root_eid = None
    if is_comm:
        root_path = VAULT / fm.get("root_text", "")
        if not root_path.is_file():
            sys.exit(f"root_text {fm.get('root_text')!r} not found")
        rfm = read_fm(root_path)
        root_tid, root_eid = rfm.get("text_id"), rfm.get("edition_id")
        if not (root_tid and root_eid):
            sys.exit(f"{root_path.name}: no text_id/edition_id — upload the root first")

    stem = path.stem
    out = VAULT / "4-SYSTEM" / "scripts" / ("parser-commentary" if is_comm else "parser-root-text") / "output" / stem
    kinds = ("text", "edition", "toc", "alignment") if is_comm else ("text", "edition", "toc")
    p = {k: json.loads((out / f"{stem}.{k}.json").read_text(encoding="utf-8")) for k in kinds}
    for k in ("durchens", "yigchungs"):
        f = out / f"{stem}.{k}.json"
        p[k] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None

    ledger = load_ledger()
    entry = ledger.setdefault(stem, {"file": str(path).replace("\\", "/"), "receipts": []})
    for k in ID_KEYS:
        if fm.get(k) and not entry.get(k):
            entry[k] = fm[k]
        if not fm.get(k) and entry.get(k) and k in ("text_id", "edition_id", "toc_id"):
            sys.exit(f"ledger has {k}={entry[k]} but the frontmatter has none — reconcile first "
                     f"(if the records were deleted, move them to the ledger's 'deleted' history)")

    if args.verify:
        tid, eid = entry.get("text_id"), entry.get("edition_id")
        t = call("GET", f"/v2/texts/{tid}")
        print(f"text {tid}: title={t.get('title')} commentary_of={t.get('commentary_of')}")
        print(f"edition {eid}: {len(paged(f'/v2/editions/{eid}/segmentation/segments'))} segments")
        d = call("GET", f"/v2/editions/{eid}/durchens") or []
        print(f"durchens: {len(d.get('items', []) if isinstance(d, dict) else d)}")
        if is_comm:
            print(f"alignment root {root_eid} -> {eid}: {len(paged(f'/v2/editions/{root_eid}/alignments/{eid}'))} pairs")
        return 0

    # ---- payload + live checks
    ed = p["edition"]
    segs = (ed.get("segmentation") or {}).get("segments", [])
    refs = [s["reference"] for s in segs]
    pairs = []
    if is_comm:
        # the parser's pairs are (source = commentary block, target = root block); the library
        # is fed root -> commentary, so re-orient them
        pairs = [{"source_segment_reference": a["target_segment_reference"],
                  "target_segment_reference": a["source_segment_reference"]}
                 for a in p["alignment"]["alignments"]]
    durch = (p["durchens"] or {}).get("durchens", []) if p["durchens"] else []
    yig = (p["yigchungs"] or {}).get("yigchungs", []) if p["yigchungs"] else []
    problems = []
    if len(refs) != len(set(refs)):
        problems.append("duplicate segment references in the edition")
    if is_comm:
        if p["text"].get("commentary_of") != root_tid:
            problems.append(f"text.json commentary_of={p['text'].get('commentary_of')!r} ≠ root text_id {root_tid} — re-run the linter and parser")
        unknown_c = {q["target_segment_reference"] for q in pairs} - set(refs)
        if unknown_c:
            problems.append(f"{len(unknown_c)} alignment refs not in the commentary edition: {sorted(unknown_c)[:5]}")
    try:
        if is_comm:
            live_root = [s["reference"] for s in paged(f"/v2/editions/{root_eid}/segmentation/segments")]
            print(f"live root edition {root_eid}: {len(live_root)} segments")
            unknown_r = {q["source_segment_reference"] for q in pairs} - set(live_root)
            if unknown_r:
                problems.append(f"{len(unknown_r)} alignment refs not in the LIVE root edition: {sorted(unknown_r)[:8]}")
            print(f"live root text {root_tid}: {call('GET', f'/v2/texts/{root_tid}').get('title')}")
        if entry.get("text_id") and not entry.get("edition_id"):
            if call("GET", f"/v2/texts/{entry['text_id']}/editions"):
                problems.append(f"live text {entry['text_id']} already has edition(s) — decide before re-uploading")
    except ApiError as exc:
        problems.append(f"live check failed: {exc}")

    print(f"\n{path.name} ({ftype})\n  host {BASE}" + (f"\n  root text {root_tid} / edition {root_eid}" if is_comm else ""))
    print(f"  edition: {len(ed['content'])} chars, {len(segs)} segments; toc nodes "
          f"{json.dumps(p['toc']).count(chr(34) + 'title' + chr(34))}; durchens {len(durch)}; yigchungs {len(yig)}")
    if is_comm:
        print(f"  alignment: {len(pairs)} pairs root→commentary")
    plan = [("text", "POST /v2/texts", "text_id"),
            ("edition", "POST /v2/texts/{text_id}/editions", "edition_id"),
            ("toc", "POST /v2/editions/{edition_id}/table-of-contents", "toc_id")]
    if durch:
        plan.append(("durchens", f"POST /v2/editions/{{edition_id}}/durchens  ({len(durch)} notes, one list)", "durchen_count"))
    if yig:
        plan.append(("yigchungs", f"POST /v2/editions/{{edition_id}}/yigchungs  ({len(yig)} marks)", "yigchung_count"))
    if is_comm and pairs:
        plan.append(("alignment", f"PUT /v2/editions/{root_eid}/alignments/{{edition_id}}", "aligned_to_edition_id"))
    elif is_comm:
        print("  alignment: 0 pairs (no transclusions yet) — skipped; re-run this script after transclusion to send it")
    print("\n== plan ==")
    for step, what, key in plan:
        print(f"  {'skip (done)' if entry.get(key) else 'send'}  {step:10} {what}")
    if problems:
        print("\n== PROBLEMS (nothing will be sent) ==")
        for x in problems:
            print("  -", x)
        return 1
    if not args.execute:
        print("\nDry run — nothing sent. Re-run with --execute after confirmation.")
        return 0

    def done(step, key, value, **kw):
        entry[key] = value
        entry["receipts"].append({"step": step, key: value,
                                  "at": dt.datetime.now().isoformat(timespec="seconds"), **kw})
        save_ledger(ledger)
        patch_fm(path, key, value)
        print(f"  ok {step}: {key}={value}")

    if not entry.get("text_id"):
        done("text", "text_id", call("POST", "/v2/texts", p["text"])["id"])
    tid = entry["text_id"]
    if not entry.get("edition_id"):
        done("edition", "edition_id", call("POST", f"/v2/texts/{tid}/editions", ed)["id"], segments=len(segs))
    eid = entry["edition_id"]
    if not entry.get("toc_id"):
        done("toc", "toc_id", call("POST", f"/v2/editions/{eid}/table-of-contents", p["toc"])["id"])
    if durch and not entry.get("durchen_count"):
        res = call("POST", f"/v2/editions/{eid}/durchens", durch)  # atomic: all notes or none
        if len(res) != len(durch):
            raise RuntimeError(f"durchens: sent {len(durch)}, got {len(res)} ids back")
        entry["durchen_ids"] = [r["id"] for r in res]
        done("durchens", "durchen_count", len(durch))
    if yig and not entry.get("yigchung_count"):
        ids = entry.setdefault("yigchung_ids", [])
        for start in range(len(ids), len(yig), 500):
            ids += [r["id"] for r in call("POST", f"/v2/editions/{eid}/yigchungs", yig[start:start + 500])]
            save_ledger(ledger)
        done("yigchungs", "yigchung_count", len(yig))
    if is_comm and pairs and not entry.get("aligned_to_edition_id"):
        call("PUT", f"/v2/editions/{root_eid}/alignments/{eid}", {"alignments": pairs})
        done("alignment", "aligned_to_edition_id", root_eid, pairs=len(pairs))
    print("\nUploaded. Run --verify to read it back.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
