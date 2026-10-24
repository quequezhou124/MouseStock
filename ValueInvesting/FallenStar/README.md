# Fallen Star backend

`backend.py` implements the historical-data import, drop/bounce labeling, pre-drop revenue-growth check, monthly competing-risk cohort forecast, selected-month JSON export, and walk-forward evaluation. It uses the Python standard library. [PLAN.md](PLAN.md) records the research rules.

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
python3 -m unittest discover -p 'test_backend.py'
```

By default the SQLite database is `data/fallen_star.sqlite`; `--db` changes it. `data/` is gitignored because it may contain licensed or nonpublic data. Generated forecasts are private until their publication rights and evaluation have been checked. The website does not consume the export yet.

## Current model and limits

The forecast is an age- and four-year drop-cohort-specific monthly bounce/delisting hazard estimated from 2011-onward episodes, smoothed toward the overall observed rate. It returns a candidate for the requested month when that month has the highest supported onset probability. At least ten historical episodes must still be at risk at an elapsed month before that month is forecast. No result is produced beyond 36 months or where historical support is insufficient.

This is an initial statistical model, not a calibrated production prediction. Evaluation reports Brier score, log loss, probability calibration, and monthly top-ten precision against a simpler training-only constant-hazard baseline. Before publishing forecasts, add broader market-regime evaluation, licensed data coverage audits, and a release threshold based on out-of-sample results. A blank result may mean no matching stocks or insufficient history; inspect `unsupported_active_episodes`, `training_episodes`, and `data_quality_warnings`.
