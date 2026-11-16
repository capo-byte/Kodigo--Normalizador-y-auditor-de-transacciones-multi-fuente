from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Dict, List

from src.models import TransactionRecord, ValidationErrorRecord


class MetricsEngine:
    """Calcula KPIs, agregaciones por divisa y diagnóstico de errores en cuarentena."""

    @staticmethod
    def _categorize_error(error_msg: str) -> str:
        msg = error_msg.lower()
        if "firma de llaves desconocida" in msg:
            return "Fuente desconocida"
        if "duplicado" in msg:
            return "ID duplicado"
        if "identificador de transacción" in msg:
            return "ID vacío o ausente"
        if "monto" in msg:
            return "Monto inválido"
        if "divisa" in msg:
            return "Divisa no soportada o ausente"
        if "fecha" in msg:
            return "Fecha inválida"
        if "estado" in msg:
            return "Estado no reconocido"
        if "malformado" in msg:
            return "Estructura JSON malformada"
        return "Otro error de validación"

    @classmethod
    def compute(
        cls,
        valid_records: List[TransactionRecord],
        invalid_records: List[ValidationErrorRecord],
    ) -> Dict[str, Any]:
        total_valid = len(valid_records)
        total_invalid = len(invalid_records)
        total_processed = total_valid + total_invalid

        by_status = Counter(r.status for r in valid_records)
        by_source = Counter(r.source for r in valid_records)
        by_currency_count = Counter(r.currency for r in valid_records)

        totals_by_currency: Dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        success_totals_by_currency: Dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

        for record in valid_records:
            totals_by_currency[record.currency] += record.amount
            if record.status == "SUCCESS":
                success_totals_by_currency[record.currency] += record.amount

        quarantine_categories: Counter[str] = Counter()
        for err_record in invalid_records:
            for err in err_record.errors:
                quarantine_categories[cls._categorize_error(err)] += 1

        return {
            "summary": {
                "total_processed": total_processed,
                "valid_count": total_valid,
                "invalid_count": total_invalid,
                "validation_rate_pct": round((total_valid / total_processed * 100), 2)
                if total_processed > 0
                else 0.0,
            },
            "counts_by_status": {
                "SUCCESS": by_status.get("SUCCESS", 0),
                "FAILED": by_status.get("FAILED", 0),
                "PENDING": by_status.get("PENDING", 0),
            },
            "counts_by_source": dict(sorted(by_source.items())),
            "counts_by_currency": dict(sorted(by_currency_count.items())),
            "amount_by_currency": {
                cur: float(total) for cur, total in sorted(totals_by_currency.items())
            },
            "success_amount_by_currency": {
                cur: float(total) for cur, total in sorted(success_totals_by_currency.items())
            },
            "quarantine_reasons_breakdown": dict(quarantine_categories.most_common()),
        }