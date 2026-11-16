import json
import sys
from pathlib import Path
import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from src.metrics import MetricsEngine
from src.validator import RecordValidator

st.set_page_config(
    page_title="Normalizador de Transacciones Multi-Fuente",
    layout="wide",
    page_icon="📊",
)

st.title("📊 Panel de Normalización y Auditoría Financiera")
st.markdown(
    "Pipeline ETL desacoplado con precisión aritmética (`decimal.Decimal`), "
    "detección de duplicados, enrutamiento a cuarentena y analítica por divisa."
)

RULES_PATH = BASE_DIR / "config" / "rules.json"
DEFAULT_INPUT_PATH = BASE_DIR / "data" / "input_sample.json"

with RULES_PATH.open("r", encoding="utf-8") as f:
    RULES = json.load(f)


def execute_etl(raw_data: object) -> dict:
    validator = RecordValidator(RULES)
    valid_recs, invalid_recs = validator.process_batch(raw_data)
    metrics = MetricsEngine.compute(valid_recs, invalid_recs)
    return {
        "valid_records": [r.to_dict() for r in valid_recs],
        "invalid_records": [e.to_dict() for e in invalid_recs],
        "metrics": metrics,
    }


# --- Barra lateral: Ingesta de datos ---
st.sidebar.header("📥 Ingesta de Datos")
uploaded_file = st.sidebar.file_uploader(
    "Sube un archivo JSON de transacciones", type=["json"]
)

if "active_source_key" not in st.session_state:
    st.session_state.active_source_key = None
if "pipeline_output" not in st.session_state:
    st.session_state.pipeline_output = None

if uploaded_file is not None:
    file_key = f"upload:{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.active_source_key != file_key:
        try:
            payload = json.load(uploaded_file)
            st.session_state.pipeline_output = execute_etl(payload)
            st.session_state.active_source_key = file_key
        except Exception as exc:
            st.sidebar.error(f"Error al procesar el JSON subido: {exc}")
    st.sidebar.success(f"Fuente activa: `{uploaded_file.name}`")
else:
    if st.session_state.active_source_key != "default_sample":
        if DEFAULT_INPUT_PATH.exists():
            with DEFAULT_INPUT_PATH.open("r", encoding="utf-8") as f:
                sample_payload = json.load(f)
            st.session_state.pipeline_output = execute_etl(sample_payload)
            st.session_state.active_source_key = "default_sample"
    st.sidebar.info("Fuente activa: `data/input_sample.json` (Muestra)")

output = st.session_state.pipeline_output

if output:
    metrics = output["metrics"]
    valid_data = output["valid_records"]
    invalid_data = output["invalid_records"]
    summary = metrics["summary"]

    # 1. KPIs Principales
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Procesados", summary["total_processed"])
    c2.metric("Registros Válidos", summary["valid_count"])
    c3.metric("En Cuarentena", summary["invalid_count"])
    c4.metric("Tasa de Validez", f"{summary['validation_rate_pct']}%")

    st.divider()

    # 2. Visualización Gráfica
    g1, g2 = st.columns(2)
    with g1:
        st.subheader("💰 Volumen Monetario por Divisa")
        if metrics["amount_by_currency"]:
            df_cur = pd.DataFrame({
                "Total General": metrics["amount_by_currency"],
                "Total Exitoso (SUCCESS)": metrics["success_amount_by_currency"],
            }).fillna(0.0)
            st.bar_chart(df_cur)
        else:
            st.info("Sin montos válidos para graficar.")

    with g2:
        st.subheader("📈 Distribución por Estado Canónico")
        df_status = pd.DataFrame.from_dict(
            metrics["counts_by_status"], orient="index", columns=["Transacciones"]
        )
        st.bar_chart(df_status)

    st.divider()

    # 3. Explorador Multidimensional de Registros Válidos
    st.subheader("🔍 Explorador de Registros Válidos (Esquema Canónico)")
    if valid_data:
        df_valid = pd.DataFrame(valid_data)
        df_valid["date_only"] = pd.to_datetime(df_valid["timestamp"]).dt.date

        f1, f2, f3, f4 = st.columns(4)
        search_id = f1.text_input("Buscar por ID de transacción:", placeholder="Ej. TX-1001")
        selected_sources = f2.multiselect(
            "Fuente:",
            options=sorted(df_valid["source"].unique()),
            default=sorted(df_valid["source"].unique()),
        )
        selected_currencies = f3.multiselect(
            "Divisa:",
            options=sorted(df_valid["currency"].unique()),
            default=sorted(df_valid["currency"].unique()),
        )
        selected_statuses = f4.multiselect(
            "Estado:",
            options=sorted(df_valid["status"].unique()),
            default=sorted(df_valid["status"].unique()),
        )

        min_date, max_date = df_valid["date_only"].min(), df_valid["date_only"].max()
        date_range = st.date_input(
            "Rango de fechas (UTC):",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        mask = (
            df_valid["source"].isin(selected_sources)
            & df_valid["currency"].isin(selected_currencies)
            & df_valid["status"].isin(selected_statuses)
        )
        if search_id.strip():
            mask &= df_valid["transaction_id"].str.contains(search_id.strip(), case=False, na=False)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            mask &= (df_valid["date_only"] >= date_range[0]) & (df_valid["date_only"] <= date_range[1])

        filtered_df = df_valid.loc[mask].drop(columns=["date_only"])
        st.dataframe(filtered_df, use_container_width=True)

        # Botones de exportación de datos limpios
        dl1, dl2 = st.columns(2)
        dl1.download_button(
            label="⬇️ Descargar Válidos (CSV)",
            data=filtered_df.to_csv(index=False).encode("utf-8"),
            file_name="transacciones_normalizadas.csv",
            mime="text/csv",
        )
        dl2.download_button(
            label="⬇️ Descargar Válidos (JSON)",
            data=filtered_df.to_json(orient="records", indent=2, force_ascii=False).encode("utf-8"),
            file_name="transacciones_normalizadas.json",
            mime="application/json",
        )
    else:
        st.info("No hay registros válidos en este lote.")

    st.divider()

    # 4. Auditoría de Cuarentena
    st.subheader("⚠️ Auditoría de Registros en Cuarentena")
    if invalid_data:
        if metrics.get("quarantine_reasons_breakdown"):
            st.caption("Frecuencia de causas de rechazo:")
            df_reasons = pd.DataFrame.from_dict(
                metrics["quarantine_reasons_breakdown"], orient="index", columns=["Ocurrencias"]
            )
            st.bar_chart(df_reasons)

        quarantine_rows = [
            {
                "Fuente Detectada": item.get("detected_source") or "Desconocida",
                "Motivos de Rechazo": " | ".join(item.get("errors", [])),
                "Registro Original": json.dumps(item.get("raw_record", {}), ensure_ascii=False),
            }
            for item in invalid_data
        ]
        st.dataframe(pd.DataFrame(quarantine_rows), use_container_width=True)

        st.download_button(
            label="⬇️ Descargar Reporte de Cuarentena (JSON)",
            data=json.dumps(invalid_data, indent=2, ensure_ascii=False).encode("utf-8"),
            file_name="quarantine_report.json",
            mime="application/json",
        )
    else:
        st.success("No se detectaron registros inválidos en este lote.")