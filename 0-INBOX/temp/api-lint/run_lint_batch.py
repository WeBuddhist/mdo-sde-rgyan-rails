#!/usr/bin/env python3
"""Run linter-root-text + parser-root-text over the root texts in 1-SOURCES/Text/.

Keeps a status file (lint-status.json, next to this script) and rewrites the
report 0-INBOX/API-LINT-BATCH.md after every text. Texts listed in holds.json
are never run, whatever the arguments say.

    py -3 0-INBOX/temp/api-lint/run_lint_batch.py --limit 5            # next 5 small/medium texts
    py -3 0-INBOX/temp/api-lint/run_lint_batch.py --sizes small --limit 20
    py -3 0-INBOX/temp/api-lint/run_lint_batch.py --ids Ar_3CBr_ Ar_3CBt_
    py -3 0-INBOX/temp/api-lint/run_lint_batch.py --report-only       # just rebuild the report

Stops at the first text that fails (lint errors, or the parser fails), so it can be
investigated and fixed; --keep-going runs past failures.

Run from the vault root. Size classes come from 0-INBOX/ROOT-WORKFLOW-BATCH.md
(small < 30,000 · medium 30,000–199,999 · large ≥ 200,000 characters).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE.parents[2]
SOURCES = VAULT / "1-SOURCES" / "Text"
SCRIPTS = VAULT / "4-SYSTEM" / "scripts"
LINTER = SCRIPTS / "linter-root-text" / "lint_text_input.py"
PARSER = SCRIPTS / "parser-root-text" / "parser.py"
LINT_OUT = SCRIPTS / "linter-root-text" / "output"
PARSE_OUT = SCRIPTS / "parser-root-text" / "output"
WORKFLOW_MD = VAULT / "0-INBOX" / "ROOT-WORKFLOW-BATCH.md"
STATUS = HERE / "lint-status.json"
HOLDS = HERE / "holds.json"
LOGS = HERE / "logs"
REPORT = VAULT / "0-INBOX" / "API-LINT-BATCH.md"
UPLOAD_STATUS = HERE / "upload-status.json"  # written by run_upload_batch.py
REASONS = HERE / "failure-reasons.json"  # id -> reason, written by hand after investigating a failure
RETITLED = HERE / "retitled.json"  # id -> {old, new, clash, basis}, written by hand when a title is changed


def _sizes():
    """id -> size class, from the workflow batch table."""
    sizes = {}
    row = re.compile(r"^\|\s*\d+\s*\|\s*(\S+)\s*\|\s*(small|medium|large)\s*\|")
    if not WORKFLOW_MD.exists():  # FORK(mdo-sde-rgyan-rails): no workflow table here -> size by chars
        return sizes
    for line in WORKFLOW_MD.read_text(encoding="utf-8").splitlines():
        m = row.match(line)
        if m:
            sizes[m.group(1)] = m.group(2)
    return sizes


def _size_from_chars(n):
    return "small" if n < 30_000 else "medium" if n < 200_000 else "large"


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path):
    """Read a JSON file another process may be rewriting at this moment."""
    if not path.exists():
        return {}
    for attempt in range(10):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            if attempt == 9:
                raise
            __import__("time").sleep(0.5)


def load_status():
    status = _read_json(STATUS)
    holds = json.loads(HOLDS.read_text(encoding="utf-8")) if HOLDS.exists() else {}
    sizes = _sizes()
    for path in sorted(SOURCES.glob("*.md")):
        tid = path.stem
        entry = status.setdefault(tid, {"status": "to do"})
        entry["chars"] = len(path.read_text(encoding="utf-8", errors="replace"))
        entry["size"] = sizes.get(tid) or _size_from_chars(entry["chars"])
        entry["size_from"] = "workflow" if tid in sizes else "source chars"
        if tid in holds:
            entry["hold"] = holds[tid]
        else:
            entry.pop("hold", None)
    for tid in [t for t in status if not (SOURCES / f"{t}.md").exists()]:
        del status[tid]  # gone from 1-SOURCES/Text
    return status


def _run(cmd):
    p = subprocess.run(cmd, cwd=VAULT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    return p.returncode, p.stdout, p.stderr


def _count(pattern, text):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else None


def run_one(tid, entry):
    src = SOURCES / f"{tid}.md"
    rel = src.relative_to(VAULT).as_posix()
    before = _hash(src)
    log = [f"# {tid}  ({date.today().isoformat()})", "", "## linter", ""]

    code, out, err = _run([sys.executable, str(LINTER), rel])
    log += [out, err]
    lint_lines = (out + err).splitlines()
    errors = [l.strip()[6:] for l in lint_lines if l.strip().startswith("ERROR")]
    warns = [l.strip()[5:] for l in lint_lines if l.strip().startswith("WARN")
             and "languages:" not in l]
    entry["lint"] = "OK" if code == 0 else "FAIL"
    entry["lint_errors"] = len(errors)
    entry["lint_warnings"] = len(warns)
    entry["first_error"] = errors[0][:160] if errors else ""
    entry["durchen_warnings"] = sum(1 for w in warns if "footnote" in w)

    lint_json = LINT_OUT / f"{tid}.lint.json"
    if entry["lint"] == "OK" and lint_json.exists():
        code, out, err = _run([sys.executable, str(PARSER), rel, str(lint_json.relative_to(VAULT))])
        log += ["## parser", "", out, err]
        entry["parse"] = "OK" if code == 0 else "FAIL"
        entry["segments"] = _count(r"segments\s*:\s*(\d+)", out)
        entry["durchens"] = _count(r"durchens\s*:\s*(\d+)", out)
        entry["yigchungs"] = _count(r"yigchungs\s*:\s*(\d+)", out)
        entry["toc_nodes"] = _count(r"toc nodes\s*:\s*(\d+)", out)
        entry["parse_warnings"] = sum(1 for l in err.splitlines() if l.strip().startswith("WARN"))
        entry["output"] = f"4-SYSTEM/scripts/parser-root-text/output/{tid}/"
    else:
        entry["parse"] = "not run"
        for k in ("segments", "durchens", "yigchungs", "toc_nodes", "parse_warnings", "output"):
            entry.pop(k, None)

    entry["source_changed"] = _hash(src) != before
    entry["status"] = "done" if entry["lint"] == "OK" and entry["parse"] == "OK" else "failed"
    if entry["status"] == "done":
        # a failure report from an earlier run is stale once the text passes
        (LINT_OUT / f"{tid}.lint.errors.json").unlink(missing_ok=True)
    entry["date"] = date.today().isoformat()
    LOGS.mkdir(exist_ok=True)
    (LOGS / f"{tid}.log").write_text("\n".join(log), encoding="utf-8")
    entry["log"] = f"0-INBOX/temp/api-lint/logs/{tid}.log"


def _cell(v):
    return "" if v is None else str(v).replace("|", "\\|")


def write_report(status):
    n = len(status)
    held = [t for t, e in status.items() if e.get("hold")]
    done = [t for t, e in status.items() if e.get("status") == "done"]
    failed = [t for t, e in status.items() if e.get("status") == "failed"]
    todo = [t for t, e in status.items() if e.get("status") == "to do" and not e.get("hold")]
    by_size = {s: sum(1 for e in status.values() if e["size"] == s) for s in ("small", "medium", "large")}
    uploads = _read_json(UPLOAD_STATUS)
    uploaded = [t for t in status if uploads.get(t, {}).get("status") == "uploaded"]
    up_failed = [t for t in status if uploads.get(t, {}).get("status") in ("failed", "partial")]
    lines = [
        "# Root-text API batch — linter + parser",
        "",
        "Runs `linter-root-text` then `parser-root-text` on every root text in `1-SOURCES/Text/`. "
        "How to run: the docstring of `0-INBOX/temp/api-lint/run_lint_batch.py`.",
        "",
        f"Updated {date.today().isoformat()} · {n} texts (small {by_size['small']} · medium "
        f"{by_size['medium']} · large {by_size['large']}) · done {len(done)} · failed {len(failed)} · "
        f"**held {len(held)}** · to do {len(todo)} · **uploaded {len(uploaded)}**"
        + (f" · upload failed {len(up_failed)}" if up_failed else ""),
        "",
        "| What | Path |",
        "|---|---|",
        "| Status (one entry per text) | `0-INBOX/temp/api-lint/lint-status.json` |",
        "| **Held texts — never run** (edit to release) | `0-INBOX/temp/api-lint/holds.json` |",
        "| Log per text | `0-INBOX/temp/api-lint/logs/<id>.log` |",
        "| Lint result | `4-SYSTEM/scripts/linter-root-text/output/<id>.lint.json` (or `.lint.errors.json`) |",
        "| API payloads | `4-SYSTEM/scripts/parser-root-text/output/<id>/` (text, edition, toc, yigchungs, durchens) |",
        "| Why the durchen texts are held | `0-INBOX/durchen-outliers-report.md` |",
        "| Upload (script; ledger with every id) | `0-INBOX/temp/api-lint/run_upload_batch.py` · `0-INBOX/temp/api-lint/upload-status.json` |",
        "| Titles changed to clear a title clash | `0-INBOX/temp/api-lint/retitled.json` |",
        "",
        "`lint` OK = no errors · `err` / `warn` = linter errors / warnings (the language-list notice "
        "not counted) · `dur. warn` = footnote warnings (lemma not matched) · `src changed` = the "
        "linter rewrote the source frontmatter. Size from `0-INBOX/ROOT-WORKFLOW-BATCH.md`.",
        "",
        "Upload columns: `upload` = uploaded / partial / failed · `text_id` = the id written into the "
        "source frontmatter · `ed.` / `toc` ✓ = created (`edition_id` / `toc_id` in the frontmatter) · "
        "`dur. up` / `yig. up` = notes sent / notes in the payload.",
        "",
        "| # | id | size | chars | status | lint | err | warn | dur. warn | parse | segments | durchens | toc nodes | src changed | upload | text_id | ed. | toc | dur. up | yig. up | note |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def _sent(u, ids_key, count_key):
        if u.get(count_key) is not None:
            return f"{u[count_key]}/{u[count_key]}"
        if u.get(ids_key):
            return f"{sum(1 for x in u[ids_key] if x)}/{len(u[ids_key])}"
        return ""

    for i, (tid, e) in enumerate(sorted(status.items()), start=1):
        st = "**held**" if e.get("hold") else e.get("status", "to do")
        u = uploads.get(tid, {})
        up = u.get("status", "")
        up = f"**{up}**" if up in ("failed", "partial") else up
        note = e.get("hold") or e.get("first_error") or (f"upload: {u['error']}" if u.get("error") else "")
        lines.append("| " + " | ".join(_cell(v) for v in [
            i, tid, e["size"], f"{e['chars']:,}", st, e.get("lint"), e.get("lint_errors"),
            e.get("lint_warnings"), e.get("durchen_warnings"), e.get("parse"), e.get("segments"),
            e.get("durchens"), e.get("toc_nodes"),
            ("**yes**" if e.get("source_changed") else "no") if "source_changed" in e else "",
            up, u.get("text_id"), "✓" if u.get("edition_id") else "", "✓" if u.get("toc_id") else "",
            _sent(u, "durchen_ids", "durchen_count"), _sent(u, "yigchung_ids", "yigchung_count"),
            note,
        ]) + " |")
    lines += _failures_section(status, uploads)
    lines += _retitled_section()
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _failures_section(status, uploads):
    """Every text that failed lint, parse or upload, with the recorded error and the verified reason.

    Built from the current state, so a text drops out as soon as it succeeds; its verified reason is
    then pruned from failure-reasons.json too, so a stale reason never comes back.
    """
    reasons = _read_json(REASONS)
    failed = []
    for tid, e in sorted(status.items()):
        u = uploads.get(tid, {})
        if e.get("hold"):
            continue
        if e.get("status") == "failed":
            stage = "lint" if e.get("lint") != "OK" else "parse"
            failed.append((tid, stage, e.get("first_error") or "parser failed — see the log"))
        elif u.get("status") in ("failed", "partial"):
            failed.append((tid, "upload" if u["status"] == "failed" else "upload (partial)", u.get("error", "")))
    still = {tid for tid, _, _ in failed}
    stale = [t for t in reasons if t not in still and t in status]
    if stale:
        for t in stale:
            del reasons[t]
        tmp = REASONS.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(reasons, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        __import__("os").replace(tmp, REASONS)

    out = ["", "## Failures", "",
           "Every text that failed lint, parse or upload. `error` is what the script recorded; "
           "`verified reason` is what investigating it found (kept in `0-INBOX/temp/api-lint/failure-reasons.json`). "
           "A text leaves this list, and its reason is removed, as soon as it succeeds.", ""]
    if failed:
        out += ["| id | stage | error | verified reason |", "|---|---|---|---|"]
        out += ["| " + " | ".join(_cell(v) for v in (tid, stage, err, reasons.get(tid) or "_not yet verified_")) + " |"
                for tid, stage, err in failed]
    else:
        out.append("None.")
    held = [(t, e["hold"]) for t, e in sorted(status.items()) if e.get("hold")]
    if held:
        out += ["", "### Held — never run", "", "Listed in `0-INBOX/temp/api-lint/holds.json`; remove a text there to release it.", "",
                "| id | reason |", "|---|---|"] + [f"| {_cell(t)} | {_cell(r)} |" for t, r in held]
    return out


def _retitled_section():
    """Texts whose `title:` was changed so the upload's title-clash check passes (from retitled.json)."""
    retitled = _read_json(RETITLED)
    if not retitled:
        return []
    out = ["", "## Retitled", "",
           "Texts whose `title:` was changed because the upload stopped on a title already in the library. "
           "The old title moved into `alt_titles`. Kept by hand in `0-INBOX/temp/api-lint/retitled.json`.", "",
           "| id | old title | new title | clashed with | basis |", "|---|---|---|---|---|"]
    out += ["| " + " | ".join(_cell(v) for v in (tid, r.get("old"), r.get("new"), r.get("clash"), r.get("basis"))) + " |"
            for tid, r in sorted(retitled.items())]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sizes", default="small,medium",
                    help="size classes to run (default small,medium; large needs asking for)")
    ap.add_argument("--limit", type=int, default=0, help="run at most N texts (0 = all selected)")
    ap.add_argument("--ids", nargs="*", default=None, help="run exactly these ids")
    ap.add_argument("--redo", action="store_true", help="also re-run texts already done/failed")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not stop at the first failed text (default: stop, so it can be investigated)")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    status = load_status()
    if not args.report_only:
        sizes = set(args.sizes.split(","))
        if args.ids:
            todo = []
            for tid in args.ids:
                if tid not in status:
                    print(f"SKIP  {tid}: not in 1-SOURCES/Text")
                elif status[tid].get("hold"):
                    print(f"SKIP  {tid}: held — {status[tid]['hold']}")
                else:
                    todo.append(tid)
        else:
            todo = [t for t, e in sorted(status.items())
                    if not e.get("hold") and e["size"] in sizes
                    and (args.redo or e.get("status") == "to do")]
        if args.limit:
            todo = todo[:args.limit]
        for k, tid in enumerate(todo, start=1):
            run_one(tid, status[tid])
            e = status[tid]
            print(f"[{k}/{len(todo)}] {tid:10} {e['size']:6} lint {e['lint']:4} "
                  f"(err {e['lint_errors']}, warn {e['lint_warnings']}) · parse {e['parse']}"
                  + (f" · durchens {e.get('durchens')}" if e.get("durchens") is not None else "")
                  + (" · SOURCE CHANGED" if e["source_changed"] else ""))
            STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
            write_report(status)
            if e["status"] == "failed" and not args.keep_going:
                print(f"STOP  {tid} failed — {e['first_error'] or 'parser failed'}; see {e['log']}")
                print("      fix it, then re-run with --ids " + tid + " (or --keep-going to run past failures)")
                break
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(status)
    print(f"report: {REPORT.relative_to(VAULT)}")


if __name__ == "__main__":
    main()
