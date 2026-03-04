#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Mark Moore
"""
gen_wallpaper.py — DankMaterialShell Vector Wallpaper Generator
===============================================================
Generates a single SVG wallpaper and prints its path to stdout so the calling
QML process (VectorWallpaper.qml) can pick it up.  The SVG is then converted
to PNG by rsvg-convert and applied by swww / swaybg / hyprpaper.

QUICK USAGE (manual)
--------------------
    # Single seed colour — palette is derived algorithmically:
    python3 gen_wallpaper.py --color "#6750A4" --style geometric --seed 42

    # Full Material You palette (what the plugin passes automatically):
    python3 gen_wallpaper.py \
        --colors "#6750A4" "#625B71" "#7D5260" "#4F378B" "#4A4458" "#633B48" \
        --surface "#141218" --accent "#D0BCFF" \
        --mode dark --style cosmos --seed 42 \
        --width 2560 --height 1440 \
        --output ~/Pictures/DankWallpapers/my_test.svg

OUTPUT
------
The script always prints the SVG path to stdout on success (one line).
Exit code 0 = success, non-zero = error (details on stderr).

PIPELINE OVERVIEW
-----------------
    1. Palette — either derived from a single hue (palette_from_color) or
       assembled directly from Material You tokens (palette_from_matugen).
    2. SVGBuilder — a thin wrapper that accumulates <defs> and elements and
       renders them into a valid SVG document.
    3. Style function — draws shapes into the SVGBuilder using the palette.
    4. File write — saves the SVG, prints the path.

ADDING A NEW STYLE
------------------
    1. Define  def style_myname(svg, rng, bg, colors, accent): ...
    2. Add it to the STYLES dict at the bottom of this section.
    3. It will automatically appear in --style choices and the plugin's
       settings panel dropdown.

STANDARD LIBRARY REFERENCES
----------------------------
    argparse  https://docs.python.org/3/library/argparse.html
    colorsys  https://docs.python.org/3/library/colorsys.html
    math      https://docs.python.org/3/library/math.html
    os        https://docs.python.org/3/library/os.html
    pathlib   https://docs.python.org/3/library/pathlib.html
    random    https://docs.python.org/3/library/random.html
"""

import argparse
import colorsys  # https://docs.python.org/3/library/colorsys.html
import math  # https://docs.python.org/3/library/math.html
import os  # https://docs.python.org/3/library/os.html
import random  # https://docs.python.org/3/library/random.html
import sys
from pathlib import Path  # https://docs.python.org/3/library/pathlib.html


# ── Output directory ───────────────────────────────────────────────────────────


def default_output_dir() -> Path:
    """
    Return ~/Pictures/DankWallpapers as a Path, creating it if needed.

    Uses the HOME environment variable so it works inside Quickshell's
    sandboxed process environment where Path.home() might not resolve
    correctly.  Falls back to Path.home() if HOME is unset.

    Relevant stdlib docs:
        os.environ  https://docs.python.org/3/library/os.html#os.environ
        Path.mkdir  https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir
    """
    home = Path(os.environ.get("HOME", str(Path.home())))
    out_dir = home / "Pictures" / "DankWallpapers"
    # parents=True  → create intermediate dirs (Pictures/) if missing
    # exist_ok=True → don't raise an error if the dir already exists
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ── Colour helpers ─────────────────────────────────────────────────────────────


