"""Handwriting engine: line segmentation + TrOCR (optional dependency).

    pip install torch transformers
TrOCR is a line-level model, so the page is first cut into text-line strips.
Weights are downloaded from the Hugging Face Hub on first use (several hundred MB
to ~1.3 GB depending on the model) and cached locally; nothing is uploaded.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PIL import Image, ImageOps

from .ocr import OcrLine

DEFAULT_MODEL = "microsoft/trocr-base-handwritten"


def segment_lines(
    img: Image.Image, ink_threshold: int = 140, min_height: int = 12, max_gap: int = 6, pad: int = 8
) -> list[Image.Image]:
    """Cut a page into horizontal text-line strips using a row ink profile."""
    gray = ImageOps.autocontrast(img.convert("L"))
    ink = gray.point(lambda p: 255 if p < ink_threshold else 0)
    rows = list(ink.resize((1, ink.height), Image.BOX).tobytes())  # mean ink per row, 0-255
    bands, start, gap = [], None, 0
    for y, v in enumerate(rows):
        if v > 1:
            if start is None:
                start = y
            end, gap = y, 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                bands.append((start, end))
                start = None
    if start is not None:
        bands.append((start, end))
    strips = []
    for a, b in bands:
        if b - a + 1 < min_height:
            continue
        strips.append(gray.crop((0, max(0, a - pad), gray.width, min(gray.height, b + 1 + pad))).convert("RGB"))
    return strips


def load_trocr(model_name: str = DEFAULT_MODEL) -> Callable[[Image.Image], tuple[str, float]]:
    """Returns recognise(strip) -> (text, confidence 0-100). Raises a clear error if deps are missing."""
    try:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as e:  # pragma: no cover - depends on environment
        raise RuntimeError("Handwriting engine needs: pip install torch transformers") from e
    processor = TrOCRProcessor.from_pretrained(model_name)
    model = VisionEncoderDecoderModel.from_pretrained(model_name).eval()

    def recognise(strip: Image.Image) -> tuple[str, float]:  # pragma: no cover - needs weights
        with torch.no_grad():
            pix = processor(images=strip, return_tensors="pt").pixel_values
            out = model.generate(pix, return_dict_in_generate=True, output_scores=True, max_new_tokens=64)
            lp = model.compute_transition_scores(out.sequences, out.scores, normalize_logits=True)[0]
        text = processor.batch_decode(out.sequences, skip_special_tokens=True)[0].strip()
        return text, round(100 * math.exp(float(lp.mean())), 1) if len(lp) else 0.0

    return recognise


def recognise_page(img: Image.Image, page: int, recognise: Callable[[Image.Image], tuple[str, float]]) -> list[OcrLine]:
    lines = []
    for strip in segment_lines(img):
        text, conf = recognise(strip)
        if text:
            lines.append(OcrLine(text, conf, page))
    return lines
