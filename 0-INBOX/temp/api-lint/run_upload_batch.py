#!/usr/bin/env python3
"""Upload the root texts whose linter + parser passed to the WeBuddhist library API.

For each text marked `done` in lint-status.json (and not held in holds.json), sends the
parser payloads in 4-SYSTEM/scripts/parser-root-text/output/<id>/ in this order:

    1. POST /v2/texts                          <- <id>.text.json       -> text_id
    2. POST /v2/texts/{text_id}/editions       <- <id>.edition.json    -> edition_id
    3. POST /v2/editions/{edition_id}/table-of-contents
                                               <- <id>.toc.json        -> toc_id
    4. POST /v2/editions/{edition_id}/durchens <- <id>.durchens.json   all notes in one atomic
                                                                       request; one id per note
    5. POST /v2/editions/{edition_id}/yigchungs <- <id>.yigchungs.json only when the file exists

After each successful step the id is written into the source frontmatter
(1-SOURCES/Text/<id>.md: text_id, edition_id, toc_id, durchen_count, yigchung_count) and
into the ledger upload-status.json next to this script, which also keeps every durchen and
yigchung id. A step whose id is already recorded is skipped, so an interrupted run resumes.
The report 0-INBOX/API-LINT-BATCH.md is rebuilt with the upload columns after every text.

Dry run is the default: it checks the payloads (and, read-only, the live API) and prints the
plan. Nothing is sent without --execute.

    py -3 0-INBOX/temp/api-lint/run_upload_batch.py                     # dry run, every ready text
    py -3 0-INBOX/temp/api-lint/run_upload_batch.py --ids Ar_3CBf_      # dry run, one text
    py -3 0-INBOX/temp/api-lint/run_upload_batch.py --ids Ar_3CBf_ --execute
    py -3 0-INBOX/temp/api-lint/run_upload_batch.py --limit 10 --execute
    py -3 0-INBOX/temp/api-lint/run_upload_batch.py --report-only
    py -3 0-INBOX/temp/api-lint/run_upload_batch.py --ids Ar_3CBf_ --delete --execute
        # deletes the live edition (with its annotations) and text; the old ids move to the
        # ledger's "deleted" history and the id keys leave the frontmatter, ready to re-upload

Credentials come from the environment, or from a WEBUDDHIST_* line in the git-ignored .env
at the vault root, and are never printed:
    WEBUDDHIST_API_KEY    X-API-Key       (sent when set; the API does not require it for now)
    WEBUDDHIST_APP        X-Application   (default "webuddhist"; used for the category check)
    WEBUDDHIST_API_BASE   default https://library.webuddhist.com

Stops at the first text that fails, so it can be investigated; --keep-going runs past it.
Run from the vault root.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_lint_batch as lint  # noqa: E402  (shares load_status / write_report)

VAULT = lint.VAULT
SOURCES = lint.SOURCES
PARSE_OUT = lint.PARSE_OUT
LEDGER = lint.UPLOAD_STATUS
STEPS = ("text", "edition", "toc", "durchens", "yigchungs")


def _load_env():
    for env in (VAULT / ".env", VAULT / "4-SYSTEM" / "scripts" / ".env"):
        if not env.exists():
            continue
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"^\s*(?:export\s+)?(WEBUDDHIST_[A-Z_]+)\s*=\s*(.*?)\s*$", line)
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2).strip("'\"")


_load_env()
BASE = os.environ.get("WEBUDDHIST_API_BASE", "https://library.webuddhist.com").rstrip("/")
APP = os.environ.get("WEBUDDHIST_APP", "webuddhist")


class ApiError(RuntimeError):
    pass


# ---------------------------------------------------------------- API

def call(method, path, body=None, app=False, timeout=120, retries=3):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("WEBUDDHIST_API_KEY", "")
    if key:
        h["X-API-Key"] = key
    if app:
        h["X-Application"] = APP
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    url = BASE + path
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:800]
            # a POST is never retried: it may have been applied, and a retry would duplicate it
            if exc.code >= 500 and method == "GET" and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"HTTP {exc.code} {method} {path}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            if method == "GET" and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise ApiError(f"network error {method} {path}: {getattr(exc, 'reason', exc)}") from None


# ---------------------------------------------------------------- files

def load_ledger():
    return json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}


def _replace(tmp, dest, tries=20):
    """os.replace, retried: on Windows a reader (Obsidian, an indexer) can hold dest open for a moment."""
    for attempt in range(tries):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.5)


def save_ledger(ledger):
    tmp = LEDGER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _replace(tmp, LEDGER)


FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
ID_KEYS = ("text_id", "edition_id", "toc_id", "durchen_count", "yigchung_count")
ANCHOR_KEYS = ("category_id", "category_name") + ID_KEYS


def read_fm_ids(path):
    m = FM_RE.match(path.read_text(encoding="utf-8"))
    out = {}
    if m:
        for key in ID_KEYS:
            k = re.search(rf"^{key}\s*:\s*\"?([^\"\r\n]*?)\"?\s*$", m.group(1), re.MULTILINE)
            if k and k.group(1):
                out[key] = k.group(1)
    return out


def patch_fm(path, key, value):
    """Set `key: value` in the frontmatter: replace it, or insert it after the category / id keys."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text[:2000] else "\n"
    lines = text.split(nl)
    if lines[0].strip() != "---":
        raise RuntimeError(f"{path.name}: no frontmatter")
    close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    new = f'{key}: "{value}"' if isinstance(value, str) else f"{key}: {value}"
    for i in range(1, close):
        if re.match(rf"^{re.escape(key)}\s*:", lines[i]):
            lines[i] = new
            break
    else:
        anchor = max((i for i in range(1, close)
                      if any(re.match(rf"^{a}\s*:", lines[i]) for a in ANCHOR_KEYS)), default=close - 1)
        lines.insert(anchor + 1, new)
    tmp = path.with_suffix(".md.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(lines))
    _replace(tmp, path)


def unpatch_fm(path, keys):
    """Remove `key:` lines from the frontmatter."""
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text[:2000] else "\n"
    lines = text.split(nl)
    close = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    keep = [l for i, l in enumerate(lines)
            if not (0 < i < close and any(re.match(rf"^{re.escape(k)}\s*:", l) for k in keys))]
    tmp = path.with_suffix(".md.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(keep))
    _replace(tmp, path)


def _delete(path):
    """DELETE path; True if it was deleted, False if it was already gone."""
    try:
        call("DELETE", path)
        return True
    except ApiError as exc:
        if " 404 " in str(exc):
            return False
        raise


def delete_one(tid, entry, workers):
    """Delete a text's live records in the reverse of the upload order:
    durchens (and yigchungs), toc, edition, text.

    The old ids move to entry["deleted"] so they stay on record; the frontmatter id keys are removed.
    """
    for kind, key in (("durchens", "durchen_ids"), ("yigchungs", "yigchung_ids")):
        ids = [i for i in entry.get(key, []) if i]
        if ids:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                n = sum(pool.map(lambda i: _delete(f"/v2/{kind}/{i}"), ids))
            print(f"    deleted {n}/{len(ids)} {kind}" + (f" ({len(ids) - n} already gone)" if n < len(ids) else ""))
    for label, path in (("toc", "/v2/table-of-contents/"), ("edition", "/v2/editions/"), ("text", "/v2/texts/")):
        i = entry.get(f"{label}_id")
        if i:
            print(f"    {'deleted' if _delete(path + i) else 'already gone:'} {label} {i}")
    old = {k: v for k, v in entry.items() if k not in ("deleted", "log")}
    old["deleted_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    history = entry.get("deleted", []) + [old]
    entry.clear()
    entry["deleted"] = history
    entry["status"] = "deleted"
    unpatch_fm(SOURCES / f"{tid}.md", ID_KEYS)


def payload_paths(tid):
    d = PARSE_OUT / tid
    return {k: d / f"{tid}.{k}.json" for k in STEPS}


def reparse_differs(tid, paths):
    """Re-run the parser on the source as it is now, into a temp folder, and compare with the payloads.

    Catches a source edited after the lint batch parsed it; the id keys this script writes into
    the frontmatter do not reach the payloads, so they never trip it.
    """
    lint_json = lint.LINT_OUT / f"{tid}.lint.json"
    if not lint_json.exists():
        return [f"missing {lint_json.name}"]
    with tempfile.TemporaryDirectory() as tmp:
        code = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); import parser as p; "
                "p.OUTPUT_DIR = Path(sys.argv[2]); p.main(sys.argv[3:])")
        r = subprocess.run([sys.executable, "-c", code, str(lint.PARSER.parent), tmp,
                            str(SOURCES / f"{tid}.md"), str(lint_json)],
                           cwd=VAULT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            return [f"re-parse failed: {(r.stderr or r.stdout).strip()[-300:]}"]
        differ = []
        for k in STEPS:
            fresh = Path(tmp) / tid / f"{tid}.{k}.json"
            if fresh.exists() != paths[k].exists() or (
                    fresh.exists() and json.loads(fresh.read_text(encoding="utf-8"))
                    != json.loads(paths[k].read_text(encoding="utf-8"))):
                differ.append(k)
    return [f"source re-parses differently from the payloads ({', '.join(differ)}) — "
            f"re-run the lint batch for it"] if differ else []


def payload_hash(paths):
    h = hashlib.sha256()
    for k in STEPS:
        if paths[k].exists():
            h.update(k.encode() + b"\0" + paths[k].read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- checks

_categories = {}


def clash_reason(tid, ledger):
    """Name the uploaded vault text(s) whose title or BDRC id this text repeats, or None."""
    def meta(t):
        p = payload_paths(t)["text"]
        if not p.exists():
            return set(), None
        d = json.loads(p.read_text(encoding="utf-8"))
        return set((d.get("title") or {}).items()), d.get("bdrc")

    titles, bdrc = meta(tid)
    found = []
    for other, e in sorted(ledger.items()):
        if other == tid or e.get("status") != "uploaded":
            continue
        t2, b2 = meta(other)
        same = [w for w, hit in (("title", titles & t2), (f"BDRC {bdrc}", bdrc and bdrc == b2)) if hit]
        if same:
            found.append(f"{other} ({' + '.join(same)})")
    return ("same " + "; ".join(found) + " as an uploaded text") if found else None


def check(tid, paths, entry, live, ledger=None):
    """Return (payloads, problems). Read-only."""
    problems = []
    for k in ("text", "edition", "toc", "durchens"):
        if not paths[k].exists():
            problems.append(f"missing payload {paths[k].name}")
    if problems:
        return None, problems
    p = {k: json.loads(paths[k].read_text(encoding="utf-8")) for k in STEPS if paths[k].exists()}
    content = p["edition"].get("content", "")
    n = len(content)
    if not content.strip():
        problems.append("edition content is empty")
    segs = (p["edition"].get("segmentation") or {}).get("segments", [])
    refs = [s["reference"] for s in segs]
    if len(refs) != len(set(refs)):
        problems.append("duplicate segment references")
    for s in segs:
        for sp in s.get("lines", []):
            if not 0 <= sp["start"] <= sp["end"] <= n:
                problems.append(f"segment {s['reference']} span out of range")
                break
    if not p["toc"].get("sections"):
        problems.append("toc has no sections")
    for d in p["durchens"].get("durchens", []):
        sp = d["span"]
        if not (0 <= sp["start"] < sp["end"] <= n) or not d.get("text", "").strip():
            problems.append(f"durchen span {sp} out of range or empty text")
            break
    for y in (p.get("yigchungs") or {}).get("yigchungs", []):
        sp = y["span"]
        if not 0 <= sp["start"] < sp["end"] <= n:
            problems.append(f"yigchung span {sp} out of range")
            break

    if not entry.get("text_id"):
        problems += reparse_differs(tid, paths)
    elif entry.get("payload_hash") and entry["payload_hash"] != payload_hash(paths):
        problems.append("payloads changed since the upload started — the live edition no longer matches them")

    if live:
        try:
            cat = p["text"].get("category_id")
            if cat not in _categories:
                try:
                    call("GET", f"/v2/categories/{cat}", app=True)
                    _categories[cat] = True
                except ApiError as exc:
                    _categories[cat] = False if " 404 " in str(exc) else None
                    if _categories[cat] is None:
                        raise
            if _categories[cat] is False:
                problems.append(f"category_id {cat} does not exist on the live API")
            if not entry.get("text_id") and p["text"].get("bdrc"):
                hits = call("GET", f"/v2/texts?bdrc={p['text']['bdrc']}&limit=5").get("items", [])
                if hits:
                    problems.append(clash_reason(tid, ledger or {}) or
                                    f"a live text already has bdrc {p['text']['bdrc']}: "
                                    f"{[h.get('id') for h in hits]} — record its text_id instead of creating a duplicate")
            if entry.get("text_id") and not entry.get("edition_id"):
                eds = call("GET", f"/v2/texts/{entry['text_id']}/editions")
                if eds:
                    problems.append(f"live text {entry['text_id']} already has edition(s) "
                                    f"{[e.get('id') for e in eds]} not in the ledger — decide which to keep")
        except ApiError as exc:
            problems.append(f"live check failed: {exc}")
    return p, problems


# ---------------------------------------------------------------- upload

def upload_one(tid, payloads, paths, entry, ledger):
    src = SOURCES / f"{tid}.md"

    def save():
        entry["updated"] = _dt.datetime.now().isoformat(timespec="seconds")
        save_ledger(ledger)

    def done(step, key, value, **kw):
        entry[key] = value
        entry.setdefault("log", []).append({"step": step, "ts": _dt.datetime.now().isoformat(timespec="seconds"), **kw})
        save()
        patch_fm(src, key, value)
        print(f"    {step:<9} {key} = {value}")

    entry.setdefault("payload_hash", payload_hash(paths))
    entry.pop("error", None)

    if not entry.get("text_id"):
        res = call("POST", "/v2/texts", payloads["text"])
        done("text", "text_id", res["id"])
    tid_live = entry["text_id"]

    if not entry.get("edition_id"):
        ed = payloads["edition"]
        res = call("POST", f"/v2/texts/{tid_live}/editions", ed)
        done("edition", "edition_id", res["id"], chars=len(ed["content"]),
             segments=len((ed.get("segmentation") or {}).get("segments", [])))
    eid = entry["edition_id"]

    if not entry.get("toc_id"):
        res = call("POST", f"/v2/editions/{eid}/table-of-contents", payloads["toc"])
        done("toc", "toc_id", res["id"])

    notes = payloads["durchens"].get("durchens", [])
    if entry.get("durchen_count") is None:
        ids = entry.setdefault("durchen_ids", [None] * len(notes))
        if len(ids) != len(notes):
            raise RuntimeError(f"ledger has {len(ids)} durchen slots, payload has {len(notes)}")
        posted = sum(1 for i in ids if i)
        if posted:  # resuming: the live count must match what the ledger knows, or a POST was lost
            live = call("GET", f"/v2/editions/{eid}/durchens") or []
            if len(live) != posted:
                raise RuntimeError(f"resume: live edition has {len(live)} durchens, ledger records {posted} — "
                                   f"check before posting more (a response may have been lost)")
        # the endpoint takes a list and is atomic, returning one id per note in order: send every
        # note in one request, so a text gets all its durchens or none. Only if the server refuses
        # the request as too large (413, nothing created) is it split in halves and retried.
        def post(batch):
            try:
                res = call("POST", f"/v2/editions/{eid}/durchens", [notes[i] for i in batch])
            except ApiError as exc:
                if "HTTP 413 " in str(exc) and len(batch) > 1:
                    half = len(batch) // 2
                    print(f"    durchens  {len(batch)} too large for one request — splitting")
                    post(batch[:half])
                    post(batch[half:])
                    return
                raise
            if len(res) != len(batch):
                raise RuntimeError(f"durchens: sent {len(batch)}, got {len(res)} ids back")
            for i, r in zip(batch, res):
                ids[i] = r["id"]
            save()

        todo = [i for i, x in enumerate(ids) if not x]
        if todo:
            post(todo)
        done("durchens", "durchen_count", len(notes))

    marks = (payloads.get("yigchungs") or {}).get("yigchungs", [])
    if marks and entry.get("yigchung_count") is None:
        ids = entry.setdefault("yigchung_ids", [])
        for start in range(len(ids), len(marks), 500):
            res = call("POST", f"/v2/editions/{eid}/yigchungs", marks[start:start + 500])
            ids += [r["id"] for r in res]
            save()
        done("yigchungs", "yigchung_count", len(marks))

    entry["status"] = "uploaded"
    entry["date"] = _dt.date.today().isoformat()
    save()
    # lint, parse and upload all succeeded: the per-text lint log has served its purpose (never committed)
    (lint.LOGS / f"{tid}.log").unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ids", nargs="*", default=None, help="upload exactly these ids")
    ap.add_argument("--limit", type=int, default=0, help="at most N texts (0 = all ready)")
    ap.add_argument("--sizes", default="small,medium,large", help="size classes to include")
    ap.add_argument("--execute", action="store_true", help="send the requests (default: dry run)")
    ap.add_argument("--no-live", action="store_true", help="skip the read-only checks against the live API")
    ap.add_argument("--workers", type=int, default=4, help="parallel durchen DELETEs per text with --delete (default 4)")
    ap.add_argument("--keep-going", action="store_true", help="do not stop at the first failed text")
    ap.add_argument("--report-only", action="store_true", help="just rebuild API-LINT-BATCH.md")
    ap.add_argument("--delete", action="store_true",
                    help="delete the live records of --ids (old ids kept in the ledger) instead of uploading")
    args = ap.parse_args()

    status = lint.load_status()
    ledger = load_ledger()
    if args.report_only:
        lint.write_report(status)
        print(f"report: {lint.REPORT.relative_to(VAULT)}")
        return 0
    if args.delete:
        if not args.ids:
            sys.exit("--delete needs --ids (never deletes the whole batch by default)")
        for tid in args.ids:
            entry = ledger.get(tid)
            if not entry or not entry.get("text_id"):
                print(f"SKIP  {tid}: nothing uploaded in the ledger")
                continue
            print(f"{tid}: text {entry['text_id']} · edition {entry.get('edition_id')}")
            if not args.execute:
                print("    (dry run — re-run with --execute to delete)")
                continue
            try:
                delete_one(tid, entry, args.workers)
            finally:
                save_ledger(ledger)
        lint.write_report(lint.load_status())
        return 0

    sizes = set(args.sizes.split(","))
    if args.ids:
        selected = []
        for tid in args.ids:
            e = status.get(tid)
            if not e:
                print(f"SKIP  {tid}: not in 1-SOURCES/Text")
            elif e.get("hold"):
                print(f"SKIP  {tid}: held — {e['hold']}")
            elif e.get("status") != "done":
                print(f"SKIP  {tid}: lint/parse status is {e.get('status')!r}, not done")
            else:
                selected.append(tid)
    else:
        selected = [t for t, e in sorted(status.items())
                    if e.get("status") == "done" and not e.get("hold") and e["size"] in sizes
                    and ledger.get(t, {}).get("status") != "uploaded"]
    if args.limit:
        selected = selected[:args.limit]

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"== {mode} == {BASE} · {len(selected)} text(s)")
    failed = 0
    for k, tid in enumerate(selected, start=1):
        entry = ledger.setdefault(tid, {})
        # the frontmatter is the durable record: adopt ids found there, refuse if the two disagree
        fm = read_fm_ids(SOURCES / f"{tid}.md")
        clash = [key for key in ("text_id", "edition_id", "toc_id")
                 if fm.get(key) and entry.get(key) and fm[key] != entry[key]]
        if clash:
            print(f"[{k}/{len(selected)}] {tid}: FAIL frontmatter and ledger disagree on {clash}")
            failed += 1
            if not args.keep_going:
                break
            continue
        for key in ("text_id", "edition_id", "toc_id"):
            if fm.get(key) and not entry.get(key):
                entry[key] = fm[key]

        paths = payload_paths(tid)
        payloads, problems = check(tid, paths, entry, live=not args.no_live, ledger=ledger)
        e = status[tid]
        todo = [s for s, key in (("text", "text_id"), ("edition", "edition_id"), ("toc", "toc_id"),
                                 ("durchens", "durchen_count"), ("yigchungs", "yigchung_count"))
                if entry.get(key) is None and (s != "yigchungs" or paths["yigchungs"].exists())]
        head = (f"[{k}/{len(selected)}] {tid:10} {e['size']:6} segs {e.get('segments')} · "
                f"durchens {e.get('durchens')} · toc {e.get('toc_nodes')} · to send: {', '.join(todo) or 'nothing'}")
        if problems:
            print(head + "\n" + "\n".join(f"      !! {p}" for p in problems))
            if args.execute:
                entry["status"] = "failed"
                entry["error"] = problems[0][:300]
                save_ledger(ledger)
            failed += 1
            if not args.keep_going:
                break
            continue
        print(head)
        if not args.execute:
            if not entry:
                del ledger[tid]
            continue
        try:
            upload_one(tid, payloads, paths, entry, ledger)
            print(f"      uploaded  text {entry['text_id']} · edition {entry['edition_id']} · toc {entry['toc_id']}")
        except (ApiError, RuntimeError) as exc:
            entry["status"] = "failed" if not entry.get("text_id") else "partial"
            entry["error"] = ((" already exists" in str(exc) and clash_reason(tid, ledger)) or str(exc))[:300]
            save_ledger(ledger)
            print(f"      FAIL {exc}")
            failed += 1
            if not args.keep_going:
                lint.write_report(lint.load_status())
                break
        lint.write_report(lint.load_status())

    if args.execute:
        lint.write_report(lint.load_status())
        print(f"ledger: {LEDGER.relative_to(VAULT)} · report: {lint.REPORT.relative_to(VAULT)}")
    else:
        print("dry run: nothing sent, no file changed. Re-run with --execute to upload.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
