"""Portable font loading so the OCR tests run on macOS and Linux CI alike."""
import os

from PIL import ImageFont

CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",                    # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",                 # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def load_font(size: int):
    if os.environ.get("MEDSCAN_TEST_FONT") != "builtin":  # "builtin" forces the Pillow fallback
        for path in CANDIDATES:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)  # Pillow >= 10.1 ships a scalable font