def hex_to_hsl(hexcol: str):
    """
    Convert a CSS hex colour string to (hue°, saturation%, lightness%).

    Accepts both 3-digit (#rgb) and 6-digit (#rrggbb) forms.

    colorsys.rgb_to_hls returns (h, l, s) — note the unusual order (HLS not
    HSL).  We reorder to the more conventional HSL and scale to human-friendly
    ranges: hue 0–360, saturation 0–100, lightness 0–100.

    stdlib: https://docs.python.org/3/library/colorsys.html#colorsys.rgb_to_hls
    """
    hexcol = hexcol.lstrip("#")
    if len(hexcol) == 3:
        hexcol = "".join(c * 2 for c in hexcol)
    r, g, b = (int(hexcol[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s * 100, l * 100


def hsla(h, s, l, a=1.0):
    """
    Format a colour as an SVG/CSS hsla() string.

    SVG 1.1 and CSS Color Level 3 both accept hsla().
    The hue is automatically wrapped to 0–360 via modulo so callers can
    pass values like 390 or -10 freely.

    Parameters
    ----------
    h : float  Hue in degrees (0–360, wraps).
    s : float  Saturation percentage (0–100).
    l : float  Lightness percentage (0–100).
    a : float  Alpha / opacity (0.0 = transparent, 1.0 = opaque).
    """
    return f"hsla({h % 360:.1f},{s:.1f}%,{l:.1f}%,{a:.3f})"


def lerp(a, b, t):
    """
    Linear interpolation between a and b.

    lerp(a, b, 0) == a
    lerp(a, b, 1) == b
    lerp(a, b, 0.5) == midpoint

    Used by style_gradient_waves to space wave baselines evenly across the
    screen height.
    """
    return a + (b - a) * t


# ── Palette builders ───────────────────────────────────────────────────────────


def palette_from_color(
    hex_color: str, rng: random.Random, dark_mode: bool | None = None
):
    """
    Derive a full wallpaper palette from a single seed hex colour.

    This path is used when only --color is supplied (no --colors).  It builds
    a set of harmonious hues algorithmically, so results look good even with
    arbitrary input colours.

    Returns
    -------
    (bg, colors, accent, dark_mode)
        bg      : str  — background fill colour (hsla format)
        colors  : list[str] — 3–5 shape fill colours (hsla format)
        accent  : str  — vivid highlight colour (hsla format)
        dark_mode: bool — True if a dark background was chosen

    TUNING GUIDE
    ------------
    Colour harmony scheme
        The scheme is picked randomly from four options.  To always use one,
        replace rng.choice([...]) with a literal string.
        "analogous"          — colours close together on the wheel (cohesive)
        "triadic"            — three equidistant hues (vibrant, balanced)
        "complementary"      — opposite hues with close neighbours (punchy)
        "split_complementary"— primary + two near-complements (dynamic)

    Background lightness (dark mode)
        bg_l = rng.uniform(5, 14)
        Range 0–100.  Lower = darker.  Try (2, 8) for near-black or
        (15, 25) for a "charcoal" feel.
        stdlib: https://docs.python.org/3/library/random.html#random.Random.uniform

    Background lightness (light mode)
        bg_l = rng.uniform(88, 97)
        Higher = whiter.  Try (80, 90) for a slightly tinted paper look.

    Shape colour lightness (dark mode)
        fg_l_range = (50, 82)
        Shapes are mid-to-bright so they read against a dark background.
        Narrow the range for more uniform shapes, e.g. (60, 70).

    Shape colour lightness (light mode)
        fg_l_range = (28, 62)
        Darker shapes on a light background.  Try (20, 50) for more contrast.

    Saturation clamping
        sat = max(40, min(95, base_s + rng.uniform(-15, 15)))
        40 = minimum saturation (never fully grey).
        95 = maximum saturation (never fully blown-out).
        Widen the uniform range for more varied saturation across shapes.

    Background saturation
        rng.uniform(20, 40)  inside the hsla() bg call.
        Low saturation keeps the background neutral.  Raise the upper bound
        (e.g. 60) for a more colourful tinted background.

    Accent hue offset
        (base_h + 180 + rng.uniform(-20, 20))
        180° = direct complement.  ±20 adds variation so the accent is
        near-complementary rather than exact.  Set to 0 to always use the
        exact complement.

    Accent saturation/lightness
        rng.uniform(70, 100)  saturation  — keeps it vivid
        rng.uniform(55, 72)   lightness   — bright but not white-washed
        Raise saturation min for even more vivid accents.

    stdlib references
        random.Random.choice   https://docs.python.org/3/library/random.html#random.Random.choice
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
        colorsys               https://docs.python.org/3/library/colorsys.html
    """
    base_h, base_s, base_l = hex_to_hsl(hex_color)

    if dark_mode is None:
        dark_mode = base_l < 50

    scheme = rng.choice(
        ["analogous", "triadic", "split_complementary", "complementary"]
    )
    if scheme == "analogous":
        hues = [base_h + d for d in [-30, -15, 0, 15, 30]]
    elif scheme == "triadic":
        hues = [base_h, base_h + 120, base_h + 240]
    elif scheme == "complementary":
        hues = [base_h, base_h + 10, base_h + 180, base_h + 170]
    else:  # split_complementary
        hues = [base_h, base_h + 150, base_h + 210]

    hues = [h % 360 for h in hues]

    if dark_mode:
        bg_l = rng.uniform(5, 14)  # ← tune: dark background lightness
        fg_l_range = (50, 82)  # ← tune: shape lightness on dark bg
    else:
        bg_l = rng.uniform(88, 97)  # ← tune: light background lightness
        fg_l_range = (28, 62)  # ← tune: shape lightness on light bg

    sat = max(40, min(95, base_s + rng.uniform(-15, 15)))  # ← tune: saturation bounds
    colors = [hsla(h, sat, rng.uniform(*fg_l_range)) for h in hues]

    bg = hsla(base_h, rng.uniform(20, 40), bg_l)  # ← tune: bg saturation range (20,40)

    accent_h = (
        base_h + 180 + rng.uniform(-20, 20)
    ) % 360  # ← tune: complement offset ±20
    accent = hsla(accent_h, rng.uniform(70, 100), rng.uniform(55, 72))

    return bg, colors, accent, dark_mode


def palette_from_matugen(
    hex_colors: list,
    rng: random.Random,
    surface: str | None = None,
    accent: str | None = None,
    dark_mode: bool | None = None,
):
    """
    Assemble a wallpaper palette directly from Material You colour tokens.

    The plugin passes six shape tokens from DankMaterialShell's Theme object
    in this fixed order, plus surface and accent as separate parameters:
        index 0  primary              Main brand colour (e.g. blue family)
        index 1  secondary            Second accent (e.g. teal/green family)
        index 2  tertiary             Third accent (e.g. orange/rose family)
        index 3  primaryContainer     Subtle container for primary elements
        index 4  secondaryContainer   Subtle container for secondary elements
        index 5  tertiaryContainer    Subtle container for tertiary elements
    surface : Theme.surface — already the correct tone for dark/light mode;
              used directly as the background without any lightness manipulation.
    accent  : Theme.inversePrimary — primary in the opposite theme, naturally
              complementary; used as the highlight/sparkle colour.

    Because these tokens are already harmonious (generated by Matugen from the
    current wallpaper's seed colour), no additional colour-theory maths is
    needed — they are used as-is for SVG fills.  SVG accepts #rrggbb hex
    natively so no conversion is required.

    Returns
    -------
    (bg, colors, accent, dark_mode)  — same contract as palette_from_color.

    TUNING GUIDE
    ------------
    Background colour
        bg = surface
        surface is the Material You token that defines the canvas colour —
        very dark in dark mode, near-white in light mode.  It's used directly
        so the wallpaper background always matches the shell's exact tone.
        Fallback when surface is None: "#141218" (dark) or "#FEFBFF" (light).
        ← tune: replace fallbacks with a custom hex if desired.

    Shape palette
        colors = list(hex_colors)
        All six tokens are passed to the style functions.  Style functions
        pick from this list randomly, so adding more colours increases variety.
        Remove indices you don't want; just ensure at least 2 remain.
        With three hue families × two intensities (vivid + container) the
        shapes naturally form cohesive clusters while staying varied.

    Accent colour
        acc = accent  (inversePrimary)
        inversePrimary is the primary colour rendered in the opposite theme —
        by Material You spec it is always high-contrast against the primary
        family, making it an ideal sparkle/highlight.
        Fallback: hex_colors[0] (primary) if accent is None.
        ← tune: swap to hex_colors[2] (tertiary) for a more exotic accent.

    dark_mode detection
        Uses surface lightness when available (most reliable M3 indicator).
        Falls back to primary lightness.  Threshold of 50 is reliable for
        Material You themes but can be adjusted for custom palettes.

    stdlib references
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
        colorsys               https://docs.python.org/3/library/colorsys.html
    """
    if dark_mode is None:
        if surface:
            _, _, surf_l = hex_to_hsl(surface)
            dark_mode = surf_l < 50
        else:
            _, _, ref_l = hex_to_hsl(hex_colors[0])
            dark_mode = ref_l < 50

    # surface is already the right tone — use it as-is for the background
    bg = (
        surface if surface else ("#141218" if dark_mode else "#FEFBFF")
    )  # ← tune: fallback bg

    # Shape palette: hex colours are used directly — SVG accepts #rrggbb natively
    colors = list(hex_colors)

    # inversePrimary is naturally complementary by M3 design — ideal as accent
    acc = (
        accent if accent else hex_colors[0]
    )  # ← tune: fallback to primary if no accent

    return bg, colors, acc, dark_mode


# ── SVG builder ────────────────────────────────────────────────────────────────


class SVGBuilder:
    """
    Minimal SVG document builder.

    Accumulates two lists of raw XML strings:
        defs     — content of the <defs> block (gradients, filters).
        elements — content of the <svg> body (shapes, paths, lines).

    After all style functions have added their elements, render() assembles
    them into a complete, valid SVG document string.

    IDs
    ---
    uid(prefix) returns a unique string ID on every call so that multiple
    filters/gradients never share an id attribute.  SVG requires unique IDs
    within a document.

    SVG specification reference:
        https://www.w3.org/TR/SVG11/
    """

    def __init__(self, width, height):
        self.w = width
        self.h = height
        self.defs = []
        self.elements = []
        self._id = 0

    def uid(self, prefix="e"):
        """Return a document-unique ID string, e.g. 'blur3' or 'grad7'."""
        self._id += 1
        return f"{prefix}{self._id}"

    def add_def(self, xml):
        """Append raw XML to the <defs> section (gradients, filters, etc.)."""
        self.defs.append(xml)

    def add(self, xml):
        """Append a raw SVG element string to the document body."""
        self.elements.append(xml)

    def linear_gradient(self, id_, stops, x1=0, y1=0, x2=1, y2=1):
        """
        Add a linearGradient to <defs>.

        Parameters
        ----------
        id_   : str   — unique id referenced by fill="url(#id_)"
        stops : list  — list of (offset, color, opacity) triples
                        offset is a CSS percentage string, e.g. "0%" or "100%"
        x1,y1,x2,y2  — gradient vector in objectBoundingBox coordinates
                        (0,0)→(1,1) = top-left to bottom-right diagonal
                        (0,0)→(1,0) = left to right horizontal
                        (0,0)→(0,1) = top to bottom vertical

        SVG spec: https://www.w3.org/TR/SVG11/pservers.html#LinearGradientElement
        """
        s = "".join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{a}"/>'
            for o, c, a in stops
        )
        self.add_def(
            f'<linearGradient id="{id_}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'gradientUnits="objectBoundingBox">{s}</linearGradient>'
        )

    def blur_filter(self, id_, std):
        """
        Add a Gaussian blur SVG filter to <defs>.

        Parameters
        ----------
        id_  : str   — unique id referenced by filter="url(#id_)"
        std  : float — blur radius in pixels (stdDeviation).
                       Higher values = softer / more diffuse.
                       Typical range: 4 (subtle glow) – 130 (nebula-scale blur).

        The filter region is expanded to ±50% on each side so blurred shapes
        that extend near the canvas edge do not get clipped.

        SVG spec: https://www.w3.org/TR/SVG11/filters.html#feGaussianBlurElement
        """
        self.add_def(
            f'<filter id="{id_}" x="-50%" y="-50%" width="200%" height="200%">'
            f'<feGaussianBlur stdDeviation="{std}"/></filter>'
        )

    def render(self):
        """Return the complete SVG document as a UTF-8 string."""
        defs_xml = "<defs>" + "".join(self.defs) + "</defs>" if self.defs else ""
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">\n'
            f"{defs_xml}\n{''.join(self.elements)}\n</svg>"
        )


# ── Style functions ────────────────────────────────────────────────────────────
#
# Each style receives:
#   svg    : SVGBuilder  — call svg.add() / svg.add_def() to emit elements
#   rng    : random.Random — seeded RNG; always use this, never random.random()
#   bg     : str  — background fill colour string (hsla or hex)
#   colors : list[str] — shape fill colours (hsla or hex)
#   accent : str  — vivid highlight colour string (hsla or hex)
#
# All coordinates are in pixels.  svg.w and svg.h give the canvas dimensions.
# math.tau == 2π  (https://docs.python.org/3/library/math.html#math.tau)
# ──────────────────────────────────────────────────────────────────────────────


def style_geometric(svg, rng, bg, colors, accent):
    """
    Geometric — overlapping polygons on a fine grid of small shapes.

    Layers (bottom to top)
    ----------------------
    1. Solid background rectangle.
    2. Large semi-transparent polygons (3–8 sides) scattered across the canvas.
    3. Grid of small shapes (rect, triangle, diamond, circle) at ~55 % density.
    4. Faint grid lines using the accent colour.
    5. Small vivid accent dots.

    TUNING GUIDE
    ------------
    Large background polygons
        Count:    rng.randint(4, 7)          ← number of large polygons
        Sides:    rng.randint(3, 8)          ← 3=triangle … 8=octagon
        Radius:   rng.uniform(0.15, 0.45)   ← fraction of min(width, height)
        Jitter:   rng.uniform(0.7, 1.3)     ← vertex radius variation;
                                               1.0 = perfect regular polygon
        Opacity:  rng.uniform(0.07, 0.20)   ← raise for more vivid overlays

    Grid
        Cell size:    rng.choice([40, 60, 80])  ← pixel size per cell;
                                                   smaller = denser grid
        Fill density: rng.random() > 0.45       ← ~55 % of cells filled;
                                                   lower threshold = denser
        Shape scale:  rng.uniform(0.3, 0.85)   ← fraction of cell size
        Opacity:      rng.uniform(0.15, 0.55)

    Grid lines (accent)
        Opacity:      0.12      ← hardcoded; raise for a visible grid overlay
        Stroke width: 0.4 px    ← raise for bolder lines

    Accent dots
        Count:   rng.randint(3, 6)
        Radius:  rng.uniform(2, 8)   ← px; raise for larger dots
        Opacity: rng.uniform(0.4, 0.9)

    stdlib references
        random.Random.randint  https://docs.python.org/3/library/random.html#random.Random.randint
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
        random.Random.choice   https://docs.python.org/3/library/random.html#random.Random.choice
        math.tau               https://docs.python.org/3/library/math.html#math.tau
        math.cos / math.sin    https://docs.python.org/3/library/math.html#math.cos
    """
    W, H = svg.w, svg.h
    svg.add(f'<rect width="{W}" height="{H}" fill="{bg}"/>')

    # ── Large background polygons ─────────────────────────────────────────────
    for _ in range(rng.randint(4, 7)):  # ← tune: polygon count
        color = rng.choice(colors)
        n = rng.randint(3, 8)  # ← tune: vertex count
        cx = rng.uniform(-0.1, 1.1) * W
        cy = rng.uniform(-0.1, 1.1) * H
        r = rng.uniform(0.15, 0.45) * min(W, H)  # ← tune: polygon size
        ao = rng.uniform(0, math.tau)
        pts = []
        for i in range(n):
            a = ao + math.tau * i / n
            jit = rng.uniform(0.7, 1.3)  # ← tune: vertex jitter
            pts.append((cx + math.cos(a) * r * jit, cy + math.sin(a) * r * jit))
        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        svg.add(
            f'<polygon points="{pts_str}" fill="{color}" '
            f'opacity="{rng.uniform(0.07, 0.20):.3f}"/>'  # ← tune: opacity range
        )

    # ── Fine grid of small shapes ─────────────────────────────────────────────
    cell = rng.choice([40, 60, 80])  # ← tune: grid cell size (px)
    for row in range(H // cell + 2):
        for col in range(W // cell + 2):
            if rng.random() > 0.45:  # ← tune: density (0.45 → ~55 % filled)
                continue
            x = col * cell - cell // 2
            y = row * cell - cell // 2
            color = rng.choice(colors)
            op = rng.uniform(0.15, 0.55)  # ← tune: shape opacity range
            shape = rng.choice(["rect", "triangle", "diamond", "circle"])
            cx2, cy2 = x + cell / 2, y + cell / 2

            if shape == "rect":
                s = rng.uniform(0.3, 0.85) * cell  # ← tune: rect size fraction
                svg.add(
                    f'<rect x="{cx2 - s / 2:.1f}" y="{cy2 - s / 2:.1f}" '
                    f'width="{s:.1f}" height="{s:.1f}" fill="{color}" '
                    f'opacity="{op:.3f}" '
                    f'transform="rotate({rng.uniform(0, 45):.1f},{cx2:.1f},{cy2:.1f})"/>'
                )
            elif shape == "triangle":
                h2 = cell * 0.5 * rng.uniform(0.5, 0.9)
                pts = (
                    f"{cx2:.1f},{cy2 - h2:.1f} "
                    f"{cx2 - h2:.1f},{cy2 + h2:.1f} "
                    f"{cx2 + h2:.1f},{cy2 + h2:.1f}"
                )
                svg.add(f'<polygon points="{pts}" fill="{color}" opacity="{op:.3f}"/>')
            elif shape == "diamond":
                s = rng.uniform(0.3, 0.75) * cell
                pts = (
                    f"{cx2:.1f},{cy2 - s:.1f} {cx2 + s:.1f},{cy2:.1f} "
                    f"{cx2:.1f},{cy2 + s:.1f} {cx2 - s:.1f},{cy2:.1f}"
                )
                svg.add(f'<polygon points="{pts}" fill="{color}" opacity="{op:.3f}"/>')
            else:  # circle
                r2 = rng.uniform(0.15, 0.4) * cell
                svg.add(
                    f'<circle cx="{cx2:.1f}" cy="{cy2:.1f}" r="{r2:.1f}" '
                    f'fill="{color}" opacity="{op:.3f}"/>'
                )

    # ── Faint grid lines ──────────────────────────────────────────────────────
    for x in range(0, W + cell, cell):
        svg.add(
            f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" '
            f'stroke="{accent}" stroke-width="0.4" opacity="0.12"/>'
        )  # ← tune: opacity, width
    for y in range(0, H + cell, cell):
        svg.add(
            f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" '
            f'stroke="{accent}" stroke-width="0.4" opacity="0.12"/>'
        )

    # ── Accent dots ───────────────────────────────────────────────────────────
    for _ in range(rng.randint(3, 6)):  # ← tune: dot count
        svg.add(
            f'<circle cx="{rng.uniform(0, W):.1f}" cy="{rng.uniform(0, H):.1f}" '
            f'r="{rng.uniform(2, 8):.1f}" fill="{accent}" '  # ← tune: dot radius
            f'opacity="{rng.uniform(0.4, 0.9):.2f}"/>'  # ← tune: dot opacity
        )


def blob_path(cx, cy, r, rng, roughness=0.3, n=8):
    """
    Generate an SVG path string for an organic blob shape.

    The blob is constructed from n points evenly distributed around a circle
    of radius r, each perturbed radially by ±roughness.  The points are
    connected with cubic Bézier curves (the C command) with control points
    derived from the neighbouring points to keep the curve smooth.

    Parameters
    ----------
    cx, cy    : float — centre of the blob in canvas coordinates
    r         : float — nominal radius in pixels
    rng       : random.Random — seeded RNG for reproducibility
    roughness : float — radial jitter fraction (0.0 = smooth circle,
                        0.5 = very irregular, >1.0 starts self-intersecting)
                        ← tune: default 0.3
    n         : int   — number of control points (more = smoother outline,
                        heavier path string)
                        ← tune: default 8; try 6 (spikier) or 12 (rounder)

    Bézier tension
        cp1x = x + (nx - px) * 0.3
        The factor 0.3 controls how far the control points reach toward their
        neighbours.  Lower = tighter corners, higher = looser/bubblier curves.
        ← tune: change 0.3 to 0.1–0.5

    stdlib references
        math.tau / math.cos / math.sin  https://docs.python.org/3/library/math.html
        random.Random.uniform           https://docs.python.org/3/library/random.html#random.Random.uniform
    """
    pts = []
    for i in range(n):
        a = math.tau * i / n
        rad = r * rng.uniform(1 - roughness, 1 + roughness)
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))

    d = []
    for i, (x, y) in enumerate(pts):
        nx, ny = pts[(i + 1) % n]
        px, py = pts[(i - 1) % n]
        cp1x = x + (nx - px) * 0.3  # ← tune: Bézier tension (0.3)
        cp1y = y + (ny - py) * 0.3
        n2x, n2y = pts[(i + 2) % n]
        if i == 0:
            d.append(f"M {x:.1f} {y:.1f}")
        d.append(
            f"C {cp1x:.1f} {cp1y:.1f} "
            f"{nx - (n2x - x) * 0.3:.1f} {ny - (n2y - y) * 0.3:.1f} "
            f"{nx:.1f} {ny:.1f}"
        )
    d.append("Z")
    return " ".join(d)


def style_organic(svg, rng, bg, colors, accent):
    """
    Organic — layered soft blobs with Gaussian blur, accent particles, curves.

    Layers (bottom to top)
    ----------------------
    1. Solid background rectangle.
    2. Large blurred blobs — heavily softened for an atmospheric backdrop.
    3. Small sharp blobs — unblurred, semi-transparent for mid-ground detail.
    4. Accent particle dots — fine scatter across the canvas.
    5. Flowing quadratic Bézier curves — loose strokes for texture.

    TUNING GUIDE
    ------------
    Large blurred blobs
        Count:      rng.randint(5, 9)           ← number of backdrop blobs
        Blur std:   rng.uniform(30, 80)         ← px; raise for cloudier blobs
        Size:       rng.uniform(0.12, 0.35)     ← fraction of min(W,H)
        Roughness:  0.25 (passed to blob_path)  ← see blob_path docstring
        Opacity:    rng.uniform(0.25, 0.65)     ← raise for more vivid blobs

    Small sharp blobs (mid-ground)
        Count:      rng.randint(6, 12)
        Size:       rng.uniform(0.04, 0.15)     ← fraction of min(W,H)
        Roughness:  0.35
        Opacity:    rng.uniform(0.08, 0.30)     ← intentionally subtle

    Accent particle dots
        Count:      rng.randint(20, 50)         ← raise for a denser field
        Radius:     rng.uniform(1, 5)           ← px
        Opacity:    rng.uniform(0.2, 0.7)

    Flowing curves
        Count:          rng.randint(3, 7)
        Control points: rng.randint(4, 8)       ← path complexity
        Stroke width:   rng.uniform(1, 4)       ← px
        Opacity:        rng.uniform(0.15, 0.45)

    stdlib references
        random.Random.randint  https://docs.python.org/3/library/random.html#random.Random.randint
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
    """
    W, H = svg.w, svg.h
    svg.add(f'<rect width="{W}" height="{H}" fill="{bg}"/>')

    # ── Large blurred backdrop blobs ──────────────────────────────────────────
    for _ in range(rng.randint(5, 9)):  # ← tune: blob count
        fid = svg.uid("blur")
        svg.blur_filter(fid, rng.uniform(30, 80))  # ← tune: blur range (px)
        color = rng.choice(colors)
        path = blob_path(
            rng.uniform(0.1, 0.9) * W,
            rng.uniform(0.1, 0.9) * H,
            rng.uniform(0.12, 0.35) * min(W, H),  # ← tune: blob size fraction
            rng,
            roughness=0.25,  # ← tune: blob roughness
        )
        svg.add(
            f'<path d="{path}" fill="{color}" '
            f'opacity="{rng.uniform(0.25, 0.65):.3f}" '  # ← tune: opacity range
            f'filter="url(#{fid})"/>'
        )

    # ── Small sharp mid-ground blobs ──────────────────────────────────────────
    for _ in range(rng.randint(6, 12)):  # ← tune: small blob count
        color = rng.choice(colors)
        path = blob_path(
            rng.uniform(-0.05, 1.05) * W,
            rng.uniform(-0.05, 1.05) * H,
            rng.uniform(0.04, 0.15) * min(W, H),  # ← tune: size fraction
            rng,
            roughness=0.35,  # ← tune: roughness
        )
        svg.add(
            f'<path d="{path}" fill="{color}" '
            f'opacity="{rng.uniform(0.08, 0.30):.3f}"/>'  # ← tune: opacity range
        )

    # ── Accent particle scatter ───────────────────────────────────────────────
    for _ in range(rng.randint(20, 50)):  # ← tune: particle count
        svg.add(
            f'<circle cx="{rng.uniform(0, W):.1f}" cy="{rng.uniform(0, H):.1f}" '
            f'r="{rng.uniform(1, 5):.1f}" fill="{accent}" '  # ← tune: radius range
            f'opacity="{rng.uniform(0.2, 0.7):.2f}"/>'  # ← tune: opacity range
        )

    # ── Flowing quadratic Bézier curves ──────────────────────────────────────
    for _ in range(rng.randint(3, 7)):  # ← tune: curve count
        color = rng.choice(colors)
        pts = [
            (rng.uniform(0, W), rng.uniform(0, H)) for _ in range(rng.randint(4, 8))
        ]  # ← tune: control points (4,8)
        d = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
        for i in range(1, len(pts) - 1):
            mx = (pts[i][0] + pts[i + 1][0]) / 2
            my = (pts[i][1] + pts[i + 1][1]) / 2
            d.append(f"Q {pts[i][0]:.1f} {pts[i][1]:.1f} {mx:.1f} {my:.1f}")
        svg.add(
            f'<path d="{" ".join(d)}" fill="none" stroke="{color}" '
            f'stroke-width="{rng.uniform(1, 4):.1f}" '  # ← tune: stroke width
            f'opacity="{rng.uniform(0.15, 0.45):.3f}"/>'  # ← tune: opacity range
        )


def style_circuit(svg, rng, bg, colors, accent):
    """
    Circuit — PCB-style trace network with decorated node points.

    Algorithm
    ---------
    1. A regular grid is laid over the canvas; each intersection becomes a
       node with 40 % probability.
    2. Adjacent nodes are connected by horizontal/vertical trace lines.
    3. Each node is drawn as one of four decorations (dot, ring, cross, square).
    4. A random subset of traces is re-drawn with a glow (blur) effect.

    TUNING GUIDE
    ------------
    Grid
        Cell size: rng.randint(40, 70)    ← px; smaller = denser, finer traces
                                            Try 20–30 for microchip density.

    Node density
        rng.random() < 0.4               ← 40 % of intersections become nodes.
                                            Raise to 0.6 for a busier board.

    Connections per node
        rng.randint(1, 3)                ← each node connects to 1–3 neighbours.
                                            Raise upper bound for more branches.

    Trace appearance
        Stroke width:  rng.uniform(1, 2.5)   ← px
        Opacity:       rng.uniform(0.3, 0.7)

    Node decorations
        Radius:  rng.uniform(3, 8)  ← px; raise for larger node markers.
        Opacity: rng.uniform(0.5, 1.0)  ← nodes are intentionally brighter.
        Kinds:   ["dot", "ring", "cross", "square"]  ← remove unwanted styles.

    Glow segments
        Count:     rng.randint(3, 8)   ← highlighted trace segments.
        Blur std:  4 px (hardcoded)    ← raise for a wider glow halo.
        Stroke:    3 px (hardcoded)    ← raise for bolder glow traces.
        Opacity:   0.6 (hardcoded)

    stdlib references
        random.Random.randint  https://docs.python.org/3/library/random.html#random.Random.randint
        random.Random.random   https://docs.python.org/3/library/random.html#random.Random.random
        random.Random.sample   https://docs.python.org/3/library/random.html#random.Random.sample
        random.Random.choice   https://docs.python.org/3/library/random.html#random.Random.choice
    """
    W, H = svg.w, svg.h
    svg.add(f'<rect width="{W}" height="{H}" fill="{bg}"/>')

    grid = rng.randint(40, 70)  # ← tune: grid cell size (px)
    cols = W // grid + 1
    rows = H // grid + 1
    nodes = {
        (c, r): True
        for r in range(rows)
        for c in range(cols)
        if rng.random() < 0.4  # ← tune: node density (0.4 = 40 %)
    }

    line_color = rng.choice(colors)
    directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    drawn: set = set()

    for col, row in nodes:
        for dc, dr in rng.sample(
            directions, rng.randint(1, 3)
        ):  # ← tune: connections (1,3)
            nc, nr = col + dc, row + dr
            if (nc, nr) in nodes:
                seg = tuple(sorted([(col, row), (nc, nr)]))
                if seg not in drawn:
                    drawn.add(seg)
                    x1, y1 = col * grid + grid // 2, row * grid + grid // 2
                    x2, y2 = nc * grid + grid // 2, nr * grid + grid // 2
                    svg.add(
                        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                        f'stroke="{line_color}" '
                        f'stroke-width="{rng.uniform(1, 2.5):.1f}" '  # ← tune: trace width
                        f'opacity="{rng.uniform(0.3, 0.7):.3f}"/>'  # ← tune: trace opacity
                    )

    for col, row in nodes:
        cx, cy = col * grid + grid // 2, row * grid + grid // 2
        kind = rng.choice(["dot", "ring", "cross", "square"])  # ← tune: remove unwanted
        op = rng.uniform(0.5, 1.0)  # ← tune: node opacity
        r = rng.uniform(3, 8)  # ← tune: node radius (px)

        if kind == "dot":
            svg.add(
                f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" '
                f'fill="{accent}" opacity="{op:.2f}"/>'
            )
        elif kind == "ring":
            svg.add(
                f'<circle cx="{cx}" cy="{cy}" r="{r:.1f}" fill="none" '
                f'stroke="{accent}" stroke-width="1.5" opacity="{op:.2f}"/>'
            )
            svg.add(
                f'<circle cx="{cx}" cy="{cy}" r="{r * 0.35:.1f}" '
                f'fill="{accent}" opacity="{op:.2f}"/>'
            )
        elif kind == "cross":
            svg.add(
                f'<line x1="{cx - r:.1f}" y1="{cy}" x2="{cx + r:.1f}" y2="{cy}" '
                f'stroke="{accent}" stroke-width="1.5" opacity="{op:.2f}"/>'
            )
            svg.add(
                f'<line x1="{cx}" y1="{cy - r:.1f}" x2="{cx}" y2="{cy + r:.1f}" '
                f'stroke="{accent}" stroke-width="1.5" opacity="{op:.2f}"/>'
            )
        else:  # square
            s = r * 1.4
            svg.add(
                f'<rect x="{cx - s / 2:.1f}" y="{cy - s / 2:.1f}" '
                f'width="{s:.1f}" height="{s:.1f}" fill="none" '
                f'stroke="{accent}" stroke-width="1.5" opacity="{op:.2f}"/>'
            )

    # ── Glow highlights on random trace segments ──────────────────────────────
    segs = list(drawn)
    for _ in range(min(rng.randint(3, 8), len(segs))):  # ← tune: glow segment count
        fid = svg.uid("glow")
        svg.blur_filter(fid, 4)  # ← tune: glow blur stdDeviation (px)
        (c1, r1), (c2, r2) = rng.choice(segs)
        x1, y1 = c1 * grid + grid // 2, r1 * grid + grid // 2
        x2, y2 = c2 * grid + grid // 2, r2 * grid + grid // 2
        svg.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{accent}" stroke-width="3" opacity="0.6" '  # ← tune: glow stroke, opacity
            f'filter="url(#{fid})"/>'
        )


