"""OKLCH -> sRGB ramp used to colour one line per year.

The year is an ordered continuous variable, so it gets a ramp rather than
categorical slots. The ramp runs blue -> red the *short* way round the hue
circle (through violet/magenta), never through a neutral midpoint: with ~45
overlapping lines a desaturated middle would drop the mid-1990s straight into
the surface. Lightness and chroma stay inside the method's bands so every step
is a legal mark colour on its own surface.
"""

import math

LIGHT_SURFACE = "#fcfcfb"
DARK_SURFACE = "#1a1a19"

# (L_start, L_end, C_start, C_end) per mode; hue is shared.
MODES = {
    "light": (0.640, 0.520, 0.130, 0.180),
    "dark": (0.660, 0.600, 0.130, 0.185),
}
HUE_START, HUE_END = 258.0, 385.0  # 385 == 25 (red), going through violet


def _oklab_to_linear_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _encode(c):
    c = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return max(0.0, min(1.0, c))


def oklch_to_hex(L, C, H):
    """Convert OKLCH to hex, reducing chroma until the colour fits in sRGB."""
    while True:
        h = math.radians(H)
        rgb = _oklab_to_linear_srgb(L, C * math.cos(h), C * math.sin(h))
        if C <= 0.0005 or all(-1e-4 <= v <= 1 + 1e-4 for v in rgb):
            break
        C -= 0.002
    return "#" + "".join(f"{round(_encode(v) * 255):02x}" for v in rgb)


def relative_luminance(hex_color):
    parts = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = relative_luminance(a), relative_luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def at(t, mode):
    """One hex colour for t in [0, 1] — 0 is the oldest (blue), 1 the newest (red)."""
    l0, l1, c0, c1 = MODES[mode]
    return oklch_to_hex(
        l0 + (l1 - l0) * t,
        c0 + (c1 - c0) * t,
        HUE_START + (HUE_END - HUE_START) * t,
    )


def ramp(positions, mode):
    """Hex colours for a list of positions in [0, 1].

    Callers pass the *year* mapped onto the span, not the row index — the source
    is missing four years, so indexing would silently stretch those gaps.
    """
    return [at(t, mode) for t in positions]


if __name__ == "__main__":
    for mode, surface in (("light", LIGHT_SURFACE), ("dark", DARK_SURFACE)):
        colors = ramp([i / 42 for i in range(43)], mode)
        ratios = [contrast(c, surface) for c in colors]
        worst = min(ratios)
        print(f"{mode:5s} surface={surface}  worst contrast {worst:.2f}:1", end="  ")
        print("PASS" if worst >= 3.0 else "WARN (<3:1 - needs relief channel)")
        for i in (0, 10, 21, 32, 42):
            print(f"    step {i:2d}  {colors[i]}  {ratios[i]:.2f}:1")
