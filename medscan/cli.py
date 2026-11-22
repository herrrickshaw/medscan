"""medscan CLI: scan | list | review | export"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import db
from .lexicon import Lexicon
from .ocr import ocr_file
from .parse import parse_lines


def cmd_scan(a) -> int:
    con = db.connect(a.db)
    lex = None if a.no_lexicon else Lexicon.load(*a.lexicon)
    recogniser = None
    if a.engine == "trocr":  # load weights once for all files
        from . import htr
        recogniser = htr.load_trocr(a.model or htr.DEFAULT_MODEL)
    for f in a.files:
        p = Path(f)
        lines = ocr_file(p, a.lang, a.engine, a.model, recogniser)
        ex = parse_lines([(l.text, l.conf) for l in lines], lex)
        doc_id, new = db.save(con, p, "\n".join(l.text for l in lines), ex)
        flagged = sum(x.needs_review for x in ex.medications + ex.labs)
        print(f"{p.name}: doc #{doc_id} {'saved' if new else 'already scanned'} - "
              f"{len(ex.medications)} medications, {len(ex.labs)} lab results, {flagged} need review")
        if a.json:
            print(json.dumps(ex.to_dict(), indent=2))
    return 0


def cmd_list(a) -> int:
    con = db.connect(a.db)
    for r in con.execute("SELECT * FROM medications ORDER BY doc_id, id"):
        print(f"[doc {r['doc_id']}] Rx  {r['drug']}{' -> ' + r['canonical'] if r['canonical'] and r['canonical'].lower() != r['drug'].lower() else ''} {r['strength']} {r['form']} {r['frequency']} {r['duration']}"
              f"{'  ⚠ review' if r['needs_review'] and not r['verified'] else ''}")
    for r in con.execute("SELECT * FROM lab_results ORDER BY doc_id, id"):
        rng = f"({r['ref_low']}-{r['ref_high']})" if r["ref_low"] is not None else ""
        print(f"[doc {r['doc_id']}] Lab {r['test']}: {r['value']} {r['unit']} {rng} {r['flag']}"
              f"{'  ⚠ review' if r['needs_review'] and not r['verified'] else ''}")
    return 0


def cmd_review(a) -> int:
    """Interactive confirm/skip of low-confidence rows (human-in-the-loop)."""
    con = db.connect(a.db)
    for table, label in (("medications", "drug"), ("lab_results", "test")):
        for r in con.execute(f"SELECT * FROM {table} WHERE needs_review=1 AND verified=0").fetchall():
            print(f"\n{table[:-1]} (OCR conf {r['conf']}): {r[label]}\n  source: {r['source_line']}")
            ans = input("  correct? [y=verify / n=delete / enter=skip] ").strip().lower()
            if ans == "y":
                con.execute(f"UPDATE {table} SET verified=1 WHERE id=?", (r["id"],))
            elif ans == "n":
                con.execute(f"DELETE FROM {table} WHERE id=?", (r["id"],))
    con.commit()
    return 0


def cmd_export(a) -> int:
    con = db.connect(a.db)
    table = "medications" if a.table == "meds" else "lab_results"
    rows = con.execute(f"SELECT * FROM {table}").fetchall()
    w = csv.writer(sys.stdout)
    if rows:
        w.writerow(rows[0].keys())
        w.writerows([tuple(r) for r in rows])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="medscan", description="Scan prescriptions/reports into a local database")
    ap.add_argument("--db", default="medscan.db")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("files", nargs="+"); s.add_argument("--lang", default="eng")
    s.add_argument("--json", action="store_true")
    s.add_argument("--engine", choices=["tesseract", "trocr"], default="tesseract",
                   help="trocr = handwriting (needs torch+transformers; downloads model weights on first use)")
    s.add_argument("--model", help="Hugging Face TrOCR model id (default microsoft/trocr-base-handwritten)")
    s.add_argument("--lexicon", action="append", default=[], help="extra drug-name file (repeatable)")
    s.add_argument("--no-lexicon", action="store_true"); s.set_defaults(fn=cmd_scan)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("review").set_defaults(fn=cmd_review)
    e = sub.add_parser("export"); e.add_argument("table", choices=["meds", "labs"]); e.set_defaults(fn=cmd_export)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
