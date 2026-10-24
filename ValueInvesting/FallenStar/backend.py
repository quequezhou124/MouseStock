"""Fallen Star historical-data pipeline and monthly competing-risk forecast.

Only observations dated 2010-01-01 or later are accepted. All input rows remain
outside git in FallenStar/data. Run ``python backend.py --help`` for commands.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import json
import math
import random
import sqlite3
import statistics
import urllib.request
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path


START = dt.date(2010, 1, 1)
ROOT = Path(__file__).parent
DATA = ROOT / "data"
MODEL_VERSION = "cohort-hazard-v1"
HORIZON = 36
MIN_RISK = 10
PRIOR = 24.0
SEC_REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
)


def date(value: str) -> dt.date:
    return dt.date.fromisoformat(value[:10])


def month(value: dt.date) -> int:
    return value.year * 12 + value.month - 1


def month_label(value: int) -> str:
    return f"{value // 12:04d}-{value % 12 + 1:02d}"


def connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS security (
          security_id TEXT PRIMARY KEY, issuer_id TEXT NOT NULL, name TEXT NOT NULL,
          ticker TEXT NOT NULL, exchange TEXT NOT NULL, country TEXT NOT NULL,
          listed_on TEXT NOT NULL, delisted_on TEXT, cik TEXT
        );
        CREATE TABLE IF NOT EXISTS price (
          security_id TEXT NOT NULL REFERENCES security(security_id),
          trading_date TEXT NOT NULL, adjusted_close REAL NOT NULL, volume REAL NOT NULL,
          PRIMARY KEY (security_id, trading_date)
        );
        CREATE TABLE IF NOT EXISTS revenue (
          issuer_id TEXT NOT NULL, fiscal_start TEXT NOT NULL, fiscal_end TEXT NOT NULL,
          filed_on TEXT NOT NULL,
          revenue REAL NOT NULL, currency TEXT NOT NULL, source TEXT NOT NULL,
          PRIMARY KEY (issuer_id, fiscal_end, filed_on, source)
        );
        CREATE TABLE IF NOT EXISTS action (
          security_id TEXT NOT NULL REFERENCES security(security_id),
          action_date TEXT NOT NULL, action_type TEXT NOT NULL,
          PRIMARY KEY (security_id, action_date, action_type)
        );
        CREATE TABLE IF NOT EXISTS source_snapshot (
          source TEXT PRIMARY KEY, sha256 TEXT NOT NULL, imported_at TEXT NOT NULL,
          rows INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS price_date ON price(trading_date);
        CREATE INDEX IF NOT EXISTS revenue_issuer ON revenue(issuer_id, filed_on);
    """)
    return db


def csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest(db: sqlite3.Connection, directory: Path) -> dict:
    """Import a provider snapshot; reject invalid rows instead of silently fixing them."""
    counts = {}
    specs = [
        ("securities.csv", "security", ("security_id", "issuer_id", "name", "ticker", "exchange", "country", "listed_on", "delisted_on", "cik")),
        ("prices.csv", "price", ("security_id", "trading_date", "adjusted_close", "volume")),
        ("revenues.csv", "revenue", ("issuer_id", "fiscal_start", "fiscal_end", "filed_on", "revenue", "currency", "source")),
        ("actions.csv", "action", ("security_id", "action_date", "action_type")),
    ]
    with db:
        for filename, table, fields in specs:
            path = directory / filename
            if not path.exists():
                if filename in {"securities.csv", "prices.csv"}:
                    raise FileNotFoundError(f"Required input missing: {path}")
                counts[filename] = 0
                continue
            rows = 0
            placeholders = ",".join("?" for _ in fields)
            sql = f"INSERT OR REPLACE INTO {table} ({','.join(fields)}) VALUES ({placeholders})"
            for line, row in enumerate(csv_rows(path), 2):
                try:
                    values = [row[field].strip() for field in fields]
                    if table == "security":
                        if not all(values[:7]) or values[5] not in {"US", "CA"}:
                            raise ValueError("missing ID/listing data or unsupported country")
                        if date(values[6]) > dt.date.today():
                            raise ValueError("future listing date")
                        if values[7] and date(values[7]) < START:
                            continue
                        values[7] = values[7] or None
                        values[8] = str(int(values[8])) if values[8] else None
                    elif table == "price":
                        if date(values[1]) < START:
                            continue
                        values[2], values[3] = float(values[2]), float(values[3])
                        if not math.isfinite(values[2]) or values[2] <= 0 or not math.isfinite(values[3]) or values[3] < 0:
                            raise ValueError("invalid adjusted close or volume")
                    elif table == "revenue":
                        if date(values[1]) < START or date(values[2]) < START or date(values[3]) < START:
                            continue
                        if not 330 <= (date(values[2]) - date(values[1])).days <= 400:
                            raise ValueError("revenue must cover one annual fiscal period")
                        values[4] = float(values[4])
                        if not math.isfinite(values[4]) or values[4] < 0 or not values[5] or not values[6]:
                            raise ValueError("invalid revenue/currency/source")
                    elif table == "action":
                        if date(values[1]) < START:
                            continue
                        if values[2] not in {"split", "dividend", "spinoff", "halt", "other"}:
                            raise ValueError("invalid action type")
                    db.execute(sql, values)
                    rows += 1
                except (KeyError, TypeError, ValueError, sqlite3.IntegrityError) as exc:
                    raise ValueError(f"{path}:{line}: {exc}") from exc
            counts[filename] = rows
            digest = file_hash(path)
            db.execute("INSERT OR IGNORE INTO source_snapshot VALUES (?,?,?,?)",
                       (f"{filename}:{digest[:16]}", digest,
                        dt.datetime.now(dt.timezone.utc).isoformat(), rows))
    return counts


