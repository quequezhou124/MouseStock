# Fallen Star plan

Status: backend and website filter implemented; a private five-stock real-price pilot has been ingested and evaluated. Full historical U.S./Canadian coverage and reliable production validation are still pending, so the live page does not publish candidate forecasts. See [REAL_DATA_AUDIT.md](REAL_DATA_AUDIT.md).

## Goal

For a user-selected future month, identify stocks whose price has had a qualifying drop and whose bounce is predicted to start in that month. Let the user narrow those results to companies with five years of growth evidence available before the drop. Results are ranked candidates, not guaranteed rebounds.

## Historical starting point

Treat **January 1, 2010 as the start of the usable history**. Do not use prices, fiscal periods, filings, drop events, outcomes, or model features from before that date. The current masterlist defines the stocks screened now; historical training and evaluation also include securities that traded from 2010 onward but have since delisted.

This starting point creates two warm-up periods:

- A drop needs a preceding 12 months of observed prices. Drops during 2010 cannot be labeled under the full-lookback rule; the first eligible drops are approximately January 2011, once a security has 12 months of post-start history.
- The proposed financial-health rule needs six consecutive annual revenue observations to measure five year-to-year intervals, with each entire fiscal period beginning in 2010 or later and all reports filed before the drop. For a calendar-year reporter, fiscal years 2010–2015 can first support the check after the 2015 report is filed, generally in 2016. Earlier drops have **Unknown** health rather than inferred growth from pre-2010 data. Other fiscal-year schedules and filing dates shift the first eligible date.

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

### Shared table behavior

Use one reusable table component for **every table on the Fallen Star page**, including timing-match results, financially healthy finalists, and any detailed data tables added later. Do not build separate scrolling or export behavior for individual tables.

- Place each table in a fixed-height or maximum-height container with vertical scrolling for long result sets and horizontal scrolling when columns exceed the available width. Keep column headers visible while scrolling. The container and controls must remain usable on desktop and mobile.
- Put a clearly visible **Download Excel** button near the top-right corner of each table. It downloads that table's data as an `.xlsx` file with meaningful column names, values, dates, and numeric formats. Include relevant context, such as the selected bounce month, data as-of date, and model version, in a metadata worksheet or an equivalent clearly labelled area.
- Derive the displayed rows and exported rows from the same filtered and sorted dataset. A month change or Financially Healthy checkbox change must update both. Export **all matching rows**, including rows outside the visible scroll area or a rendered page. Scrolling never changes the export; if sorting is available, the workbook retains the current sort order.
- Keep the table's complete permitted result set available to the export path, or provide an explicit full-result export source if the page later loads rows in batches. Do not mistake only the rows currently rendered in the browser for the full filtered dataset.

### UI implementation steps

1. Define a shared table interface for column labels, display and Excel value types, the complete filtered row set, current sort order, and export metadata. Use it for candidate results and detailed tables.
2. Design the responsive scroll container, sticky headers, and top-right Download Excel control once in the shared component.
3. Connect the selected bounce month and Financially Healthy checkbox to one derived result set that drives both rendering and `.xlsx` export. Preserve any active sorting in that result set.
4. Verify the export against the backend's selected-month output, including data as-of date and model version, before publishing any candidate data.

### UI acceptance criteria

- Every Fallen Star table has vertical scrolling within a bounded height, horizontal scrolling when needed, sticky headers, and a visible Download Excel button on desktop and mobile.
- For each selected month and checkbox state, the workbook contains every row shown by that filter, including rows not currently visible in the scroll container; it contains no rows excluded by the filter.
- Changing the month, checkbox, or supported sort order changes the displayed table and workbook consistently. Scrolling alone changes neither the exported rows nor their order.
- Each workbook is a valid `.xlsx` file with readable column names, appropriate date and numeric cell formats, and applicable bounce-month, as-of-date, and model-version metadata.
- New Fallen Star tables receive these behaviors through the same reusable component.
