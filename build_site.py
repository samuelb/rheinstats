#!/usr/bin/env python3
"""Build the Rekingen spaghetti charts from rhein_rekingen_daily.csv.

One chart per measured parameter, switched by tabs — never two scales on one
plot. Writes two files from one template:
  index.html     standalone page, open it locally
  artifact.html  the same body, without the html/head wrapper
"""

import csv
import datetime as dt
import json
import math
import statistics as st
from collections import defaultdict

import ramp

CSV_IN = "rhein_rekingen_daily.csv"
MIN_DAYS = 30    # a year with fewer points than this is a portal artifact, not a line
FULL_DAYS = 360  # below this a year's mean is not comparable, so it stays out of the trend
R2_STRONG = 0.1  # under this the fit explains so little that calling it a trend would mislead

MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# column, tab label, unit, decimals shown, encoding scale/offset, zero baseline?
# Water level is an altitude in m ü.M., so a zero baseline would be meaningless —
# discharge and temperature both have a real zero and keep one.
PARAMS = [
    dict(key="temperature", col="temperature_c", label="Temperatur",
         unit="°C", decimals=1, scale=10, offset=0, zero=True),
    dict(key="discharge", col="discharge_m3s", label="Abfluss",
         unit="m³/s", decimals=0, scale=10, offset=0, zero=True),
    dict(key="level", col="waterlevel_m", label="Wasserstand",
         unit="m ü.M.", decimals=2, scale=1000, offset=320, zero=False),
]


def load():
    """-> (years, {param key: {year: [365 values]}}, missing years) on a non-leap grid."""
    data = {p["key"]: defaultdict(lambda: [None] * 365) for p in PARAMS}
    for row in csv.DictReader(open(CSV_IN)):
        date = dt.date.fromisoformat(row["date"])
        if (date.month, date.day) == (2, 29):
            continue  # not on the grid; the source omits it anyway
        index = sum(MONTH_LENGTHS[: date.month - 1]) + date.day - 1
        for p in PARAMS:
            if row[p["col"]]:
                data[p["key"]][date.year][index] = float(row[p["col"]])

    counts = data[PARAMS[0]["key"]]
    years = [y for y in sorted(counts) if sum(v is not None for v in counts[y]) >= MIN_DAYS]
    # everything the source skipped, plus years too sparse to draw as a line
    missing = [y for y in range(years[0], years[-1] + 1) if y not in years]
    return years, data, missing


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
    """Annual means plus a least-squares fit over them.

    Only years that are essentially complete take part — a partial year's mean is
    biased by whichever seasons it happens to contain and is not comparable.
    """
    pts = [(i, y, by_year[y]) for i, y in enumerate(years)
           if sum(v is not None for v in by_year[y]) >= FULL_DAYS]
    idx = [i for i, _, _ in pts]
    yrs = [y for _, y, _ in pts]
    means = [st.fmean(v for v in vals if v is not None) for _, _, vals in pts]

    slope, intercept = st.linear_regression(yrs, means)
    r = st.correlation(yrs, means)
    domain, ticks = axis_for(means, zero=False)

    return {
        "idx": idx,
        "means": [round(m, 4) for m in means],
        "x0": yrs[0], "x1": yrs[-1],
        "xticks": [y for y in range(math.ceil(yrs[0] / 5) * 5, yrs[-1] + 1, 5)],
        "domain": domain, "ticks": ticks,
        "y0": round(slope * yrs[0] + intercept, 4),   # fitted line endpoints
        "y1": round(slope * yrs[-1] + intercept, 4),
        "perDecade": round(slope * 10, 4),
        "total": round(slope * (yrs[-1] - yrs[0]), 4),
        "r2": round(r * r, 3),
        "strong": r * r >= R2_STRONG,
        "dropped": [y for y in years if y not in yrs],
    }