def import_sec_revenue(db: sqlite3.Connection, issuer_id: str, cik: str, user_agent: str) -> int:
    """Import SEC annual company facts as dated vintages for one mapped issuer."""
    if not user_agent or "@" not in user_agent:
        raise ValueError("Provide a contact User-Agent, for example 'MouseStocks contact@example.com'")
    mapped = db.execute("SELECT 1 FROM security WHERE issuer_id=? AND cik=? AND country='US' LIMIT 1",
                        (issuer_id, str(int(cik)))).fetchone()
    if not mapped:
        raise ValueError("Issuer ID and CIK must be mapped to a U.S. security in securities.csv")
    req = urllib.request.Request(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json",
        headers={"User-Agent": user_agent, "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
    facts = json.loads(raw)["facts"]
    gaap = facts.get("us-gaap", {})
    count = 0
    with db:
        for tag in SEC_REVENUE_TAGS:
            for currency, rows in gaap.get(tag, {}).get("units", {}).items():
                if currency not in {"USD", "CAD"}:
                    continue
                for row in rows:
                    try:
                        start, end, filed = date(row["start"]), date(row["end"]), date(row["filed"])
                        days = (end - start).days
                        if start < START or filed < START or not 330 <= days <= 400 or row.get("form") not in {"10-K", "10-K/A", "20-F", "40-F"}:
                            continue
                        amount = float(row["val"])
                        if not math.isfinite(amount) or amount < 0:
                            continue
                        db.execute("INSERT OR IGNORE INTO revenue VALUES (?,?,?,?,?,?,?)",
                                   (issuer_id, start.isoformat(), end.isoformat(), filed.isoformat(), amount,
                                    currency, f"SEC:{tag}"))
                        count += 1
                    except (KeyError, TypeError, ValueError):
                        continue
        digest = hashlib.sha256(raw).hexdigest()
        db.execute("INSERT OR IGNORE INTO source_snapshot VALUES (?,?,?,?)",
                   (f"SEC:{cik}:{digest[:16]}", digest,
                    dt.datetime.now(dt.timezone.utc).isoformat(), count))
    return count


@dataclass
class Episode:
    security_id: str
    issuer_id: str
    ticker: str
    exchange: str
    name: str
    drop_date: str
    drop_pct: float
    peak: float
    trough: float
    end_month: int | None
    outcome: str
    observed_through: int
    onset_date: str | None = None
    confirmation_date: str | None = None
    pending_onset_date: str | None = None

    @property
    def drop_month(self) -> int:
        return month(date(self.drop_date))


def episodes_for_security(db: sqlite3.Connection, security: sqlite3.Row, as_of: dt.date) -> list[Episode]:
    prices = db.execute(
        "SELECT trading_date, adjusted_close, volume FROM price WHERE security_id=? AND trading_date BETWEEN ? AND ? ORDER BY trading_date",
        (security["security_id"], START.isoformat(), as_of.isoformat()),
    ).fetchall()
    if len(prices) < 200:
        return []
    closes = {}
    month_last_day = {}
    for row in prices:
        key = month(date(row["trading_date"]))
        closes[key] = row["adjusted_close"]
        month_last_day[key] = row["trading_date"]
    actions = {(r["action_date"], r["action_type"]) for r in db.execute(
        "SELECT action_date, action_type FROM action WHERE security_id=? AND action_date<=?",
        (security["security_id"], as_of.isoformat()))}
    result = []
    recent = deque()
    highs = deque()
    active = None
    armed = True
    trough_by_month = {}
    for row in prices:
        day = date(row["trading_date"])
        close = row["adjusted_close"]
        # Twelve observed calendar months and at least 200 sessions are required.
        cutoff = day - dt.timedelta(days=365)
        while recent and recent[0][0] < cutoff:
            expired = recent.popleft()
            if highs and highs[0] == expired:
                highs.popleft()
        if day >= START + dt.timedelta(days=365) and active is None and armed and len(recent) >= 200 and recent[0][0] <= cutoff + dt.timedelta(days=14):
            peak = highs[0][1]
            if close <= peak * 0.80 and row["volume"] > 0:
                # Exclude mechanical distributions or reorganizations around the event.
                nearby = any(abs((date(a_day) - day).days) <= 3 and kind in {"split", "spinoff", "other"}
                             for a_day, kind in actions)
                if not nearby:
                    active = Episode(security["security_id"], security["issuer_id"], security["ticker"],
                                     security["exchange"], security["name"], day.isoformat(),
                                     round(1 - close / peak, 4), peak, close, None, "open", month(day))
                    trough_by_month = {}
                    result.append(active)
                    armed = False
        if active is not None:
            active.trough = min(active.trough, close)
            active.observed_through = month(day)
            current = month(day)
            if row["trading_date"] == month_last_day[current] and month_is_complete(current, as_of):
                previous = current - 1
                if previous >= active.drop_month and previous in closes:
                    # The prior month's onset is confirmed only now. The prior
                    # month's trough was saved before any later lows occurred.
                    threshold = trough_by_month.get(previous, active.trough) * 1.15
                    if closes[previous] >= threshold and close >= threshold:
                        active.end_month = previous
                        active.outcome = "bounce"
                        active.onset_date = month_last_day[previous]
                        active.confirmation_date = day.isoformat()
                        active.pending_onset_date = None
                        active = None
                if active is not None:
                    active.pending_onset_date = day.isoformat() if close >= active.trough * 1.15 else None
        if active is None and not armed:
            # A new episode needs full recovery to the old peak.
            if result and close >= result[-1].peak:
                armed = True
        if active is not None:
            trough_by_month[month(day)] = active.trough
        item = (day, close)
        recent.append(item)
        while highs and highs[-1][1] <= close:
            highs.pop()
        highs.append(item)
    delisted = security["delisted_on"]
    if active is not None and delisted and date(delisted) <= as_of:
        active.end_month = month(date(delisted))
        active.outcome = "delisted"
    return result


def month_is_complete(value: int, as_of: dt.date) -> bool:
    if value < month(as_of):
        return True
    return value == month(as_of) and as_of.day == calendar.monthrange(as_of.year, as_of.month)[1]


def collect_episodes(db: sqlite3.Connection, as_of: dt.date) -> list[Episode]:
    output = []
    for security in db.execute("SELECT * FROM security ORDER BY security_id"):
        output.extend(episodes_for_security(db, security, as_of))
    return output


def summarize_episodes(db: sqlite3.Connection, as_of: dt.date, output: Path) -> dict:
    """Export a private, auditable historical episode inventory."""
    episodes = collect_episodes(db, as_of)
    counts = Counter(ep.outcome for ep in episodes)
    securities = db.execute("SELECT COUNT(*) FROM security").fetchone()[0]
    price_rows, first_price, last_price = db.execute(
        "SELECT COUNT(*),MIN(trading_date),MAX(trading_date) FROM price").fetchone()
    records = []
    for ep in episodes:
        record = asdict(ep)
        record["drop_month"] = month_label(ep.drop_month)
        record["outcome_month"] = month_label(ep.end_month) if ep.end_month is not None else None
        record["elapsed_months"] = ep.end_month - ep.drop_month if ep.end_month is not None else None
        records.append(record)
    result = {"as_of": as_of.isoformat(), "securities": securities,
              "price_rows": price_rows, "first_price": first_price, "last_price": last_price,
              "episodes": len(records), "confirmed_bounces": counts["bounce"],
              "delistings": counts["delisted"], "unresolved": counts["open"],
              "records": records}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return {key: value for key, value in result.items() if key != "records"}


def health(db: sqlite3.Connection, issuer_id: str, drop_date: str) -> dict:
    rows = db.execute(
        "SELECT * FROM revenue WHERE issuer_id=? AND filed_on<? AND fiscal_end>=? AND fiscal_end<? ORDER BY fiscal_end, filed_on",
        (issuer_id, drop_date, START.isoformat(), drop_date),
    ).fetchall()
    by_year = defaultdict(list)
    for row in rows:
        by_year[date(row["fiscal_end"]).year].append(row)
    years = sorted(by_year)
    if len(years) < 6:
        return {"status": "Unknown", "reason": "fewer than six filed annual observations from 2010 onward"}
    selected = []
    for yr in years[-6:]:
        # A fiscal year can have multiple vintages; choose latest filed as of the drop.
        selected.append(max(by_year[yr], key=lambda r: (r["filed_on"], r["fiscal_end"])))
    if [r["fiscal_end"][:4] for r in selected] != [str(y) for y in range(years[-1] - 5, years[-1] + 1)]:
        return {"status": "Unknown", "reason": "annual observations are not consecutive"}
    if (date(drop_date) - date(selected[-1]["fiscal_end"])).days > 550:
        return {"status": "Unknown", "reason": "latest annual report is stale"}
    if len({r["currency"] for r in selected}) != 1:
        return {"status": "Unknown", "reason": "revenue currency changed"}
    vals = [r["revenue"] for r in selected]
    if vals[0] <= 0:
        return {"status": "Unknown", "reason": "zero baseline revenue"}
    increases = sum(b > a for a, b in zip(vals, vals[1:]))
    passed = vals[-1] > vals[0] and increases >= 3
    return {"status": "Pass" if passed else "Fail", "increases": increases,
            "growth_pct": round(100 * (vals[-1] / vals[0] - 1), 2),
            "evidence": [{"fiscal_start": r["fiscal_start"], "fiscal_end": r["fiscal_end"],
                          "filed_on": r["filed_on"],
                          "revenue": r["revenue"], "currency": r["currency"], "source": r["source"]}
                         for r in selected]}


def cohort(drop_year: int) -> int:
    """Four-year drop cohorts allow timing to change across historical eras."""
    return (drop_year - 2011) // 4


def fit_hazards(episodes: list[Episode], training_as_of: dt.date) -> dict:
    """Age- and era-specific competing-risk hazards with global shrinkage."""
    end = month(training_as_of) if month_is_complete(month(training_as_of), training_as_of) else month(training_as_of) - 1
    counts = defaultdict(lambda: [0, 0, 0])
    cohort_counts = defaultdict(lambda: [0, 0, 0])
    totals = [0, 0, 0]
    for ep in episodes:
        if ep.drop_month >= end:
            continue
        observed = min(ep.observed_through, end)
        terminal = ep.end_month if ep.end_month is not None and ep.end_month <= end else None
        last_age = min(HORIZON, (terminal if terminal is not None else observed) - ep.drop_month)
        if last_age < 0:
            continue
        for age in range(last_age + 1):
            cell = counts[age]
            cell[0] += 1
            era_cell = cohort_counts[(cohort(date(ep.drop_date).year), age)]
            era_cell[0] += 1
            totals[0] += 1
            if terminal == ep.drop_month + age:
                index = 1 if ep.outcome == "bounce" else 2
                cell[index] += 1
                era_cell[index] += 1
                totals[index] += 1
    global_bounce = totals[1] / totals[0] if totals[0] else 0.0
    global_delist = totals[2] / totals[0] if totals[0] else 0.0
    hazards = {}
    for age, (risk, bounces, delists) in counts.items():
        if risk >= MIN_RISK:
            hazards[age] = ((bounces + PRIOR * global_bounce) / (risk + PRIOR),
                            (delists + PRIOR * global_delist) / (risk + PRIOR), risk)
    era_hazards = {}
    for (era, age), (risk, bounces, delists) in cohort_counts.items():
        if age in hazards:
            base_bounce, base_delist, _ = hazards[age]
            era_hazards[(era, age)] = ((bounces + PRIOR * base_bounce) / (risk + PRIOR),
                                       (delists + PRIOR * base_delist) / (risk + PRIOR), risk)
    return {"hazards": hazards, "era_hazards": era_hazards,
            "episodes": len(episodes), "training_as_of": training_as_of.isoformat(),
            "global_bounce": global_bounce, "global_delist": global_delist}


def forecast(model: dict, ep: Episode, as_of: dt.date) -> list[dict]:
    """Conditional onset probabilities after the as-of month, capped at data support."""
    age = month(as_of) - ep.drop_month
    if age < 0 or ep.outcome != "open" or ep.pending_onset_date:
        return []
    survival = 1.0
    output = []
    for future_age in range(age + 1, HORIZON + 1):
        if future_age not in model["hazards"]:
            break
        bounce, delist, risk = model["era_hazards"].get(
            (cohort(date(ep.drop_date).year), future_age), model["hazards"][future_age])
        output.append({"month": month_label(ep.drop_month + future_age),
                       "probability": round(survival * bounce, 6), "at_risk": risk})
        survival *= max(0.0, 1 - bounce - delist)
    return output


def run(db: sqlite3.Connection, as_of: dt.date, target: str, output: Path) -> dict:
    target_month = month(date(target + "-01"))
    if target_month <= month(as_of):
        raise ValueError("Target month must be after the as-of month")
    last_price = db.execute("SELECT MAX(trading_date) FROM price").fetchone()[0]
    if not last_price or (as_of - date(last_price)).days > 10:
        raise ValueError("No recent price data for the requested as-of date")
    episodes = collect_episodes(db, as_of)
    model = fit_hazards(episodes, as_of)
    candidates = []
    unsupported = 0
    for ep in episodes:
        if ep.outcome != "open":
            continue
        if month(as_of) - ep.observed_through > 1:
            unsupported += 1
            continue
        months = forecast(model, ep, as_of)
        if not months or not any(r["month"] == target for r in months):
            unsupported += 1
            continue
        best = max(months, key=lambda r: r["probability"])
        if best["month"] == target:
            candidates.append({"security_id": ep.security_id, "issuer_id": ep.issuer_id,
                               "name": ep.name, "ticker": ep.ticker, "exchange": ep.exchange,
                               "drop_date": ep.drop_date, "drop_pct": ep.drop_pct,
                               "trough": round(ep.trough, 4), "predicted_month": target,
                               "probability": best["probability"],
                               "elapsed_months": target_month - ep.drop_month,
                               "health": health(db, ep.issuer_id, ep.drop_date)})
    candidates.sort(key=lambda r: r["probability"], reverse=True)
    snapshot = "|".join(f"{r['source']}:{r['sha256']}" for r in db.execute(
        "SELECT source,sha256 FROM source_snapshot ORDER BY source"))
    data_version = hashlib.sha256(snapshot.encode()).hexdigest()[:16]
    delisted_count = db.execute("SELECT COUNT(*) FROM security WHERE delisted_on IS NOT NULL").fetchone()[0]
    warnings = []
    if not delisted_count:
        warnings.append("No delisted securities imported; training may have survivor bias")
    if db.execute("SELECT COUNT(*) FROM revenue").fetchone()[0] == 0:
        warnings.append("No annual revenues imported; health results will be Unknown")
    payload = {"as_of": as_of.isoformat(), "target_month": target,
               "model_version": MODEL_VERSION, "data_version": data_version,
               "history_start": START.isoformat(), "last_price_date": last_price,
               "data_quality_warnings": warnings,
               "training_episodes": model["episodes"], "unsupported_active_episodes": unsupported,
               "candidates": candidates}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def evaluate(db: sqlite3.Connection, cutoffs: list[dt.date], horizon_months: int = 12) -> dict:
    """Walk-forward monthly calibration/ranking versus a training-only baseline."""
    if horizon_months < 1 or horizon_months > HORIZON:
        raise ValueError(f"horizon must be between 1 and {HORIZON} months")
    last_price = db.execute("SELECT MAX(trading_date) FROM price").fetchone()[0]
    if not last_price:
        raise ValueError("No prices imported")
    final_month = month(date(last_price))
    observations = []
    eligible = 0
    pending = 0
    unsupported = 0
    censored = 0
    timing_errors = []
    for cutoff in cutoffs:
        if month(cutoff) + horizon_months + 1 > final_month:
            raise ValueError(f"Cutoff {cutoff} lacks {horizon_months} months of follow-up")
        before = collect_episodes(db, cutoff)
        after = {ep.security_id + "|" + ep.drop_date: ep for ep in collect_episodes(
            db, date(month_label(month(cutoff) + horizon_months + 1) + "-01") - dt.timedelta(days=1))}
        model = fit_hazards(before, cutoff)
        for ep in before:
            if ep.outcome != "open":
                continue
            if ep.pending_onset_date:
                pending += 1
                continue
            eligible += 1
            key = ep.security_id + "|" + ep.drop_date
            actual = after.get(key)
            if actual is None:
                continue
            predicted = forecast(model, ep, cutoff)
            if not predicted:
                unsupported += 1
                continue
            within_horizon = [p for p in predicted if month(date(p["month"] + "-01")) <= month(cutoff) + horizon_months]
            if actual.outcome == "bounce" and actual.end_month is not None and month(cutoff) < actual.end_month <= month(cutoff) + horizon_months and within_horizon:
                best = max(within_horizon, key=lambda row: row["probability"])
                timing_errors.append(abs(month(date(best["month"] + "-01")) - actual.end_month))
            for p in predicted[:horizon_months]:
                target_age = month(date(p["month"] + "-01"))
                if target_age > month(cutoff) + horizon_months:
                    break
                # An unresolved episode without prices through this month is
                # right-censored, not a known negative result.
                if actual.outcome == "open" and actual.observed_through < target_age:
                    censored += 1
                    continue
                y = int(actual.outcome == "bounce" and actual.end_month == target_age)
                offset = target_age - month(cutoff)
                base = (1 - model["global_bounce"] - model["global_delist"]) ** (offset - 1) * model["global_bounce"]
                observations.append({"probability": p["probability"], "baseline": base, "actual": y,
                                     "target": p["month"], "cutoff": cutoff.isoformat(),
                                     "exchange": ep.exchange, "issuer_id": ep.issuer_id})
    if not observations:
        return {"eligible_open_episodes": eligible, "pending_confirmation_excluded": pending,
                "unsupported_forecasts": unsupported, "right_censored_targets": censored,
                "observations": 0,
                "reason": "no supported and fully observed forecasts at selected cutoffs"}
    n = len(observations)
    prevalence = sum(r["actual"] for r in observations) / n
    brier = sum((r["probability"] - r["actual"]) ** 2 for r in observations) / n
    baseline = sum((r["baseline"] - r["actual"]) ** 2 for r in observations) / n
    def log_loss(key):
        return -sum(r["actual"] * math.log(max(1e-9, min(1 - 1e-9, r[key]))) +
                    (1 - r["actual"]) * math.log(max(1e-9, min(1 - 1e-9, 1 - r[key])))
                    for r in observations) / n
    bins = defaultdict(list)
    by_month = defaultdict(list)
    for r in observations:
        bins[min(9, int(r["probability"] * 10))].append(r)
        by_month[(r["cutoff"], r["target"])].append(r)
    top_10 = []
    for group in by_month.values():
        picked = sorted(group, key=lambda r: r["probability"], reverse=True)[:10]
        top_10.append(sum(r["actual"] for r in picked) / len(picked))
    calibration = [{"probability_range": f"{i/10:.1f}-{(i+1)/10:.1f}",
                    "count": len(rows), "mean_probability": round(sum(r["probability"] for r in rows) / len(rows), 4),
                    "actual_rate": round(sum(r["actual"] for r in rows) / len(rows), 4)}
                   for i, rows in sorted(bins.items())]
    def group_metrics(rows):
        count = len(rows)
        return {"observations": count, "actual_bounces": sum(r["actual"] for r in rows),
                "brier": round(sum((r["probability"] - r["actual"]) ** 2 for r in rows) / count, 6),
                "baseline_brier": round(sum((r["baseline"] - r["actual"]) ** 2 for r in rows) / count, 6)}
    grouped_year = defaultdict(list)
    grouped_exchange = defaultdict(list)
    grouped_regime = defaultdict(list)
    for row in observations:
        year = int(row["target"][:4])
        grouped_year[year].append(row)
        grouped_exchange[row["exchange"]].append(row)
        grouped_regime["2020-2021" if year in {2020, 2021} else "other years"].append(row)
    issuers = sorted({row["issuer_id"] for row in observations})
    by_issuer = {issuer: [row for row in observations if row["issuer_id"] == issuer] for issuer in issuers}
    rng = random.Random(17)
    differences = []
    for _ in range(500):
        sample = [row for issuer in rng.choices(issuers, k=len(issuers)) for row in by_issuer[issuer]]
        differences.append(sum((row["probability"] - row["actual"]) ** 2 -
                               (row["baseline"] - row["actual"]) ** 2 for row in sample) / len(sample))
    differences.sort()
    return {"eligible_open_episodes": eligible, "pending_confirmation_excluded": pending,
            "unsupported_forecasts": unsupported, "right_censored_targets": censored,
            "observations": n, "issuer_clusters": len(issuers),
            "actual_rate": round(prevalence, 6),
            "mean_probability": round(sum(r["probability"] for r in observations) / n, 6),
            "brier": round(brier, 6), "constant_hazard_baseline_brier": round(baseline, 6),
            "log_loss": round(log_loss("probability"), 6),
            "constant_hazard_baseline_log_loss": round(log_loss("baseline"), 6),
            "mean_top_10_precision": round(sum(top_10) / len(top_10), 6),
            "timing_error_observed_bounces": len(timing_errors),
            "median_absolute_onset_error_months": statistics.median(timing_errors) if timing_errors else None,
            "within_one_month_rate": round(sum(error <= 1 for error in timing_errors) / len(timing_errors), 6) if timing_errors else None,
            "model_minus_baseline_brier_ci95_by_issuer": [round(differences[12], 6), round(differences[487], 6)],
            "by_target_year": {str(year): group_metrics(rows) for year, rows in sorted(grouped_year.items())},
            "by_exchange": {exchange: group_metrics(rows) for exchange, rows in sorted(grouped_exchange.items())},
            "by_regime": {regime: group_metrics(rows) for regime, rows in sorted(grouped_regime.items())},
            "calibration": calibration, "cutoffs": [d.isoformat() for d in cutoffs]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DATA / "fallen_star.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("ingest", help="Import CSV provider snapshot")
    p.add_argument("directory", type=Path)
    p = commands.add_parser("sec-revenue", help="Fetch SEC annual revenue for one mapped issuer")
    p.add_argument("issuer_id")
    p.add_argument("cik")
    p.add_argument("--user-agent", required=True)
    p = commands.add_parser("run", help="Build selected-month candidate JSON")
    p.add_argument("--as-of", type=date, required=True)
    p.add_argument("--target", required=True, help="Future YYYY-MM")
    p.add_argument("--output", type=Path, required=True)
    p = commands.add_parser("evaluate", help="Walk-forward monthly Brier evaluation")
    p.add_argument("--cutoffs", nargs="+", type=date, required=True)
    p.add_argument("--horizon", type=int, default=12)
    p = commands.add_parser("episodes", help="Export private historical drop/bounce inventory")
    p.add_argument("--as-of", type=date, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with connection(args.db) as db:
        if args.command == "ingest":
            result = ingest(db, args.directory)
        elif args.command == "sec-revenue":
            result = {"imported_facts": import_sec_revenue(db, args.issuer_id, args.cik, args.user_agent)}
        elif args.command == "run":
            result = run(db, args.as_of, args.target, args.output)
        elif args.command == "evaluate":
            result = evaluate(db, args.cutoffs, args.horizon)
        else:
            result = summarize_episodes(db, args.as_of, args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
