from typing import Any, Dict, List, Tuple

from src.detector import SourceDetector
from src.models import TransactionRecord, ValidationErrorRecord
from src.normalizer import RecordNormalizer


class RecordValidator:
    """Valida reglas de integridad, duplicidad y clasifica registros válidos vs. cuarentena."""

    def __init__(self, rules: Dict[str, Any]) -> None:
        self.rules = rules
        self.sources_cfg: Dict[str, Any] = rules.get("sources", {})
        self.supported_currencies: set[str] = set(rules.get("supported_currencies", []))
        self.detector = SourceDetector(self.sources_cfg)
        self.normalizer = RecordNormalizer(rules)

    def process_record(
        self, raw_record: Dict[str, Any]
    ) -> TransactionRecord | ValidationErrorRecord:
        errors: List[str] = []
        source = self.detector.detect(raw_record)

        if not source:
            return ValidationErrorRecord(
                raw_record=raw_record,
                detected_source=None,
                errors=["No se pudo identificar la fuente: firma de llaves desconocida."],
            )

        src_cfg = self.sources_cfg[source]
        fmap = src_cfg["field_map"]

        # 1. Validar ID de transacción
        raw_id = raw_record.get(fmap["transaction_id"])
        tx_id = str(raw_id).strip() if raw_id is not None and not isinstance(raw_id, bool) else ""
        if not tx_id:
            errors.append("El identificador de transacción está vacío o ausente.")

        # 2. Normalizar y validar monto y divisa
        raw_amount = raw_record.get(fmap["amount"])
        raw_currency = raw_record.get(fmap["currency"]) if fmap["currency"] else None
        divisor = int(src_cfg.get("amount_divisor", 1))

        amount = None
        currency = None
        try:
            amount, currency = self.normalizer.parse_amount_and_currency(
                raw_amount, raw_currency, divisor
            )
            if amount <= 0:
                errors.append(f"El monto debe ser mayor que 0 (recibido: {amount}).")
        except ValueError as exc:
            errors.append(str(exc))

        if not currency:
            errors.append("No se pudo determinar la divisa de la transacción.")
        elif currency not in self.supported_currencies:
            errors.append(f"Divisa no soportada: '{currency}'.")

        # 3. Normalizar y validar marca temporal
        raw_ts = raw_record.get(fmap["timestamp"])
        timestamp = None
        try:
            timestamp = self.normalizer.parse_timestamp(raw_ts, src_cfg["date_formats"])
        except ValueError as exc:
            errors.append(str(exc))

        # 4. Normalizar y validar estado
        raw_status = raw_record.get(fmap["status"])
        status = None
        try:
            status = self.normalizer.parse_status(raw_status)
        except ValueError as exc:
            errors.append(str(exc))

        if errors:
            return ValidationErrorRecord(
                raw_record=raw_record,
                detected_source=source,
                errors=errors,
            )

        return TransactionRecord(
            transaction_id=tx_id,
            source=source,
            amount=amount,  # type: ignore[arg-type]
            currency=currency,  # type: ignore[arg-type]
            timestamp=timestamp,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
        )

    def process_batch(
        self, raw_records: Any
    ) -> Tuple[List[TransactionRecord], List[ValidationErrorRecord]]:
        if not isinstance(raw_records, list):
            raise ValueError("El payload de entrada debe ser una lista JSON de transacciones.")

        valid_records: List[TransactionRecord] = []
        invalid_records: List[ValidationErrorRecord] = []
        seen_ids: set[str] = set()

        for item in raw_records:
            if not isinstance(item, dict):
                invalid_records.append(
                    ValidationErrorRecord(
                        raw_record={"_raw_element": item},
                        detected_source=None,
                        errors=["Elemento malformado: cada registro debe ser un objeto JSON."],
                    )
                )
                continue

            result = self.process_record(item)
            if isinstance(result, TransactionRecord):
                if result.transaction_id in seen_ids:
                    invalid_records.append(
                        ValidationErrorRecord(
                            raw_record=item,
                            detected_source=result.source,
                            errors=[
                                f"ID de transacción duplicado en el lote: '{result.transaction_id}'."
                            ],
                        )
                    )
                else:
                    seen_ids.add(result.transaction_id)
                    valid_records.append(result)
            else:
                invalid_records.append(result)

        return valid_records, invalid_records