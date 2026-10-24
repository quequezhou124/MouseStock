import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import connection
from ingest_eodhd import ingest_symbol


class EodhdIngestTest(unittest.TestCase):
    def test_normalizes_private_demo_history_without_importing_revised_financials(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bars = []
            day = dt.date(2010, 1, 1)
            while len(bars) < 210:
                if day.weekday() < 5:
                    bars.append({"date": day.isoformat(), "adjusted_close": 10 + len(bars) / 100,
                                 "volume": 1000})
                day += dt.timedelta(days=1)
            profile = {"General": {"Name": "Example Corp", "Type": "Common Stock",
                                   "CIK": "0000320193", "IPODate": "1980-12-12", "Exchange": "NASDAQ"},
                       "Financials": {"Income_Statement": {"yearly": {"2015-12-31": {"totalRevenue": "999"}}}}}
            splits = [{"date": "2010-06-01", "split": "2.000000/1.000000"}]
            responses = [(value, json.dumps(value).encode()) for value in (bars, profile, splits)]
            with connection(root / "pilot.sqlite") as db, patch("ingest_eodhd.fetch", side_effect=responses):
                result = ingest_symbol(db, "AAPL.US", "demo", root)
                self.assertEqual(result["prices"], 210)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM action").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM revenue").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT cik FROM security").fetchone()[0], "320193")
                self.assertEqual(len(list((root / "raw").glob("*.json"))), 3)


if __name__ == "__main__":
    unittest.main()
