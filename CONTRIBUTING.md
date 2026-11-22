# Contributing to medscan

Thanks for helping. `medscan` reads prescriptions and lab reports into a local SQLite database, so
a wrong value can mislead a person. Correctness and honest uncertainty matter more than coverage of
features. It is **not a medical device**, and everything it extracts needs human review.

Everyone taking part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Never post patient data

Do not put real prescriptions, lab reports, names, or any other patient information in issues, pull
requests, tests, fixtures or screenshots. Use synthetic text or images. If a real document triggers a
bug, describe the failure ("a line like `Tab X 500 mg BD` was read as...") and re-create it with made-up
data.

## Setup

```bash
brew install tesseract poppler      # macOS; poppler is only needed for PDFs
# Debian/Ubuntu: sudo apt-get install tesseract-ocr poppler-utils
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pre-commit
pre-commit install                  # runs ruff and file checks on every commit
```

The handwriting engine (`--engine trocr`) is optional: `pip install torch transformers`. The first run
downloads model weights from Hugging Face. The tests do **not** need these; they use a fake recogniser,
so a contributor without a GPU or a large download can run the whole suite.

## Before you open a pull request

```bash
python -m pytest                    # tests, with coverage via pytest-cov if you add --cov=medscan
pre-commit run --all-files          # ruff lint + format, whitespace, YAML, large files
```

CI runs the same two things: the `lint` job runs the pre-commit hooks, and the `test` job runs pytest
on Python 3.10, 3.11, 3.12 and 3.13. Both must pass. Ruff settings are in `pyproject.toml` (line length
120, target Python 3.10), so code must stay compatible with 3.10.

Please also:
- add or update tests for any behaviour you change (see "Tests" below);
- update `README.md` if the change is visible to users, including limits and caveats;
- keep the change focused; unrelated cleanups belong in a separate pull request.

## Project layout

| Path | Role |
|---|---|
| `medscan/ocr.py` | Image/PDF to text lines with confidence (Tesseract; dispatches to TrOCR) |
| `medscan/htr.py` | Handwriting: line segmentation and the TrOCR wrapper (heavy imports are lazy) |
| `medscan/parse.py` | Regex extraction of medications and lab results, review flags |
| `medscan/lexicon.py` | Drug-name lexicon and fuzzy matching |
| `medscan/db.py` | SQLite schema, additive migrations, saving, de-duplication by file hash |
| `medscan/cli.py` | `scan`, `list`, `review`, `export` |
| `medscan/data/drugs.txt` | Starter drug-name list |
| `tests/` | Pytest suite; `tests/fonts.py` loads fonts portably |

## Design rules to keep

These exist because mistakes here are costly. Changes that weaken them need a clear justification.

1. **Never overwrite OCR text.** The original text is stored, and any lexicon match is recorded beside it
   (`canonical`, `match_score`, `alternatives`).
2. **Uncertain means `needs_review`.** Only an exact lexicon hit skips review. A fuzzy match, an unknown
   name, a near-tie between candidates, low OCR confidence, or a missing strength must all be flagged.
3. **Be conservative when parsing.** A line becomes a medication only with at least two prescription
   signals (form, frequency, strength), so headers and prose do not leak in. Prefer missing a row, which
   `list` makes visible, to inventing one.
4. **Keep the raw text** (`documents.raw_text`) so rows can be re-parsed or audited later.
5. **Schema changes must be additive.** Add columns with a migration in `db.connect()` so databases from
   earlier versions keep working.
6. **Everything stays local.** Do not add network calls to the scan path. Model weights are the one
   download, and only for the optional handwriting engine.

## Tests

- Use synthetic images and text only. Generate images with Pillow (see `tests/test_medscan.py`).
- Get fonts through `load_font` in `tests/fonts.py` so tests pass on macOS and Linux. Setting
  `MEDSCAN_TEST_FONT=builtin` forces Pillow's built-in font, which is a quick way to check portability.
- Test the failure direction too. For a safety rule such as "a fuzzy match is flagged", assert the flag is
  set, not just that the happy path works.
- Do not test against real TrOCR weights in CI. Pass a fake recogniser to `ocr_file(..., recogniser=...)`.
- Interactive commands (`review`) are tested by monkeypatching `builtins.input`.

## Adding drug names

`medscan/data/drugs.txt` is a **starter list, not clinically validated**. One entry per line, lowercase:

```text
metformin                  # a generic name
dolo|paracetamol           # brand|generic: a brand maps to its generic
```

For a pull request that adds names, cite the source (for example RxNorm, WHO ATC, CDSCO or BDPM) and keep
the entries accurate; a wrong brand-to-generic mapping is worse than a missing one. Large national lists
should be loaded with `--lexicon FILE` rather than committed here.

## Datasets and literature

- Do not commit datasets or sample documents. Link to them instead.
- When you add a dataset or paper to the README, check it against the primary source (the paper, the
  data host's own page) and record the licence you actually saw. Mark anything you could not verify as
  "not verified". Prefer the original publisher over a re-upload.
- Confirm each link resolves. For arXiv entries, the link text should be the paper's real title.

## Licence

By contributing you agree that your contribution is licensed under the [MIT License](LICENSE).
