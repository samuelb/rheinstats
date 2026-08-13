#!/usr/bin/env python3
"""Fetch daily means (Tagesmittel) for a BAFU hydro station from hydrodaten.admin.ch.

This is the *complementary* source: the primary data are the full-series CSV
exports of the BAFU Datenservice Hydrologie in measurements/. build_site.py
takes the CSV written here only for days the export does not cover — run this
to pick up the days since the export date, until a fresh export replaces them.

The public station pages render their "Jahresganglinie" with Plotly. The JSON
behind those plots contains the full daily-mean series for the selected year, at
higher precision than the published Jahrestabellen PDFs.

    https://www.hydrodaten.admin.ch/web/hydro/de/<plot>/<station>/<year>/plot

Caveats of this source (see README):
  * only ~1981 onwards is served, and 1983/1985/1986 come back empty
  * the x axis is a 365-day day-of-year grid, so 29 February is missing

Usage:
    python3 fetch_hydrodaten.py                 # station 2143, 1981..current
    python3 fetch_hydrodaten.py --station 2091 --start 2000 --end 2024
"""

import argparse
import csv
import datetime as dt
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "https://www.hydrodaten.admin.ch/web/hydro/de/{plot}/{station}/{year}/plot"

# plot name -> (column name, unit)
PARAMS = {
    "p_annual": ("waterlevel_m", "m ü.M."),
    "q_annual": ("discharge_m3s", "m³/s"),
    "temperature_annual": ("temperature_c", "°C"),
}


def fetch_year(station, plot, year):
    """Return {date: value} of daily means, or {} if the year has no data."""
    url = BASE.format(plot=plot, station=station, year=year)
    with urllib.request.urlopen(url, timeout=60) as r:
        doc = json.load(r)

    # The series for the requested year is the trace literally named e.g. "2020";
    # the others are the reference-period percentiles, median and current year.
    trace = next(
        (t for t in doc["plot"]["data"] if str(t.get("name")) == str(year)), None
    )
    if trace is None:
        return {}

    out = {}
    for stamp, value in zip(trace.get("x") or [], trace.get("y") or []):
        if value is None:
            continue
        # x is a day-of-year grid stamped with the *current* year -> re-date it.
        month, day = stamp.split("-")[1:]
        out[dt.date(year, int(month), int(day))] = value
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", default="2143")
    ap.add_argument("--start", type=int, default=1981)
    ap.add_argument("--end", type=int, default=dt.date.today().year)
    ap.add_argument("--out", default="rhein_rekingen_daily.csv")
    args = ap.parse_args()

    years = range(args.start, args.end + 1)
    jobs = [(plot, y) for plot in PARAMS for y in years]

    def run(job):
        plot, year = job
        try:
            return job, fetch_year(args.station, plot, year)
        except Exception as exc:  # noqa: BLE001 - report and carry on
            print(f"  ! {plot} {year}: {exc}")
            return job, {}

    rows = {}
    with ThreadPoolExecutor(6) as pool:
        for (plot, year), series in pool.map(run, jobs):
            column = PARAMS[plot][0]
            for date, value in series.items():
                rows.setdefault(date, {})[column] = value
            print(f"  {plot:20s} {year}  {len(series):3d} days")

    columns = [PARAMS[p][0] for p in PARAMS]
    with open(args.out, "w", newline="\n") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date"] + columns)
        for date in sorted(rows):
            writer.writerow([date.isoformat()] + [rows[date].get(c, "") for c in columns])

    missing = [y for y in years if not any(d.year == y for d in rows)]
    print(f"\n{len(rows)} days -> {args.out}")
    if missing:
        print(f"years with no data at all: {missing}")


if __name__ == "__main__":
    main()
