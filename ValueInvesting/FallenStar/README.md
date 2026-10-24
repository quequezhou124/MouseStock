# Fallen Star backend

`backend.py` implements the historical-data import, drop/bounce labeling, pre-drop revenue-growth check, monthly competing-risk cohort **baseline**, selected-month JSON export, and walk-forward evaluation. It uses the Python standard library. [PLAN.md](PLAN.md) records the research rules; [REAL_DATA_AUDIT.md](REAL_DATA_AUDIT.md) reports the private real-price pilot and its limits.

## Data input

Create a private directory containing UTF-8 CSV files. The required files are:

| File | Columns |
| --- | --- |
| `securities.csv` | `security_id,issuer_id,name,ticker,exchange,country,listed_on,delisted_on,cik` |
| `prices.csv` | `security_id,trading_date,adjusted_close,volume` |

Optional files:

| File | Columns |
| --- | --- |
| `revenues.csv` | `issuer_id,fiscal_start,fiscal_end,filed_on,revenue,currency,source` |
| `actions.csv` | `security_id,action_date,action_type` (`split`, `dividend`, `spinoff`, `halt`, `other`) |

Dates are ISO `YYYY-MM-DD`; country is `US` or `CA`. IDs must remain stable across ticker changes; cross-listed securities share an issuer ID. `adjusted_close` must be split-adjusted and in the listing currency. The provider must include delisted securities and their final dates. Keep the original provider snapshots in the private data directory for audit; the database records their hashes. Prices and entire annual fiscal periods before 2010 are ignored. Prices require a full observed trailing year and at least 200 sessions to create a drop. Corporate-action records help suppress mechanical drops. A missing optional file is allowed, but missing revenues produce `Unknown` health.

The current names-only Excel masterlist cannot supply these historical records. SEC annual revenue can be imported one issuer at a time using its CIK and a contact User-Agent; Canadian annual revenue and historical prices require a separate permitted source. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) describes its company facts data and access rules.

## Commands

Run from `ValueInvesting/FallenStar`:

```sh
python3 backend.py ingest /private/path/to/provider-csvs
python3 backend.py sec-revenue ISSUER_ID CIK --user-agent 'MouseStocks contact@example.com'
python3 backend.py run --as-of 2026-10-24 --target 2026-11 --output data/forecast-2026-11.json
python3 backend.py evaluate --cutoffs 2020-12-31 2021-12-31 --horizon 12
python3 backend.py episodes --as-of 2026-10-23 --output data/episodes.json
python3 -m unittest discover -p 'test_backend.py'
```

By default the SQLite database is `data/fallen_star.sqlite`; `--db` changes it. `data/` is gitignored because it may contain licensed or nonpublic data. Generated forecasts are private until their publication rights and evaluation have been checked.

## Private real-price pilot

`ingest_eodhd.py` downloads the EODHD demo histories for AAPL, MSFT, AMZN, TSLA, and MCD into `data/eodhd_demo.sqlite`, with raw provider responses under `data/eodhd_demo/raw/`. Run `python3 ingest_eodhd.py` from this directory. It uses the public `demo` token unless `EODHD_API_TOKEN` is set. The pilot has five currently active U.S. stocks, no delisted securities, no Canadian securities, and **no point-in-time annual revenues**. EODHD's `adjusted_close` includes split and dividend adjustments; the pilot also imports split dates. This dataset is for private method verification, not public candidate publication.

## Website result contract

The GitHub Pages page at `docs/value-investing/fallen-star/` reads `data/manifest.json` and one result file named `data/YYYY-MM.json` for each published bounce month. The result files use the JSON produced by `backend.py run`; each must contain its matching `target_month`, `as_of`, `model_version`, and complete `candidates` list. The frontend applies the Financially Healthy checkbox to that full list and exports the same filtered and sorted rows to Excel.

After historical data rights and out-of-sample performance have been reviewed, generate the next 12 months of approved result files from the **same as-of snapshot**, then set the manifest to `{"status":"ready","as_of":"YYYY-MM-DD","model_version":"...","months":["YYYY-MM",...]}` with only the published months. Publish the manifest last so the page never advertises missing files. Until then, leave the manifest in `awaiting_data` state. Do not place the SQLite database, provider CSVs, or unapproved financial records under `docs/`.

## Current model and limits

The forecast is an age- and four-year drop-cohort-specific monthly bounce/delisting hazard estimated from 2011-onward episodes, smoothed toward the overall observed rate. This is a **historical cohort baseline, not a feature-trained machine-learning model**. It returns a candidate for the requested month when that month has the highest supported onset probability. An episode with a possible, unconfirmed onset is withheld until the following month's close can confirm or reject it. At least ten historical episodes must still be at risk at an elapsed month before that month is forecast. No result is produced beyond 36 months or where historical support is insufficient.

This baseline is not a calibrated production prediction. Evaluation reports Brier score, log loss, probability calibration, onset timing error, monthly top-ten precision, year/exchange breakdowns, and an issuer-cluster uncertainty interval against a simpler training-only constant-hazard baseline. The private five-stock pilot did not beat that baseline in its later exploratory window. Before publishing forecasts, obtain historical delisted and Canadian coverage, point-in-time financial facts, a fresh untouched evaluation period, and demonstrated out-of-sample improvement. A blank result may mean no matching stocks or insufficient history; inspect `unsupported_active_episodes`, `training_episodes`, and `data_quality_warnings`.
