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
[data-testid="stSidebar"] .stFileUploader label,
[data-testid="stSidebar"] .stDateInput label,
[data-testid="stSidebar"] .stTextInput label { color: #CCCCCC !important; font-size: 0.82rem; }
section[data-testid="stSidebar"] { min-width: 250px !important; transform: none !important; display: block !important; }
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }
[data-testid="stSidebar"] input { color: #35352E !important; background: #FFFFFF !important; }
[data-testid="stSidebar"] .stDateInput input { color: #35352E !important; }
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


def render_kpis(df_clean, df_over):
    total_t   = df_clean["Cantidad (t) Programada"].sum() if "Cantidad (t) Programada" in df_clean.columns else 0
    total_h   = df_clean["Tiempo lam. (h)"].sum() if "Tiempo lam. (h)" in df_clean.columns else 0
    util_mean = df_clean["Índice de utilización (%)"].mean() if "Índice de utilización (%)" in df_clean.columns else 0
    n_mats    = len(df_clean)
    has_over  = len(df_over) > 0
    over_h    = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0.0

    st.markdown(
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
        '</div>',
        unsafe_allow_html=True,
    )
    return total_t, total_h, util_mean, n_mats, has_over, over_h


def render_dashboard(df_clean, month, year):
    import plotly.express as px
    import plotly.graph_objects as go

    DARK  = "#35352E"
    RED   = "#C0392B"
    GOLD  = "#D4A017"
    GREEN = "#27AE60"
    COLORS = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
              "#44BBA4", "#E94F37", "#393E41", "#F5A623", "#7B2D8B",
              "#1A936F", "#C6425E", "#5C7AEA", "#F4845F", "#2D6A4F"]

    st.markdown('<div class="section-title">📊 Dashboard Ejecutivo</div>', unsafe_allow_html=True)

    # ── GANTT ──────────────────────────────────────────────────────────────
    if "Inicio" in df_clean.columns and "Fin" in df_clean.columns:
        df_gantt = df_clean.copy()
        df_gantt["Inicio"] = pd.to_datetime(df_gantt["Inicio"], errors="coerce")
        df_gantt["Fin"]    = pd.to_datetime(df_gantt["Fin"],    errors="coerce")
        df_gantt = df_gantt.dropna(subset=["Inicio", "Fin"])
        df_gantt["Material_corto"] = df_gantt["Material"].str[:25]

        mat_list = df_gantt["Material_corto"].tolist()
        color_map = {m: COLORS[i % len(COLORS)] for i, m in enumerate(mat_list)}

        fig_gantt = go.Figure()
        for _, row in df_gantt.iterrows():
            dur_h = (row["Fin"] - row["Inicio"]).total_seconds() / 3600
            fig_gantt.add_trace(go.Bar(
                x=[dur_h],
                y=[row["Material_corto"]],
                orientation="h",
                base=[(row["Inicio"] - df_gantt["Inicio"].min()).total_seconds() / 3600],
                marker_color=color_map[row["Material_corto"]],
                name=row["Material_corto"],
                showlegend=False,
                hovertemplate=(
                    "<b>" + row["Material_corto"] + "</b><br>"
                    "Inicio: " + str(row["Inicio"]) + "<br>"
                    "Fin: " + str(row["Fin"]) + "<br>"
                    "Duración: " + "{:.1f}".format(dur_h) + " h<br>"
                    "Cantidad: " + "{:,.0f}".format(row.get("Cantidad (t) Programada", 0)) + " t"
                    "<extra></extra>"
                ),
            ))

        fig_gantt.update_layout(
            title=dict(text="Cronograma de Producción — {:02d}/{}".format(month, year),
                       font=dict(size=16, color=DARK, family="Inter")),
            xaxis_title="Horas desde inicio",
            yaxis=dict(autorange="reversed", tickfont=dict(size=11)),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#F5F5F0",
            height=max(350, len(df_gantt) * 28 + 80),
            margin=dict(l=20, r=20, t=50, b=40),
            bargap=0.25,
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

    col1, col2 = st.columns(2)

    # ── PRODUCTIVIDAD ──────────────────────────────────────────────────────
    with col1:
        if "Product. (t/h)" in df_clean.columns:
            df_prod = df_clean[["Material", "Product. (t/h)"]].copy()
            df_prod["Material"] = df_prod["Material"].str[:20]
            df_prod = df_prod.sort_values("Product. (t/h)", ascending=True)
            fig_prod = px.bar(
                df_prod, x="Product. (t/h)", y="Material", orientation="h",
                color="Product. (t/h)",
                color_continuous_scale=[[0, "#D4A017"], [0.5, "#2E86AB"], [1, "#35352E"]],
                title="Productividad por Material (t/h)",
            )
            fig_prod.update_layout(
                plot_bgcolor="#FFFFFF", paper_bgcolor="#F5F5F0",
                height=380, showlegend=False,
                coloraxis_showscale=False,
                title_font=dict(size=14, color=DARK, family="Inter"),
                margin=dict(l=10, r=10, t=45, b=30),
            )
            fig_prod.update_traces(hovertemplate="<b>%{y}</b><br>%{x:.1f} t/h<extra></extra>")
            st.plotly_chart(fig_prod, use_container_width=True)

    # ── UTILIZACIÓN DONA ──────────────────────────────────────────────────
    with col2:
        if all(c in df_clean.columns for c in ["Tiempo lam. (h)", "Paradas setups (h)", "Paradas imprevistas (h)", "Mtto pro. (h)"]):
            lam   = df_clean["Tiempo lam. (h)"].sum()
            setup = df_clean["Paradas setups (h)"].sum()
            imp   = df_clean["Paradas imprevistas (h)"].sum()
            mtto  = df_clean["Mtto pro. (h)"].sum()
            fig_dona = go.Figure(go.Pie(
                labels=["Laminación efectiva", "Paradas setup", "Paradas imprevistas", "Mantenimiento"],
                values=[lam, setup, imp, mtto],
                hole=0.55,
                marker_colors=[GREEN, GOLD, RED, "#888888"],
                textinfo="percent+label",
                textfont=dict(size=11),
                hovertemplate="<b>%{label}</b><br>%{value:.1f} h (%{percent})<extra></extra>",
            ))
            fig_dona.update_layout(
                title=dict(text="Distribución del Tiempo Total", font=dict(size=14, color=DARK, family="Inter")),
                plot_bgcolor="#FFFFFF", paper_bgcolor="#F5F5F0",
                height=380,
                margin=dict(l=10, r=10, t=45, b=30),
                showlegend=True,
                legend=dict(orientation="v", font=dict(size=10)),
                annotations=[dict(text="Tiempo<br>Total", x=0.5, y=0.5,
                                  font_size=13, showarrow=False, font_color=DARK)],
            )
            st.plotly_chart(fig_dona, use_container_width=True)

    # ── TONELADAS POR MATERIAL ─────────────────────────────────────────────
    if "Cantidad (t) Programada" in df_clean.columns:
        df_tons = df_clean[["Material", "Cantidad (t) Programada"]].copy()
        df_tons["Material"] = df_tons["Material"].str[:22]
        df_tons = df_tons.sort_values("Cantidad (t) Programada", ascending=False)
        fig_tons = px.bar(
            df_tons, x="Material", y="Cantidad (t) Programada",
            color="Cantidad (t) Programada",
            color_continuous_scale=[[0, "#D4A017"], [0.5, "#2E86AB"], [1, "#35352E"]],
            title="Toneladas Programadas por Material",
        )
        fig_tons.update_layout(
            plot_bgcolor="#FFFFFF", paper_bgcolor="#F5F5F0",
            height=340, showlegend=False,
            coloraxis_showscale=False,
            title_font=dict(size=14, color=DARK, family="Inter"),
            margin=dict(l=10, r=10, t=45, b=80),
            xaxis_tickangle=-35,
        )
        fig_tons.update_traces(hovertemplate="<b>%{x}</b><br>%{y:,.0f} t<extra></extra>")
        st.plotly_chart(fig_tons, use_container_width=True)


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

            total_t, total_h, util_mean, n_mats, has_over, over_h = render_kpis(df_clean, df_over)

            tab1, tab2 = st.tabs(["📅 Cronograma", "📊 Dashboard"])

            with tab1:
                st.markdown('<div class="section-title">Cronograma de producción</div>', unsafe_allow_html=True)
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

            with tab2:
                render_dashboard(df_clean, month, year)

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