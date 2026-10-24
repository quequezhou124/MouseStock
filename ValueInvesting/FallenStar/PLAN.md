# Fallen Star plan

Status: planning. No Fallen Star data pipeline, model, or filter has been implemented.

## Goal

For a user-selected future month, identify stocks whose price has had a qualifying drop and whose bounce is predicted to start in that month. Let the user narrow those results to companies with five years of growth evidence available before the drop. Results are ranked candidates, not guaranteed rebounds.

## Historical starting point

Treat **January 1, 2010 as the start of the usable history**. Do not use prices, fiscal periods, filings, drop events, outcomes, or model features from before that date. The current masterlist defines the stocks screened now; historical training and evaluation also include securities that traded from 2010 onward but have since delisted.

This starting point creates two warm-up periods:

- A drop needs a preceding 12 months of observed prices. Drops during 2010 cannot be labeled under the full-lookback rule; the first eligible drops are approximately January 2011, once a security has 12 months of post-start history.
- The proposed financial-health rule needs six consecutive annual revenue observations to measure five year-to-year intervals, with all fiscal periods ending in 2010 or later and all reports filed before the drop. For a calendar-year reporter, fiscal years 2010–2015 can first support the check after the 2015 report is filed, generally in 2016. Earlier drops have **Unknown** health rather than inferred growth from pre-2010 data. Other fiscal-year schedules and filing dates shift the first eligible date.

Training and evaluation must respect these warm-up periods. A prediction may use only observations available by its historical as-of date. Episodes still open at the end of the available history remain unresolved, not failures.

## Agreed behavior

| Item | Rule |
| --- | --- |
| Big drop | The adjusted closing price first falls **20% or more** below its preceding 12-month high. A continuing decline is one episode. |
| Recency | No fixed cutoff such as “dropped in the last 12 months.” Each unresolved drop remains eligible while it is within the model's validated forecast horizon. |
| Target month | The user selects any future calendar month. Show stocks whose predicted bounce-onset month equals that month, ranked by the probability assigned to it. Mark unsupported forecast horizons rather than extrapolating. |
| Time to bounce | Count elapsed calendar months from the drop month to the predicted bounce month. September to November is two elapsed months; September plus three months is December. |
| Financially healthy checkbox | Use five years of growth evidence from financial reports filed before the drop. The proposed first rule is revenue growth over the period and increases in at least three intervening years. Missing history is **Unknown**, not Pass. |

A proposed bounce label is a 15% rise from the low after the drop that holds into the next month. This label and the growth rule require validation against historical cases before they become final production definitions.

“Nothing fundamentally changed” is a separate review item. The drop, bounce, and pre-drop growth rules alone do not establish it.

## Data foundation

The existing ValueInvesting masterlist is names-only. Build a 2010-onward historical security and issuer map with exchange, stable IDs, ticker changes, corporate actions, listing and delisting dates, adjusted prices, volume, and point-in-time financial reports. Include securities that traded on or after January 1, 2010 and later became inactive or delisted in training and evaluation. Link cross-listed securities to one issuer for fundamentals while retaining their listing-specific prices.

U.S. filing histories and structured company facts are available through the [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). Historical prices, actions, and Canadian fundamentals require a source with sufficient coverage and permitted use. Review [TMX historical data](https://www.tmx.com/resource/en/268), [CSE historical data](https://thecse.com/trading/market-data/), and [SEDAR+ terms](https://sedarplus.ca/onlinehelp/terms-of-use/) before choosing that source.

## Estimation and validation

1. Create one historical episode per qualifying drop. Record a confirmed bounce, a delisting or other terminal outcome, or a still-unresolved episode.
2. Report historical bounce timing by eligible drop cohort from approximately 2011 onward, including sample sizes and uncertainty. Test whether timing changed across eras; do not assume faster information spread caused a shorter wait. A 2010 drop cannot be assessed under the full 12-month lookback without using pre-2010 prices.
3. Train a monthly time-to-event model using only information known at each historical forecast date. Estimate the probability that a bounce starts in each future month, accounting separately for delisting and unresolved episodes.
4. Update active-stock scores when new prices and filings arrive; retrain periodically. Publish an as-of date, data version, and model version with every result.
5. Use walk-forward evaluation across market periods and exchanges. Compare calibrated monthly probabilities and selected-month candidate quality against the historical-cohort baseline. Release model forecasts only when they improve on that baseline out of sample.

## User flow

Place the month selector and results under **ValueInvesting → Candidate filter → Fallen Star**. Show each candidate's issuer, listing, drop date and magnitude, forecast bounce month, monthly probability, elapsed time, growth-check status, evidence, and data freshness. Applying the financially healthy checkbox keeps only Pass results. The page should explain unsupported horizons and missing data explicitly.

Keep licensed raw data outside the public repository. The GitHub Pages frontend can read permitted, precomputed forecast results from a scheduled backend job.
