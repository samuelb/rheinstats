#!/usr/bin/env python3
"""Build the Rekingen spaghetti charts.

Primary source are the full-series CSV exports of the BAFU Datenservice
Hydrologie in measurements/ (Abfluss ab 1904, Pegel ab 1964, Wassertemperatur
ab 1969). The hydrodaten.admin.ch cache rhein_rekingen_daily.csv only fills
days the export does not cover — in practice the days since the export date.

One chart per measured parameter, switched by tabs — never two scales on one
plot. Writes two files from one template:
  index.html     standalone page, open it locally
  artifact.html  the same body, without the html/head wrapper
"""

import csv
import datetime as dt
import glob
import json
import math
import statistics as st
from collections import defaultdict

import ramp

CSV_API = "rhein_rekingen_daily.csv"
EXPORT_GLOB = "measurements/*.csv"
# Parameter name in the export -> our param key
EXPORT_PARAMS = {
    "Wassertemperatur": "temperature",
    "Abfluss": "discharge",
    "Pegel": "level",
    "Elektrische Leitfähigkeit": "conductivity",
    "pH-Wert": "ph",
    "Sauerstoff": "oxygen",
    "Sauerstoff-Sättigung": "oxysat",
}
MIN_DAYS = 30    # a year with fewer points than this is a portal artifact, not a line
FULL_DAYS = 360  # below this a year's mean is not comparable, so it stays out of the trend

MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTHS_FULL = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember"]
MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# column, tab label, unit, decimals shown, encoding scale/offset, zero baseline?
# Temperature, discharge and oxygen have a real zero within reach and keep one.
# Water level is an altitude, pH a log scale, saturation lives around 100 % and
# conductivity far above zero — a zero baseline would flatten those, so their
# axes zoom to the data instead. `axis` labels the y axis where the bare unit
# would not (pH has none).
PARAMS = [
    dict(key="temperature", col="temperature_c", label="Temperatur",
         unit="°C", decimals=1, scale=10, offset=0, zero=True),
    dict(key="discharge", col="discharge_m3s", label="Abfluss",
         unit="m³/s", decimals=0, scale=10, offset=0, zero=True),
    dict(key="level", col="waterlevel_m", label="Wasserstand",
         unit="m ü.M.", decimals=2, scale=1000, offset=320, zero=False),
    dict(key="conductivity", col="conductivity_uscm", label="Leitfähigkeit",
         unit="µS/cm", decimals=1, scale=10, offset=250, zero=False),
    dict(key="ph", col="ph", label="pH-Wert",
         unit="", axis="pH-Wert", decimals=2, scale=100, offset=7, zero=False),
    dict(key="oxygen", col="oxygen_mgl", label="Sauerstoff",
         unit="mg/l", decimals=2, scale=100, offset=0, zero=True),
    dict(key="oxysat", col="oxygen_sat_pct", label="Sauerstoff-Sättigung",
         unit="%", decimals=1, scale=10, offset=0, zero=False),
]


def load():
    """-> (years, {param key: {year: [365 values]}}, missing years, newest date)
    on a non-leap grid.

    The Datenservice export is written first and wins; the API cache may only
    fill days the export leaves empty, so a value never silently changes source.
    """
    data = {p["key"]: defaultdict(lambda: [None] * 365) for p in PARAMS}
    latest = None

    def put(key, date, value):
        nonlocal latest
        if latest is None or date > latest:
            latest = date
        if (date.month, date.day) == (2, 29):
            return  # the 365-day grid has no slot for it
        index = sum(MONTH_LENGTHS[: date.month - 1]) + date.day - 1
        if data[key][date.year][index] is None:
            data[key][date.year][index] = value

    for path in sorted(glob.glob(EXPORT_GLOB)):
        with open(path, encoding="cp1252") as fh:
            lines = fh.read().splitlines()
        head = next(i for i, l in enumerate(lines) if l.startswith("Stationsname;"))
        for row in csv.DictReader(lines[head:], delimiter=";"):
            key = EXPORT_PARAMS.get(row["Parameter"])
            if key is None or row["Zeitreihe"] != "Tagesmittel":
                continue
            try:
                value = float(row["Wert"])
            except ValueError:
                continue  # gaps are spelled "Lücke"
            put(key, dt.date.fromisoformat(row["Zeitstempel"][:10]), value)

    # the API carries only temperature, discharge and level — .get skips the rest
    for row in csv.DictReader(open(CSV_API)):
        date = dt.date.fromisoformat(row["date"])
        for p in PARAMS:
            if row.get(p["col"]):
                put(p["key"], date, float(row[p["col"]]))

    def days(key, year):
        return sum(v is not None for v in data[key].get(year, ()))

    # a year is drawn if any parameter has enough of it for a line
    all_years = sorted({y for k in data for y in data[k]})
    years = [y for y in all_years if any(days(k, y) >= MIN_DAYS for k in data)]
    missing = [y for y in range(years[0], years[-1] + 1) if y not in years]
    return years, data, missing, latest


def encode(values, scale, offset):
    """365 values -> "65,64,,69" of scaled ints; an empty field means no measurement."""
    return ",".join("" if v is None else str(round((v - offset) * scale)) for v in values)


def step_for(span, target=6):
    """A 1/2/2.5/5 x 10^k step giving roughly `target` gridlines across `span`."""
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def axis_for(values, zero):
    """-> ([lo, hi], [tick, ...]) — a domain that frames the data without lying."""
    lo_v, hi_v = min(values), max(values)
    if zero:
        lo, hi = 0.0, hi_v
        step = step_for(hi - lo)
        hi = math.ceil(hi / step) * step          # top tick sits at the top
    else:
        pad = (hi_v - lo_v) * 0.10
        lo, hi = lo_v - pad, hi_v + pad
        step = step_for(hi - lo)

    ticks, t = [], math.ceil(lo / step) * step
    while t <= hi + 1e-9:
        ticks.append(round(t, 6))
        t += step
    return [round(lo, 6), round(hi, 6)], ticks


def trend_for(years, by_year):
    """Annual means, split into complete and incomplete years.

    An incomplete year's mean is biased by whichever seasons it happens to
    contain, so it is drawn hollow and never feeds the fit. The least-squares
    fit itself lives client-side, where the year range can be narrowed and the
    fit has to follow the selection.
    """
    full, part = [], []
    for i, y in enumerate(years):
        vals = [v for v in by_year[y] if v is not None]
        if vals:
            (full if len(vals) >= FULL_DAYS else part).append((i, st.fmean(vals)))
    domain, ticks = axis_for([m for _, m in full + part], zero=False)

    return {
        "idx": [i for i, _ in full],
        "means": [round(m, 4) for _, m in full],
        "pidx": [i for i, _ in part],
        "pmeans": [round(m, 4) for _, m in part],
        "domain": domain, "ticks": ticks,
    }


def german_date(d):
    return f"{d.day}. {MONTHS_FULL[d.month - 1]} {d.year}"


