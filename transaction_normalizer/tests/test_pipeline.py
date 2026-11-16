import json
import unittest
from decimal import Decimal
from pathlib import Path

from src.metrics import MetricsEngine
from src.validator import RecordValidator

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "rules.json"


class TestTransactionPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with RULES_PATH.open("r", encoding="utf-8") as f:
            cls.rules = json.load(f)
        cls.validator = RecordValidator(cls.rules)

    def test_european_and_anglo_amount_formats(self) -> None:
        batch = [
            {
                "ref": "EU-1",
                "amount": "€1.250,50",
                "date": "2025-03-10T14:22:00Z",
                "result": "success",
            },
            {
                "id": "US-1",
                "amount": "$1,250.50",
                "currency": "USD",
                "timestamp": "2025-03-10 14:22:00",
                "status": "completed",
            },
        ]
        valid, invalid = self.validator.process_batch(batch)
        self.assertEqual(len(valid), 2)
        self.assertEqual(len(invalid), 0)
        self.assertEqual(valid[0].amount, Decimal("1250.50"))
        self.assertEqual(valid[0].currency, "EUR")
        self.assertEqual(valid[1].amount, Decimal("1250.50"))
        self.assertEqual(valid[1].currency, "USD")

    def test_timezone_offsets_and_invalid_calendar_dates(self) -> None:
        batch = [
            {
                "ref": "TZ-1",
                "amount": "50.00",
                "date": "2025-03-10T16:22:00+02:00",
                "result": "success",
            },
            {
                "transaction_id": "BAD-DATE",
                "total": 1000,
                "currency": "USD",
                "created_at": "31/02/2025 10:00",
                "state": "OK",
            },
        ]
        valid, invalid = self.validator.process_batch(batch)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].timestamp, "2025-03-10T14:22:00Z")
        self.assertEqual(len(invalid), 1)
        self.assertIn("Fecha", invalid[0].errors[0])

    def test_duplicate_transaction_ids_in_batch(self) -> None:
        batch = [
            {
                "id": "DUP-100",
                "amount": "25.00",
                "currency": "USD",
                "timestamp": "2025-03-10 10:00:00",
                "status": "completed",
            },
            {
                "id": "DUP-100",
                "amount": "25.00",
                "currency": "USD",
                "timestamp": "2025-03-10 10:01:00",
                "status": "completed",
            },
        ]
        valid, invalid = self.validator.process_batch(batch)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)
        self.assertIn("duplicado", invalid[0].errors[0])

    def test_non_finite_booleans_and_malformed_elements(self) -> None:
        batch = [
            {
                "id": "BOOL-1",
                "amount": True,
                "currency": "USD",
                "timestamp": "2025-03-10 10:00:00",
                "status": "completed",
            },
            {
                "id": "NAN-1",
                "amount": float("nan"),
                "currency": "USD",
                "timestamp": "2025-03-10 10:00:00",
                "status": "completed",
            },
            "cadena_suelta_invalida",
        ]
        valid, invalid = self.validator.process_batch(batch)
        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 3)

    def test_non_list_root_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.validator.process_batch({"id": "not_a_list"})

    def test_metrics_and_quarantine_breakdown(self) -> None:
        batch = [
            {
                "id": "M-1",
                "amount": "10.10",
                "currency": "USD",
                "timestamp": "2025-03-10 10:00:00",
                "status": "completed",
            },
            {
                "ref": "M-2",
                "amount": "€20,20",
                "date": "2025-03-10T10:00:00Z",
                "result": "failed",
            },
            {
                "unknown_key": 123,
            },
        ]
        valid, invalid = self.validator.process_batch(batch)
        metrics = MetricsEngine.compute(valid, invalid)

        self.assertEqual(metrics["amount_by_currency"], {"EUR": 20.2, "USD": 10.1})
        self.assertEqual(metrics["success_amount_by_currency"], {"USD": 10.1})
        self.assertEqual(metrics["counts_by_currency"], {"EUR": 1, "USD": 1})
        self.assertEqual(metrics["quarantine_reasons_breakdown"], {"Fuente desconocida": 1})


if __name__ == "__main__":
    unittest.main()