def main():
    years, data, missing = load()
    span = years[-1] - years[0]
    positions = [(y - years[0]) / span for y in years]

    # the legend gradient is sampled evenly so it stays a true year scale even
    # though the drawn years are not evenly spaced
    stops = [i / 60 for i in range(61)]

    params = []
    for p in PARAMS:
        by_year = data[p["key"]]
        flat = [v for y in years for v in by_year[y] if v is not None]
        domain, ticks = axis_for(flat, p["zero"])
        params.append({
            "key": p["key"], "label": p["label"], "unit": p["unit"],
            "decimals": p["decimals"], "scale": p["scale"], "offset": p["offset"],
            "domain": domain, "ticks": ticks,
            "series": [encode(by_year[y], p["scale"], p["offset"]) for y in years],
            "trend": trend_for(years, by_year),
        })

    payload = {
        "years": years,
        "params": params,
        "light": ramp.ramp(positions, "light"),
        "dark": ramp.ramp(positions, "dark"),
        "legendLight": ramp.ramp(stops, "light"),
        "legendDark": ramp.ramp(stops, "dark"),
        "months": MONTHS,
        "monthLengths": MONTH_LENGTHS,
    }

    counts = data[PARAMS[0]["key"]]
    partial = [y for y in years if sum(v is not None for v in counts[y]) < 360]
    note = (
        f"{len(years)} Jahrgänge, {years[0]}–{years[-1]}. "
        f"Nicht abgedeckt: {', '.join(str(y) for y in missing)} — "
        "auf hydrodaten.admin.ch nicht abrufbar. "
        f"{', '.join(str(y) for y in partial)} unvollständig. "
        "Der 29. Februar fehlt quellenbedingt."
    )

    body = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False)).replace(
        "__NOTE__", note
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

TEMPLATE = r"""<title>Der Rhein bei Rekingen — Temperatur, Abfluss, Wasserstand</title>
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
    display: inline-flex; gap: 2px; padding: 3px; margin-bottom: 14px;
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
  .trend-line.weak { opacity: 0.28; }
  .spine { stroke: var(--axis); stroke-width: 1; fill: none; opacity: 0.55; }
  .dot-year circle { stroke: var(--surface-1); stroke-width: 2; }

  .legend { margin: 18px 0 4px; }
  .legend-bar { height: 8px; border-radius: 4px; border: 1px solid var(--hairline); }
  .legend-ticks {
    position: relative; height: 14px; margin-top: 5px;
    font-size: 0.7rem; color: var(--text-muted); font-variant-numeric: tabular-nums;
  }
  .legend-ticks span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
  .legend-cap { font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 6px; }

  .years { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 16px; }
  .yr {
    font: inherit; font-size: 0.72rem; font-variant-numeric: tabular-nums;
    color: var(--text-secondary); background: transparent;
    border: 1px solid transparent; border-radius: 6px;
    padding: 3px 6px 3px 5px; cursor: pointer;
    display: inline-flex; align-items: center; gap: 5px;
  }
  .yr:hover { background: var(--ghost); }
  .yr:focus-visible { outline: 2px solid var(--text-primary); outline-offset: 2px; }
  .yr[aria-pressed="true"] { color: var(--text-primary); font-weight: 600; border-color: var(--axis); }
  .yr-key { width: 10px; height: 3px; border-radius: 2px; flex: none; }
  .note { font-size: 0.75rem; color: var(--text-muted); margin-top: 22px; line-height: 1.6; }
  .note a { color: inherit; }
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
      <div class="legend-cap">Messjahr</div>
      <div class="legend-bar" id="legend-bar"></div>
      <div class="legend-ticks" id="legend-ticks"></div>
    </div>
  </div>

  <div class="card">
    <div class="card-head"><h2 class="card-title" id="trend-title">Jahresmittel im Vergleich</h2></div>
    <p class="card-note" id="trend-note"></p>
    <div class="plot" id="trend-plot">
      <svg id="trend" viewBox="0 0 960 250" role="img" aria-label="Jahresmittel je Jahrgang mit linearem Trend">
        <g id="trend-grid"></g>
        <path id="trend-spine" class="spine"></path>
        <path id="trend-fit" class="trend-line"></path>
        <g id="trend-dots"></g>
        <g id="trend-axes"></g>
      </svg>
      <div class="tooltip" id="trend-tooltip" role="status" aria-live="polite"></div>
    </div>
  </div>

  <div class="years" id="years" role="group" aria-label="Jahr auswählen"></div>

  <p class="note">
    Quelle: Bundesamt für Umwelt BAFU, Station 2143 Rhein–Rekingen, Tagesmittel
    von Wassertemperatur, Abfluss und Wasserstand, abgerufen über die
    Jahresganglinien von hydrodaten.admin.ch. Der Wasserstand ist eine Höhe über
    Meer, seine Achse beginnt daher nicht bei null. __NOTE__
  </p>
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
  let colors = isDark() ? D.dark : D.light;

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
    yTitle.textContent = p.unit;
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
    colors = dark ? D.dark : D.light;
    paths.forEach((p, i) => p.setAttribute("stroke", colors[i]));
    document.getElementById("legend-bar").style.background =
      "linear-gradient(to right," + (dark ? D.legendDark : D.legendLight).join(",") + ")";
    document.querySelectorAll(".yr-key").forEach((k, i) => { k.style.background = colors[i]; });
    render();
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", paint);
  new MutationObserver(paint).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  /* ---- legend ticks, placed at their true position on the year scale ---- */
  const Y0 = YEARS[0], Y1 = YEARS[N - 1], SPAN = Y1 - Y0;
  const ticks = document.getElementById("legend-ticks");
  [Y0, 1990, 2000, 2010, 2020, Y1].forEach(yr => {
    const s = document.createElement("span");
    s.textContent = yr;
    const f = (yr - Y0) / SPAN;
    s.style.left = (f * 100) + "%";
    if (f < 0.02) s.style.transform = "none";
    if (f > 0.98) s.style.transform = "translateX(-100%)";
    ticks.appendChild(s);
  });

  /* ---- state ---- */
  let selected = null, hovered = null, cursorDay = null;

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

  function fmt(v) { return P().nf.format(v) + " " + P().unit; }

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
  // keyboard: the chart itself steps through years, so selection never needs a pointer
  svg.addEventListener("keydown", ev => {
    const step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[ev.key];
    if (step) {
      selected = selected == null ? (step > 0 ? 0 : N - 1)
                                  : Math.min(N - 1, Math.max(0, selected + step));
      if (cursorDay == null) cursorDay = 195;   // mid-July, where the years spread widest
      ev.preventDefault();
      render();
    } else if (ev.key === "Home") { selected = 0; ev.preventDefault(); render(); }
    else if (ev.key === "End") { selected = N - 1; ev.preventDefault(); render(); }
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
  const tSpine = document.getElementById("trend-spine");
  const tTip = document.getElementById("trend-tooltip");

  const tx = yr => {
    const t = P().trend;
    return TM.left + ((yr - t.x0) / (t.x1 - t.x0)) * TPW;
  };
  const ty = v => {
    const [lo, hi] = P().trend.domain;
    return TM.top + TPH - ((v - lo) / (hi - lo)) * TPH;
  };

  function drawTrend() {
    const p = P(), t = p.trend;
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
    t.xticks.forEach(yr => {
      const lb = el("text", { class: "tick", x: tx(yr), y: base + 18, "text-anchor": "middle" });
      lb.textContent = yr;
      tAxes.appendChild(lb);
    });
    const unit = el("text", { class: "axis-title", x: TM.left - 9, y: TM.top - 12, "text-anchor": "end" });
    unit.textContent = p.unit;
    tAxes.appendChild(unit);

    // the year-to-year line stays recessive; it is context for the fit, not the point
    // break the line across missing years rather than implying a measurement
    tSpine.setAttribute("d", t.idx.map((ix, k) => {
      const gap = k > 0 && YEARS[ix] - YEARS[t.idx[k - 1]] > 1;
      return (k && !gap ? "L" : "M") + tx(YEARS[ix]).toFixed(1) + " " + ty(t.means[k]).toFixed(1);
    }).join(" "));

    tFit.setAttribute("d", `M${tx(t.x0).toFixed(1)} ${ty(t.y0).toFixed(1)} L${tx(t.x1).toFixed(1)} ${ty(t.y1).toFixed(1)}`);
    tFit.classList.toggle("weak", !t.strong);

    renderTrendDots();
    writeTrendNote();
  }

  function renderTrendDots() {
    const t = P().trend;
    tDots.textContent = "";
    t.idx.forEach((ix, k) => {
      const lift = ix === selected || ix === hovered;
      const g = el("g", { class: "dot-year" });
      g.appendChild(el("circle", {
        cx: tx(YEARS[ix]), cy: ty(t.means[k]), r: lift ? 6 : 4,
        fill: colors[ix], opacity: (selected != null || hovered != null) && !lift ? 0.35 : 1,
      }));
      tDots.appendChild(g);
    });
  }

  function writeTrendNote() {
    const p = P(), t = p.trend;
    const note = document.getElementById("trend-note");
    const sign = t.perDecade > 0 ? "+" : "−";
    const dec = p.rateNf.format(Math.abs(t.perDecade));
    const tot = p.rateNf.format(Math.abs(t.total));
    const r2 = new Intl.NumberFormat("de-CH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(t.r2);

    note.textContent = t.strong
      ? `Ein Punkt je Jahrgang. Linearer Trend ${sign}${dec} ${p.unit} pro Jahrzehnt, `
        + `über ${t.x1 - t.x0} Jahre ${sign}${tot} ${p.unit} (r² = ${r2}). `
        + `Nur vollständige Jahrgänge, ${t.x0}–${t.x1}; die Achse ist auf die Jahresmittel gezoomt.`
      : `Ein Punkt je Jahrgang. Kein erkennbarer Trend — die Ausgleichsgerade erklärt nur `
        + `r² = ${r2} der Schwankung, die Unterschiede zwischen den Jahren überwiegen deutlich `
        + `(rechnerisch ${sign}${dec} ${p.unit} pro Jahrzehnt). `
        + `Nur vollständige Jahrgänge, ${t.x0}–${t.x1}; die Achse ist auf die Jahresmittel gezoomt.`;
  }

  /* nearest year wins, so the pointer never has to hit a 8px dot dead-centre */
  function nearestYear(ev) {
    const t = P().trend;
    const box = tSvg.getBoundingClientRect();
    const sx = ((ev.clientX - box.left) / box.width) * TW;
    let best = null, bestD = Infinity;
    t.idx.forEach((ix, k) => {
      const d = Math.abs(tx(YEARS[ix]) - sx);
      if (d < bestD) { bestD = d; best = { ix, k }; }
    });
    return bestD < 24 ? best : null;
  }

  tSvg.addEventListener("pointermove", ev => {
    const hit = nearestYear(ev);
    const p = P(), t = p.trend;
    if (!hit) { tTip.style.opacity = 0; hovered = null; render(); return; }
    hovered = hit.ix;

    tTip.textContent = "";
    const head = document.createElement("div");
    head.className = "tt-day";
    head.textContent = "Jahresmittel";
    tTip.appendChild(head);
    const row = document.createElement("div");
    row.className = "tt-row";
    const key = document.createElement("span");
    key.className = "tt-key";
    key.style.background = colors[hit.ix];
    const val = document.createElement("span");
    val.className = "tt-val";
    val.textContent = p.nf.format(t.means[hit.k]) + " " + p.unit;
    const lab = document.createElement("span");
    lab.className = "tt-lab";
    lab.textContent = YEARS[hit.ix];
    row.append(key, val, lab);
    tTip.appendChild(row);

    tTip.style.opacity = 1;
    const box = tSvg.getBoundingClientRect();
    const px = (tx(YEARS[hit.ix]) / TW) * box.width;
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
      "Tagesmittel " + P().label + " des Rheins bei Rekingen in " + P().unit +
      ", ein Linienzug pro Jahr. Mit den Pfeiltasten Jahre durchgehen.");
    drawAxes();
    drawPaths();
    drawTrend();
    render();
  }

  crosshair.setAttribute("y1", M.top);
  crosshair.setAttribute("y2", BASE_Y);
  select(0);
  paint();
})();
</script>
"""

if __name__ == "__main__":
    main()
