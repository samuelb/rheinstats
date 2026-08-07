# Where to get Rhein @ Rekingen (BAFU station 2143) data

Station page: <https://www.hydrodaten.admin.ch/de/seen-und-fluesse/stationen-und-daten/2143>

Record start according to BAFU:

| Parameter                 | measured since |
| ------------------------- | -------------- |
| Abfluss (discharge)       | 1904           |
| Wasserstand (water level) | 1964           |
| Temperatur                | 1969           |
| Sauerstoff, Leitfähigkeit | 1976           |

## 1. Datenservice Hydrologie — the full record (recommended)

Free since 2020-01-01. Daily means/maxima/minima plus continuous data (5 min /
10 min / hourly, available from 1974). This is the only way to get the whole
series back to 1904/1964/1969.

- Info + order form: <https://www.bafu.admin.ch/de/datenservice-hydrologie-fuer-fliessgewaesser-und-seen>
- <hydrologie@bafu.admin.ch>, +41 58 464 71 87

Ask for: **station 2143 Rhein–Rekingen, Tagesmittel Abfluss + Wasserstand +
Wassertemperatur, gesamte Messreihe bis heute, CSV**. Takes a few days.

## 2. hydrodaten.admin.ch annual-plot JSON — 1981 onwards, scriptable

The Jahresganglinie on the station page is Plotly; the JSON behind it carries the
full daily-mean series:

```
https://www.hydrodaten.admin.ch/web/hydro/de/<plot>/2143/<year>/plot
   plot = p_annual | q_annual | temperature_annual
```

`fetch_hydrodaten.py` in this repo pulls it into `rhein_rekingen_daily.csv`.

Verified against the official Jahrestabelle PDF (2024 temperature): the API
matches to the PDF's rounding and carries two decimals instead of one.

Limits of this source:

- Only **1981 onwards** — an artifact of the portal, not the station. Stations
  with much longer records (2289 Basel, 2091 Rheinfelden) cut off at 1981 too.
- **1983, 1985 and 1986 return empty** for every parameter and every station
  tested — also a portal artifact, not a real measurement gap. Order those from
  the Datenservice.
- **1988 returns only 1 January** (reproducibly, all three parameters; 1987 and
  1989 are complete). Same story — order it.
- The x axis is a 365-day day-of-year grid, so **29 February is missing** in leap
  years.

## 3. Jahrestabellen PDFs — daily means, official, but PDF

`https://www.hydrodaten.admin.ch/documents/Jahrestabellen/2143<P>_<YY>.pdf`
where `<P>` is `Q` (Abfluss, 1993–2026) or `T` (Temperatur, 1997–2024).

Tables of Tagesmittel, one page per year, plus monthly means and extremes. Text
extracts cleanly (`gs -sDEVICE=txtwrite`), so they are usable as a cross-check
for 1993–1996 where the JSON API has data too. No water-level PDFs are offered.

## 4. Sources checked and rejected

- **LINDAS / `environment.ld.admin.ch`** (`lindas.admin.ch/foen/hydro`,
  SPARQL at <https://ld.admin.ch/query>) — current measurements only, no history.
- **opendata.swiss** — the BAFU hydro entries ("Messstationen Wassertemperatur",
  "Wassertemperatur der Flüsse", "Basismessnetz Oberflächengewässer") are station
  locations and current-value XML/JSON feeds, not archives. They point back at
  <hydrologie@bafu.admin.ch> for historical data.
- **api.existenz.ch** (`/apiv1/hydro/`) — third-party mirror of hydrodaten,
  10-minute values. Standard API keeps 32 days; the long-term InfluxDB archive
  only starts around 2018. Useful for live data, not for a long timeline.
- **GRDC** (<https://grdc.bafg.de/data/data_portal/>) — holds daily discharge for
  Swiss Rhine stations, but discharge only (no temperature) and research-use-only
  terms. Only worth it if BAFU cannot deliver.

## Note on "water level"

For a decades-long visualisation, **Abfluss (discharge, m³/s)** is the better
variable than Wasserstand. The record is longer (1904 vs 1964), and water level
at Rekingen is in m ü.M. against a datum affected by the run-of-river power plant
downstream, so it is less comparable across the decades than discharge is.