def main():
    years, data, missing, latest = load()

    # the legend gradient is sampled evenly so it stays a true year scale even
    # though the drawn years are not evenly spaced
    stops = [i / 60 for i in range(61)]

    params = []
    for p in PARAMS:
        by_year = data[p["key"]]
        flat = [v for y in years for v in by_year[y] if v is not None]
        domain, ticks = axis_for(flat, p["zero"])

        # each parameter spends the full blue-to-red ramp on its own coverage,
        # so a shorter record is not squeezed into the red end of a longer one
        covered = [y for y in years if any(v is not None for v in by_year[y])]
        y0, y1 = covered[0], covered[-1]
        pos = [min(1.0, max(0.0, (y - y0) / (y1 - y0))) for y in years]

        # legend ticks on the year scale; endpoints always, decades in between
        step = 20 if y1 - y0 > 80 else 10
        legend_years = [y0] + [
            y for y in range(math.ceil(y0 / step) * step, y1 + 1, step)
            if 0.03 < (y - y0) / (y1 - y0) < 0.97   # keep clear of the endpoint labels
        ] + [y1]

        params.append({
            "key": p["key"], "label": p["label"], "unit": p["unit"],
            "axis": p.get("axis", p["unit"]),
            "decimals": p["decimals"], "scale": p["scale"], "offset": p["offset"],
            "domain": domain, "ticks": ticks,
            "series": [encode(by_year[y], p["scale"], p["offset"]) for y in years],
            "trend": trend_for(years, by_year),
            "light": ramp.ramp(pos, "light"),
            "dark": ramp.ramp(pos, "dark"),
            "y0": y0, "y1": y1, "legendYears": legend_years,
        })

    payload = {
        "years": years,
        "params": params,
        "legendLight": ramp.ramp(stops, "light"),
        "legendDark": ramp.ramp(stops, "dark"),
        "months": MONTHS,
        "monthLengths": MONTH_LENGTHS,
    }

    def days(key, year):
        return sum(v is not None for v in data[key].get(year, ()))

    # a year counts as partial only if no parameter has it complete
    partial = [y for y in years if max(days(p["key"], y) for p in PARAMS) < FULL_DAYS]
    coverage = ", ".join(
        f"{p['label']} ab {min(y for y in years if days(p['key'], y))}" for p in PARAMS
    )
    gaps = (
        f"Nicht abgedeckt: {', '.join(str(y) for y in missing)}. " if missing else ""
    )
    note = (
        f"{len(years)} Jahrgänge, {years[0]}–{years[-1]} — {coverage}; "
        "die Jahresliste führt je Messgrösse nur Jahre mit Messwerten. "
        f"{gaps}"
        f"{', '.join(str(y) for y in partial)} unvollständig. "
        "Der 29. Februar liegt ausserhalb des 365-Tage-Rasters der Darstellung."
    )

    built = dt.datetime.now()
    stamp = (
        f"Neueste Messwerte vom {german_date(latest)} · "
        f"Seite erstellt am {german_date(built)} um {built:%H:%M} Uhr"
    )

    body = (
        TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
        .replace("__NOTE__", note)
        .replace("__STAMP__", stamp)
    )

    open("artifact.html", "w").write(body)
    open("index.html", "w").write(
        '<!doctype html>\n<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<style>\n{STANDALONE_CSS}</style>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )
    print(f"{len(years)} years -> index.html / artifact.html")
    print(note)


# Only the standalone file needs this. The hosted-artifact wrapper supplies its
# own reset, but a bare page keeps the UA margin on <body>, which shows up as a
# white frame around the plane — and stays white in dark mode.
STANDALONE_CSS = """\
  html, body { margin: 0; padding: 0; background: #f9f9f7; }
  html { color-scheme: light; }
  @media (prefers-color-scheme: dark) {
    html:not([data-theme="light"]), html:not([data-theme="light"]) body { background: #0d0d0d; }
    html:not([data-theme="light"]) { color-scheme: dark; }
  }
  html[data-theme="dark"], html[data-theme="dark"] body { background: #0d0d0d; }
  html[data-theme="dark"] { color-scheme: dark; }
  html[data-theme="light"], html[data-theme="light"] body { background: #f9f9f7; }
  html[data-theme="light"] { color-scheme: light; }
"""

TEMPLATE = r"""<title>Der Rhein bei Rekingen — Temperatur, Abfluss, Wasserstand, Wasserchemie</title>
<style>
  .viz-root {
    color-scheme: light;
    --surface-1: #fcfcfb;
    --plane: #f9f9f7;
    --text-primary: #0b0b0b;
    --text-secondary: #52514e;
    --text-muted: #898781;
    --grid: #e1e0d9;
    --axis: #c3c2b7;
    --hairline: rgba(11, 11, 11, 0.10);
    --ghost: rgba(11, 11, 11, 0.045);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background: var(--plane);
    color: var(--text-primary);
    min-height: 100%;
    margin: 0;
    padding: 28px 20px 56px;
    -webkit-font-smoothing: antialiased;
    position: relative;   /* anchor for the GitHub corner */
    overflow-x: clip;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --surface-1: #1a1a19;
      --plane: #0d0d0d;
      --text-primary: #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted: #898781;
      --grid: #2c2c2a;
      --axis: #383835;
      --hairline: rgba(255, 255, 255, 0.10);
      --ghost: rgba(255, 255, 255, 0.06);
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --plane: #0d0d0d;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --grid: #2c2c2a;
    --axis: #383835;
    --hairline: rgba(255, 255, 255, 0.10);
    --ghost: rgba(255, 255, 255, 0.06);
  }

  /* GitHub corner — the octocat waves out of the top right, after
     github.com/tholman/github-corners (MIT). Inlined, no external assets. */
  .github-corner { position: absolute; top: 0; right: 0; color: var(--surface-1); }
  .github-corner svg { display: block; width: 80px; height: 80px; fill: var(--text-primary); }
  .github-corner:focus-visible { outline: 2px solid var(--text-primary); outline-offset: -8px; }
  .octo-arm { transform-origin: 130px 106px; }
  .github-corner:hover .octo-arm { animation: octocat-wave 560ms ease-in-out; }
  @keyframes octocat-wave {
    0%, 100% { transform: rotate(0); }
    20%, 60% { transform: rotate(-25deg); }
    40%, 80% { transform: rotate(10deg); }
  }
  /* no hover on touch, so wave once on arrival instead */
  @media (max-width: 700px) {
    .github-corner svg { width: 60px; height: 60px; }
    .github-corner:hover .octo-arm { animation: none; }
    .github-corner .octo-arm { animation: octocat-wave 560ms ease-in-out; }
  }
  @media (prefers-reduced-motion: reduce) {
    .github-corner .octo-arm, .github-corner:hover .octo-arm { animation: none; }
  }

  .wrap { max-width: 1080px; margin: 0 auto; }
  /* below this width the corner reaches into the centred column */
  @media (max-width: 1240px) { .title, .subtitle { padding-right: 88px; } }
  .title { font-size: 1.4rem; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
  .subtitle { font-size: 0.9rem; color: var(--text-secondary); margin: 0 0 20px; line-height: 1.5; }

  .tabs {
    display: inline-flex; flex-wrap: wrap; gap: 2px; padding: 3px; margin-bottom: 14px;
    background: var(--ghost); border-radius: 9px;
  }
  .tab {
    font: inherit; font-size: 0.85rem; color: var(--text-secondary);
    background: transparent; border: 0; border-radius: 7px;
    padding: 7px 15px; cursor: pointer; white-space: nowrap;
  }
  .tab:hover { color: var(--text-primary); }
  .tab[aria-selected="true"] {
    background: var(--surface-1); color: var(--text-primary);
    font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,.10);
  }
  .tab:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 1px; }

  svg:focus { outline: none; }   /* a click must not leave a ring; keyboard still does */
  svg:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 3px; border-radius: 8px; }

  .card {
    background: var(--surface-1); border: 1px solid var(--hairline);
    border-radius: 12px; padding: 14px 16px 8px; position: relative;
  }
  .plot { position: relative; }
  svg { display: block; width: 100%; height: auto; touch-action: none; }
  .grid-line { stroke: var(--grid); stroke-width: 1; }
  .axis-line { stroke: var(--axis); stroke-width: 1; }
  .tick { fill: var(--text-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
  .axis-title { fill: var(--text-secondary); font-size: 11px; }
  .line { fill: none; stroke-linejoin: round; stroke-linecap: round; transition: opacity .12s ease; }
  .crosshair { stroke: var(--axis); stroke-width: 1; pointer-events: none; opacity: 0; }
  .dot { pointer-events: none; opacity: 0; }
  .dot circle { stroke: var(--surface-1); stroke-width: 2; }

  .tooltip {
    position: absolute; pointer-events: none; opacity: 0; transition: opacity .1s ease;
    background: var(--surface-1); border: 1px solid var(--hairline);
    border-radius: 9px; padding: 8px 10px; min-width: 128px;
    box-shadow: 0 4px 14px rgba(0,0,0,.10); z-index: 4;
  }
  .tt-day { font-size: 0.72rem; color: var(--text-muted); margin-bottom: 5px; }
  .tt-row { display: flex; align-items: baseline; gap: 7px; margin-top: 3px; }
  .tt-key { width: 12px; height: 2px; border-radius: 1px; flex: none; align-self: center; }
  .tt-val { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); }
  .tt-lab { font-size: 0.75rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
  .tt-sel { font-size: 0.7rem; color: var(--text-muted); }

  .card + .card { margin-top: 16px; }
  .card-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin-bottom: 2px; }
  .card-title { font-size: 0.95rem; font-weight: 600; margin: 0; }
  .card-note { font-size: 0.78rem; color: var(--text-secondary); margin: 0 0 10px; line-height: 1.45; }
  .trend-line { stroke: var(--text-primary); stroke-width: 2; fill: none; stroke-linecap: round; }
  .trend-linear { stroke-dasharray: 8 5; }
  .trend-roll { stroke-dasharray: 0.1 6.5; }
  /* the trend selector: one fit at a time, picked like a tab */
  .trend-keys {
    display: inline-flex; flex-wrap: wrap; gap: 2px; margin-left: auto;
    padding: 2px; background: var(--ghost); border-radius: 8px;
  }
  .trend-key {
    font: inherit; font-size: 0.75rem; color: var(--text-secondary);
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
    background: transparent; border: 0; border-radius: 6px; padding: 4px 9px; cursor: pointer;
  }
  .trend-key:hover:not(:disabled) { color: var(--text-primary); }
  .trend-key[aria-pressed="true"] {
    background: var(--surface-1); color: var(--text-primary); font-weight: 600;
    box-shadow: 0 1px 3px rgba(0,0,0,.10);
  }
  .trend-key:disabled { opacity: 0.45; cursor: default; }
  .trend-key:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 1px; }
  /* the page-wide svg rule stretches to 100% width — the key samples must not;
     the sample wears the button's ink, not the chart line's */
  .trend-key svg { flex: none; width: 26px; height: 6px; }
  .trend-key .trend-line { stroke: currentColor; }
  .spine { stroke: var(--axis); stroke-width: 1; fill: none; opacity: 0.55; }
  .dot-year circle { stroke: var(--surface-1); stroke-width: 2; }

  .legend { margin: 18px 0 4px; }
  .legend-track { position: relative; }
  .legend-bar { height: 8px; border-radius: 4px; border: 1px solid var(--hairline); }
  .legend-shade {
    position: absolute; top: 0; height: 100%; pointer-events: none;
    background: var(--plane); opacity: 0.82;
  }
  #shade-lo { left: 0; border-radius: 4px 0 0 4px; }
  #shade-hi { right: 0; border-radius: 0 4px 4px 0; }
  /* two stacked native sliders make the dual-thumb range; only the thumbs are
     interactive, the shared track underneath is the gradient bar itself */
  .legend-track input {
    position: absolute; top: -4px; left: 0; width: 100%; height: 16px; margin: 0;
    -webkit-appearance: none; appearance: none; background: none; pointer-events: none;
  }
  #range-lo { z-index: 3; }
  #range-hi { z-index: 4; }
  .legend-track input::-webkit-slider-thumb {
    -webkit-appearance: none; appearance: none; pointer-events: auto;
    width: 16px; height: 16px; border-radius: 50%;
    background: var(--surface-1); border: 2px solid var(--text-secondary);
    box-shadow: 0 1px 3px rgba(0,0,0,.25); cursor: ew-resize;
  }
  .legend-track input::-moz-range-track { background: none; }
  .legend-track input::-moz-range-thumb {
    pointer-events: auto; width: 12px; height: 12px; border-radius: 50%;
    background: var(--surface-1); border: 2px solid var(--text-secondary);
    box-shadow: 0 1px 3px rgba(0,0,0,.25); cursor: ew-resize;
  }
  .legend-track input:focus-visible::-webkit-slider-thumb { outline: 2px solid var(--text-primary); outline-offset: 1px; }
  .legend-track input:focus-visible::-moz-range-thumb { outline: 2px solid var(--text-primary); outline-offset: 1px; }
  .legend-ticks {
    position: relative; height: 14px; margin-top: 5px;
    font-size: 0.7rem; color: var(--text-muted); font-variant-numeric: tabular-nums;
  }
  .legend-ticks span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
  .legend-cap {
    font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 6px;
    display: flex; align-items: center; gap: 8px; min-height: 20px;
  }
  .range-reset {
    font: inherit; font-size: 0.72rem; color: var(--text-secondary);
    background: transparent; border: 1px solid var(--hairline); border-radius: 6px;
    padding: 1px 7px; cursor: pointer;
  }
  .range-reset:hover { color: var(--text-primary); background: var(--ghost); }
  .range-reset:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 1px; }

  .years { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 16px; }
  .yr {
    font: inherit; font-size: 0.72rem; font-variant-numeric: tabular-nums;
    color: var(--text-secondary); background: transparent;
    border: 1px solid transparent; border-radius: 6px;
    padding: 3px 6px 3px 5px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .yr[hidden] { display: none; }   /* inline-flex would beat the UA hidden rule */
  .yr:hover { background: var(--ghost); }
  .yr:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 2px; }
  .yr[aria-pressed="true"] { color: var(--text-primary); font-weight: 600; border-color: var(--axis); }
  .yr-key { width: 10px; height: 3px; border-radius: 2px; flex: none; }
  .note { font-size: 0.75rem; color: var(--text-muted); margin-top: 22px; line-height: 1.6; }
  .note a { color: inherit; }
  .stamp { margin-top: 8px; }
</style>

<div class="viz-root">
<a class="github-corner" href="https://github.com/samuelb/rheinstats"
   target="_blank" rel="noopener" aria-label="Quellcode und Daten auf GitHub ansehen">
  <svg viewBox="0 0 250 250" aria-hidden="true">
    <path d="M0,0 L115,115 L130,115 L142,142 L250,250 L250,0 Z"></path>
    <path class="octo-arm" fill="currentColor" d="M128.3,109.0 C113.8,99.7 119.0,89.6 119.0,89.6 C122.0,82.7 120.5,78.6 120.5,78.6 C119.2,72.0 123.4,76.3 123.4,76.3 C127.3,80.9 125.5,87.3 125.5,87.3 C122.9,97.6 130.6,101.9 134.4,103.2"></path>
    <path class="octo-body" fill="currentColor" d="M115.0,115.0 C114.9,115.1 118.7,116.5 119.8,115.4 L133.7,101.8 C136.9,99.2 139.9,98.4 142.2,98.6 C133.8,88.0 127.5,74.4 143.8,58.0 C148.5,53.4 154.0,51.2 159.7,51.0 C160.3,49.4 163.2,43.6 171.4,40.1 C171.4,40.1 176.1,42.5 178.8,56.2 C183.1,58.4 187.2,61.2 190.9,64.9 C194.5,68.5 197.3,72.5 199.5,76.7 C213.2,79.4 215.7,84.1 215.7,84.1 C212.2,92.3 206.4,95.2 204.8,95.8 C204.6,101.5 202.4,107.0 197.8,111.7 C181.4,128.0 167.8,121.7 157.2,113.3 C157.4,115.6 156.6,118.6 154.0,121.8 L140.4,135.7 C139.3,136.8 140.7,140.6 140.8,140.5"></path>
  </svg>
</a>
<div class="wrap">
  <h1 class="title">Der Rhein bei Rekingen</h1>
  <p class="subtitle">
    BAFU-Messstation 2143, Tagesmittel — ein Linienzug pro Jahr, über den
    Jahresverlauf gelegt. Die Farbe codiert das Jahr, Blau die ältesten und Rot
    die jüngsten Messungen. Das laufende Jahr ist hervorgehoben; eine Linie
    anklicken hebt stattdessen deren Jahr hervor.
  </p>

  <div class="tabs" id="tabs" role="tablist" aria-label="Messgrösse"></div>

  <div class="card" id="panel" role="tabpanel">
    <div class="plot" id="plot">
      <svg id="chart" viewBox="0 0 960 470" role="img" tabindex="0"
           aria-label="Tagesmittel des Rheins bei Rekingen, ein Linienzug pro Jahr. Mit den Pfeiltasten Jahre durchgehen.">
        <g id="grid"></g>
        <g id="lines"></g>
        <line id="crosshair" class="crosshair"></line>
        <g id="dots"></g>
        <g id="axes"></g>
      </svg>
      <div class="tooltip" id="tooltip" role="status" aria-live="polite"></div>
    </div>

    <div class="legend">
      <div class="legend-cap">Messjahr<span id="range-label"></span>
        <button type="button" class="range-reset" id="range-reset" hidden>Alle Jahre</button>
      </div>
      <div class="legend-track">
        <div class="legend-bar" id="legend-bar"></div>
        <div class="legend-shade" id="shade-lo"></div>
        <div class="legend-shade" id="shade-hi"></div>
        <input type="range" id="range-lo" step="1" aria-label="Ältestes angezeigtes Jahr">
        <input type="range" id="range-hi" step="1" aria-label="Jüngstes angezeigtes Jahr">
      </div>
      <div class="legend-ticks" id="legend-ticks"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-head">
      <h2 class="card-title" id="trend-title">Jahresmittel im Vergleich</h2>
      <div class="trend-keys" role="group" aria-label="Trendlinie wählen">
        <button type="button" class="trend-key" id="key-loess" aria-pressed="true">
          <svg width="26" height="6" viewBox="0 0 26 6" aria-hidden="true"><line class="trend-line" x1="1" y1="3" x2="25" y2="3"></line></svg>
          LOESS-Glättung</button>
        <button type="button" class="trend-key" id="key-linear" aria-pressed="false">
          <svg width="26" height="6" viewBox="0 0 26 6" aria-hidden="true"><line class="trend-line trend-linear" x1="1" y1="3" x2="25" y2="3"></line></svg>
          Lineare Regression</button>
        <button type="button" class="trend-key" id="key-roll" aria-pressed="false">
          <svg width="26" height="6" viewBox="0 0 26 6" aria-hidden="true"><line class="trend-line trend-roll" x1="1" y1="3" x2="25" y2="3"></line></svg>
          <span id="key-roll-label">Gleitendes Mittel</span></button>
      </div>
    </div>
    <p class="card-note" id="trend-note"></p>
    <div class="plot" id="trend-plot">
      <svg id="trend" viewBox="0 0 960 250" role="img" aria-label="Jahresmittel je Jahrgang mit wählbarer Trendlinie: LOESS-Glättung, lineare Regression oder gleitendes Mittel">
        <g id="trend-grid"></g>
        <path id="trend-spine" class="spine"></path>
        <path id="trend-fit" class="trend-line trend-linear"></path>
        <path id="trend-roll" class="trend-line trend-roll"></path>
        <path id="trend-loess" class="trend-line"></path>
        <g id="trend-dots"></g>
        <g id="trend-axes"></g>
      </svg>
      <div class="tooltip" id="trend-tooltip" role="status" aria-live="polite"></div>
    </div>
  </div>

  <div class="years" id="years" role="group" aria-label="Jahr auswählen"></div>

  <p class="note">
    Quelle: Bundesamt für Umwelt BAFU, Station 2143 Rhein–Rekingen, Tagesmittel
    von Wassertemperatur, Abfluss, Wasserstand, elektrischer Leitfähigkeit,
    pH-Wert, Sauerstoffgehalt und Sauerstoff-Sättigung. Vollständige Messreihen
    vom Datenservice Hydrologie des BAFU, ergänzt um die jüngsten Tage aus den
    Jahresganglinien von hydrodaten.admin.ch. Wasserstand (eine Höhe über Meer),
    Leitfähigkeit, pH-Wert und Sauerstoff-Sättigung tragen auf die Messwerte
    gezoomte Achsen ohne Nullpunkt. __NOTE__
  </p>
  <footer class="note stamp">__STAMP__</footer>
</div>
</div>

<script>
(function () {
  const D = __DATA__;
  const YEARS = D.years;
  const N = YEARS.length;
  const DAYS = 365;

  // each parameter carries its own scale, unit and domain — they never share an axis
  const PARAMS = D.params.map(p => Object.assign({}, p, {
    // "65,64,,69" of scaled ints -> [6.5, 6.4, null, 6.9]
    values: p.series.map(s => s.split(",").map(v => v === "" ? null : +v / p.scale + p.offset)),
    nf: new Intl.NumberFormat("de-CH", {
      minimumFractionDigits: p.decimals, maximumFractionDigits: p.decimals
    }),
    // ticks are whole numbers; they should not wear the value precision
    tickNf: new Intl.NumberFormat("de-CH", {
      minimumFractionDigits: 0, maximumFractionDigits: p.decimals
    }),
    // a rate needs one digit more than the value, or +0.484/decade rounds to +0.5
    rateNf: new Intl.NumberFormat("de-CH", {
      minimumFractionDigits: p.decimals + 1, maximumFractionDigits: p.decimals + 1
    }),
  }));
  let pi = 0;                       // active parameter
  const P = () => PARAMS[pi];
  const SERIES = () => P().values;
  // the parameters start in different decades, so year availability is per tab
  const HAS = PARAMS.map(p => p.values.map(vals => vals.some(v => v != null)));

  const W = 960, H = 470;
  const M = { top: 28, right: 16, bottom: 54, left: 62 };   // top leaves room for the unit label
  const PW = W - M.left - M.right;
  const PH = H - M.top - M.bottom;

  const x = d => M.left + (d / (DAYS - 1)) * PW;
  const y = v => {
    const [lo, hi] = P().domain;
    return M.top + PH - ((v - lo) / (hi - lo)) * PH;
  };

  const svg = document.getElementById("chart");
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  };

  /* ---- month boundaries on the day grid ---- */
  const monthStart = [];
  let acc = 0;
  for (const len of D.monthLengths) { monthStart.push(acc); acc += len; }

  /* ---- theme ---- */
  const isDark = () => {
    const stamp = document.documentElement.getAttribute("data-theme");
    if (stamp) return stamp === "dark";
    return matchMedia("(prefers-color-scheme: dark)").matches;
  };
  // every parameter spreads the full ramp over its own coverage
  let colors = isDark() ? PARAMS[0].dark : PARAMS[0].light;

  /* ---- grid & axes, rebuilt whenever the parameter changes ---- */
  const grid = document.getElementById("grid");
  const axes = document.getElementById("axes");
  const BASE_Y = M.top + PH;

  function drawAxes() {
    const p = P();
    grid.textContent = "";
    axes.textContent = "";
    p.ticks.forEach(v => {
      grid.appendChild(el("line", { class: "grid-line", x1: M.left, x2: W - M.right, y1: y(v), y2: y(v) }));
      const t = el("text", { class: "tick", x: M.left - 9, y: y(v) + 4, "text-anchor": "end" });
      t.textContent = p.tickNf.format(v);
      axes.appendChild(t);
    });
    axes.appendChild(el("line", { class: "axis-line", x1: M.left, x2: W - M.right, y1: BASE_Y, y2: BASE_Y }));
    D.months.forEach((name, i) => {
      const mid = monthStart[i] + D.monthLengths[i] / 2;
      const t = el("text", { class: "tick", x: x(mid), y: BASE_Y + 20, "text-anchor": "middle" });
      t.textContent = name;
      axes.appendChild(t);
      if (i > 0) grid.appendChild(el("line", { class: "grid-line", x1: x(monthStart[i]), x2: x(monthStart[i]), y1: M.top, y2: BASE_Y }));
    });
    const yTitle = el("text", { class: "axis-title", x: M.left - 9, y: M.top - 12, "text-anchor": "end" });
    yTitle.textContent = p.axis;
    axes.appendChild(yTitle);
  }

  /* ---- lines ---- */
  const linesG = document.getElementById("lines");
  const paths = YEARS.map(yr => {
    // data-year survives the reordering that lifts a line to the top
    const p = el("path", { class: "line", "stroke-width": 1.1, "data-year": yr });
    linesG.appendChild(p);
    return p;
  });

  function drawPaths() {
    SERIES().forEach((vals, i) => {
      let d = "", pen = false;
      for (let k = 0; k < DAYS; k++) {
        const v = vals[k];
        if (v == null) { pen = false; continue; }
        d += (pen ? "L" : "M") + x(k).toFixed(1) + " " + y(v).toFixed(1) + " ";
        pen = true;
      }
      paths[i].setAttribute("d", d.trim());
    });
  }

  function paint() {
    const dark = isDark();
    colors = dark ? P().dark : P().light;
    paths.forEach((p, i) => p.setAttribute("stroke", colors[i]));
    document.getElementById("legend-bar").style.background =
      "linear-gradient(to right," + (dark ? D.legendDark : D.legendLight).join(",") + ")";
    document.querySelectorAll(".yr-key").forEach((k, i) => { k.style.background = colors[i]; });
    render();
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paint);
  new MutationObserver(paint).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  /* ---- legend ticks, placed at their true position on the year scale ---- */
  const ticks = document.getElementById("legend-ticks");
  function drawLegendTicks() {
    const p = P();
    ticks.textContent = "";
    p.legendYears.forEach(yr => {
      const s = document.createElement("span");
      s.textContent = yr;
      const f = (yr - p.y0) / (p.y1 - p.y0);
      s.style.left = (f * 100) + "%";
      if (f < 0.02) s.style.transform = "none";
      if (f > 0.98) s.style.transform = "translateX(-100%)";
      ticks.appendChild(s);
    });
  }

  /* ---- state ---- */
  let selected = null, hovered = null, cursorDay = null;

  /* ---- year-range slider: two thumbs on the legend bar cap the drawn years ---- */
  let rLo = null, rHi = null;   // in years, kept across tabs; null = no cap
  const loIn = document.getElementById("range-lo");
  const hiIn = document.getElementById("range-hi");
  const shadeLo = document.getElementById("shade-lo");
  const shadeHi = document.getElementById("shade-hi");
  const rangeLabel = document.getElementById("range-label");
  const rangeReset = document.getElementById("range-reset");

  // a range carried over from another tab may not intersect this parameter's
  // coverage at all — showing nothing helps no one, so the caps yield instead
  // and the tab falls back to all of its measured years
  const effRange = () => {
    const p = P();
    const lo = Math.max(p.y0, rLo == null ? p.y0 : rLo);
    const hi = Math.min(p.y1, rHi == null ? p.y1 : rHi);
    return lo > hi ? [p.y0, p.y1] : [lo, hi];
  };
  const effLo = () => effRange()[0];
  const effHi = () => effRange()[1];
  const inRange = i => YEARS[i] >= effLo() && YEARS[i] <= effHi();
  const visible = i => HAS[pi][i] && inRange(i);

  function syncRange() {
    const p = P();
    loIn.min = hiIn.min = p.y0;
    loIn.max = hiIn.max = p.y1;
    loIn.value = effLo();
    hiIn.value = effHi();
    const f0 = (effLo() - p.y0) / (p.y1 - p.y0);
    const f1 = (effHi() - p.y0) / (p.y1 - p.y0);
    shadeLo.style.width = (f0 * 100) + "%";
    shadeHi.style.width = ((1 - f1) * 100) + "%";
    const capped = effLo() > p.y0 || effHi() < p.y1;
    rangeLabel.textContent = capped ? ` · ${effLo()}–${effHi()}` : "";
    rangeReset.hidden = !capped;
    // both thumbs parked on the right edge: only the lower one can still move,
    // so it must win the pointer over the upper input stacked above it
    loIn.style.zIndex = effLo() === p.y1 ? 5 : "";
    if (selected != null && !visible(selected)) selected = null;
    if (hovered != null && !visible(hovered)) hovered = null;
    yearBtns.forEach((b, k) => { b.hidden = !visible(k); });
    drawTrend();   // the fit follows the selection
    render();
  }

  loIn.addEventListener("input", () => {
    rLo = Math.min(+loIn.value, effHi());
    if (rLo <= P().y0) rLo = null;   // at the stop = no cap, also on longer tabs
    syncRange();
  });
  hiIn.addEventListener("input", () => {
    rHi = Math.max(+hiIn.value, effLo());
    if (rHi >= P().y1) rHi = null;
    syncRange();
  });
  rangeReset.addEventListener("click", () => { rLo = rHi = null; syncRange(); });

  /* ---- year legend: identity that does not rely on telling the hues apart ---- */
  const yearsBox = document.getElementById("years");
  const yearBtns = YEARS.map((yr, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "yr";
    b.setAttribute("aria-pressed", "false");
    const key = document.createElement("span");
    key.className = "yr-key";
    b.appendChild(key);
    b.appendChild(document.createTextNode(String(yr)));
    b.addEventListener("click", () => { selected = selected === i ? null : i; render(); });
    b.addEventListener("pointerenter", () => { hovered = i; render(); });
    b.addEventListener("pointerleave", () => { if (hovered === i) { hovered = null; render(); } });
    b.addEventListener("focus", () => { hovered = i; render(); });
    b.addEventListener("blur", () => { if (hovered === i) { hovered = null; render(); } });
    yearsBox.appendChild(b);
    return b;
  });

  const tooltip = document.getElementById("tooltip");
  const crosshair = document.getElementById("crosshair");
  const dotsG = document.getElementById("dots");

  // translucent so 42 overlapping lines build density instead of hiding each other
  const OP_REST = 0.55, OP_DIM = 0.10, OP_LIFT = 1;

  // the running year, so the emphasis moves on by itself as data is added
  const CURRENT = Math.max(0, YEARS.indexOf(new Date().getFullYear()));

  function render() {
    const focus = hovered != null ? hovered : selected;
    const anyFocus = focus != null || selected != null;
    paths.forEach((p, i) => {
      p.style.display = visible(i) ? "" : "none";
      const lift = i === focus || i === selected;
      const current = !anyFocus && i === CURRENT;   // yields as soon as a year is picked
      p.style.opacity = anyFocus ? (lift ? OP_LIFT : OP_DIM) : (current ? OP_LIFT : OP_REST);
      p.setAttribute("stroke-width", lift ? 2.4 : current ? 1.9 : 1.1);
    });
    // draw order last, so the emphasised line is not buried under the rest
    if (anyFocus) {
      if (selected != null) linesG.appendChild(paths[selected]);
      if (focus != null && focus !== selected) linesG.appendChild(paths[focus]);
    } else {
      linesG.appendChild(paths[CURRENT]);
    }
    yearBtns.forEach((b, i) => b.setAttribute("aria-pressed", i === selected ? "true" : "false"));
    drawReadout();
    renderTrendDots();
  }

  function fmt(v) { return P().nf.format(v) + (P().unit ? " " + P().unit : ""); }

  function dayLabel(d) {
    let m = 0;
    while (m < 11 && d >= monthStart[m + 1]) m++;
    return (d - monthStart[m] + 1) + ". " + D.months[m];
  }

  function drawReadout() {
    dotsG.textContent = "";
    if (cursorDay == null) {
      crosshair.style.opacity = 0;
      tooltip.style.opacity = 0;
      return;
    }
    const rows = [];
    if (hovered != null) rows.push(hovered);
    if (selected != null && selected !== hovered) rows.push(selected);
    const shown = rows.filter(i => SERIES()[i][cursorDay] != null);

    crosshair.style.opacity = 1;
    crosshair.setAttribute("x1", x(cursorDay));
    crosshair.setAttribute("x2", x(cursorDay));

    tooltip.textContent = "";
    const day = document.createElement("div");
    day.className = "tt-day";
    day.textContent = dayLabel(cursorDay);
    tooltip.appendChild(day);

    if (!shown.length) {
      const hint = document.createElement("div");
      hint.className = "tt-sel";
      hint.textContent = "Linie ansteuern für Werte";
      tooltip.appendChild(hint);
    }

    shown.forEach(i => {
      const v = SERIES()[i][cursorDay];
      const row = document.createElement("div");
      row.className = "tt-row";
      const key = document.createElement("span");
      key.className = "tt-key";
      key.style.background = colors[i];
      const val = document.createElement("span");
      val.className = "tt-val";
      val.textContent = fmt(v);
      const lab = document.createElement("span");
      lab.className = "tt-lab";
      lab.textContent = YEARS[i];
      row.append(key, val, lab);
      tooltip.appendChild(row);

      const g = el("g", { class: "dot", style: "opacity:1" });
      g.appendChild(el("circle", { cx: x(cursorDay), cy: y(v), r: 4, fill: colors[i] }));
      dotsG.appendChild(g);
    });

    if (selected != null) {
      const hint = document.createElement("div");
      hint.className = "tt-sel";
      hint.textContent = YEARS[selected] + " ausgewählt";
      tooltip.appendChild(hint);
    }

    tooltip.style.opacity = 1;
    const box = svg.getBoundingClientRect();
    const px = (x(cursorDay) / W) * box.width;
    const flip = px > box.width - tooltip.offsetWidth - 24;
    tooltip.style.left = (flip ? px - tooltip.offsetWidth - 14 : px + 14) + "px";
    tooltip.style.top = "10px";
  }

  /* ---- pointer: crosshair snaps to the day, nearest line wins ---- */
  function locate(ev) {
    const box = svg.getBoundingClientRect();
    const sx = ((ev.clientX - box.left) / box.width) * W;
    const sy = ((ev.clientY - box.top) / box.height) * H;
    const day = Math.round(((sx - M.left) / PW) * (DAYS - 1));
    if (day < 0 || day >= DAYS) return null;
    let best = null, bestDist = Infinity;
    for (let i = 0; i < N; i++) {
      if (!visible(i)) continue;
      const v = SERIES()[i][day];
      if (v == null) continue;
      const dist = Math.abs(y(v) - sy);
      if (dist < bestDist) { bestDist = dist; best = i; }
    }
    return { day, near: bestDist < 34 ? best : null };
  }

  svg.addEventListener("pointermove", ev => {
    const hit = locate(ev);
    if (!hit) return;
    cursorDay = hit.day;
    hovered = hit.near;
    render();
  });
  svg.addEventListener("pointerleave", () => { cursorDay = null; hovered = null; render(); });
  svg.addEventListener("click", ev => {
    const hit = locate(ev);
    if (!hit) return;
    if (hit.near != null) selected = selected === hit.near ? null : hit.near;
    else selected = null;
    render();
  });
  // keyboard: the chart itself steps through years, so selection never needs a
  // pointer; years outside the range or without data are skipped over
  function nextWithData(from, dir) {
    for (let j = from; j >= 0 && j < N; j += dir) if (visible(j)) return j;
    return null;
  }
  svg.addEventListener("keydown", ev => {
    const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[ev.key];
    if (step) {
      const next = selected == null ? nextWithData(step > 0 ? 0 : N - 1, step)
                                    : nextWithData(selected + step, step);
      if (next != null) selected = next;
      if (cursorDay == null) cursorDay = 195;   // mid-July, where the years spread widest
      ev.preventDefault();
      render();
    } else if (ev.key === "Home") { selected = nextWithData(0, 1); ev.preventDefault(); render(); }
    else if (ev.key === "End") { selected = nextWithData(N - 1, -1); ev.preventDefault(); render(); }
  });
  document.addEventListener("keydown", ev => {
    if (ev.key === "Escape") { selected = null; cursorDay = null; render(); }
  });

  /* ---- second chart: one annual mean per year, plus a least-squares fit ---- */
  const TW = 960, TH = 250;
  const TM = { top: 26, right: 16, bottom: 30, left: 62 };
  const TPW = TW - TM.left - TM.right;
  const TPH = TH - TM.top - TM.bottom;

  const tSvg = document.getElementById("trend");
  const tGrid = document.getElementById("trend-grid");
  const tAxes = document.getElementById("trend-axes");
  const tDots = document.getElementById("trend-dots");
  const tFit = document.getElementById("trend-fit");
  const tLoess = document.getElementById("trend-loess");
  const tRoll = document.getElementById("trend-roll");
  const keyLinear = document.getElementById("key-linear");
  const keyLoess = document.getElementById("key-loess");
  const keyRoll = document.getElementById("key-roll");
  const keyRollLabel = document.getElementById("key-roll-label");
  const tSpine = document.getElementById("trend-spine");

  // which fit is drawn — one at a time, LOESS by default
  let trendMode = "loess";
  const modeBtns = { loess: keyLoess, linear: keyLinear, roll: keyRoll };
  for (const [m, b] of Object.entries(modeBtns)) {
    b.addEventListener("click", () => {
      if (trendMode !== m) { trendMode = m; drawTrend(); }
    });
  }
  const tTip = document.getElementById("trend-tooltip");

  // the x domain follows the year-range selection; the fit is recomputed over
  // exactly the complete years in view, so line and note never show stale data
  let tView = { x0: 0, x1: 1 };
  let tPts = [];    // { ix, yr, m } of the complete years within the range
  let tPart = [];   // incomplete years: drawn hollow, never part of the fit

  const tx = yr => TM.left + ((yr - tView.x0) / (tView.x1 - tView.x0)) * TPW;
  const ty = v => {
    const [lo, hi] = P().trend.domain;
    return TM.top + TPH - ((v - lo) / (hi - lo)) * TPH;
  };

  const R2_STRONG = 0.1;  // under this the fit explains so little that calling it a trend would mislead

  function fitOver(pts) {
    const n = pts.length;
    const mx = pts.reduce((s, d) => s + d.yr, 0) / n;
    const my = pts.reduce((s, d) => s + d.m, 0) / n;
    let sxx = 0, sxy = 0, syy = 0;
    for (const d of pts) {
      const dx = d.yr - mx, dy = d.m - my;
      sxx += dx * dx; sxy += dx * dy; syy += dy * dy;
    }
    if (!sxx || !syy) return null;
    const slope = sxy / sxx;
    return { slope, intercept: my - slope * mx, r2: (sxy * sxy) / (sxx * syy) };
  }

  const LOESS_MIN = 7;   // fewer years than this and a local fit is just noise

  // LOESS: a tricube-weighted linear regression around each complete year,
  // each local fit seeing the nearest half of the years in view
  function loessOver(pts) {
    const n = pts.length;
    const k = Math.min(n, Math.max(LOESS_MIN, Math.ceil(n / 2)));
    return pts.map(d => {
      const dist = pts.map(q => Math.abs(q.yr - d.yr)).sort((a, b) => a - b);
      const h = dist[k - 1];
      let sw = 0, swx = 0, swy = 0, swxx = 0, swxy = 0;
      for (const q of pts) {
        const u = Math.abs(q.yr - d.yr) / h;
        if (u >= 1) continue;
        const w = (1 - u ** 3) ** 3;
        sw += w; swx += w * q.yr; swy += w * q.m;
        swxx += w * q.yr * q.yr; swxy += w * q.yr * q.m;
      }
      const det = sw * swxx - swx * swx;
      const v = Math.abs(det) > 1e-9
        ? (swy * swxx - swx * swxy + (sw * swxy - swx * swy) * d.yr) / det
        : swy / sw;
      return { yr: d.yr, v };
    });
  }

  // centered mean over a fixed window of years, drawn only where the whole
  // window lies inside the selection — the ends carry no half-window bias
  function rollingOver(pts, win) {
    const half = (win - 1) / 2;
    const y0 = pts[0].yr, y1 = pts[pts.length - 1].yr;
    const out = [];
    for (const d of pts) {
      if (d.yr - half < y0 || d.yr + half > y1) continue;
      const w = pts.filter(q => Math.abs(q.yr - d.yr) <= half);
      if (w.length <= half) continue;   // a mostly-missing window would fake a value
      out.push({ yr: d.yr, v: w.reduce((s, q) => s + q.m, 0) / w.length });
    }
    return out;
  }

  // polyline through smoothed points; a hole in the record wider than maxGap
  // breaks the line rather than bridging unmeasured years
  const smoothPath = (pts, maxGap) => pts.map((d, k) => {
    const gap = k > 0 && d.yr - pts[k - 1].yr > maxGap;
    return (k && !gap ? "L" : "M") + tx(d.yr).toFixed(1) + " " + ty(d.v).toFixed(1);
  }).join(" ");

  function drawTrend() {
    const p = P(), t = p.trend;
    tPts = [];
    t.idx.forEach((ix, k) => {
      if (inRange(ix)) tPts.push({ ix, yr: YEARS[ix], m: t.means[k] });
    });
    tPart = [];
    t.pidx.forEach((ix, k) => {
      if (inRange(ix)) tPart.push({ ix, yr: YEARS[ix], m: t.pmeans[k], part: true });
    });
    // the view spans every drawn dot, hollow ones included
    const shown = tPts.concat(tPart);
    const yr0 = shown.length ? Math.min(...shown.map(d => d.yr)) : effLo();
    const yr1 = shown.length ? Math.max(...shown.map(d => d.yr)) : effHi();
    tView = yr1 > yr0 ? { x0: yr0, x1: yr1 } : { x0: yr0 - 1, x1: yr0 + 1 };

    tGrid.textContent = "";
    tAxes.textContent = "";
    t.ticks.forEach(v => {
      tGrid.appendChild(el("line", { class: "grid-line", x1: TM.left, x2: TW - TM.right, y1: ty(v), y2: ty(v) }));
      const lb = el("text", { class: "tick", x: TM.left - 9, y: ty(v) + 4, "text-anchor": "end" });
      lb.textContent = p.tickNf.format(v);
      tAxes.appendChild(lb);
    });
    const base = TM.top + TPH;
    tAxes.appendChild(el("line", { class: "axis-line", x1: TM.left, x2: TW - TM.right, y1: base, y2: base }));
    const span = tView.x1 - tView.x0;
    const xstep = span > 60 ? 10 : span > 25 ? 5 : span > 12 ? 2 : 1;
    for (let yr = Math.ceil(tView.x0 / xstep) * xstep; yr <= tView.x1; yr += xstep) {
      const lb = el("text", { class: "tick", x: tx(yr), y: base + 18, "text-anchor": "middle" });
      lb.textContent = yr;
      tAxes.appendChild(lb);
    }
    const unit = el("text", { class: "axis-title", x: TM.left - 9, y: TM.top - 12, "text-anchor": "end" });
    unit.textContent = p.axis;
    tAxes.appendChild(unit);

    // the year-to-year line stays recessive; it is context for the fit, not the point
    // break the line across missing years rather than implying a measurement
    tSpine.setAttribute("d", tPts.map((d, k) => {
      const gap = k > 0 && d.yr - tPts[k - 1].yr > 1;
      return (k && !gap ? "L" : "M") + tx(d.yr).toFixed(1) + " " + ty(d.m).toFixed(1);
    }).join(" "));

    // same weight and colour in every tab; how much the fit is worth is said in
    // the caption, not whispered through the line's opacity
    // the fitted line spans only the complete years it is computed from
    // all three fits are computed over the same complete years; the selector
    // decides which one is drawn — the others keep their buttons ready
    const fit = tPts.length >= 3 ? fitOver(tPts) : null;
    if (fit) {
      const fx0 = tPts[0].yr, fx1 = tPts[tPts.length - 1].yr;
      tFit.setAttribute("d",
        `M${tx(fx0).toFixed(1)} ${ty(fit.slope * fx0 + fit.intercept).toFixed(1)} ` +
        `L${tx(fx1).toFixed(1)} ${ty(fit.slope * fx1 + fit.intercept).toFixed(1)}`);
    }

    const loess = tPts.length >= LOESS_MIN ? loessOver(tPts) : null;
    if (loess) tLoess.setAttribute("d", smoothPath(loess, 8));

    // the window adapts once: 11 years on a long view, 5 on a zoomed-in one
    const win = tPts.length && tPts[tPts.length - 1].yr - tPts[0].yr >= 30 ? 11 : 5;
    let roll = tPts.length ? rollingOver(tPts, win) : [];
    if (roll.length < 2) roll = null;
    if (roll) tRoll.setAttribute("d", smoothPath(roll, win));
    keyRollLabel.textContent = `Gleitendes Mittel (${win} Jahre)`;

    tFit.style.display = fit && trendMode === "linear" ? "" : "none";
    tLoess.style.display = loess && trendMode === "loess" ? "" : "none";
    tRoll.style.display = roll && trendMode === "roll" ? "" : "none";
    // a fit the selection cannot support stays listed but not pressable
    keyLinear.disabled = !fit;
    keyLoess.disabled = !loess;
    keyRoll.disabled = !roll;
    for (const [m, b] of Object.entries(modeBtns)) {
      b.setAttribute("aria-pressed", String(m === trendMode));
    }

    renderTrendDots();
    writeTrendNote(fit, loess, roll, win);
  }

  function renderTrendDots() {
    tDots.textContent = "";
    const dim = (selected != null || hovered != null);
    tPts.concat(tPart).forEach(d => {
      const lift = d.ix === selected || d.ix === hovered;
      const g = el("g", { class: "dot-year" });
      const c = el("circle", {
        cx: tx(d.yr), cy: ty(d.m), r: lift ? 6 : 4,
        fill: colors[d.ix], opacity: dim && !lift ? 0.35 : 1,
      });
      // hollow ring = complete year; filled dot = incomplete, shown but not trusted
      if (!d.part) c.setAttribute("style", "fill:none;stroke:" + colors[d.ix] + ";stroke-width:2");
      g.appendChild(c);
      tDots.appendChild(g);
    });
  }

  function writeTrendNote(fit, loess, roll, win) {
    const p = P();
    const note = document.getElementById("trend-note");
    const hollow = tPart.length
      ? ` ${tPart.length} unvollständige Jahrgänge erscheinen als ausgefüllte Punkte und bleiben aussen vor.`
      : "";
    const tail = hollow + " Die Achse ist auf die Jahresmittel gezoomt.";
    const u = p.unit ? " " + p.unit : "";
    // end minus start of a smoothed curve — the honest "how much overall"
    const dd = pts => (pts[pts.length - 1].v >= pts[0].v ? "+" : "−")
      + p.rateNf.format(Math.abs(pts[pts.length - 1].v - pts[0].v));

    if (trendMode === "linear" && fit) {
      const x0 = tPts[0].yr, x1 = tPts[tPts.length - 1].yr;
      const perDecade = fit.slope * 10;
      const sign = perDecade > 0 ? "+" : "−";
      const dec = p.rateNf.format(Math.abs(perDecade));
      const tot = p.rateNf.format(Math.abs(fit.slope * (x1 - x0)));
      const r2 = new Intl.NumberFormat("de-CH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(fit.r2);
      note.textContent = (fit.r2 >= R2_STRONG
        ? `Ein Punkt je Jahrgang. Linearer Trend ${sign}${dec}${u} pro Jahrzehnt, `
          + `über ${x1 - x0} Jahre ${sign}${tot}${u} (r² = ${r2}). `
          + `Die gestrichelte Gerade stützt sich auf die vollständigen Jahrgänge ${x0}–${x1}.`
        : `Ein Punkt je Jahrgang. Kein erkennbarer Trend — die gestrichelte Ausgleichsgerade erklärt nur `
          + `r² = ${r2} der Schwankung, die Unterschiede zwischen den Jahren überwiegen deutlich `
          + `(rechnerisch ${sign}${dec}${u} pro Jahrzehnt). `
          + `Die Gerade stützt sich auf die vollständigen Jahrgänge ${x0}–${x1}.`) + tail;
    } else if (trendMode === "loess" && loess) {
      const x0 = tPts[0].yr, x1 = tPts[tPts.length - 1].yr;
      note.textContent = `Ein Punkt je Jahrgang. Die LOESS-Glättung — eine lokale Regression, `
        + `deren Spannweite jeweils die halbe Jahresliste umfasst — folgt den vollständigen `
        + `Jahrgängen ${x0}–${x1}; zwischen Kurvenanfang und -ende liegen ${dd(loess)}${u}.` + tail;
    } else if (trendMode === "roll" && roll) {
      note.textContent = `Ein Punkt je Jahrgang. Das gleitende Mittel fasst je ${win} Jahrgänge `
        + `zentriert zusammen und ist nur gezeichnet, wo das ganze Fenster in der Auswahl liegt `
        + `(${roll[0].yr}–${roll[roll.length - 1].yr}); zwischen Anfang und Ende liegen ${dd(roll)}${u}.` + tail;
    } else {
      const what = { linear: "eine Ausgleichsgerade", loess: "eine LOESS-Glättung",
                     roll: "ein gleitendes Mittel" }[trendMode];
      note.textContent = `Ein Punkt je Jahrgang. Für ${what} liegen im Bereich `
        + `${effLo()}–${effHi()} zu wenige vollständige Jahrgänge.` + hollow;
    }
  }

  /* nearest year wins, so the pointer never has to hit a 8px dot dead-centre */
  function nearestYear(ev) {
    const box = tSvg.getBoundingClientRect();
    const sx = ((ev.clientX - box.left) / box.width) * TW;
    let best = null, bestD = Infinity;
    tPts.concat(tPart).forEach(d => {
      const dd = Math.abs(tx(d.yr) - sx);
      if (dd < bestD) { bestD = dd; best = d; }
    });
    return bestD < 24 ? best : null;
  }

  tSvg.addEventListener("pointermove", ev => {
    const hit = nearestYear(ev);
    const p = P();
    if (!hit) { tTip.style.opacity = 0; hovered = null; render(); return; }
    hovered = hit.ix;

    tTip.textContent = "";
    const head = document.createElement("div");
    head.className = "tt-day";
    head.textContent = hit.part ? "Jahresmittel — Jahrgang unvollständig" : "Jahresmittel";
    tTip.appendChild(head);
    const row = document.createElement("div");
    row.className = "tt-row";
    const key = document.createElement("span");
    key.className = "tt-key";
    key.style.background = colors[hit.ix];
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = p.nf.format(hit.m) + (p.unit ? " " + p.unit : "");
    const lab = document.createElement("span");
    lab.className = "tt-lab";
    lab.textContent = hit.yr;
    row.append(key, val, lab);
    tTip.appendChild(row);

    tTip.style.opacity = 1;
    const box = tSvg.getBoundingClientRect();
    const px = (tx(hit.yr) / TW) * box.width;
    const flip = px > box.width - tTip.offsetWidth - 24;
    tTip.style.left = (flip ? px - tTip.offsetWidth - 14 : px + 14) + "px";
    tTip.style.top = "6px";
    render();
  });
  tSvg.addEventListener("pointerleave", () => { tTip.style.opacity = 0; hovered = null; render(); });
  tSvg.addEventListener("click", ev => {
    const hit = nearestYear(ev);
    selected = hit && selected !== hit.ix ? hit.ix : null;
    render();
  });

  /* ---- tabs: one parameter at a time, so the chart never carries two scales ---- */
  const tabsBox = document.getElementById("tabs");
  const panel = document.getElementById("panel");
  const tabs = PARAMS.map((p, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tab";
    b.id = "tab-" + p.key;
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(i === pi));
    b.tabIndex = i === pi ? 0 : -1;
    b.textContent = p.label;
    b.addEventListener("click", () => select(i));
    tabsBox.appendChild(b);
    return b;
  });

  tabsBox.addEventListener("keydown", ev => {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
    if (!step) return;
    ev.preventDefault();
    const next = (pi + step + tabs.length) % tabs.length;
    select(next);
    tabs[next].focus();
  });

  function select(i) {
    pi = i;
    tabs.forEach((b, k) => {
      b.setAttribute("aria-selected", String(k === i));
      b.tabIndex = k === i ? 0 : -1;
    });
    panel.setAttribute("aria-labelledby", tabs[i].id);
    svg.setAttribute("aria-label",
      "Tagesmittel " + P().label + " des Rheins bei Rekingen" +
      (P().unit ? " in " + P().unit : "") +
      ", ein Linienzug pro Jahr. Mit den Pfeiltasten Jahre durchgehen.");
    drawAxes();
    drawPaths();
    drawLegendTicks();
    paint();       // colors are per parameter; ends in render()
    syncRange();   // year buttons, trend fit and visibility follow the range
  }

  crosshair.setAttribute("y1", M.top);
  crosshair.setAttribute("y2", BASE_Y);
  select(0);
})();
</script>
"""

if __name__ == "__main__":
    main()
