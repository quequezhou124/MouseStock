# Fallen Star backend audit and private real-price pilot

Last checked: 2026-10-24. The live website remains in `awaiting_data` state. All provider responses, the SQLite pilot database, episode inventory, and evaluation JSON are under gitignored `data/` and have not been published.

## What the backend actually does

`backend.py` imports security, price, corporate-action, and annual-revenue records into SQLite. It labels 20% drops against a preceding observed year, then tests whether a 15% rise from the post-drop low persists at the following monthly close. A continuing decline stays one episode; a new episode requires recovery to the prior peak. It now records the bounce-onset date separately from its confirmation date. Unresolved episodes are right-censored; a known delisting is a distinct outcome. Episodes with a possible onset awaiting confirmation are withheld from future-month predictions.

The predictor is an **age- and four-year drop-cohort competing-risk hazard baseline** with shrinkage toward the overall historical rate. It updates when the dataset is updated. It has no learned price, liquidity, sector, market, or financial feature coefficients and has **not** been calibrated on a representative market sample. Forecasts stop at 36 elapsed months from the drop or earlier when fewer than ten historical episodes are at risk. Annual growth uses six consecutive fiscal-year observations wholly from 2010 onward, each filed before the drop; the pilot has no qualifying financial facts.

Walk-forward code retrains the baseline at each historical cutoff and scores subsequent months with Brier score, log loss, calibration buckets, timing error, selected-month top-ten precision, year/exchange slices, and an issuer-cluster bootstrap interval. The original tests used synthetic series; the numbers below come from **real provider prices**. Monthly cutoffs of the same issuer/episode are correlated, and the five-stock pilot cannot validate delisting behavior or a general U.S./Canadian predictor.

## Sources investigated and coverage

