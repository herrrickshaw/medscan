"""Rule-based extraction of prescriptions and lab results from OCR text.

Deliberately transparent (regex + small lexicons) so every field is auditable.
Anything uncertain is flagged `needs_review` rather than silently trusted.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

REVIEW_CONF = 70.0  # below this mean OCR confidence a row needs human review

FREQ = {  # abbreviation -> plain meaning
    "od": "once daily", "qd": "once daily", "bd": "twice daily", "bid": "twice daily",
    "tds": "three times daily", "tid": "three times daily", "qid": "four times daily",
    "hs": "at bedtime", "sos": "if needed", "prn": "if needed", "stat": "immediately",
    "1-0-1": "twice daily", "1-1-1": "three times daily", "1-0-0": "morning",
    "0-0-1": "night", "0-1-0": "afternoon", "1-1-1-1": "four times daily",
}
FORMS = r"(?:tab(?:let)?s?|cap(?:sule)?s?|syr(?:up)?|inj(?:ection)?|oint(?:ment)?|drops?|cream|gel|susp(?:ension)?)"
STRENGTH = r"(\d+(?:\.\d+)?)\s*(mcg|µg|mg|g|ml|iu|%)"
FREQ_RE = r"(1-1-1-1|1-0-1|1-1-1|1-0-0|0-0-1|0-1-0|\b(?:od|qd|bd|bid|tds|tid|qid|hs|sos|prn|stat)\b)"
DURATION_RE = r"(?:x|for)?\s*(\d+)\s*(day|days|d|week|weeks|wk|wks|month|months)\b"

RX_LINE = re.compile(
    rf"^\W*(?:\d+[.)]\s*)?(?:(?P<form>{FORMS})\.?\s+)?(?P<drug>[A-Za-z][A-Za-z\-]+(?:\s[A-Za-z\-]+)?)\s*"
    rf"(?P<strength>{STRENGTH})?",
    re.I,
)
LAB_LINE = re.compile(
    r"^(?P<test>[A-Za-z][A-Za-z0-9 ()/\-,]+?)\s{0,3}[:\-]?\s+(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-z%µ/][A-Za-z0-9%µ/\^.]*)?\s*"
    r"(?:(?P<lo>\d+(?:\.\d+)?)\s*[-–]\s*(?P<hi>\d+(?:\.\d+)?))?\s*(?P<flag>\b[HL]\b|High|Low)?\s*$",
    re.I,
)
HEADER = {
    "patient": re.compile(r"(?:patient|name)\s*[:\-]\s*(.+)", re.I),
    "age_sex": re.compile(r"(?:age\s*/\s*sex|age)\s*[:\-]\s*(.+)", re.I),
    "date": re.compile(r"(?:date|reported|collected)\s*[:\-]\s*([0-9]{1,4}[-/.][0-9]{1,2}[-/.][0-9]{1,4})", re.I),
    "doctor": re.compile(r"(?:dr\.?|doctor|ref(?:erred)? by)\s*[:\-]?\s*([A-Za-z. ]{3,40})", re.I),
}
NOT_DRUG = {"patient", "name", "date", "age", "sex", "dr", "doctor", "rx", "address", "diagnosis", "test", "report", "sample"}


@dataclass
class Medication:
    drug: str
    strength: str = ""
    form: str = ""
    frequency: str = ""
    frequency_plain: str = ""
    duration: str = ""
    source_line: str = ""
    conf: float = 0.0
    needs_review: bool = False
    canonical: str = ""      # lexicon match (generic name); empty if none
    match_score: float = 0.0
    alternatives: str = ""    # look-alike candidates when ambiguous


@dataclass
class LabResult:
    test: str
    value: float
    unit: str = ""
    ref_low: float | None = None
    ref_high: float | None = None
    flag: str = ""  # H / L / "" (computed from range when not printed)
    source_line: str = ""
    conf: float = 0.0
    needs_review: bool = False


@dataclass
class Extraction:
    header: dict = field(default_factory=dict)
    medications: list[Medication] = field(default_factory=list)
    labs: list[LabResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse_lines(lines: list[tuple[str, float]], lexicon=None) -> Extraction:
    """`lines` = [(text, mean_confidence)]."""
    out = Extraction()
    for text, conf in lines:
        text = text.strip()
        if not text:
            continue
        for key, rx in HEADER.items():
            m = rx.search(text)
            if m and key not in out.header:
                out.header[key] = m.group(1).strip()
        lab = _parse_lab(text, conf)
        if lab:
            out.labs.append(lab)
            continue
        med = _parse_med(text, conf)
        if med:
            _apply_lexicon(med, lexicon)
            out.medications.append(med)
    return out


def _parse_lab(text: str, conf: float) -> LabResult | None:
    m = LAB_LINE.match(text)
    if not m:
        return None
    test = m["test"].strip()
    if test.lower().split()[0] in NOT_DRUG or re.search(rf"\b{FORMS}\b", test, re.I):
        return None
    lo = float(m["lo"]) if m["lo"] else None
    hi = float(m["hi"]) if m["hi"] else None
    val = float(m["value"])
    flag = (m["flag"] or "")[:1].upper()
    if not flag and lo is not None and hi is not None:
        flag = "L" if val < lo else "H" if val > hi else ""
    # a "lab" line with neither unit nor range is almost certainly not a lab result
    if not m["unit"] and lo is None:
        return None
    return LabResult(test, val, m["unit"] or "", lo, hi, flag, text, round(conf, 1), conf < REVIEW_CONF)


def _parse_med(text: str, conf: float) -> Medication | None:
    has_form = re.search(rf"\b{FORMS}\b", text, re.I)
    freq = re.search(FREQ_RE, text, re.I)
    strength = re.search(STRENGTH, text, re.I)
    # require at least two prescription signals so headers/prose don't leak in
    if sum(bool(x) for x in (has_form, freq, strength)) < 2:
        return None
    m = RX_LINE.match(text)
    if not m or m["drug"].split()[0].lower() in NOT_DRUG:
        return None
    drug = re.sub(rf"\b{FORMS}\b", "", m["drug"], flags=re.I).strip()
    if not drug:
        return None
    dur = re.search(DURATION_RE, text, re.I)
    f = freq.group(1).lower() if freq else ""
    return Medication(
        drug=drug.title(),
        strength=f"{strength.group(1)} {strength.group(2).lower()}" if strength else "",
        form=(m["form"] or (has_form.group(0) if has_form else "")).lower().rstrip("."),
        frequency=f,
        frequency_plain=FREQ.get(f, ""),
        duration=f"{dur.group(1)} {dur.group(2)}" if dur else "",
        source_line=text,
        conf=round(conf, 1),
        needs_review=conf < REVIEW_CONF or not strength,
    )


def _apply_lexicon(med: Medication, lexicon) -> None:
    """Annotate (never overwrite) the OCR'd drug name; flag anything not confidently matched."""
    if lexicon is None:
        return
    m = lexicon.match(med.drug)
    if m is None:
        med.needs_review = True  # unknown to the lexicon: possible OCR error or missing entry
        return
    med.canonical, med.match_score = m.canonical, m.score
    med.alternatives = ", ".join(m.alternatives)
    if not m.confident:
        med.needs_review = True
