# Fewer cases, more crime: Bangladesh 2019–2026

An interactive data story on the monthly crime statistics published by Bangladesh Police
Headquarters, January 2019 – August 2026.

**Live site:** https://spaul571.github.io/bangladesh-crime-viz/
**Explorer (filter by period, police unit and crime head):** https://spaul571.github.io/bangladesh-crime-viz/explorer.html

CSE628 Data Visualization, Fall 2026, Class Test 1 (group task).

## What is here

| Path | Contents |
|---|---|
| `data/Bangladesh_Crime_Statistics_Jan2019-Aug2026.xlsx` | The dataset: all 92 monthly PHQ tables merged into one sheet (1,564 rows = 92 months × 17 police units), each row tagged with the last day of its month (for example `30 Jun 2025`). Also lists the source PDF of every month and the translated table footnotes. |
| `data/bgd_adm1.geojson` | Boundaries of the eight divisions (geoBoundaries, CC0), for the maps. |
| `build_site.py` | Builds the website into `docs/`. |
| `analysis.py` | Loads the Excel file and computes every statistic and model behind the charts. |
| `charts.py` | The 24 interactive charts (Plotly and Vega-Altair), each in a light and a dark version. |
| `theme.py` | Colours and fonts shared by all charts. |
| `static/` | Page styles, the chart loader (`site.js`) and the explorer (`explorer.js`). |
| `docs/` | The built website, served by GitHub Pages. |

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

## Methods in brief

- **Before and after 5 August 2024:** 24 months before (Aug 2022 – Jul 2024) against 24 months after
  (Sep 2024 – Aug 2026), August 2024 excluded. Mann–Whitney U, Cliff's δ, bootstrap 95% CI.
- **Interrupted time series:** negative-binomial GLM with trend, post-break level and slope, month
  effects and COVID / August-2024 dummies.
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
