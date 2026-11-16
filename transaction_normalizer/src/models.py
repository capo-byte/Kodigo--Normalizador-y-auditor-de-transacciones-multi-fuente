from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

CanonicalStatus = Literal["SUCCESS", "FAILED", "PENDING"]


@dataclass(frozen=True)
class TransactionRecord:
    """Representa una transacción válida bajo el esquema canónico."""
    transaction_id: str
    source: str
    amount: Decimal
    currency: str
    timestamp: str  # Formato ISO-8601 estandarizado (ej. 2025-03-10T14:22:00Z)
    status: CanonicalStatus

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el registro convirtiendo Decimal a float estándar para salida JSON."""
        return {
            "transaction_id": self.transaction_id,
            "source": self.source,
            "amount": float(self.amount),
            "currency": self.currency,
            "timestamp": self.timestamp,
            "status": self.status,
        }


@dataclass
class ValidationErrorRecord:
    """Registra un objeto rechazado junto con su contexto original y motivo de fallo."""
    raw_record: Dict[str, Any]
    detected_source: Optional[str]
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
