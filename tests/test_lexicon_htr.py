import sqlite3

from fonts import load_font
from PIL import Image, ImageDraw

from medscan import htr
from medscan.lexicon import Lexicon
from medscan.ocr import ocr_file
from medscan.parse import parse_lines

LEX = Lexicon.load()


def test_exact_and_brand():
    m = LEX.match("Metformin")
    assert m.canonical == "metformin" and m.score == 1.0 and m.confident
    assert LEX.match("Dolo").canonical == "paracetamol"


def test_ocr_typo_matched_but_not_confident():
    m = LEX.match("Metforrnin")  # classic rn/m OCR confusion
    assert m.canonical == "metformin" and 0.8 <= m.score < 1.0 and not m.confident


def test_truncated_name_is_not_confident():
    m = LEX.match("Hydroxyzin")  # 0.95 similar but not exact -> must go to review
    assert m.canonical == "hydroxyzine" and not m.confident


def test_ambiguity_mechanism():
    # Mechanism test with a synthetic near-tie. NB: real look-alikes such as hydroxyzine/hydralazine
    # are NOT close under difflib; they are caught only because every fuzzy match is sent to review.
    lex = Lexicon({"drugaxine": "drugaxine", "drugazine": "drugazine"})
    m = lex.match("drugaxzine")
    assert m.ambiguous and set([m.canonical, *m.alternatives]) == {"drugaxine", "drugazine"}
    assert not m.confident


def test_unknown_word_returns_none():
    assert LEX.match("Zzqxplon") is None


def test_parser_never_overwrites_ocr_text_and_flags_review():
    ex = parse_lines(
        [("Tab Metforrnin 500 mg BD", 95), ("Tab Zzqxplon 5 mg OD", 95), ("Tab Metformin 500 mg BD", 95)], LEX
    )
    typo, unknown, exact = ex.medications
    assert typo.drug == "Metforrnin" and typo.canonical == "metformin" and typo.needs_review
    assert unknown.canonical == "" and unknown.needs_review
    assert exact.canonical == "metformin" and not exact.needs_review


def test_extra_lexicon_file(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("# custom\nzzqxplon\n")
    assert Lexicon.load(f).match("Zzqxplon").canonical == "zzqxplon"


def _page(lines, h=90):
    img = Image.new("RGB", (1200, 60 + h * len(lines)), "white")
    d = ImageDraw.Draw(img)
    font = load_font(40)
    for i, t in enumerate(lines):
        d.text((50, 40 + h * i), t, fill="black", font=font)
    return img


def test_segment_lines_finds_each_line():
    strips = htr.segment_lines(_page(["Tab Metformin 500 mg BD", "Cap Amoxicillin 250 mg TDS", "Tab Atorvastatin"]))
    assert len(strips) == 3 and all(s.height < 90 for s in strips)


def test_trocr_engine_wiring_with_fake_recogniser(tmp_path):
    """Real TrOCR weights are not exercised here - only segmentation -> parser -> DB plumbing."""
    p = tmp_path / "hw.png"
    _page(["Tab Metformin", "Cap Amoxicillin"]).save(p)
    script = iter([("Tab Metformin 500 mg BD", 88.0), ("Cap Amoxicillin 250 mg TDS", 91.0)])
    lines = ocr_file(p, engine="trocr", recogniser=lambda strip: next(script))
    assert [ln.text for ln in lines] == ["Tab Metformin 500 mg BD", "Cap Amoxicillin 250 mg TDS"]
    assert lines[0].conf == 88.0


def test_db_migration_from_v1(tmp_path):
    dbp = tmp_path / "old.db"
    con = sqlite3.connect(dbp)
    con.execute(
        "CREATE TABLE medications(id INTEGER PRIMARY KEY, doc_id INTEGER, drug TEXT, strength TEXT, form TEXT,"
        " frequency TEXT, frequency_plain TEXT, duration TEXT, source_line TEXT, conf REAL,"
        " needs_review INTEGER, verified INTEGER DEFAULT 0)"
    )
    con.commit()
    con.close()
    from medscan import db

    cols = {r[1] for r in db.connect(dbp).execute("PRAGMA table_info(medications)")}
    assert {"canonical", "match_score", "alternatives"} <= cols
