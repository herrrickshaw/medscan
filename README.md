# medscan

[![tests](https://github.com/herrrickshaw/medscan/actions/workflows/ci.yml/badge.svg)](https://github.com/herrrickshaw/medscan/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![codecov](https://codecov.io/gh/herrrickshaw/medscan/graph/badge.svg)](https://codecov.io/gh/herrrickshaw/medscan)

Local tool that scans prescription / lab-report images and PDFs, extracts structured
medications and lab results, and records them in SQLite. Nothing leaves your machine.

```bash
brew install tesseract poppler          # poppler only needed for PDFs
python3 -m venv .venv && .venv/bin/pip install pytesseract pillow pytest
.venv/bin/python -m medscan.cli scan rx.jpg report.pdf    # OCR -> parse -> save
.venv/bin/python -m medscan.cli list                      # everything, ⚠ = needs review
.venv/bin/python -m medscan.cli review                    # confirm/delete low-confidence rows
.venv/bin/python -m medscan.cli export labs > labs.csv
.venv/bin/python -m pytest
```

**How it works:** preprocess (grayscale/upscale/contrast) → Tesseract with per-line confidence →
regex parsers (drug, strength, form, frequency incl. `1-0-1`/BD/TDS, duration; lab test/value/unit/
reference range with H/L flag computed from the range) → SQLite (raw OCR text kept; identical
files deduplicated by SHA-256). Rows with OCR confidence < 70 or no strength are flagged
`needs_review`.

### Handwriting (TrOCR) — `--engine trocr`
```bash
.venv/bin/pip install torch transformers
.venv/bin/python -m medscan.cli scan handwritten_rx.jpg --engine trocr
```
The page is cut into text-line strips (row-ink projection) and each strip is read by
[`microsoft/trocr-base-handwritten`](https://huggingface.co/microsoft/trocr-base-handwritten)
(override with `--model`). Per-line confidence = exp(mean token log-prob). Weights download from
the Hugging Face Hub on first use and are cached locally; nothing is uploaded.
**Status:** run once end-to-end with the real weights (torch 2.15, transformers 5.24) on a
3-line image rendered in the *Bradley Hand* script font (not real handwriting). All three lines
were read correctly, matched the lexicon exactly, and were still flagged for review because line
confidence was 59-69 (< 70). TrOCR also appended junk to the line ends (`1/ 1/`, `3/2`), so
review catches it. A one-image synthetic test says nothing about accuracy on real doctors'
handwriting, which is unmeasured and expected to be much worse; the papers above fine-tune on
prescription data for that reason. A "pooler weights MISSING" load notice is printed; the
output was sensible regardless.

### Drug-name matching
Each OCR'd drug name is looked up in `medscan/data/drugs.txt` (~120 generics + a few Indian brands,
a **starter list, not clinically validated**). Extend with `--lexicon FILE` (one name per line,
`brand|generic` for brands), e.g. from RxNorm, WHO ATC, CDSCO or [BDPM](https://github.com/matthieugraziani/bdpm-prescription-ocr).
The OCR text is **never overwritten**: the match is stored beside it (`canonical`, `match_score`,
`alternatives`). Only an exact hit skips review; fuzzy matches (`Metforrnin`→metformin), unknown
names and near-ties between two candidates are all marked `needs_review`. Similarity is
`difflib`, which does not catch real look-alike pairs (hydroxyzine/hydralazine) as ambiguous;
they rely on the review flag.

**Limits (read before trusting it):** verified only on synthetic Arial images, not real clinical
documents. Tesseract + regexes do not read handwriting. Not a medical device; a human must
verify every record before it is relied on.

## Literature
Found via web search; I read abstracts/snippets only, not the full papers.

**Handwritten prescriptions**
- [Leveraging Deep Learning with Multi-Head Attention for Accurate Extraction of Medicine from Handwritten Prescriptions](https://arxiv.org/abs/2412.18199) (2024): Mask R-CNN to locate the medicine region + TrOCR; reports ~1.4% CER.
- [MIRAGE](https://arxiv.org/abs/2410.09729) (2024): fine-tuned LLaVA/Idefics2 on 743,118 *simulated* medical-record images (from 1,133 Indian doctors) and reports ~82% name+dosage extraction. The data is simulated, not scanned real prescriptions, and only a 100-record subset is public (see Datasets below).
- [Weakly supervised information extraction from inscrutable handwritten document images](https://arxiv.org/abs/2306.06823): medicine-name language model injected into recognition.
- [Doctor's prescription recognition system, multi-language](https://arxiv.org/abs/2210.11666) (2022).
- [ACL Industry 2023 paper on digitising prescriptions](https://aclanthology.org/2023.acl-industry.76.pdf): notes US-trained NER degrades on non-US prescription vocabulary.
- [EACL 2026 industry: entity extraction/linking on French prescriptions](https://aclanthology.org/2026.eacl-industry.68.pdf).

**Medical reports / benchmarks**
- [MedRepBench](https://arxiv.org/abs/2508.16674): 1,900 real reports; OCR+LLM pipelines suffer layout-blindness and latency vs. end-to-end VLMs.
- [Compact multimodal LMs as OCR alternatives for noisy clinical reports](https://arxiv.org/abs/2511.13523) (EACL 2026): Tesseract underperforms on handheld captures.
- [MedStruct-S](https://arxiv.org/abs/2605.03103), [MeDocVL](https://arxiv.org/abs/2602.06402), [ClinOCR-Bench](https://arxiv.org/abs/2607.03650), [MedDocBench (ICML 2026)](https://icml.cc/virtual/2026/71758).

**General handwriting background**
- [Handwritten OCR: Systematic Literature Review](https://arxiv.org/abs/2001.00139) · [Handwritten Text Recognition: A Survey (2025)](https://arxiv.org/abs/2502.08417)

## More literature
Added 2026-11-22 from a second round of searches. Again I read search-result summaries, not the full
papers; the link checker confirms each arXiv link text is that paper's real title, nothing more.

### Text recognition and document-understanding models
- [TrOCR: Transformer-based Optical Character Recognition with Pre-trained Models](https://arxiv.org/abs/2109.10282): the line-level model behind `--engine trocr` (AAAI 2023).
- [OCR-free Document Understanding Transformer](https://arxiv.org/abs/2111.15664): Donut, which skips the OCR step and emits structured output directly (ECCV 2022); used by one of the repos above.
- [LayoutLM: Pre-training of Text and Layout for Document Image Understanding](https://arxiv.org/abs/1912.13318): adds 2D position to text, the basis for layout-aware form and report extraction.
- [Document Understanding for Healthcare Referrals](https://arxiv.org/abs/2309.13184): applied document-understanding on clinical referral documents.

### Vision-language models and OCR benchmarks
- [Qwen2-VL: Enhancing Vision-Language Model's Perception of the World at Any Resolution](https://arxiv.org/abs/2409.12191)
- [Qwen2.5-VL Technical Report](https://arxiv.org/abs/2502.13923)
- [OCRBench v2: An Improved Benchmark for Evaluating Large Multimodal Models on Visual Text Localization and Reasoning](https://arxiv.org/abs/2501.00321): per its summary, models still err often on handwritten content.
- [Ocean-OCR: Towards General OCR Application via a Vision-Language Model](https://arxiv.org/abs/2501.15558): includes a handwriting evaluation.
- [PaddleOCR-VL: Boosting Multilingual Document Parsing via a 0.9B Ultra-Compact Vision-Language Model](https://arxiv.org/abs/2510.14528): small enough to run locally. Its handwriting numbers and Ocean-OCR's use different metrics, so do not compare them across papers.

### Datasets (public doctor-handwriting data is scarce)
- [RxHandBD: A Handwritten Prescription Word Image Dataset](https://data.mendeley.com/datasets/dsb5r6vskg): about 5.6k cropped handwritten words from real prescriptions; check its licence before use.
- [Dataset for classification of handwritten and printed text in a doctor's prescription](https://ieee-dataport.org/documents/dataset-classification-handwritten-and-printed-text-doctors-prescription): useful for routing handwritten vs printed lines to the right engine; reportedly needs an IEEE DataPort account.
- [An online cursive handwritten medical words recognition system for busy doctors in developing countries](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8897401/): about 17k samples of 480 medical terms (Scientific Reports, 2022).

### Clinical medication extraction (what to do with the text once you have it)
- [2018 n2c2 shared task on adverse drug events and medication extraction: overview](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085): drug, dosage, frequency, duration entities on discharge summaries; the standard evaluation for this step.
- [n2c2 2018 Track 2 challenge page](https://n2c2.dbmi.hms.harvard.edu/challenge/2018-track-2-ade-medication-extraction): data is released under a data-use agreement.
- [An ensemble of neural models for nested adverse drug events and medication extraction with subwords](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6913208/): one top participant system.

### Drug-name confusion and safety
- [Identification of Confusable Drug Names: A New Approach and Evaluation Methodology](https://aclanthology.org/C04-1137/): COLING 2004; orthographic + phonetic similarity for look-alike/sound-alike pairs; the kind of measure `difflib` lacks.
- [Automatic Identification of Confusable Drug Names](https://doi.org/10.1016/j.artmed.2005.07.005): Kondrak & Dorr, Artificial Intelligence in Medicine 36(1), 2006; journal follow-up, where combining several similarity measures worked best.
- [The problem of look-alike, sound-alike name errors: Drivers and solutions](https://pubmed.ncbi.nlm.nih.gov/32198938/)

**Gaps the searches suggest:** I found no study that measures how OCR error rate degrades downstream
medication-extraction accuracy, and the public benchmarks above are mostly non-Indian or non-English.
Search summaries also mention safety objections to fuzzy matching in medication order entry; I did not
locate the primary source, so treat that as a lead, not a citation. It is why `medscan` flags every
inexact match instead of auto-correcting it.

## Datasets
Checked against primary sources on 2026-11-22: the papers' full text (via their arXiv PDFs), the Mendeley
Data API, the Hugging Face API and the public Kaggle pages. **Nothing was downloaded**, and none of it has
been used to evaluate `medscan`. Real prescriptions can contain patient data, so check consent and
de-identification before using any real clinical images. Where a Kaggle copy and a primary source both
exist, prefer the primary one; Kaggle entries are re-uploads whose licence fields I could only partly read
from the static page.

| Dataset | What it is | Licence / access (as checked) |
|---|---|---|
| [RxHandBD, Mendeley Data](https://data.mendeley.com/datasets/dsb5r6vskg) (v3) | 5,578 cropped handwritten words from physical prescriptions, 512x512; two ~128 MB zips (Raw, ML). Word-level, not full pages. | CC BY 4.0 (Mendeley API). Primary source. |
| [RxHandBD, Kaggle copy](https://www.kaggle.com/datasets/abrahametry/rxhandbd-handwritten-word-image-dataset) | Re-upload of the above. A search listing described it as 128x128, i.e. an older version than Mendeley's v3 (not confirmed on the page). | Not verified. |
| [Doctor's Handwritten Prescription BD](https://www.kaggle.com/datasets/mamun1113/doctors-handwritten-prescription-bd-dataset) | Word crops of medicine names, listed as 4,680 words in 78 classes, Excel/CSV. Good for classifying a medicine-name crop, not for reading whole lines. | Not verified (search summaries suggest ODbL; confirm on the page). |
| [OCR-Processed Handwritten Prescriptions](https://www.kaggle.com/datasets/nadaarfaoui/ocr-processed-handwritten-prescriptions) | OCR *text output* derived from the BD dataset above, so it carries that dataset's errors. | Apache 2.0 (read from the page). |
| [Handwritten Medical Prescriptions Collection](https://www.kaggle.com/datasets/mehaksingal/illegible-medical-prescription-images-dataset) | Small set of whole-prescription images (listing: 129 files), good for a smoke test. | Not verified (a search listing showed MIT). |
| [Bilingual medical prescriptions (Arabic & English)](https://www.kaggle.com/datasets/nooralzoghby/bilingual-medical-prescriptions-arabic-and-english) | Handwritten/printed prescriptions with medication, dosage and frequency annotations; the listing says it is still being expanded. | Not verified. |
| [100 handwritten medical records, Hugging Face](https://huggingface.co/datasets/chaithanyakota/100-handwritten-medical-records) | The public 100-record subset of MIRAGE's *simulated* data, one parquet file. | CC BY-ND 4.0 (HF tag): no derivative works, which limits redistributing modified copies. |
| [Noisy Medical Document Images (OCR)](https://www.kaggle.com/datasets/devp1866/noisy-medical-document-images-ocr) | 1,000 *synthetic* bills and discharge summaries with scan noise and JSON ground truth (per listing). No real patient data. | CC BY-SA 4.0 (read from the page). |
| [Multi-Document Dataset for OCR, Document AI & LLM](https://www.kaggle.com/datasets/miadul/multi-document-dataset-for-ocr-document-ai-and-llm) | Synthetic documents in eight types, one of them "Medical Report", with JSON labels. | Not verified. |
| [Complete Blood Count (CBC) Test](https://www.kaggle.com/datasets/ahmedelsayedtaha/complete-blood-count-cbc-test) | Tabular values for 500 patients (listing says transcribed from CBC images). **Values only, no images**, so not usable for OCR. | Not verified. |

**Data used by the papers themselves**
- [arXiv 2412.18199](https://arxiv.org/abs/2412.18199): about 1,000 prescriptions from 50 doctors in Pakistan, augmented to 9,920 images. The text I read has no statement that the data is released, so assume it is private.
- [arXiv 2306.06823](https://arxiv.org/abs/2306.06823): its Table 1 lists 9,645 images from 117 doctors, about 4.5 medicines per image; no release statement found, so assume private.
- [arXiv 2410.09729](https://arxiv.org/abs/2410.09729): large simulated set, only the 100-record subset above is public.

**Gaps:** I found no public set of *real, full-page* prescriptions with line-level transcriptions, and no public
*real lab-report scans* with ground truth; the lab-report options above are synthetic or tabular. That is the main
obstacle to measuring `medscan` honestly beyond synthetic images.

## Related GitHub repos (stars as of 2026-11-22)
| Repo | ★ | Notes |
|---|---|---|
| [Aniket025/Medical-Prescription-OCR](https://github.com/Aniket025/Medical-Prescription-OCR) | 138 | Prescription → digital text |
| [JonSnow1807/Medical-Prescription-OCR](https://github.com/JonSnow1807/Medical-Prescription-OCR) | 24 | Handwritten; Donut transformer + zero-shot classification |
| [Shriram2005/MediScribe-OCR](https://github.com/Shriram2005/MediScribe-OCR) | 16 | College project |
| [matthieugraziani/bdpm-prescription-ocr](https://github.com/matthieugraziani/bdpm-prescription-ocr) | 4 | OCR + fuzzy-match to French BDPM drug DB (the lexicon idea above) |
| [Waqas-Khan-CodeCanvas/RxRead-Ai](https://github.com/Waqas-Khan-CodeCanvas/RxRead-Ai) | 3 | Tesseract + local Ollama, React/Express |
| [Baranwal-47/MedScan](https://github.com/Baranwal-47/MedScan) | 3 | Prescription OCR inside a pharmacy-delivery app |
| [abelmou/Healthcare-Assistant](https://github.com/abelmou/Healthcare-Assistant) | 8 | RAG assistant with prescription OCR |
| [sumanthml/ScanTree](https://github.com/sumanthml/ScanTree) | 0 | Lab-report OCR + biomarkers via Gemini Vision |
| [Yarram-Koushik/DocAssist](https://github.com/Yarram-Koushik/DocAssist) | 1 | Lab-report parsing + openFDA interaction checker |

I have not run or audited these repos; descriptions come from GitHub metadata. A search for
"medical prescription handwriting recognition" returned no repos.

## License
MIT, see [LICENSE](LICENSE).