def style_cosmos(svg, rng, bg, colors, accent):
    """
    Cosmos — deep-space scene with nebulae, star field, and shooting stars.

    NOTE: This style always produces a dark background regardless of the
    --mode flag.  Stars and nebulae require a dark sky to be visible.
    If you want a light-mode variant, replace dark_bg with the bg argument.

    Layers (bottom to top)
    ----------------------
    1. Deep-space background rectangle (very dark blue-to-indigo).
    2. Nebula clouds — large, heavily blurred, coloured ellipses.
    3. Background star field — hundreds of tiny circles.
    4. Bright stars — small circles with a soft glow halo.
    5. Shooting stars — fading linear gradient streaks.

    TUNING GUIDE
    ------------
    Sky colour
        Hue:        rng.uniform(220, 270)   ← blue (220°) to indigo (270°).
                                               Try (260, 300) for a purple sky
                                               or (170, 220) for a teal nebula.
        Saturation: rng.uniform(30, 60)     ← raise for a more vivid sky.
        Lightness:  rng.uniform(3, 10)      ← raise to (10, 20) for "dusk" feel.

    Nebula clouds
        Count:   rng.randint(3, 6)
        Blur:    rng.uniform(60, 130)      ← px stdDeviation; raise for bigger halos
        Width:   rng.uniform(0.15, 0.5)   ← fraction of canvas width
        Height:  rng.uniform(0.1, 0.4)    ← fraction of canvas height
        Opacity: rng.uniform(0.2, 0.55)

    Background star field
        Count:    rng.randint(300, 700)    ← raise for a milky-way density field
        Radius:   rng.uniform(0.3, 2.2)   ← px; keep small for distant stars
        Opacity:  rng.uniform(0.5, 1.0)
        Colours:  ["#ffffff","#fffde7","#e3f2fd","#fce4ec", accent]
                  ← add or remove star tint colours freely

    Bright stars (with glow)
        Count:      rng.randint(10, 25)
        Radius:     rng.uniform(2, 5)      ← px; the glow halo is 2× this
        Glow blur:  rng.uniform(3, 10)     ← px; raise for a larger diffraction spike

    Shooting stars
        Count:   rng.randint(2, 5)
        Length:  rng.uniform(80, 200)      ← px; raise for longer streaks
        Angle:   rng.uniform(π/6, π/3)    ← 30°–60° from horizontal;
                                              narrower range = more consistent direction

    stdlib references
        random.Random.randint  https://docs.python.org/3/library/random.html#random.Random.randint
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
        math.pi                https://docs.python.org/3/library/math.html#math.pi
        math.cos / math.sin    https://docs.python.org/3/library/math.html#math.cos
    """
    W, H = svg.w, svg.h

    # Always dark — stars are invisible on a light background
    dark_bg = (
        f"hsl({rng.uniform(220, 270):.0f},"  # ← tune: sky hue range (degrees)
        f"{rng.uniform(30, 60):.0f}%,"  # ← tune: sky saturation range
        f"{rng.uniform(3, 10):.0f}%)"  # ← tune: sky lightness range
    )
    svg.add(f'<rect width="{W}" height="{H}" fill="{dark_bg}"/>')

    # ── Nebula clouds ─────────────────────────────────────────────────────────
    for _ in range(rng.randint(3, 6)):  # ← tune: nebula count
        fid = svg.uid("neb")
        svg.blur_filter(fid, rng.uniform(60, 130))  # ← tune: blur range
        color = rng.choice(colors)
        cx = rng.uniform(0.1, 0.9) * W
        cy = rng.uniform(0.1, 0.9) * H
        rx = rng.uniform(0.15, 0.5) * W  # ← tune: nebula width fraction
        ry = rng.uniform(0.1, 0.4) * H  # ← tune: nebula height fraction
        angle = rng.uniform(0, 360)
        svg.add(
            f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
            f'fill="{color}" opacity="{rng.uniform(0.2, 0.55):.3f}" '  # ← tune: nebula opacity
            f'filter="url(#{fid})" transform="rotate({angle:.1f},{cx:.1f},{cy:.1f})"/>'
        )

    # ── Background star field ─────────────────────────────────────────────────
    star_colors = [
        "#ffffff",
        "#fffde7",
        "#e3f2fd",
        "#fce4ec",
        accent,
    ]  # ← tune: tint colours
    for _ in range(rng.randint(300, 700)):  # ← tune: star count
        svg.add(
            f'<circle cx="{rng.uniform(0, W):.1f}" cy="{rng.uniform(0, H):.1f}" '
            f'r="{rng.uniform(0.3, 2.2):.1f}" '  # ← tune: star radius range
            f'fill="{rng.choice(star_colors)}" '
            f'opacity="{rng.uniform(0.5, 1.0):.2f}"/>'  # ← tune: star opacity range
        )

    # ── Bright stars with glow halos ─────────────────────────────────────────
    for _ in range(rng.randint(10, 25)):  # ← tune: bright star count
        fid = svg.uid("star")
        svg.blur_filter(fid, rng.uniform(3, 10))  # ← tune: glow blur range
        sx = rng.uniform(0.05, 0.95) * W
        sy = rng.uniform(0.05, 0.95) * H
        sr = rng.uniform(2, 5)  # ← tune: bright star radius
        svg.add(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr * 2:.1f}" '
            f'fill="white" opacity="0.3" filter="url(#{fid})"/>'
        )
        svg.add(
            f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="{sr:.1f}" '
            f'fill="white" opacity="0.9"/>'
        )

    # ── Shooting star streaks ─────────────────────────────────────────────────
    for _ in range(rng.randint(2, 5)):  # ← tune: streak count
        x1 = rng.uniform(0, W)
        y1 = rng.uniform(0, H * 0.6)  # ← tune: vertical spawn zone
        length = rng.uniform(80, 200)  # ← tune: streak length (px)
        angle_r = rng.uniform(math.pi / 6, math.pi / 3)  # ← tune: angle range (30°–60°)
        x2 = x1 + math.cos(angle_r) * length
        y2 = y1 + math.sin(angle_r) * length
        gid = svg.uid("streak")
        svg.linear_gradient(
            gid, [("0%", "white", 0.8), ("100%", "white", 0)], 0, 0, 1, 0
        )
        svg.add(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="url(#{gid})" '
            f'stroke-width="{rng.uniform(0.5, 1.5):.2f}" opacity="0.8"/>'  # ← tune: width, opacity
        )


