import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple


class RecordNormalizer:
    """Transforma registros crudos hacia los tipos y formatos del esquema canónico."""

    def __init__(self, rules: Dict[str, Any]) -> None:
        self.rules = rules
        self.currency_symbols: Dict[str, str] = rules.get("currency_symbols", {})
        self.status_map: Dict[str, str] = {
            k.strip().lower(): v for k, v in rules.get("status_map", {}).items()
        }

    def _normalize_numeric_string(self, raw_text: str, original_value: Any) -> str:
        """Resuelve separadores decimales y de miles en formatos europeos y anglosajones."""
        cleaned = raw_text.replace(" ", "")
        has_comma = "," in cleaned
        has_dot = "." in cleaned

        if has_comma and has_dot:
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                # Formato europeo: 1.250,50 -> 1250.50
                if cleaned.count(",") > 1:
                    raise ValueError(f"Formato numérico ambiguo en monto: '{original_value}'.")
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # Formato anglosajón: 1,250.50 -> 1250.50
                if cleaned.count(".") > 1:
                    raise ValueError(f"Formato numérico ambiguo en monto: '{original_value}'.")
                cleaned = cleaned.replace(",", "")
        elif has_comma:
            if cleaned.count(",") > 1:
                raise ValueError(f"Formato numérico ambiguo en monto: '{original_value}'.")
            cleaned = cleaned.replace(",", ".")
        elif has_dot:
            if cleaned.count(".") > 1:
                raise ValueError(f"Formato numérico ambiguo en monto: '{original_value}'.")

        if not re.fullmatch(r"[+-]?\d+(\.\d+)?", cleaned):
            raise ValueError(f"Formato numérico no válido en monto: '{original_value}'.")

        return cleaned

    def parse_amount_and_currency(
        self, raw_amount: Any, raw_currency: Any, divisor: int
    ) -> Tuple[Decimal, Optional[str]]:
        if raw_amount is None or isinstance(raw_amount, bool):
            raise ValueError("El monto está ausente o tiene tipo inválido.")

        inferred_currency: Optional[str] = None

        if isinstance(raw_amount, (int, float)):
            if isinstance(raw_amount, float) and (math.isnan(raw_amount) or math.isinf(raw_amount)):
                raise ValueError(f"El monto no es un número finito válido: '{raw_amount}'.")
            numeric_str = str(raw_amount)
        elif isinstance(raw_amount, str):
            cleaned = raw_amount.strip()
            if not cleaned:
                raise ValueError("El monto es una cadena vacía.")

            for symbol, iso_code in self.currency_symbols.items():
                if symbol in cleaned:
                    inferred_currency = iso_code
                    cleaned = cleaned.replace(symbol, "").strip()
                    break

            numeric_str = self._normalize_numeric_string(cleaned, raw_amount)
        else:
            raise ValueError(f"Tipo de dato no soportado para monto: {type(raw_amount).__name__}.")

        try:
            amount_dec = Decimal(numeric_str) / Decimal(str(divisor))
        except (InvalidOperation, ZeroDivisionError) as exc:
            raise ValueError(f"Error aritmético al convertir monto '{raw_amount}': {exc}") from exc

        final_currency: Optional[str] = None
        if isinstance(raw_currency, str) and raw_currency.strip():
            final_currency = raw_currency.strip().upper()
        elif inferred_currency:
            final_currency = inferred_currency

        return amount_dec, final_currency

    def parse_timestamp(self, raw_timestamp: Any, date_formats: List[str]) -> str:
        if not isinstance(raw_timestamp, str) or not raw_timestamp.strip():
            raise ValueError("La fecha está ausente o no es texto.")

        value = raw_timestamp.strip()

        # 1. Intentar formatos explícitos configurados para el proveedor
        for fmt in date_formats:
            try:
                dt = datetime.strptime(value, fmt)
                dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                continue

        # 2. Respaldo ISO-8601 completo con offsets complejos (ej. 2025-03-10T16:22:00+02:00)
        if "T" in value or " " in value:
            try:
                dt = datetime.fromisoformat(value)
                dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                pass

        raise ValueError(f"Fecha '{raw_timestamp}' no coincide con los formatos esperados.")

    def parse_status(self, raw_status: Any) -> str:
        if not isinstance(raw_status, str) or not raw_status.strip():
            raise ValueError("El estado está ausente o no es texto.")

        normalized = self.status_map.get(raw_status.strip().lower())
        if not normalized:
            raise ValueError(f"Estado no reconocido en catálogo: '{raw_status}'.")
        return normalized