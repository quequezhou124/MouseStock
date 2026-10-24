# MouseStocks

MouseStocks is a static GitHub Pages site for stock research. The current research section is [ValueInvesting](https://quequezhou124.github.io/MouseStock/value-investing/).

## Repository layout

| Path | Purpose |
| --- | --- |
| `ValueInvesting/build_masterstock.py` | Builds the ValueInvesting names-only stock universe. |
| `ValueInvesting/masterstockexcel.xlsx` | Excel copy of that universe. |
| `docs/` | Public GitHub Pages site. |
| `docs/value-investing/masterlist/stocks.json` | Website copy of the same names. |
| `docs/masterlist/index.html` | Redirect for the former global Masterlist URL. |

## Refresh the ValueInvesting masterlist

Run from the repository root:

```sh
python3 ValueInvesting/build_masterstock.py
```

The script downloads current Nasdaq Trader, TSX/TSXV, and CSE listings, filters out OTC and non-stock securities, deduplicates company names, and updates both the Excel file and the website JSON. It uses only the Python standard library. Review the generated changes, then commit and push to `main` to publish the website update.

The masterlist is a starting pool for ValueInvesting research. It does not represent screened Fallen Star or Black Hourse candidates.