def style_gradient_waves(svg, rng, bg, colors, accent):
    """
    Gradient Waves — layered sinusoidal bands with an accent glow.

    Each wave is a filled SVG path that follows a sine curve across the canvas,
    producing a stacked beach-wave / aurora effect.  Waves are layered bottom
    to top and cycle through the colour palette.

    Layers (bottom to top)
    ----------------------
    1. Solid background rectangle.
    2. n_waves sinusoidal filled bands.
    3. A single softly glowing horizontal ellipse at mid-height (accent).

    TUNING GUIDE
    ------------
    Wave count
        n_waves = rng.randint(6, 14)        ← more waves = busier, more layered

    Wave amplitude
        rng.uniform(0.03, 0.12) * H         ← vertical swing as fraction of height.
                                               0.03 = gentle ripple, 0.12 = bold wave.
                                               Raise upper bound for dramatic crests.

    Wave frequency
        rng.uniform(1, 3)                   ← complete cycles across the canvas.
                                               1 = one full S-curve, 3 = three crests.
                                               Raise for tighter, more turbulent waves.

    Wave phase
        rng.uniform(0, math.tau)            ← random horizontal offset per wave
                                               so waves don't all align at x=0.

    Wave baseline spacing
        lerp(0.15, 0.92, t) * H            ← waves spread from 15 % to 92 % height.
                                               Adjust 0.15/0.92 to shift or compress
                                               the band region.

    Wave opacity
        rng.uniform(0.35, 0.65)             ← per-wave opacity; waves are additive
                                               so total effect is stronger than any
                                               single value suggests.

    Path sampling step
        step = 4                            ← x-step in pixels for path points.
                                               Lower = smoother curve, heavier SVG.

    Accent glow ellipse
        Width:   W * 0.4    ← 40 % of canvas width; raise for a broader halo.
        Height:  H * 0.08   ← 8 % of canvas height; raise for a taller band.
        Blur:    40 px       ← stdDeviation; raise for a more diffuse glow.
        Opacity: 0.4

    stdlib references
        random.Random.randint  https://docs.python.org/3/library/random.html#random.Random.randint
        random.Random.uniform  https://docs.python.org/3/library/random.html#random.Random.uniform
        math.sin               https://docs.python.org/3/library/math.html#math.sin
        math.tau               https://docs.python.org/3/library/math.html#math.tau
    """
    W, H = svg.w, svg.h
    svg.add(f'<rect width="{W}" height="{H}" fill="{bg}"/>')

    n_waves = rng.randint(6, 14)  # ← tune: wave count
    step = 4  # ← tune: x-sampling step (px)

    for i in range(n_waves):
        t = i / (n_waves - 1)
        color = colors[i % len(colors)]
        amplitude = rng.uniform(0.03, 0.12) * H  # ← tune: wave amplitude fraction
        frequency = rng.uniform(1, 3)  # ← tune: cycles across canvas
        phase = rng.uniform(0, math.tau)  # ← tune: phase offset range
        y_base = lerp(0.15, 0.92, t) * H  # ← tune: vertical span (0.15, 0.92)

        pts = [
            (x, y_base + math.sin(x / W * math.tau * frequency + phase) * amplitude)
            for x in range(0, W + step, step)
        ]

        path_d = f"M 0 {H} L {pts[0][0]:.1f} {pts[0][1]:.1f} "
        for j in range(1, len(pts) - 1):
            mx = (pts[j][0] + pts[j + 1][0]) / 2
            my = (pts[j][1] + pts[j + 1][1]) / 2
            path_d += f"Q {pts[j][0]:.1f} {pts[j][1]:.1f} {mx:.1f} {my:.1f} "
        path_d += f"L {W} {H} Z"

        svg.add(
            f'<path d="{path_d}" fill="{color}" '
            f'opacity="{rng.uniform(0.35, 0.65):.3f}"/>'  # ← tune: wave opacity range
        )

    # ── Accent glow band ──────────────────────────────────────────────────────
    fid = svg.uid("hglow")
    svg.blur_filter(fid, 40)  # ← tune: glow blur (px)
    svg.add(
        f'<ellipse cx="{W / 2:.1f}" cy="{H * 0.5:.1f}" '
        f'rx="{W * 0.4:.1f}" ry="{H * 0.08:.1f}" '  # ← tune: ellipse size fractions
        f'fill="{accent}" opacity="0.4" filter="url(#{fid})"/>'  # ← tune: glow opacity
    )


