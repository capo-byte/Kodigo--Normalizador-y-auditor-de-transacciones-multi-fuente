import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from src.metrics import MetricsEngine
from src.validator import RecordValidator

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_RULES_PATH = BASE_DIR / "config" / "rules.json"
DEFAULT_INPUT_PATH = BASE_DIR / "data" / "input_sample.json"
DEFAULT_QUARANTINE_PATH = BASE_DIR / "data" / "quarantine.json"


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_pipeline(
    input_path: Path = DEFAULT_INPUT_PATH,
    rules_path: Path = DEFAULT_RULES_PATH,
    quarantine_path: Path = DEFAULT_QUARANTINE_PATH,
    output_valid_path: Path | None = None,
) -> Dict[str, Any]:
    rules = load_json(rules_path)
    raw_records = load_json(input_path)

    validator = RecordValidator(rules)
    valid_records, invalid_records = validator.process_batch(raw_records)

    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    quarantine_payload = [err.to_dict() for err in invalid_records]
    with quarantine_path.open("w", encoding="utf-8") as f:
        json.dump(quarantine_payload, f, indent=2, ensure_ascii=False)

    valid_payload = [r.to_dict() for r in valid_records]
    if output_valid_path is not None:
        output_valid_path.parent.mkdir(parents=True, exist_ok=True)
        with output_valid_path.open("w", encoding="utf-8") as f:
            json.dump(valid_payload, f, indent=2, ensure_ascii=False)

    metrics = MetricsEngine.compute(valid_records, invalid_records)
    return {
        "valid_records": valid_payload,
        "invalid_records": quarantine_payload,
        "metrics": metrics,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline ETL de normalización y auditoría de transacciones multi-fuente."
    )
    parser.add_argument(
        "-i", "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="Ruta al archivo JSON de entrada (por defecto: data/input_sample.json).",
    )
    parser.add_argument(
        "-r", "--rules",
        type=Path,
        default=DEFAULT_RULES_PATH,
        help="Ruta al archivo JSON de reglas (por defecto: config/rules.json).",
    )
    parser.add_argument(
        "-q", "--quarantine",
        type=Path,
        default=DEFAULT_QUARANTINE_PATH,
        help="Ruta de salida para registros en cuarentena (por defecto: data/quarantine.json).",
    )
    parser.add_argument(
        "-o", "--output-valid",
        type=Path,
        default=None,
        help="Ruta opcional para exportar las transacciones válidas normalizadas en JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        output = run_pipeline(
            input_path=args.input,
            rules_path=args.rules,
            quarantine_path=args.quarantine,
            output_valid_path=args.output_valid,
        )
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR DE EJECUCIÓN] {exc}", file=sys.stderr)
        sys.exit(1)

    print("=== MÉTRICAS DEL PIPELINE ===")
    print(json.dumps(output["metrics"], indent=2, ensure_ascii=False))
    print(f"\nRegistros válidos: {len(output['valid_records'])}")
    if args.output_valid:
        print(f"Exportados válidos -> {args.output_valid}")
    print(f"Registros en cuarentena: {len(output['invalid_records'])} -> {args.quarantine}")