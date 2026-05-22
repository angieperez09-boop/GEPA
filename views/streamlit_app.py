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

# ─── CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GEPA-LAMIN | Acerías PazdelRío",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

APR_LOGO = "https://www.pazdelrio.com.co/wp-content/uploads/2023/04/Grupo-403.svg"
UPTC_LOGO = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/af/Logo_de_la_UPTC.svg/512px-Logo_de_la_UPTC.svg.png"
API_URL = "https://gepa.onrender.com/predict/schedule"

COLOR_DARK   = "#35352E"
COLOR_RED    = "#C0392B"
COLOR_GOLD   = "#D4A017"
COLOR_LIGHT  = "#F5F5F0"
COLOR_WHITE  = "#FFFFFF"

# ─── CSS CORPORATIVO ────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

  html, body, [class*="css"] {{
    font-family: 'Inter', sans-serif;
    background-color: {COLOR_LIGHT};
  }}

  /* Header */
  .gepa-header {{
    background: linear-gradient(135deg, {COLOR_DARK} 0%, #1a1a14 100%);
    padding: 1.2rem 2rem;
    border-radius: 0 0 12px 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  }}
  .gepa-header-left {{
    display: flex;
    align-items: center;
    gap: 1.2rem;
  }}
  .gepa-header h1 {{
    color: {COLOR_WHITE};
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0;
    letter-spacing: 1px;
  }}
  .gepa-header p {{
    color: #AAAAAA;
    font-size: 0.85rem;
    margin: 0;
    letter-spacing: 0.5px;
  }}
  .gepa-badge {{
    background: {COLOR_RED};
    color: white;
    padding: 0.25rem 0.7rem;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 1px;
  }}

  /* KPI Cards */
  .kpi-container {{
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }}
  .kpi-card {{
    background: {COLOR_WHITE};
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    flex: 1;
    border-left: 4px solid {COLOR_DARK};
    box-shadow: 0 2px 10px rgba(0,0,0,0.08);
  }}
  .kpi-card.red   {{ border-left-color: {COLOR_RED}; }}
  .kpi-card.gold  {{ border-left-color: {COLOR_GOLD}; }}
  .kpi-card.green {{ border-left-color: #27AE60; }}
  .kpi-label {{
    font-size: 0.75rem;
    color: #888;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 0.3rem;
  }}
  .kpi-value {{
    font-size: 1.9rem;
    font-weight: 700;
    color: {COLOR_DARK};
    line-height: 1;
  }}
  .kpi-sub {{
    font-size: 0.75rem;
    color: #888;
    margin-top: 0.2rem;
  }}

  /* Sección */
  .section-title {{
    font-size: 1rem;
    font-weight: 700;
    color: {COLOR_DARK};
    border-bottom: 2px solid {COLOR_RED};
    padding-bottom: 0.4rem;
    margin-bottom: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  /* Overflow row */
  .overflow-alert {{
    background: #FDECEA;
    border: 1px solid {COLOR_RED};
    border-radius: 8px;
    padding: 0.8rem 1.2rem;
    color: {COLOR_RED};
    font-weight: 600;
    margin-top: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}

  /* Footer */
  .gepa-footer {{
    background: {COLOR_DARK};
    color: #AAAAAA;
    padding: 1rem 2rem;
    border-radius: 12px 12px 0 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 2rem;
    font-size: 0.78rem;
  }}
  .gepa-footer strong {{ color: {COLOR_WHITE}; }}

  /* Sidebar */
  [data-testid="stSidebar"] {{
    background: {COLOR_DARK};
  }}
  [data-testid="stSidebar"] * {{
    color: {COLOR_WHITE} !important;
  }}
  [data-testid="stSidebar"] .stFileUploader label,
  [data-testid="stSidebar"] .stDateInput label,
  [data-testid="stSidebar"] .stTextInput label {{
    color: #CCCCCC !important;
    font-size: 0.82rem;
  }}
  section[data-testid="stSidebar"] {{
    min-width: 250px !important;
    transform: none !important;
    display: block !important;
  }}
  [data-testid="collapsedControl"] {{
    display: flex !important;
    visibility: visible !important;
  }}

  /* Botón principal */
  .stButton > button {{
    background: {COLOR_RED};
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.6rem 2rem;
    font-size: 0.95rem;
    width: 100%;
    transition: background 0.2s;
  }}
  .stButton > button:hover {{
    background: #A93226;
  }}

  /* Tabla */
  .dataframe {{ border-radius: 8px; overflow: hidden; }}
  thead tr th {{ background: {COLOR_DARK} !important; color: white !important; }}

  /* Ocultar menú Streamlit */
  #MainMenu, footer, header {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)


# ─── HEADER ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="gepa-header">
  <div class="gepa-header-left">
    <img src="{APR_LOGO}" height="52" style="filter: brightness(0) invert(1);" onerror="this.style.display='none'"/>
    <div>
      <h1>GEPA-LAMIN</h1>
      <p>Sistema Predictivo de Programación de Producción · Trenes Laminadores</p>
    </div>
  </div>
  <div style="display:flex; align-items:center; gap:1rem;">
    <span class="gepa-badge">ML POWERED</span>
    <span style="color:#888; font-size:0.78rem;">Acerías PazdelRío · Sogamoso</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─── MODELOS ────────────────────────────────────────────────────────────────
@st.cache_resource
def load_models():
    try:
        from joblib import load as jload
        d = ROOT / 'models' / 'artifacts'
        return (
            jload(d / 'xgb.joblib') if (d / 'xgb.joblib').exists() else None,
            jload(d / 'encoders.joblib') if (d / 'encoders.joblib').exists() else None,
            jload(d / 'feature_cols.joblib') if (d / 'feature_cols.joblib').exists() else [],
            jload(d / 'mtto_lookup.joblib') if (d / 'mtto_lookup.joblib').exists() else None,
            jload(d / 'setup_lookup.joblib') if (d / 'setup_lookup.joblib').exists() else None,
            jload(d / 'imprevistas_lookup.joblib') if (d / 'imprevistas_lookup.joblib').exists() else None,
            jload(d / 'imprevistas_model.joblib') if (d / 'imprevistas_model.joblib').exists() else None,
            jload(d / 'util_lookup.joblib') if (d / 'util_lookup.joblib').exists() else None,
            jload(d / 'util_product_lookup.joblib') if (d / 'util_product_lookup.joblib').exists() else None,
        )
    except Exception:
        return (None,) * 9


def parse_start_time(raw: str) -> time:
    cleaned = raw.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", cleaned):
        raise ValueError("Formato HH:MM requerido.")
    h, m = int(cleaned[:2]), int(cleaned[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Hora fuera de rango.")
    return time(h, m)


def to_excel_bytes(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()


# ─── SIDEBAR ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center; padding:1rem 0 1.5rem;'>
      <img src='{APR_LOGO}' width='120' style='filter: brightness(0) invert(1);'
           onerror="this.style.display='none'"/>
      <div style='margin-top:0.8rem; font-size:0.7rem; color:#888; letter-spacing:1px;'>
        SISTEMA DE PROGRAMACIÓN
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 📁 Archivo de entrada")
    uploaded = st.file_uploader("Programa TREN MORGAN (.xlsx)", type=["xlsx"], key="morgan",
                                 label_visibility="collapsed")

    st.markdown("#### 📅 Parámetros de programación")
    start_date = st.date_input("Fecha de inicio", value=date.today(), label_visibility="collapsed")
    start_time_text = st.text_input("Hora inicio (HH:MM)", value="00:00", max_chars=5)

    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.72rem; color:#888; line-height:1.6;'>
    <strong style='color:#ccc;'>Modelos activos</strong><br>
    🤖 XGBoost — R² = 0.9998<br>
    🌲 Random Forest — R² = 0.9922<br>
    ⚙️ Optimizador Held-Karp<br>
    📅 Scheduler secuencial 24h
    </div>
    """, unsafe_allow_html=True)

    generar = st.button("⚡ Generar Programación")


# ─── MAIN ───────────────────────────────────────────────────────────────────
month = start_date.month
year  = start_date.year

if uploaded is None:
    st.markdown("""
    <div style='background:white; border-radius:12px; padding:3rem; text-align:center;
                box-shadow:0 2px 10px rgba(0,0,0,0.08); margin:1rem 0;'>
      <div style='font-size:3rem;'>🏭</div>
      <h3 style='color:#35352E; margin:1rem 0 0.5rem;'>Bienvenido a GEPA-LAMIN</h3>
      <p style='color:#888; max-width:500px; margin:0 auto;'>
        Carga el archivo Excel del programa de laminación del <strong>Tren Morgan</strong>
        en el panel izquierdo y presiona <strong>Generar Programación</strong>.
      </p>
      <div style='margin-top:1.5rem; display:flex; justify-content:center; gap:2rem;
                  flex-wrap:wrap; font-size:0.82rem; color:#aaa;'>
        <span>📊 Predicción ML de productividad</span>
        <span>⚙️ Optimización de secuencias</span>
        <span>📅 Cronograma automático</span>
        <span>📥 Exportación Excel</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # Preview del archivo
    try:
        df_preview = pd.read_excel(uploaded, engine="openpyxl")
        uploaded.seek(0)

        _, enc, _, _, setup_lk, _, _, _, _ = load_models()
        df_valid_prev = validate_input_df(df_preview)
        df_valid_prev = optimize_campaign_order(df_valid_prev, tipo_cod=0,
                                                encoders=enc, setup_lookup=setup_lk)

        st.markdown(f'<div class="section-title">📋 Orden optimizado — {len(df_valid_prev)} materiales</div>',
                    unsafe_allow_html=True)
        st.dataframe(df_valid_prev[["material", "cantidad_t"]].rename(
            columns={"material": "Material", "cantidad_t": "Cantidad (t)"}),
            use_container_width=True, height=200)
    except Exception as e:
        st.warning(f"Vista previa no disponible: {e}")

    if generar:
        try:
            t_inicio = parse_start_time(start_time_text)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        initial_start = datetime.combine(start_date, t_inicio)

        with st.spinner("🔄 Enviando a la API y generando cronograma..."):
            try:
                import requests
                uploaded.seek(0)
                resp = requests.post(
                    API_URL,
                    files={"file_morgan": ("morgan.xlsx", uploaded.getvalue())},
                    data={"month": month, "year": year,
                          "initial_start": initial_start.isoformat(sep=" ")},
                    timeout=90,
                )
            except Exception as e:
                st.error(f"No se pudo conectar con la API: {e}")
                st.stop()

        if resp.status_code != 200:
            st.error(f"Error API {resp.status_code}: {resp.text[:300]}")
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

            # Detectar overflow
            overflow_mask = df["Material"].astype(str).str.contains("OVERFLOW", na=False)
            df_clean  = df[~overflow_mask]
            df_over   = df[overflow_mask]

            # ─── KPIs ───────────────────────────────────────────────────────
            total_t    = df_clean["Cantidad (t) Programada"].sum() if "Cantidad (t) Programada" in df_clean else 0
            total_h    = df_clean["Tiempo lam. (h)"].sum() if "Tiempo lam. (h)" in df_clean else 0
            util_mean  = df_clean["Índice de utilización (%)"].mean() if "Índice de utilización (%)" in df_clean else 0
            n_mats     = len(df_clean)
            has_over   = len(df_over) > 0
            over_h     = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0

            st.markdown(f"""
            <div class="kpi-container">
              <div class="kpi-card">
                <div class="kpi-label">📦 Toneladas programadas</div>
                <div class="kpi-value">{total_t:,.0f}</div>
                <div class="kpi-sub">{n_mats} órdenes de producción</div>
              </div>
              <div class="kpi-card gold">
                <div class="kpi-label">⏱ Horas de laminación</div>
                <div class="kpi-value">{total_h:,.1f}</div>
                <div class="kpi-sub">de 744 h disponibles en el mes</div>
              </div>
              <div class="kpi-card green">
                <div class="kpi-label">📊 Utilización promedio</div>
                <div class="kpi-value">{util_mean:.1f}%</div>
                <div class="kpi-sub">índice de eficiencia operativa</div>
              </div>
              <div class="kpi-card {'red' if has_over else ''}">
                <div class="kpi-label">⚠️ Overflow mensual</div>
                <div class="kpi-value" style="color:{'#C0392B' if has_over else '#27AE60'}">
                  {'SÍ' if has_over else 'NO'}
                </div>
                <div class="kpi-sub">{'%.1f h fuera del mes' % over_h if has_over else 'Programa dentro del mes'}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ─── CRONOGRAMA ─────────────────────────────────────────────────
            st.markdown(f'<div class="section-title">📅 Cronograma de producción — {month:02d}/{year}</div>',
                        unsafe_allow_html=True)
            st.dataframe(df_clean, use_container_width=True, height=420)

            if has_over:
                st.markdown(f"""
                <div class="overflow-alert">
                  ⚠️ &nbsp;<strong>ADVERTENCIA DE OVERFLOW:</strong>&nbsp;
                  El programa excede la capacidad mensual en <strong>{over_h:.1f} horas</strong>.
                  Se recomienda diferir algunas órdenes al mes siguiente.
                </div>
                """, unsafe_allow_html=True)

            # ─── DESCARGA ───────────────────────────────────────────────────
            st.markdown("<br>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.download_button(
                    label=f"📥 Descargar cronograma {month:02d}/{year}",
                    data=excel_bytes,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


# ─── FOOTER ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="gepa-footer">
  <div>
    <strong>GEPA-LAMIN</strong> · Sistema Predictivo de Programación de Producción<br>
    Especialización en Analítica Estratégica de Datos · 2026
  </div>
  <div style='display:flex; align-items:center; gap:1rem;'>
    <span>Angie Pérez · Manuel Quintero · Javier Ortiz · Jhon Patiño</span>
    <img src='{UPTC_LOGO}' height='36'
         style='filter: brightness(0) invert(1); opacity:0.85;'
         onerror="this.style.display='none'"/>
  </div>
</div>
""", unsafe_allow_html=True)