"""Security Check Captcha Generator for FreshMart.

Generates self-contained, lightweight SVG captcha images with noise lines,
scattered dots, and font glyph rotations without requiring external C libraries.
"""
import random
from typing import Tuple

CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # Omits 0, O, 1, I for readability


def generate_captcha_code(length: int = 5) -> str:
    """Generate a random 5-character alphanumeric captcha code."""
    return "".join(random.choices(CAPTCHA_CHARS, k=length))


def generate_captcha_svg(code: str) -> str:
    """Generate an SVG string for the given security code with anti-bot distortion."""
    width = 150
    height = 50

    # Background gradient colors (soft cream/light mint)
    bg_colors = [
        ("#f1f7f3", "#e2efe7"),
        ("#fef9ee", "#f7ede0"),
        ("#eef6f1", "#d8eade"),
    ]
    bg1, bg2 = random.choice(bg_colors)

    # Noise lines
    lines = []
    line_colors = ["#22a05a", "#14532d", "#e8532f", "#85978a", "#0f4d33"]
    for _ in range(5):
        x1 = random.randint(0, 30)
        y1 = random.randint(5, height - 5)
        x2 = random.randint(width - 40, width)
        y2 = random.randint(5, height - 5)
        color = random.choice(line_colors)
        stroke_w = random.choice([1.2, 1.6, 2.0])
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{stroke_w}" opacity="0.45" />')

    # Noise dots
    dots = []
    for _ in range(25):
        cx = random.randint(5, width - 5)
        cy = random.randint(5, height - 5)
        r = random.uniform(1.0, 2.2)
        color = random.choice(line_colors)
        dots.append(f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="{color}" opacity="0.4" />')

    # Character rendering with variable rotation and color
    char_elements = []
    char_colors = ["#14532d", "#0f3d21", "#1e7240", "#b9381e", "#0b4628"]
    base_x = 18
    for i, ch in enumerate(code):
        x = base_x + i * 24 + random.randint(-2, 3)
        y = random.randint(31, 37)
        angle = random.randint(-18, 18)
        color = random.choice(char_colors)
        font_size = random.randint(22, 26)
        char_elements.append(
            f'<text x="{x}" y="{y}" font-family="Inter, -apple-system, sans-serif" font-weight="800" '
            f'font-size="{font_size}" fill="{color}" transform="rotate({angle} {x} {y})">{ch}</text>'
        )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="cbg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{bg1}" />
      <stop offset="100%" stop-color="{bg2}" />
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" rx="8" fill="url(#cbg)" stroke="#cddcd2" stroke-width="1.5" />
  {''.join(lines)}
  {''.join(dots)}
  {''.join(char_elements)}
</svg>"""
    return svg
