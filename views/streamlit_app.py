import warnings
warnings.filterwarnings('ignore')

import os
import sys
import pathlib
import re
from datetime import date, datetime, time
import pandas as pd
import numpy as np
import streamlit as st

# Ensure project root is on sys.path so MVC packages resolve when Streamlit runs
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controllers.utils.parsers import (
    validate_input_df,
    featurize,
    lookup_setup_duration,
    lookup_monthly_mtto_profile,
    allocate_monthly_mtto,
    lookup_util_pct,
    match_to_canonical,
)
from controllers.scheduler import run_scheduler
from controllers.config import get_family
from controllers.optimizer import optimize_campaign_order


@st.cache_resource
def load_models():
    try:
        from joblib import load
        models_dir = ROOT / 'models' / 'artifacts'
        xgb = load(models_dir / 'xgb.joblib') if (models_dir / 'xgb.joblib').exists() else None
        enc = load(models_dir / 'encoders.joblib') if (models_dir / 'encoders.joblib').exists() else None
        fcols = load(models_dir / 'feature_cols.joblib') if (models_dir / 'feature_cols.joblib').exists() else []
        mtto = load(models_dir / 'mtto_lookup.joblib') if (models_dir / 'mtto_lookup.joblib').exists() else None
        setup = load(models_dir / 'setup_lookup.joblib') if (models_dir / 'setup_lookup.joblib').exists() else None
        imprevistas_lookup = load(models_dir / 'imprevistas_lookup.joblib') if (models_dir / 'imprevistas_lookup.joblib').exists() else None
        imprevistas_model = load(models_dir / 'imprevistas_model.joblib') if (models_dir / 'imprevistas_model.joblib').exists() else None
        util = load(models_dir / 'util_lookup.joblib') if (models_dir / 'util_lookup.joblib').exists() else None
        util_product = load(models_dir / 'util_product_lookup.joblib') if (models_dir / 'util_product_lookup.joblib').exists() else None
        return xgb, enc, fcols, mtto, setup, imprevistas_lookup, imprevistas_model, util, util_product
    except Exception:
        return (None,) * 9


def predict_local(X, df_feat, plant_name, month):
    xgb_model, encoders, feature_cols, mtto_lookup, setup_lookup, imprevistas_lookup, imprevistas_model, util_lookup, util_product_lookup = load_models()

    n = len(X)
    if xgb_model is None or encoders is None:
        return pd.DataFrame({
            "product_t_h": [50.0] * n,
            "mtto_h": [0.0] * n,
            "setup_h": [0.0] * n,
            "paradas_imprev_h": [0.0] * n,
            "util_pct": [0.0] * n,
        })

    le = encoders['producto']
    tipo_cod = 0 if 'MORGAN' in plant_name.upper() else 1
    X_m = X.copy()
    matched = X_m['producto'].apply(lambda m: match_to_canonical(m, le.classes_))
    X_m['producto_cod'] = le.transform(matched)
    X_m['tipo_cod'] = tipo_cod

    matched_list = matched.tolist()
    familias = [get_family(m) for m in matched_list]

    # mtto: allocate monthly profile
    mtto = np.zeros(n)
    if mtto_lookup is not None:
        mtto_count, mtto_duration = lookup_monthly_mtto_profile(mtto_lookup, tipo_cod, month)
        mtto = allocate_monthly_mtto(matched_list, mtto_count, mtto_duration)

    # setup
    setup = np.zeros(n)
    if setup_lookup is not None:
        for i in range(n):
            is_transition = (i < n - 1) and (familias[i] != familias[i + 1])
            if is_transition:
                setup[i] = lookup_setup_duration(setup_lookup, tipo_cod, matched_list[i], familias[i], familias[i + 1])

    # imprevistas
    imprevistas = np.zeros(n)
    if imprevistas is not None:
        # prefer model prediction if available
        try:
            if imprevistas_lookup is None and imprevistas_model is None:
                imprevistas = np.zeros(n)
            elif imprevistas_model is not None:
                imp_cols = [c for c in ['tipo_cod', 'producto_cod', 'mes_num', 'anio', 'hora_inicio', 'dia_semana'] if c in X_m.columns]
                X_imp_in = X_m[imp_cols].copy().fillna(0)
                imprevistas = imprevistas_model.predict(X_imp_in.values if hasattr(imprevistas_model, 'predict') else X_imp_in)
                imprevistas = np.nan_to_num(imprevistas, 0.0)
            else:
                for i in range(n):
                    key = (tipo_cod, matched_list[i], month)
                    try:
                        imprevistas[i] = float(imprevistas_lookup.get(key, 0.0))
                    except Exception:
                        imprevistas[i] = 0.0
        except Exception:
            imprevistas = np.zeros(n)

    # util_pct by product/family lookup (prefer product-level)
    util_lookups = {'family': util_lookup, 'product': util_product_lookup}
    util_pct = [lookup_util_pct(util_lookups, tipo_cod, familias[i], matched_list[i], 0.0) for i in range(n)]

    # populate features needed by model before predicting
    X_m['mtto_h'] = mtto
    X_m['paradas_setup_h'] = setup
    X_m['paradas_imprev_h'] = imprevistas
    X_m['paradas_total_h'] = X_m['paradas_setup_h'] + X_m['paradas_imprev_h']

    for c in feature_cols:
        if c not in X_m.columns:
            X_m[c] = 0

    try:
        preds = xgb_model.predict(X_m[feature_cols].values)
    except Exception:
        preds = np.full(n, 50.0)

    # compute tiempo_lam_h per row (cantidad / product_t_h)
    cantidad = df_feat.get('cantidad_t') if hasattr(df_feat, 'get') else df_feat['cantidad_t']
    tiempo_lam = np.zeros(n)
    for i in range(n):
        try:
            cant = float(cantidad.iloc[i]) if cantidad is not None else 0.0
        except Exception:
            cant = 0.0
        prod = float(preds[i]) if i < len(preds) else 0.0
        tiempo_lam[i] = (cant / prod) if prod > 0 else 0.0

    # apply formula: ((cantidad/product)/util_pct) - tiempo_lam
    paradas_calc = np.zeros(n)
    for i in range(n):
        u = util_pct[i]
        if u and u > 0 and tiempo_lam[i] >= 0:
            paradas_calc[i] = (tiempo_lam[i] / u) - tiempo_lam[i]
        else:
            paradas_calc[i] = imprevistas[i]

    return pd.DataFrame({
        "product_t_h": preds,
        "mtto_h": mtto,
        "setup_h": setup,
        "paradas_imprev_h": paradas_calc,
        "util_pct": util_pct,
    })


