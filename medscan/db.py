"""SQLite store. Local file only; keeps raw OCR text for audit and re-parsing."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from .parse import Extraction

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY, sha256 TEXT UNIQUE, filename TEXT, scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
  patient TEXT, doc_date TEXT, doctor TEXT, header_json TEXT, raw_text TEXT);
CREATE TABLE IF NOT EXISTS medications(
  id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  drug TEXT, strength TEXT, form TEXT, frequency TEXT, frequency_plain TEXT, duration TEXT,
  source_line TEXT, conf REAL, needs_review INTEGER, verified INTEGER DEFAULT 0,
  canonical TEXT DEFAULT '', match_score REAL DEFAULT 0, alternatives TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS lab_results(
  id INTEGER PRIMARY KEY, doc_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  test TEXT, value REAL, unit TEXT, ref_low REAL, ref_high REAL, flag TEXT,
  source_line TEXT, conf REAL, needs_review INTEGER, verified INTEGER DEFAULT 0);
"""


def connect(path: str | Path = "medscan.db") -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=ON")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(medications)")}
    for col, ddl in (('canonical', "TEXT DEFAULT ''"), ('match_score', 'REAL DEFAULT 0'), ('alternatives', "TEXT DEFAULT ''")):
        if col not in have:  # migrate databases created by the first version
            con.execute(f'ALTER TABLE medications ADD COLUMN {col} {ddl}')
    return con


def save(con: sqlite3.Connection, file: Path, raw_text: str, ex: Extraction) -> tuple[int, bool]:
    """Returns (doc_id, is_new). Re-scanning identical bytes is a no-op."""
    sha = hashlib.sha256(file.read_bytes()).hexdigest()
    row = con.execute("SELECT id FROM documents WHERE sha256=?", (sha,)).fetchone()
    if row:
        return row["id"], False
    h = ex.header
    cur = con.execute(
        "INSERT INTO documents(sha256,filename,patient,doc_date,doctor,header_json,raw_text) VALUES(?,?,?,?,?,?,?)",
        (sha, file.name, h.get("patient"), h.get("date"), h.get("doctor"), json.dumps(h), raw_text),
    )
    doc_id = cur.lastrowid
    con.executemany(
        "INSERT INTO medications(doc_id,drug,strength,form,frequency,frequency_plain,duration,source_line,conf,needs_review,canonical,match_score,alternatives)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(doc_id, m.drug, m.strength, m.form, m.frequency, m.frequency_plain, m.duration, m.source_line, m.conf, m.needs_review, m.canonical, m.match_score, m.alternatives)
         for m in ex.medications],
    )
    con.executemany(
        "INSERT INTO lab_results(doc_id,test,value,unit,ref_low,ref_high,flag,source_line,conf,needs_review)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(doc_id, r.test, r.value, r.unit, r.ref_low, r.ref_high, r.flag, r.source_line, r.conf, r.needs_review)
         for r in ex.labs],
    )
    con.commit()
    return doc_id, True
