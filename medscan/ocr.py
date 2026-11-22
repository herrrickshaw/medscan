"""OCR layer: image/PDF -> text with per-line confidence (local Tesseract only)."""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image, ImageFilter, ImageOps


@dataclass
class OcrLine:
    text: str
    conf: float  # 0-100, mean word confidence
    page: int = 1


def preprocess(img: Image.Image) -> Image.Image:
    """Grayscale, upscale small scans, autocontrast, light denoise."""
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 1500:
        scale = 1500 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    img = ImageOps.autocontrast(img)
    return img.filter(ImageFilter.MedianFilter(3))


def _page_images(path: Path) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["pdftoppm", "-r", "300", "-png", str(path), f"{d}/p"], check=True)
            return [Image.open(p).copy() for p in sorted(Path(d).glob("p*.png"))]
    return [Image.open(path)]


def ocr_file(path: str | Path, lang: str = "eng", engine: str = "tesseract", model: str | None = None,
             recogniser=None) -> list[OcrLine]:
    """engine: "tesseract" (printed text) or "trocr" (handwriting; needs torch+transformers)."""
    lines: list[OcrLine] = []
    if engine == "trocr":
        from . import htr
        recogniser = recogniser or htr.load_trocr(model or htr.DEFAULT_MODEL)
    elif engine != "tesseract":
        raise ValueError(f"unknown engine {engine!r}")
    for page_no, img in enumerate(_page_images(Path(path)), 1):
        if engine == "trocr":
            lines += htr.recognise_page(preprocess(img), page_no, recogniser)
            continue
        data = pytesseract.image_to_data(
            preprocess(img), lang=lang, config="--psm 6", output_type=pytesseract.Output.DICT
        )
        grouped: dict[tuple, list[tuple[str, float]]] = {}
        for i, word in enumerate(data["text"]):
            if word.strip() and float(data["conf"][i]) >= 0:
                key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                grouped.setdefault(key, []).append((word, float(data["conf"][i])))
        for words in grouped.values():
            lines.append(
                OcrLine(" ".join(w for w, _ in words), sum(c for _, c in words) / len(words), page_no)
            )
    return lines