# ── Style registry ─────────────────────────────────────────────────────────────
# Maps the --style CLI value to its function.
# To add a new style: define style_myname() above, then add it here.

STYLES = {
    "geometric": style_geometric,
    "organic": style_organic,
    "circuit": style_circuit,
    "cosmos": style_cosmos,
    "gradient_waves": style_gradient_waves,
}


# ── Top-level generate() ───────────────────────────────────────────────────────


def generate(
    width=1920,
    height=1080,
    style="all",
    seed=None,
    color="#6750A4",
    colors=None,
    surface=None,
    accent=None,
    mode="auto",
    output=None,
):
    """
    Generate one SVG wallpaper and write it to disk.

    Parameters
    ----------
    width, height : int
        Output dimensions in pixels.  Should match the display resolution.
        The plugin reads these from Qt.application.screens[0].

    style : str
        One of the keys in STYLES, or "all" to pick one at random.
        When "all" is used, the seed governs which style is chosen so the
        result is still reproducible for a given seed.

    seed : int or None
        Seed for the random number generator.
        Same seed + same colours → identical output every time.
        None → non-deterministic (different result each run).
        stdlib: https://docs.python.org/3/library/random.html#random.seed

    color : str
        Single hex colour used by palette_from_color (the --colors fallback).

    colors : list[str] or None
        Six Material You hex tokens in this order:
            primary, secondary, tertiary,
            primaryContainer, secondaryContainer, tertiaryContainer.
        When provided (and len >= 2), palette_from_matugen is used instead
        of palette_from_color.

    surface : str or None
        Material You surface colour hex (e.g. "#141218" dark, "#FEFBFF" light).
        Used directly as the background — no lightness manipulation applied.
        None → palette_from_matugen computes a near-black/near-white fallback.

    accent : str or None
        Material You inversePrimary hex.  Used as the highlight/sparkle colour.
        None → palette_from_matugen falls back to colors[0] (primary).

    mode : "auto" | "dark" | "light"
        "auto"  → infer dark/light from the surface or seed colour's lightness.
        "dark"  → always produce a dark background.
        "light" → always produce a light background.
        The plugin passes the current SessionData.isLightMode value.

    output : str or None
        Absolute path for the output SVG file.
        None → ~/Pictures/DankWallpapers/dms_wallpaper_current.svg
               (always overwritten; use --output for named files)

    Returns
    -------
    (output_path: str, chosen_style: str)
        output_path is printed to stdout so the QML process can read it.
    """
    rng = random.Random(
        seed
    )  # https://docs.python.org/3/library/random.html#random.Random

    if style == "all":
        style = rng.choice(list(STYLES.keys()))

    dark_override = (
        True if mode == "dark" else False if mode == "light" else None  # auto
    )

    if colors and len(colors) >= 2:
        bg, palette, fill_accent, _ = palette_from_matugen(
            colors, rng, surface=surface, accent=accent, dark_mode=dark_override
        )
    else:
        bg, palette, fill_accent, _ = palette_from_color(color, rng, dark_override)

    svg = SVGBuilder(width, height)
    STYLES[style](svg, rng, bg, palette, fill_accent)

    if output is None:
        output = str(default_output_dir() / "dms_wallpaper_current.svg")

    # pathlib.Path.write_text — https://docs.python.org/3/library/pathlib.html#pathlib.Path.write_text
    Path(output).write_text(svg.render(), encoding="utf-8")
    return output, style


