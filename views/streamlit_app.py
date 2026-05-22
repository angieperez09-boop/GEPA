import warnings
warnings.filterwarnings('ignore')

import os
import sys
import pathlib
import re
import base64
import io
from datetime import date, datetime, time
import pandas as pd
import numpy as np
import streamlit as st

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from controllers.utils.parsers import (
    validate_input_df, featurize, lookup_setup_duration,
    lookup_monthly_mtto_profile, allocate_monthly_mtto,
    lookup_util_pct, match_to_canonical,
)
from controllers.scheduler import run_scheduler
from controllers.config import get_family
from controllers.optimizer import optimize_campaign_order

st.set_page_config(
    page_title="GEPA-LAMIN | Acerías PazdelRío",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

APR_LOGO  = "https://www.pazdelrio.com.co/wp-content/uploads/2023/04/Grupo-403.svg"
UPTC_LOGO = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Logo_de_la_UPTC.svg/512px-Logo_de_la_UPTC.svg.png"
API_URL   = "https://gepa.onrender.com/predict/schedule"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; background-color: #F5F5F0; }
.gepa-header {
  background: linear-gradient(135deg, #35352E 0%, #1a1a14 100%);
  padding: 1.2rem 2rem; border-radius: 0 0 12px 12px;
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 1.5rem; box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.gepa-header-left { display: flex; align-items: center; gap: 1.2rem; }
.gepa-header h1 { color: #FFFFFF; font-size: 1.8rem; font-weight: 700; margin: 0; letter-spacing: 1px; }
.gepa-header p  { color: #AAAAAA; font-size: 0.85rem; margin: 0; }
.gepa-badge { background: #C0392B; color: white; padding: 0.25rem 0.7rem; border-radius: 20px; font-size: 0.7rem; font-weight: 600; letter-spacing: 1px; }
.kpi-container { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.kpi-card { background: #FFFFFF; border-radius: 12px; padding: 1.2rem 1.5rem; flex: 1; border-left: 4px solid #35352E; box-shadow: 0 2px 10px rgba(0,0,0,0.08); }
.kpi-card.red   { border-left-color: #C0392B; }
.kpi-card.gold  { border-left-color: #D4A017; }
.kpi-card.green { border-left-color: #27AE60; }
.kpi-label { font-size: 0.75rem; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 0.3rem; }
.kpi-value { font-size: 1.9rem; font-weight: 700; color: #35352E; line-height: 1; }
.kpi-sub   { font-size: 0.75rem; color: #888; margin-top: 0.2rem; }
.section-title { font-size: 1rem; font-weight: 700; color: #35352E; border-bottom: 2px solid #C0392B; padding-bottom: 0.4rem; margin-bottom: 1rem; text-transform: uppercase; letter-spacing: 0.5px; }
.overflow-alert { background: #FDECEA; border: 1px solid #C0392B; border-radius: 8px; padding: 0.8rem 1.2rem; color: #C0392B; font-weight: 600; margin-top: 1rem; }
.gepa-footer { background: #35352E; color: #AAAAAA; padding: 1rem 2rem; border-radius: 12px 12px 0 0; display: flex; align-items: center; justify-content: space-between; margin-top: 2rem; font-size: 0.78rem; }
.gepa-footer strong { color: #FFFFFF; }
[data-testid="stSidebar"] { background: #35352E; }
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
.stButton > button { background: #C0392B; color: white; border: none; border-radius: 8px; font-weight: 600; padding: 0.6rem 2rem; font-size: 0.95rem; width: 100%; }
.stButton > button:hover { background: #A93226; }
#MainMenu, footer, header { visibility: hidden; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

HEADER_HTML = (
    '<div class="gepa-header">'
    '<div class="gepa-header-left">'
    '<img src="' + APR_LOGO + '" height="52" style="filter: brightness(0) invert(1);" onerror="this.style.display=\'none\'"/>'
    '<div><h1>GEPA-LAMIN</h1>'
    '<p>Sistema Predictivo de Programación de Producción · Trenes Laminadores</p></div>'
    '</div>'
    '<div style="display:flex;align-items:center;gap:1rem;">'
    '<span class="gepa-badge">ML POWERED</span>'
    '<span style="color:#888;font-size:0.78rem;">Acerías PazdelRío · Sogamoso</span>'
    '</div></div>'
)
st.markdown(HEADER_HTML, unsafe_allow_html=True)


@st.cache_resource
def load_models():
    try:
        from joblib import load as jload
        d = ROOT / 'models' / 'artifacts'
        xgb  = jload(d / 'xgb.joblib') if (d / 'xgb.joblib').exists() else None
        enc  = jload(d / 'encoders.joblib') if (d / 'encoders.joblib').exists() else None
        fcol = jload(d / 'feature_cols.joblib') if (d / 'feature_cols.joblib').exists() else []
        mtto = jload(d / 'mtto_lookup.joblib') if (d / 'mtto_lookup.joblib').exists() else None
        setup= jload(d / 'setup_lookup.joblib') if (d / 'setup_lookup.joblib').exists() else None
        ilkp = jload(d / 'imprevistas_lookup.joblib') if (d / 'imprevistas_lookup.joblib').exists() else None
        imod = jload(d / 'imprevistas_model.joblib') if (d / 'imprevistas_model.joblib').exists() else None
        util = jload(d / 'util_lookup.joblib') if (d / 'util_lookup.joblib').exists() else None
        utp  = jload(d / 'util_product_lookup.joblib') if (d / 'util_product_lookup.joblib').exists() else None
        return xgb, enc, fcol, mtto, setup, ilkp, imod, util, utp
    except Exception:
        return (None,) * 9


def parse_start_time(raw):
    cleaned = raw.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", cleaned):
        raise ValueError("Formato HH:MM requerido.")
    h, m = int(cleaned[:2]), int(cleaned[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Hora fuera de rango.")
    return time(h, m)


# ─── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="text-align:center;padding:1rem 0 1.5rem;">'
        '<img src="' + APR_LOGO + '" width="120" style="filter:brightness(0) invert(1);" onerror="this.style.display=\'none\'"/>'
        '<div style="margin-top:0.8rem;font-size:0.7rem;color:#888;letter-spacing:1px;">SISTEMA DE PROGRAMACIÓN</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("#### 📁 Archivo de entrada")
    uploaded = st.file_uploader("Programa TREN MORGAN (.xlsx)", type=["xlsx"], key="morgan", label_visibility="collapsed")
    st.markdown("#### 📅 Parámetros")
    start_date = st.date_input("Fecha de inicio", value=date.today(), label_visibility="collapsed")
    start_time_text = st.text_input("Hora inicio (HH:MM)", value="00:00", max_chars=5)
    st.markdown("---")
    st.markdown(
        '<div style="font-size:0.72rem;color:#888;line-height:1.8;">'
        '<strong style="color:#ccc;">Modelos activos</strong><br>'
        '🤖 XGBoost — R² = 0.9998<br>'
        '🌲 Random Forest — R² = 0.9922<br>'
        '⚙️ Optimizador Held-Karp<br>'
        '📅 Scheduler secuencial 24h'
        '</div>',
        unsafe_allow_html=True,
    )
    generar = st.button("⚡ Generar Programación")

month = start_date.month
year  = start_date.year

# ─── MAIN ───────────────────────────────────────────────────────────────────
if uploaded is None:
    st.markdown(
        '<div style="background:white;border-radius:12px;padding:3rem;text-align:center;'
        'box-shadow:0 2px 10px rgba(0,0,0,0.08);margin:1rem 0;">'
        '<div style="font-size:3rem;">🏭</div>'
        '<h3 style="color:#35352E;margin:1rem 0 0.5rem;">Bienvenido a GEPA-LAMIN</h3>'
        '<p style="color:#888;max-width:500px;margin:0 auto;">'
        'Carga el archivo Excel del programa de laminación del <strong>Tren Morgan</strong> '
        'en el panel izquierdo y presiona <strong>Generar Programación</strong>.'
        '</p>'
        '<div style="margin-top:1.5rem;display:flex;justify-content:center;gap:2rem;'
        'flex-wrap:wrap;font-size:0.82rem;color:#aaa;">'
        '<span>📊 Predicción ML de productividad</span>'
        '<span>⚙️ Optimización de secuencias</span>'
        '<span>📅 Cronograma automático</span>'
        '<span>📥 Exportación Excel</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )
else:
    try:
        df_preview = pd.read_excel(uploaded, engine="openpyxl")
        uploaded.seek(0)
        _, enc, _, _, setup_lk, _, _, _, _ = load_models()
        df_vp = validate_input_df(df_preview)
        df_vp = optimize_campaign_order(df_vp, tipo_cod=0, encoders=enc, setup_lookup=setup_lk)
        st.markdown('<div class="section-title">📋 Orden optimizado de materiales</div>', unsafe_allow_html=True)
        st.dataframe(
            df_vp[["material","cantidad_t"]].rename(columns={"material":"Material","cantidad_t":"Cantidad (t)"}),
            use_container_width=True, height=200,
        )
    except Exception as e:
        st.warning("Vista previa no disponible: " + str(e))

    if generar:
        try:
            t_inicio = parse_start_time(start_time_text)
        except ValueError as ve:
            st.error(str(ve))
            st.stop()

        initial_start = datetime.combine(start_date, t_inicio)

        with st.spinner("🔄 Generando cronograma con IA..."):
            try:
                import requests
                uploaded.seek(0)
                resp = requests.post(
                    API_URL,
                    files={"file_morgan": ("morgan.xlsx", uploaded.getvalue())},
                    data={"month": month, "year": year, "initial_start": initial_start.isoformat(sep=" ")},
                    timeout=90,
                )
            except Exception as conn_err:
                st.error("No se pudo conectar con la API: " + str(conn_err))
                st.stop()

        if resp.status_code != 200:
            st.error("Error API " + str(resp.status_code) + ": " + resp.text[:300])
            st.stop()

        j = resp.json()
        for res in j.get("results", []):
            excel_b64 = res.get("excel_b64")
            filename  = res.get("filename", "cronograma.xlsx")

            if not excel_b64:
                st.warning("La API no devolvió el cronograma.")
                continue

            excel_bytes = base64.b64decode(excel_b64)
            df = pd.read_excel(io.BytesIO(excel_bytes))

            if "t/día efectiva" in df.columns:
                df["t/día"] = df["t/día efectiva"]
                df = df.drop(columns=["t/día efectiva"], errors="ignore")

            overflow_mask = df["Material"].astype(str).str.contains("OVERFLOW", na=False)
            df_clean = df[~overflow_mask]
            df_over  = df[overflow_mask]

            total_t   = df_clean["Cantidad (t) Programada"].sum() if "Cantidad (t) Programada" in df_clean.columns else 0
            total_h   = df_clean["Tiempo lam. (h)"].sum() if "Tiempo lam. (h)" in df_clean.columns else 0
            util_mean = df_clean["Índice de utilización (%)"].mean() if "Índice de utilización (%)" in df_clean.columns else 0
            n_mats    = len(df_clean)
            has_over  = len(df_over) > 0
            over_h    = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0.0

            kpi_html = (
                '<div class="kpi-container">'
                '<div class="kpi-card">'
                '<div class="kpi-label">📦 Toneladas programadas</div>'
                '<div class="kpi-value">' + "{:,.0f}".format(total_t) + '</div>'
                '<div class="kpi-sub">' + str(n_mats) + ' órdenes de producción</div>'
                '</div>'
                '<div class="kpi-card gold">'
                '<div class="kpi-label">⏱ Horas de laminación</div>'
                '<div class="kpi-value">' + "{:,.1f}".format(total_h) + '</div>'
                '<div class="kpi-sub">de 744 h disponibles en el mes</div>'
                '</div>'
                '<div class="kpi-card green">'
                '<div class="kpi-label">📊 Utilización promedio</div>'
                '<div class="kpi-value">' + "{:.1f}%".format(util_mean) + '</div>'
                '<div class="kpi-sub">índice de eficiencia operativa</div>'
                '</div>'
                '<div class="kpi-card ' + ('red' if has_over else '') + '">'
                '<div class="kpi-label">⚠️ Overflow mensual</div>'
                '<div class="kpi-value" style="color:' + ('#C0392B' if has_over else '#27AE60') + '">'
                + ('SÍ' if has_over else 'NO') +
                '</div>'
                '<div class="kpi-sub">' + ("{:.1f} h fuera del mes".format(over_h) if has_over else "Programa dentro del mes") + '</div>'
                '</div>'
                '</div>'
            )
            st.markdown(kpi_html, unsafe_allow_html=True)

            st.markdown('<div class="section-title">📅 Cronograma de producción</div>', unsafe_allow_html=True)
            st.dataframe(df_clean, use_container_width=True, height=420)

            if has_over:
                st.markdown(
                    '<div class="overflow-alert">⚠️ <strong>ADVERTENCIA DE OVERFLOW:</strong> '
                    'El programa excede la capacidad mensual en <strong>' + "{:.1f}".format(over_h) + ' horas</strong>. '
                    'Se recomienda diferir algunas órdenes al mes siguiente.</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                st.download_button(
                    label="📥 Descargar cronograma {:02d}/{}".format(month, year),
                    data=excel_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

# ─── FOOTER ─────────────────────────────────────────────────────────────────
FOOTER_HTML = (
    '<div class="gepa-footer">'
    '<div><strong>GEPA-LAMIN</strong> · Sistema Predictivo de Programación de Producción<br>'
    'Especialización en Analítica Estratégica de Datos · 2026</div>'
    '<div style="display:flex;align-items:center;gap:1rem;">'
    '<span>Angie Pérez · Manuel Quintero · Javier Ortiz · Jhon Patiño</span>'
    '<img src="' + UPTC_LOGO + '" height="36" style="filter:brightness(0) invert(1);opacity:0.85;" onerror="this.style.display=\'none\'"/>'
    '</div></div>'
)
st.markdown(FOOTER_HTML, unsafe_allow_html=True)