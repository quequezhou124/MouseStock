"""Private EODHD demo-price pilot; not a survivorship-safe production feed.

The public demo token permits only a fixed set of active U.S. names. Raw provider
responses and the SQLite database stay in FallenStar/data (gitignored).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from backend import DATA, START, connection, date


DEMO_SYMBOLS = ("AAPL.US", "MSFT.US", "AMZN.US", "TSLA.US", "MCD.US")
BASE = "https://eodhd.com/api/"


def fetch(endpoint: str, symbol: str, token: str, start: dt.date) -> tuple[object, bytes]:
    params = {"api_token": token, "fmt": "json"}
    if endpoint == "eod":
        params["from"] = start.isoformat()
    elif endpoint == "splits":
        params["from"] = start.isoformat()
    url = f"{BASE}{endpoint}/{urllib.parse.quote(symbol, safe='.') }?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "MouseStocks private historical research"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        # Do not print the token-bearing URL from urllib's exception.
        raise RuntimeError(f"EODHD {endpoint} returned HTTP {exc.code} for {symbol}") from None
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError as exc:
        raise ValueError(f"EODHD {endpoint} returned invalid JSON for {symbol}") from exc


def ingest_symbol(db, symbol: str, token: str, directory: Path) -> dict:
    if token == "demo" and symbol not in DEMO_SYMBOLS:
        raise ValueError(f"Demo token is limited to {', '.join(DEMO_SYMBOLS)}")
    if not symbol.endswith(".US") or not symbol.replace(".", "").isalnum():
        raise ValueError("This pilot only accepts simple U.S. ticker codes")
    prices, price_raw = fetch("eod", symbol, token, START)
    profile, profile_raw = fetch("fundamentals", symbol, token, START)
    splits, split_raw = fetch("splits", symbol, token, START)
    if not isinstance(prices, list) or not isinstance(profile, dict) or not isinstance(splits, list):
        raise ValueError(f"Unexpected EODHD response shape for {symbol}")
    general = profile.get("General") or {}
    if general.get("Type") != "Common Stock" or not general.get("Name") or not general.get("CIK"):
        raise ValueError(f"Missing common-stock issuer metadata for {symbol}")
    cik = str(int(general["CIK"]))
    listed = general.get("IPODate")
    if not listed or not prices:
        raise ValueError(f"Missing listing date or price history for {symbol}")
    date(listed)
    parsed = []
    seen = set()
    for row in prices:
        day = date(row["date"])
        if day < START:
            continue
        adjusted = float(row["adjusted_close"])
        volume = float(row["volume"])
        if day in seen or not 0 < adjusted < 1e9 or not 0 <= volume < 1e14:
            raise ValueError(f"Invalid or duplicate EODHD price for {symbol} on {day}")
        seen.add(day)
        parsed.append((day.isoformat(), adjusted, volume))
    if len(parsed) < 200:
        raise ValueError(f"Insufficient 2010-onward daily history for {symbol}")
    parsed.sort()
    warnings = []
    gaps = [(date(b[0]) - date(a[0])).days for a, b in zip(parsed, parsed[1:])]
    if gaps and max(gaps) > 10:
        warnings.append(f"Trading-history gap of {max(gaps)} calendar days needs review")
    zero_volume = sum(row[2] == 0 for row in parsed)
    if zero_volume:
        warnings.append(f"{zero_volume} zero-volume daily bars need review")
    action_days = set()
    for row in splits:
        day = date(row["date"])
        if day >= START:
            action_days.add(day.isoformat())
    closes = {row[0]: row[1] for row in parsed}
    for action_day in sorted(action_days):
        preceding = [row for row in parsed if row[0] < action_day]
        if action_day in closes and preceding:
            adjusted_change = closes[action_day] / preceding[-1][1] - 1
            if abs(adjusted_change) > 0.5:
                warnings.append(f"Adjusted close changes {adjusted_change:.1%} on split date {action_day}")
    security_id = f"EODHD:{symbol}"
    issuer_id = f"US:CIK:{cik}"
    with db:
        db.execute("INSERT OR REPLACE INTO security VALUES (?,?,?,?,?,?,?,?,?)",
                   (security_id, issuer_id, general["Name"], symbol.split(".")[0],
                    general.get("Exchange") or "US", "US", listed, None, cik))
        db.executemany("INSERT OR REPLACE INTO price VALUES (?,?,?,?)",
                       ((security_id, *row) for row in parsed))
        db.executemany("INSERT OR REPLACE INTO action VALUES (?,?,?)",
                       ((security_id, day, "split") for day in sorted(action_days)))
        for name, raw in (("eod", price_raw), ("fundamentals", profile_raw), ("splits", split_raw)):
            path = directory / "raw" / f"{symbol}-{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            db.execute("INSERT OR IGNORE INTO source_snapshot VALUES (?,?,?,?)",
                       (f"EODHD:{symbol}:{name}:{digest[:16]}", digest,
                        dt.datetime.now(dt.timezone.utc).isoformat(), len(parsed) if name == "eod" else 1))
    return {"symbol": symbol, "security_id": security_id, "issuer_id": issuer_id,
            "prices": len(parsed), "first_price": parsed[0][0], "last_price": parsed[-1][0],
            "splits": len(action_days), "annual_financials_imported": 0,
            "data_quality_warnings": warnings,
            "coverage": "active-U.S.-demo-only; no delisted or Canadian securities"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DATA / "eodhd_demo.sqlite")
    parser.add_argument("--directory", type=Path, default=DATA / "eodhd_demo")
    parser.add_argument("--symbols", nargs="+", default=list(DEMO_SYMBOLS))
    args = parser.parse_args()
    token = os.environ.get("EODHD_API_TOKEN", "demo")
    results = []
    with connection(args.db) as db:
        for symbol in args.symbols:
            results.append(ingest_symbol(db, symbol.upper(), token, args.directory))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
