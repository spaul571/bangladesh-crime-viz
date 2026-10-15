# Fewer cases, more crime: Bangladesh 2019–2026

An interactive data story on the monthly crime statistics published by Bangladesh Police
Headquarters, January 2019 – September 2026.

**Live site:** https://spaul571.github.io/bangladesh-crime-viz/

One page. It opens on an overview that fits one screen on a laptop or desktop: filters for period,
police units and crime heads, eight tiles (totals and what changed) and eight charts, all following the
filters. Below it, the story with 26 interactive charts.

CSE628 Data Visualization, Fall 2026, Class Test 1 (group task).

## What is here

| Path | Contents |
|---|---|
| `data/Bangladesh_Crime_Statistics_Jan2019-Sep2026.xlsx` | The dataset: all 93 monthly PHQ tables merged into one sheet (1,581 rows = 93 months × 17 police units), each row tagged with the last day of its month (for example `30 Jun 2025`). Also lists the source PDF of every month and the translated table footnotes. |
| `data/raw_pdf/` | The 28 PDFs published by Bangladesh Police Headquarters (police.gov.bd), as downloaded: yearly bundles for 2019–2024, single months January 2025 – September 2026 and the January–December 2025 summary. Scanned tables; kept for reference, the site reads only the Excel file. |
| `data/bgd_adm1.geojson` | Boundaries of the eight divisions (geoBoundaries, CC0), for the maps. |
| `build_site.py` | Builds the website into `docs/`. |
| `analysis.py` | Loads the Excel file and computes every statistic and model behind the charts. |
| `charts.py` | The 26 interactive charts (Plotly and Vega-Altair), each in a light and a dark version. |
| `theme.py` | Colours and fonts shared by all charts. |
| `static/` | Page styles, the chart loader (`site.js`) and the overview (`explorer.js`). |
| `docs/` | The built website, served by GitHub Pages. |
| `pdf/Bangladesh_Crime_Story_2019-2026.pdf` | The website as a PDF (light theme, white background): the dashboard on page 1, then the story with every chart in its default view. |
| `make_pdf.py` | Prints the website to that PDF. |
| `powerbi/` | `CrimeVisuals.pbix`, a Power BI report on the same dataset (data to August 2026), and `CrimeVisuals.pdf`, its five pages exported. |

The site uses only the Excel file. National figures are the sum of the 17 police units.

## Rebuild

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/python build_site.py                   # about 2 minutes the first time
python -m http.server 8000 --directory docs      # then open http://localhost:8000
```

The SARIMAX forecasts are the slow step; results are cached in `.cache/` and recomputed only when the
Excel file changes. Open the site through a web server, as above; opening `docs/index.html` straight
from disk blocks the chart files from loading.

To refresh the PDF after the live site changes: `pip install playwright`, then `python make_pdf.py`
(uses Microsoft Edge; without it, run `playwright install chromium` once).

## Methods in brief

- **Before and after 5 August 2024:** 24 months before (Aug 2022 – Jul 2024) against 24 months after
  (Sep 2024 – Aug 2026), August 2024 excluded. Mann–Whitney U, Cliff's δ, bootstrap 95% CI.
- **Interrupted time series:** negative-binomial GLM with trend, post-break level and slope, month
  effects and COVID / August-2024 dummies.
- **The 2020 pandemic pause:** April–May 2020 (the general holiday) and July–September 2020 against the
  same months of 2019; each month around the 2020 and 2024 shocks as a % of the same month in the last
  normal year (2019 and 2023).
- **Seasonality:** robust STL decomposition (period 12) on log counts.
- **Forecasting:** SARIMAX on log counts with a regime dummy and Fourier seasonality, chosen by
  walk-forward backtest.
- **Change points and anomalies:** PELT (ruptures); Isolation Forest (scikit-learn).
- **Clustering:** k-means (k = 3) on the centred log-ratio of each unit's crime mix, shown with PCA.

## Sources

- Bangladesh Police Headquarters, monthly crime statistics, https://www.police.gov.bd/ (scanned PDFs,
  digitised with OCR and checked against the printed row, column and annual totals).
- Population: BBS Population and Housing Census 2022, adjusted figures (The Business Standard,
  9 April 2023).
- Division boundaries: geoBoundaries (CC0).

Recorded cases are not the same as crimes committed: recording depends on victims coming forward and
on police capacity.
