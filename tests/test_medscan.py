import sqlite3

from fonts import load_font
from PIL import Image, ImageDraw

from medscan.cli import main
from medscan.parse import parse_lines

RX = [
    "Patient: Asha Rao",
    "Date: 12/11/2026",
    "Dr. Mehta",
    "1. Tab Metformin 500 mg BD x 30 days",
    "2. Cap Amoxicillin 250 mg TDS x 5 days",
    "3. Tab Atorvastatin 10 mg HS",
]
LAB = [
    "Patient: Ravi Kumar",
    "Date: 10/11/2026",
    "Hemoglobin 11.2 g/dL 13.0-17.0 L",
    "Fasting Glucose 142 mg/dL 70-100 H",
    "Creatinine 0.9 mg/dL 0.7-1.3",
]


def _img(tmp_path, name, lines):
    img = Image.new("RGB", (1600, 160 + 90 * len(lines)), "white")
    d = ImageDraw.Draw(img)
    font = load_font(44)
    for i, t in enumerate(lines):
        d.text((60, 60 + 90 * i), t, fill="black", font=font)
    p = tmp_path / name
    img.save(p)
    return p


def test_parse_prescription_text():
    ex = parse_lines([(t, 95) for t in RX])
    assert ex.header["patient"] == "Asha Rao"
    drugs = {m.drug: m for m in ex.medications}
    assert set(drugs) == {"Metformin", "Amoxicillin", "Atorvastatin"}
    assert drugs["Metformin"].strength == "500 mg" and drugs["Metformin"].frequency_plain == "twice daily"
    assert drugs["Metformin"].duration == "30 days"
    assert not ex.labs


def test_parse_lab_text_flags():
    ex = parse_lines([(t, 95) for t in LAB])
    res = {r.test: r for r in ex.labs}
    assert res["Hemoglobin"].flag == "L"
    assert res["Fasting Glucose"].flag == "H"
    assert res["Creatinine"].flag == ""
    assert not ex.medications


def test_low_confidence_flagged():
    ex = parse_lines([("Tab Metformin 500 mg BD", 40)])
    assert ex.medications[0].needs_review


def test_end_to_end_image_and_dedupe(tmp_path):
    rx, lab = _img(tmp_path, "rx.png", RX), _img(tmp_path, "lab.png", LAB)
    dbp = str(tmp_path / "t.db")
    assert main(["--db", dbp, "scan", str(rx), str(lab)]) == 0
    assert main(["--db", dbp, "scan", str(rx)]) == 0  # duplicate -> no new rows
    con = sqlite3.connect(dbp)
    assert con.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM medications").fetchone()[0] == 3
    assert con.execute("SELECT count(*) FROM lab_results").fetchone()[0] == 3