# ── CLI entry point ────────────────────────────────────────────────────────────


def main():
    """
    Parse CLI arguments and call generate().

    The script is designed to be called by VectorWallpaper.qml via
    Quickshell's Process type, but it is also usable interactively.

    On success it prints the output SVG path to stdout (one line) and exits 0.
    On failure it prints a message to stderr and exits non-zero.

    argparse docs: https://docs.python.org/3/library/argparse.html
    """
    parser = argparse.ArgumentParser(
        description="DankMaterialShell Vector Wallpaper Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Single colour, random style:\n"
            '  python3 gen_wallpaper.py --color "#6750A4"\n\n'
            "  # Full Material You palette, forced dark, fixed seed:\n"
            "  python3 gen_wallpaper.py \\\n"
            '      --colors "#6750A4" "#625B71" "#7D5260" "#4F378B" "#4A4458" "#633B48" \\\n'
            '      --surface "#141218" --accent "#D0BCFF" \\\n'
            "      --mode dark --style cosmos --seed 42\n\n"
            "  # Custom output path:\n"
            '  python3 gen_wallpaper.py --color "#B5179E" --output ~/my_wall.svg\n'
        ),
    )
    parser.add_argument(
        "--width", type=int, default=1920, help="Output width in pixels (default: 1920)"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Output height in pixels (default: 1080)",
    )
    parser.add_argument(
        "--style",
        type=str,
        default="all",
        help=f"Visual style: {', '.join(list(STYLES) + ['all'])} "
        f"(default: all — chosen randomly per seed)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="RNG seed for reproducible output (default: random)",
    )
    parser.add_argument(
        "--color",
        type=str,
        default="#6750A4",
        help="Single seed hex colour — used when --colors is absent (default: #6750A4)",
    )
    parser.add_argument(
        "--colors",
        type=str,
        nargs="+",
        default=None,
        help="Six Material You hex tokens in order: "
        "primary secondary tertiary "
        "primaryContainer secondaryContainer tertiaryContainer. "
        "When provided, overrides --color.",
    )
    parser.add_argument(
        "--surface",
        type=str,
        default=None,
        help="Material You surface hex — used directly as background "
        "(e.g. '#141218' dark, '#FEFBFF' light)",
    )
    parser.add_argument(
        "--accent",
        type=str,
        default=None,
        help="Material You inversePrimary hex — used as highlight colour",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="auto",
        choices=["auto", "dark", "light"],
        help="Background theme: auto (detect from colours), "
        "dark, or light (default: auto)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output SVG file path "
        "(default: ~/Pictures/DankWallpapers/dms_wallpaper_current.svg)",
    )
    args = parser.parse_args()

    if args.style not in list(STYLES) + ["all"]:
        print(f"ERROR: unknown style '{args.style}'", file=sys.stderr)
        sys.exit(1)

    out_path, chosen_style = generate(
        width=args.width,
        height=args.height,
        style=args.style,
        seed=args.seed,
        color=args.color,
        colors=args.colors,
        surface=args.surface,
        accent=args.accent,
        mode=args.mode,
        output=args.output,
    )

    # Print path to stdout — VectorWallpaper.qml reads this via SplitParser
    print(out_path)


if __name__ == "__main__":
    main()