st.title("GEPA - Programación de Laminación (Prototipo)")

st.header("Sube un archivo de la planta (TREN MORGAN)")
uploaded_morgan = st.file_uploader("TREN MORGAN (.xlsx)", type=["xlsx"], key="morgan")
start_date = st.date_input("Fecha inicio del primer material", value=date.today())
start_time_text = st.text_input(
    "Hora inicio del primer material",
    value="00:00",
    max_chars=5,
    help="Usa el formato HH:MM",
    placeholder="00:00",
)


def parse_start_time(raw_value: str) -> time:
    cleaned = raw_value.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", cleaned):
        raise ValueError("La hora debe tener el formato HH:MM usando solo números.")
    hour_text, minute_text = cleaned.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23:
        raise ValueError("La hora debe estar entre 00 y 23.")
    if minute < 0 or minute > 59:
        raise ValueError("Los minutos deben estar entre 00 y 59.")
    return time(hour, minute)


def build_initial_start(selected_date: date, raw_time: str) -> datetime:
    return datetime.combine(selected_date, parse_start_time(raw_time))


month = start_date.month
year = start_date.year


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    import io

    with io.BytesIO() as buffer:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        return buffer.getvalue()

if uploaded_morgan is not None:
    try:
        df_m = pd.read_excel(uploaded_morgan, engine="openpyxl")
        df_m_valid = validate_input_df(df_m)

        # Optimize campaign order so the preview reflects what the backend will produce.
        _, encoders_m, _, _, setup_lookup_m, _, _, _, _ = load_models()
        df_m_valid = optimize_campaign_order(
            df_m_valid,
            tipo_cod=0,
            encoders=encoders_m,
            setup_lookup=setup_lookup_m,
        )

        X_m, df_m_feat = featurize(df_m_valid, int(month), int(year))

        st.subheader(f"Preview TREN MORGAN — {len(df_m_valid)} filas (orden optimizado por campañas)")
        st.dataframe(df_m_valid, height=400)

        if st.button("Generar programación"):
            # always send files to backend API
            try:
                initial_start = build_initial_start(start_date, start_time_text)
                import requests
                url = "https://gepa.onrender.com/predict/schedule"
                files = {
                    'file_morgan': ('morgan.xlsx', uploaded_morgan.getvalue()),
                }
                data = {'month': int(month), 'year': int(year), 'initial_start': initial_start.isoformat(sep=' ')}
                with st.spinner('Enviando archivos al servidor...'):
                    resp = requests.post(url, files=files, data=data, timeout=60)
                if resp.status_code != 200:
                    st.error(f"Error del servidor: {resp.status_code} - {resp.text}")
                else:
                    j = resp.json()
                    for res in j.get('results', []):
                        st.subheader(f"Programación {res.get('plant')}")
                        excel_b64 = res.get('excel_b64')
                        filename = res.get('filename', f"{res.get('plant')}_schedule.xlsx")
                        if excel_b64:
                            import base64, io
                            excel_bytes = base64.b64decode(excel_b64)
                            df_full = pd.read_excel(io.BytesIO(excel_bytes))
                            if 't/día efectiva' in df_full.columns:
                                df_full['t/día'] = df_full['t/día efectiva']
                                df_full = df_full.drop(columns=['t/día efectiva'], errors='ignore')
                            st.write(f"Mostrando planilla completa: {len(df_full)} filas")
                            st.dataframe(df_full)
                            st.download_button(f"Descargar {res.get('plant')}", excel_bytes, file_name=filename)
                        else:
                            st.warning("El servidor no devolvió el cronograma.")
            except Exception as e:
                st.error(f"Error enviando al servidor: {e}")
    except Exception as e:
        st.error(f"Error procesando los archivos: {e}")
else:
    st.info("Sube el archivo TREN MORGAN (.xlsx) para generar la programación en el servidor.")
