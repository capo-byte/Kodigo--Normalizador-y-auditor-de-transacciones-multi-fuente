from typing import Any, Dict, Optional


class SourceDetector:
    """Identifica el proveedor de origen mediante la firma estructural de llaves JSON."""

    def __init__(self, sources_config: Dict[str, Any]) -> None:
        self.signatures: Dict[str, set[str]] = {
            source_name: set(cfg["signature_keys"])
            for source_name, cfg in sources_config.items()
        }

    def detect(self, raw_record: Dict[str, Any]) -> Optional[str]:
        if not isinstance(raw_record, dict) or not raw_record:
            return None

        record_keys = set(raw_record.keys())

        # 1. Coincidencia exacta de esquema
        for source_name, sig_keys in self.signatures.items():
            if record_keys == sig_keys:
                return source_name

        # 2. Respaldo: todas las llaves obligatorias presentes (ordenadas por especificidad)
        candidates = [
            (len(sig_keys), source_name)
            for source_name, sig_keys in self.signatures.items()
            if sig_keys.issubset(record_keys)
        ]
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        return None