| Source | Accessible result | Historical/delisted scope | Limitation |
| --- | --- | --- | --- |
| [EODHD end-of-day API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) with public demo token | Ingested AAPL, MSFT, AMZN, TSLA, MCD; 21,018 daily bars from 2010-01-04 through 2026-10-23 (TSLA from 2010-06-29); provider-adjusted close, volume, and split dates | **Five active U.S. stocks only** in this pilot; zero delisted and zero Canadian | Demo is for evaluation. Its adjusted close includes splits and dividends. We did not establish permission to publish derived results. [EODHD's delisted endpoint](https://eodhd.com/financial-apis/delisted-stock-companies-data-2) requires broader access and has weaker fundamentals coverage for older delistings. |
| [SEC EDGAR company facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Official API and filing dates documented; requests from this environment returned HTTP 403 | U.S. filings; not complete Canadian coverage | No SEC facts were imported in this run. EODHD's current fundamentals response included `filing_date`, but we did not treat its current normalized values as point-in-time historical vintages. |
| [Nasdaq Trader symbol directory](https://nasdaqtrader.com/trader.aspx?id=symbollookup) | Used by the existing names-only current masterlist | Current-day listings only | Does not reconstruct delisted historical securities. [Nasdaq Daily List](https://www.nasdaqtrader.com/Trader.aspx?id=DailyListPD) has historical listing changes but is a subscription product. |
| [Nasdaq WIKI prices](https://data.nasdaq.com/databases/WIKIP) | Public-domain historical dataset documented; API request from this environment returned HTTP 403 | About 3,000 U.S. tickers, ending April 2018 | Unsupported and stale; unsuitable for present-day forecasts even if access is restored. |
| [TMX historical products](https://www.tmx.com/resource/en/268), [CSE market data](https://thecse.com/trading/market-data/), [SEDAR+](https://sedarplus.ca/onlinehelp/terms-of-use/) | No Canadian historical feed ingested | Required for TSX, TSXV, CSE and Canadian statements | Exchange historical products require licensing; SEDAR+ restricts automated collection and reuse. |

No subscription or dataset was purchased. As a possible paid route, [EODHD lists a historical-price plan at $19.99/month when billed monthly](https://eodhd.com/pricing) and describes delisted-symbol access, but its [personal-use terms](https://eodhd.com/financial-apis/commercial-vs-personal-license-use), historical identity coverage, Canadian coverage, point-in-time financial revisions, and public output rights all need verification before purchase or publication. Research-grade alternatives include [Nasdaq Sharadar SEP](https://data.nasdaq.com/databases/SEP/documentation?anchor=sample-data) and [CRSP U.S. stock data](https://www.crsp.org/research/crsp-us-stock-databases-2025-layout/); neither was acquired.

## Real historical episodes

At the 2026-10-23 pilot as-of date, the agreed event rules produced **34 drops: 33 confirmed bounces, one unresolved episode, zero delistings**. The 33/34 bounce share reflects this active-only sample and must not be used as a market estimate.

Two price-level checks against the imported daily bars:

- AAPL on 2020-03-12: adjusted close 59.872 versus preceding-year high 78.9192, a 24.14% drop. The post-drop low through the onset month was 54.117; the 15% threshold was 62.2345. The 2020-04-30 close was 70.8632 and the 2020-05-29 close was 76.8933, so onset and confirmation are separate months.
- AAPL on 2018-11-20: adjusted close 41.9553 versus preceding-year high 54.8238, a 23.47% drop. The post-drop low was 33.7079; the 15% threshold was 38.7641. The 2019-01-31 close was 39.4567 and the 2019-02-28 close was 41.2234.

The imported split dates did not create mechanical crash labels: adjusted one-day changes at AAPL's 2020-08-31 split, TSLA's 2022-08-25 split, and AMZN's 2022-06-06 split were +3.39%, -0.35%, and +1.99% respectively. These spot checks support the adapter's adjustment choice for this pilot; they are not a full corporate-action audit.

## Exploratory walk-forward results

At each **monthly** cutoff, the evaluator reconstructs episodes using prices available by that cutoff, fits the cohort hazard, and scores up to 12 future onset months. The simpler comparator is a constant bounce/delisting hazard estimated only from the same training cutoff. Outcomes are read from later price months; open cases without follow-up are censored.

| Window | Eligible open episode instances after pending-onset exclusion | Scored stock-month observations | Cohort Brier | Constant-hazard Brier | Cohort log loss | Constant-hazard log loss |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development cutoffs, Jan 2016–Dec 2023 | 34 | 27, from 4 issuers | 0.157265 | **0.150282** | 0.497487 | 0.475779 |
| Later exploratory cutoffs, Jan 2024–Sep 2025 | 5 | 18, from 3 issuers | 0.193230 | **0.191213** | 0.562333 | 0.555343 |

The figures and other metrics should be read from the private JSON reports if the code or data changes. In the later window, 5 of 18 scored target months were actual onsets. The monthly top-ten precision was 0.2667; all 18 observations were NASDAQ and had 2025 target months, so exchange/era comparisons are **not estimable** there. The median absolute onset timing error among five evaluable bounces was zero months, but this does not repair poor probability calibration or missing market coverage. The issuer-cluster 95% bootstrap interval for **cohort minus constant-hazard Brier** was approximately -0.0038 to +0.0068; only three issuer clusters contributed.

This later period is *not a pristine final holdout*: an earlier exploratory run inspected part of it before the pending-onset correction. A genuinely untouched final period must be reserved after a broader, survivor-inclusive dataset and model specification are fixed.

## Publication decision and blockers

**Do not publish the pilot forecasts.** The cohort model did not outperform the simpler baseline in this sample, the probabilities are not reliably calibrated, no delisted or Canadian securities were included, and no point-in-time revenue facts were imported. The existing GitHub Pages manifest remains `awaiting_data`; no real-data result JSON was written under `docs/`.

Full coverage requires a permitted historical U.S./Canadian feed containing inactive securities, delisting outcomes, stable security IDs and symbol histories, adjusted daily bars with actions, plus point-in-time financial statements. Provider rights for public candidate scores and evidence must be checked. Only then can the model be compared with its baseline on a genuinely untouched later period and the current frontend be populated safely.
