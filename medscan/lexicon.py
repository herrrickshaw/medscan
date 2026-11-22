"""Drug-name lexicon with fuzzy matching.

OCR output is never silently "corrected": the original text is kept, the best
canonical candidate and its score are recorded, and look-alike pairs
(e.g. hydroxyzine / hydralazine) are marked ambiguous so a human decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / "data" / "drugs.txt"
MIN_SCORE = 0.80  # below this: no candidate offered
CONFIDENT = 1.0  # only an exact lexicon hit skips review; any fuzzy match is flagged
AMBIGUITY_GAP = 0.06  # runner-up within this of the winner => ambiguous


@dataclass
class Match:
    canonical: str
    score: float
    ambiguous: bool = False
    alternatives: list[str] = field(default_factory=list)

    @property
    def confident(self) -> bool:
        return self.score >= CONFIDENT and not self.ambiguous


class Lexicon:
    def __init__(self, entries: dict[str, str]):
        self.entries = entries  # lowercase surface form -> canonical generic

    @classmethod
    def load(cls, *extra: str | Path) -> Lexicon:
        entries: dict[str, str] = {}
        for p in (DEFAULT_PATH, *map(Path, extra)):
            for raw in Path(p).read_text().splitlines():
                line = raw.split("#", 1)[0].strip().lower()
                if not line:
                    continue
                brand, _, generic = line.partition("|")
                entries[brand.strip()] = (generic or brand).strip()
        return cls(entries)

    def match(self, text: str) -> Match | None:
        text = text.strip().lower()
        if not text:
            return None
        probes = {text, text.split()[0]}
        best: dict[str, float] = {}  # canonical -> best score
        for surface, canon in self.entries.items():
            score = max(SequenceMatcher(None, p, surface).ratio() for p in probes)
            if score > best.get(canon, 0):
                best[canon] = score
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        if not ranked or ranked[0][1] < MIN_SCORE:
            return None
        top, score = ranked[0]
        close = [c for c, s in ranked[1:4] if score < 1.0 and score - s <= AMBIGUITY_GAP and s >= MIN_SCORE]
        return Match(top, round(score, 3), bool(close), close)
