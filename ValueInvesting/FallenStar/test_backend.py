import csv
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from backend import Episode, collect_episodes, connection, evaluate, fit_hazards, forecast, health, ingest, month, run


def write_csv(path, header, rows):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        write_csv(folder / "securities.csv",
                  ["security_id", "issuer_id", "name", "ticker", "exchange", "country", "listed_on", "delisted_on", "cik"],
                  [["S1", "I1", "Example", "EX", "NASDAQ", "US", "2010-01-01", "", ""]])
        prices = []
        current = dt.date(2010, 1, 1)
        while current <= dt.date(2018, 12, 31):
            if current.weekday() < 5:
                close = 100
                if dt.date(2017, 1, 3) <= current < dt.date(2017, 4, 1):
                    close = 79
                elif dt.date(2017, 4, 1) <= current < dt.date(2017, 5, 1):
                    close = 85
                elif dt.date(2017, 5, 1) <= current < dt.date(2017, 6, 1):
                    close = 93
                elif dt.date(2017, 6, 1) <= current < dt.date(2017, 7, 1):
                    close = 94
                prices.append(["S1", current.isoformat(), close, 1000])
            current += dt.timedelta(days=1)
        write_csv(folder / "prices.csv", ["security_id", "trading_date", "adjusted_close", "volume"], prices)
        write_csv(folder / "revenues.csv",
                  ["issuer_id", "fiscal_start", "fiscal_end", "filed_on", "revenue", "currency", "source"],
                  [["I1", f"{yr}-01-01", f"{yr}-12-31", f"{yr+1}-03-01", 100 + 10 * (yr - 2010), "USD", "test"]
                   for yr in range(2010, 2016)] +
                  [["I1", "2015-01-01", "2015-12-31", "2018-03-01", 1, "USD", "restatement"]])
        self.db = connection(folder / "test.sqlite")
        self.addCleanup(self.db.close)
        ingest(self.db, folder)

    def test_2010_warmup_and_bounce_confirmation(self):
        self.assertEqual(collect_episodes(self.db, dt.date(2010, 12, 31)), [])
        before = collect_episodes(self.db, dt.date(2017, 5, 31))
        self.assertEqual(len(before), 1)
        self.assertEqual(before[0].outcome, "open")
        after = collect_episodes(self.db, dt.date(2017, 6, 30))
        self.assertEqual(after[0].outcome, "bounce")
        self.assertEqual(after[0].end_month, month(dt.date(2017, 5, 1)))

    def test_late_2010_drop_is_still_ineligible(self):
        with self.db:
            self.db.execute("UPDATE price SET adjusted_close=79 WHERE security_id='S1' AND trading_date BETWEEN '2010-12-20' AND '2010-12-31'")
        self.assertEqual(collect_episodes(self.db, dt.date(2010, 12, 31)), [])

    def test_health_uses_only_reports_available_before_drop(self):
        self.assertEqual(health(self.db, "I1", "2015-06-01")["status"], "Unknown")
        result = health(self.db, "I1", "2017-01-03")
        self.assertEqual(result["status"], "Pass")
        self.assertEqual(result["evidence"][-1]["revenue"], 150)

    def test_health_fails_when_total_revenue_shrinks(self):
        with self.db:
            self.db.execute("UPDATE revenue SET revenue=90 WHERE issuer_id='I1' AND fiscal_end='2015-12-31' AND filed_on='2016-03-01'")
        self.assertEqual(health(self.db, "I1", "2017-01-03")["status"], "Fail")

    def test_competing_hazards_produce_future_month_probabilities(self):
        def episode(i, outcome, end):
            return Episode(str(i), str(i), str(i), "NASDAQ", "Example", "2020-01-15",
                           0.25, 100, 75, end, outcome, month(dt.date(2020, 12, 1)))
        first = month(dt.date(2020, 1, 1))
        training = [episode(i, "bounce", first + 3) for i in range(20)]
        training += [episode(i + 20, "delisted", first + 5) for i in range(5)]
        training += [episode(i + 25, "open", None) for i in range(10)]
        model = fit_hazards(training, dt.date(2020, 12, 31))
        active = episode(50, "open", None)
        active.drop_date = "2020-10-15"
        predicted = forecast(model, active, dt.date(2020, 10, 31))
        self.assertTrue(predicted)
        self.assertEqual(predicted[0]["month"], "2020-11")
        self.assertLessEqual(sum(p["probability"] for p in predicted), 1)

    def test_export_marks_unsupported_when_history_is_insufficient(self):
        output = Path(self.temp.name) / "result.json"
        result = run(self.db, dt.date(2017, 5, 31), "2017-06", output)
        self.assertTrue(output.exists())
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["unsupported_active_episodes"], 1)
        self.assertEqual(len(result["data_version"]), 16)

    def test_evaluation_reports_insufficient_training_support(self):
        result = evaluate(self.db, [dt.date(2017, 5, 31)], 3)
        self.assertEqual(result["observations"], 0)
        self.assertEqual(result["eligible_open_episodes"], 1)


if __name__ == "__main__":
    unittest.main()
