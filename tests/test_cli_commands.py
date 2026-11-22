"""list / review / export commands, driven through the real CLI entry point."""

import csv
import io
import sqlite3

import pytest

from medscan import db
from medscan.cli import main
from medscan.lexicon import Lexicon
from medscan.parse import parse_lines

LINES = [
    ("Patient: Asha Rao", 95),
    ("Tab Metformin 500 mg BD x 30 days", 95),  # exact lexicon hit -> no review
    ("Tab Metforrnin 500 mg BD", 95),  # OCR typo, fuzzy match -> review
    ("Tab Zzqxplon 5 mg OD", 95),  # unknown to lexicon -> review
    ("Hemoglobin 11.2 g/dL 13.0-17.0 L", 95),  # confident lab
    ("Creatinine 0.9 mg/dL 0.7-1.3", 40),  # low OCR confidence -> review
]


@pytest.fixture
def dbpath(tmp_path):
    path = str(tmp_path / "t.db")
    f = tmp_path / "doc.bin"
    f.write_bytes(b"fake scan bytes")
    con = db.connect(path)
    db.save(con, f, "raw", parse_lines(LINES, Lexicon.load()))
    con.close()
    return path


def rows(path, sql):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_list_shows_rows_canonical_and_review_marks(dbpath, capsys):
    assert main(["--db", dbpath, "list"]) == 0
    out = capsys.readouterr().out.splitlines()
    meds = [ln for ln in out if "] Rx " in ln]
    labs = [ln for ln in out if "] Lab " in ln]
    assert len(meds) == 3 and len(labs) == 2
    assert not any("review" in ln for ln in meds if "Metformin 500" in ln and "->" not in ln)
    typo = next(ln for ln in meds if "Metforrnin" in ln)
    assert "-> metformin" in typo and "review" in typo  # canonical shown, flagged
    assert "review" in next(ln for ln in meds if "Zzqxplon" in ln)
    assert "Hemoglobin: 11.2 g/dL (13.0-17.0) L" in next(ln for ln in labs if "Hemoglobin" in ln)
    assert "review" not in next(ln for ln in labs if "Hemoglobin" in ln)
    assert "review" in next(ln for ln in labs if "Creatinine" in ln)


def test_list_empty_database_prints_nothing(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "e.db"), "list"]) == 0
    assert capsys.readouterr().out == ""


def test_review_verify_delete_skip(dbpath, monkeypatch, capsys):
    answers = iter(["y", "n", ""])  # typo -> verify, unknown -> delete, creatinine -> skip
    prompts = []
    monkeypatch.setattr("builtins.input", lambda p="": prompts.append(p) or next(answers))
    assert main(["--db", dbpath, "review"]) == 0
    assert len(prompts) == 3  # exactly the three flagged rows were offered
    out = capsys.readouterr().out
    assert "Metforrnin" in out and "source: Tab Zzqxplon 5 mg OD" in out and "Creatinine" in out

    assert rows(dbpath, "SELECT verified FROM medications WHERE drug='Metforrnin'") == [(1,)]
    assert rows(dbpath, "SELECT count(*) FROM medications WHERE drug='Zzqxplon'") == [(0,)]
    assert rows(dbpath, "SELECT verified, needs_review FROM lab_results WHERE test='Creatinine'") == [(0, 1)]
    assert rows(dbpath, "SELECT count(*) FROM medications") == [(2,)]  # nothing else touched

    main(["--db", dbpath, "list"])  # a verified row no longer carries the review mark
    listed = capsys.readouterr().out.splitlines()
    assert "review" not in next(ln for ln in listed if "Metforrnin" in ln)
    assert "review" in next(ln for ln in listed if "Creatinine" in ln)


def test_review_does_not_reoffer_verified_rows(dbpath, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda p="": "y")
    main(["--db", dbpath, "review"])  # verify everything flagged
    monkeypatch.setattr("builtins.input", lambda p="": pytest.fail("nothing left to review"))
    assert main(["--db", dbpath, "review"]) == 0


def test_export_meds_csv(dbpath, capsys):
    assert main(["--db", dbpath, "export", "meds"]) == 0
    got = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert [r["drug"] for r in got] == ["Metformin", "Metforrnin", "Zzqxplon"]
    assert got[1]["canonical"] == "metformin" and got[1]["needs_review"] == "1"
    assert got[0]["frequency_plain"] == "twice daily" and got[0]["duration"] == "30 days"


def test_export_labs_csv(dbpath, capsys):
    assert main(["--db", dbpath, "export", "labs"]) == 0
    got = {r["test"]: r for r in csv.DictReader(io.StringIO(capsys.readouterr().out))}
    assert set(got) == {"Hemoglobin", "Creatinine"}
    assert got["Hemoglobin"]["flag"] == "L" and float(got["Hemoglobin"]["value"]) == 11.2


def test_export_empty_table_prints_nothing(tmp_path, capsys):
    assert main(["--db", str(tmp_path / "e.db"), "export", "labs"]) == 0
    assert capsys.readouterr().out == ""
