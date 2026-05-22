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
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap');

:root {
  --coal:    #1C1C17;
  --dark:    #2A2A22;
  --steel:   #35352E;
  --crimson: #B8281F;
  --ember:   #D4380D;
  --gold:    #C8860A;
  --sage:    #2D6A4F;
  --ice:     #F7F7F3;
  --snow:    #FAFAF8;
  --mist:    #EFEFEA;
  --smoke:   #9B9B8E;
  --bone:    #E8E8E2;
}

html, body, [class*="css"], .stApp {
  font-family: 'DM Sans', sans-serif;
  background-color: var(--ice) !important;
  color: var(--coal);
}

/* ── SIDEBAR ─────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: var(--coal) !important;
  border-right: 1px solid #2E2E26;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }
section[data-testid="stSidebar"] {
  min-width: 270px !important;
  transform: none !important;
  display: block !important;
}
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }

[data-testid="stSidebar"] * { color: #E8E8E2 !important; }
[data-testid="stSidebar"] input {
  background: #2E2E26 !important;
  color: #F0F0EA !important;
  border: 1px solid #3E3E34 !important;
  border-radius: 8px !important;
  padding: 0.5rem 0.75rem !important;
}
[data-testid="stSidebar"] input:focus { border-color: var(--ember) !important; outline: none !important; }
[data-testid="stSidebar"] label { color: #9B9B8E !important; font-size: 0.72rem !important; letter-spacing: 0.08em; text-transform: uppercase; }
[data-testid="stSidebar"] .stFileUploader {
  background: #232319 !important;
  border: 1.5px dashed #3E3E34 !important;
  border-radius: 12px !important;
  padding: 1rem !important;
  transition: border-color 0.2s;
}
[data-testid="stSidebar"] .stFileUploader:hover { border-color: var(--ember) !important; }
[data-testid="stSidebar"] .stFileUploader * { color: #9B9B8E !important; font-size: 0.82rem !important; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * { color: #6B6B5E !important; }
[data-testid="stSidebar"] small { color: #5B5B4E !important; }
[data-testid="stSidebar"] hr { border-color: #2E2E26 !important; margin: 1.2rem 0 !important; }
[data-testid="stSidebar"] h4 { color: #9B9B8E !important; font-size: 0.65rem !important; letter-spacing: 0.12em; text-transform: uppercase; margin: 1.2rem 0 0.5rem !important; font-family: 'DM Sans', sans-serif !important; }

/* ── MAIN CONTENT ────────────────────────────────── */
.block-container { padding: 0 2rem 2rem !important; max-width: 100% !important; }

/* ── HEADER ──────────────────────────────────────── */
.gepa-header {
  background: linear-gradient(120deg, var(--coal) 0%, #282820 60%, #1A1A12 100%);
  padding: 1.4rem 2.5rem;
  border-bottom: 2px solid var(--crimson);
  display: flex; align-items: center; justify-content: space-between;
  margin: 0 -2rem 2rem;
  position: relative; overflow: hidden;
}
.gepa-header::before {
  content: '';
  position: absolute; top: 0; right: 0; bottom: 0;
  width: 40%;
  background: radial-gradient(ellipse at right center, rgba(184,40,31,0.08) 0%, transparent 70%);
  pointer-events: none;
}
.gepa-header-left { display: flex; align-items: center; gap: 1.5rem; }
.gepa-title { font-family: 'Syne', sans-serif; }
.gepa-title h1 {
  color: #FAFAF8; font-size: 1.9rem; font-weight: 800; margin: 0;
  letter-spacing: -0.02em; line-height: 1;
}
.gepa-title p { color: #7B7B6E; font-size: 0.8rem; margin: 0.3rem 0 0; letter-spacing: 0.04em; }
.gepa-badge {
  background: var(--crimson); color: white;
  padding: 0.3rem 0.9rem; border-radius: 999px;
  font-size: 0.65rem; font-weight: 600; letter-spacing: 0.12em;
  text-transform: uppercase; font-family: 'Syne', sans-serif;
}
.gepa-header-right { display: flex; align-items: center; gap: 1.2rem; }
.header-meta { text-align: right; }
.header-meta span { display: block; color: #5B5B4E; font-size: 0.72rem; letter-spacing: 0.05em; }
.header-meta strong { color: #9B9B8E; font-size: 0.78rem; }

/* ── KPI CARDS ───────────────────────────────────── */
.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.8rem; }
.kpi-card {
  background: var(--snow);
  border-radius: 16px; padding: 1.4rem 1.6rem;
  border: 1px solid var(--bone);
  position: relative; overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.04);
  transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card::after {
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: var(--bone);
}
.kpi-card.accent-red::after  { background: var(--crimson); }
.kpi-card.accent-gold::after { background: var(--gold); }
.kpi-card.accent-green::after{ background: var(--sage); }
.kpi-card.accent-dark::after { background: var(--steel); }
.kpi-icon { font-size: 1.3rem; margin-bottom: 0.8rem; opacity: 0.9; }
.kpi-label {
  font-size: 0.67rem; color: var(--smoke);
  font-weight: 500; text-transform: uppercase;
  letter-spacing: 0.1em; margin-bottom: 0.5rem;
}
.kpi-value {
  font-family: 'Syne', sans-serif;
  font-size: 2.1rem; font-weight: 700;
  color: var(--coal); line-height: 1; letter-spacing: -0.03em;
}
.kpi-sub { font-size: 0.72rem; color: var(--smoke); margin-top: 0.4rem; }

/* ── SECTION TITLES ──────────────────────────────── */
.section-header {
  display: flex; align-items: center; gap: 0.75rem;
  margin: 0.5rem 0 1.2rem;
}
.section-icon {
  width: 36px; height: 36px;
  background: var(--crimson);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1rem; flex-shrink: 0;
}
.section-title {
  font-family: 'Syne', sans-serif;
  font-size: 0.95rem; font-weight: 700;
  color: var(--coal); letter-spacing: 0.02em;
  text-transform: uppercase;
}
.section-sub { font-size: 0.72rem; color: var(--smoke); margin-top: 0.1rem; }

/* ── OVERFLOW ALERT ──────────────────────────────── */
.overflow-alert {
  background: #FEF2F1;
  border-left: 4px solid var(--crimson);
  border-radius: 0 12px 12px 0;
  padding: 1rem 1.4rem;
  color: var(--crimson); font-weight: 500;
  margin: 1rem 0; font-size: 0.88rem;
  display: flex; align-items: flex-start; gap: 0.75rem;
}

/* ── WELCOME SCREEN ──────────────────────────────── */
.welcome-card {
  background: var(--snow);
  border-radius: 20px; padding: 4rem 3rem;
  text-align: center; border: 1px solid var(--bone);
  box-shadow: 0 2px 24px rgba(0,0,0,0.05);
  margin: 2rem 0;
}
.welcome-icon { font-size: 3.5rem; margin-bottom: 1.5rem; opacity: 0.85; }
.welcome-title {
  font-family: 'Syne', sans-serif;
  font-size: 1.6rem; font-weight: 700;
  color: var(--coal); margin-bottom: 0.75rem;
}
.welcome-sub { color: var(--smoke); max-width: 480px; margin: 0 auto 2rem; font-size: 0.9rem; line-height: 1.6; }
.welcome-chips {
  display: flex; justify-content: center; gap: 0.75rem; flex-wrap: wrap;
}
.chip {
  background: var(--mist); color: var(--steel);
  padding: 0.4rem 1rem; border-radius: 999px;
  font-size: 0.78rem; font-weight: 500; border: 1px solid var(--bone);
}

/* ── BUTTON ──────────────────────────────────────── */
.stButton > button {
  background: var(--crimson) !important;
  color: white !important; border: none !important;
  border-radius: 10px !important; font-weight: 600 !important;
  padding: 0.65rem 2rem !important; font-size: 0.88rem !important;
  width: 100% !important; font-family: 'DM Sans', sans-serif !important;
  letter-spacing: 0.03em; transition: background 0.2s !important;
  box-shadow: 0 2px 8px rgba(184,40,31,0.3) !important;
}
.stButton > button:hover { background: var(--ember) !important; }

/* ── TABS ────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
  background: var(--mist); border-radius: 12px; padding: 4px; gap: 4px;
  border: 1px solid var(--bone);
}
[data-testid="stTabs"] [role="tab"] {
  border-radius: 9px !important; font-family: 'DM Sans', sans-serif !important;
  font-weight: 500 !important; font-size: 0.85rem !important;
  color: var(--smoke) !important; padding: 0.5rem 1.2rem !important;
  transition: all 0.15s !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  background: var(--snow) !important; color: var(--coal) !important;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important;
}

/* ── DATAFRAME ───────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 12px !important; overflow: hidden !important; border: 1px solid var(--bone) !important; }

/* ── FOOTER ──────────────────────────────────────── */
.gepa-footer {
  background: var(--coal);
  border-top: 1px solid #2E2E26;
  padding: 1.2rem 2.5rem; margin: 3rem -2rem 0;
  display: flex; align-items: center; justify-content: space-between;
}
.footer-left { }
.footer-title { font-family: 'Syne', sans-serif; color: #E8E8E2; font-size: 0.9rem; font-weight: 700; }
.footer-sub   { color: #5B5B4E; font-size: 0.72rem; margin-top: 0.2rem; }
.footer-right { display: flex; align-items: center; gap: 1.2rem; }
.footer-team  { color: #5B5B4E; font-size: 0.72rem; text-align: right; line-height: 1.5; }

/* ── HIDE STREAMLIT DEFAULT UI ───────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ── HEADER ───────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="gepa-header">'
    '<div class="gepa-header-left">'
    '<img src="' + APR_LOGO + '" height="48" style="filter:brightness(0) invert(1);flex-shrink:0;" onerror="this.style.display=\'none\'"/>'
    '<div class="gepa-title">'
    '<h1>GEPA-LAMIN</h1>'
    '<p>SISTEMA PREDICTIVO DE PROGRAMACIÓN · TRENES LAMINADORES</p>'
    '</div>'
    '</div>'
    '<div class="gepa-header-right">'
    '<span class="gepa-badge">ML POWERED</span>'
    '<div class="header-meta">'
    '<strong>Acerías PazdelRío</strong>'
    '<span>Sogamoso, Boyacá · Colombia</span>'
    '</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)


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


def parse_start_time(raw):
    cleaned = raw.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", cleaned):
        raise ValueError("Formato HH:MM requerido.")
    h, m = int(cleaned[:2]), int(cleaned[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("Hora fuera de rango.")
    return time(h, m)


def section_header(icon, title, sub=""):
    sub_html = '<div class="section-sub">' + sub + '</div>' if sub else ''
    st.markdown(
        '<div class="section-header">'
        '<div class="section-icon">' + icon + '</div>'
        '<div><div class="section-title">' + title + '</div>' + sub_html + '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_kpis(df_clean, df_over):
    total_t   = df_clean["Cantidad (t) Programada"].sum() if "Cantidad (t) Programada" in df_clean.columns else 0
    total_h   = df_clean["Tiempo lam. (h)"].sum() if "Tiempo lam. (h)" in df_clean.columns else 0
    util_mean = df_clean["Índice de utilización (%)"].mean() if "Índice de utilización (%)" in df_clean.columns else 0
    n_mats    = len(df_clean)
    has_over  = len(df_over) > 0
    over_h    = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0.0

    st.markdown(
        '<div class="kpi-grid">'
        '<div class="kpi-card accent-dark">'
        '<div class="kpi-icon">📦</div>'
        '<div class="kpi-label">Toneladas Programadas</div>'
        '<div class="kpi-value">' + "{:,.0f}".format(total_t) + '</div>'
        '<div class="kpi-sub">' + str(n_mats) + ' órdenes · Tren Morgan</div>'
        '</div>'
        '<div class="kpi-card accent-gold">'
        '<div class="kpi-icon">⏱</div>'
        '<div class="kpi-label">Horas de Laminación</div>'
        '<div class="kpi-value">' + "{:,.1f}".format(total_h) + '</div>'
        '<div class="kpi-sub">de 744 h disponibles en el mes</div>'
        '</div>'
        '<div class="kpi-card accent-green">'
        '<div class="kpi-icon">📊</div>'
        '<div class="kpi-label">Utilización Promedio</div>'
        '<div class="kpi-value">' + "{:.1f}%".format(util_mean) + '</div>'
        '<div class="kpi-sub">índice de eficiencia operativa</div>'
        '</div>'
        '<div class="kpi-card ' + ('accent-red' if has_over else 'accent-green') + '">'
        '<div class="kpi-icon">' + ('⚠️' if has_over else '✅') + '</div>'
        '<div class="kpi-label">Overflow Mensual</div>'
        '<div class="kpi-value" style="color:' + ('#B8281F' if has_over else '#2D6A4F') + '">'
        + ('SÍ' if has_over else 'NO') +
        '</div>'
        '<div class="kpi-sub">' + ("{:.1f} h fuera del mes".format(over_h) if has_over else "Programa dentro del mes") + '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    return total_t, total_h, util_mean, n_mats, has_over, over_h


def render_dashboard(df_clean, month, year):
    import plotly.graph_objects as go
    import plotly.express as px

    FONT   = "DM Sans"
    COAL   = "#1C1C17"
    SNOW   = "#FAFAF8"
    ICE    = "#F7F7F3"
    SMOKE  = "#9B9B8E"
    BONE   = "#E8E8E2"
    RED    = "#B8281F"
    GOLD   = "#C8860A"
    SAGE   = "#2D6A4F"
    BLUE   = "#1D4E89"
    TEAL   = "#1A7A6E"
    EMBER  = "#D4380D"

    PALETTE = [RED, BLUE, GOLD, SAGE, TEAL, EMBER,
               "#6B3FA0", "#1D6E4A", "#7C4D2A", "#1A5276",
               "#784212", "#1F618D", "#922B21", "#1E8449", "#6E2F87"]

    plot_bg   = dict(plot_bgcolor=SNOW, paper_bgcolor=ICE)
    title_fmt = dict(font=dict(family=FONT, size=15, color=COAL), x=0, xanchor="left", pad=dict(l=4))
    axis_fmt  = dict(gridcolor=BONE, linecolor=BONE, tickfont=dict(family=FONT, size=11, color=SMOKE), title_font=dict(family=FONT, size=11, color=SMOKE))
    margins   = dict(l=8, r=8, t=48, b=36)

    section_header("📅", "Cronograma Gantt", "Línea de tiempo de producción por material")

    # ── GANTT ─────────────────────────────────────────────────────────────
    if "Inicio" in df_clean.columns and "Fin" in df_clean.columns:
        df_g = df_clean.copy()
        df_g["Inicio"] = pd.to_datetime(df_g["Inicio"], errors="coerce")
        df_g["Fin"]    = pd.to_datetime(df_g["Fin"],    errors="coerce")
        df_g = df_g.dropna(subset=["Inicio", "Fin"])
        df_g["Mat"] = df_g["Material"].str[:28]
        t0 = df_g["Inicio"].min()

        fig = go.Figure()
        for i, (_, row) in enumerate(df_g.iterrows()):
            dur = (row["Fin"] - row["Inicio"]).total_seconds() / 3600
            base = (row["Inicio"] - t0).total_seconds() / 3600
            color = PALETTE[i % len(PALETTE)]
            fig.add_trace(go.Bar(
                x=[dur], y=[row["Mat"]], orientation="h", base=[base],
                marker=dict(color=color, line=dict(color="rgba(0,0,0,0.1)", width=0.5)),
                showlegend=False,
                hovertemplate=(
                    "<b style='font-family:DM Sans'>" + row["Mat"] + "</b><br>"
                    "<span style='color:#9B9B8E'>Inicio:</span> " + str(row["Inicio"])[:16] + "<br>"
                    "<span style='color:#9B9B8E'>Fin:</span> " + str(row["Fin"])[:16] + "<br>"
                    "<span style='color:#9B9B8E'>Duración:</span> {:.1f} h<br>".format(dur) +
                    "<span style='color:#9B9B8E'>Cantidad:</span> {:,.0f} t".format(row.get("Cantidad (t) Programada", 0)) +
                    "<extra></extra>"
                ),
            ))

        fig.update_layout(
            **plot_bg,
            title=dict(text="Programación Mensual — {:02d}/{}".format(month, year), **title_fmt),
            xaxis=dict(title="Horas desde inicio de programación", **axis_fmt),
            yaxis=dict(autorange="reversed", **axis_fmt),
            height=max(380, len(df_g) * 30 + 80),
            margin=margins, bargap=0.3,
            hoverlabel=dict(bgcolor=COAL, font_size=12, font_family=FONT, font_color=SNOW, bordercolor=COAL),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns([1, 1], gap="large")

    # ── PRODUCTIVIDAD ─────────────────────────────────────────────────────
    with col1:
        section_header("⚡", "Productividad por Material", "Toneladas por hora predichas por el modelo")
        if "Product. (t/h)" in df_clean.columns:
            df_p = df_clean[["Material", "Product. (t/h)"]].copy()
            df_p["Mat"] = df_p["Material"].str[:22]
            df_p = df_p.sort_values("Product. (t/h)")
            avg = df_p["Product. (t/h)"].mean()

            bar_colors = [RED if v < avg * 0.92 else (GOLD if v < avg * 1.05 else SAGE) for v in df_p["Product. (t/h)"]]

            fig2 = go.Figure(go.Bar(
                x=df_p["Product. (t/h)"], y=df_p["Mat"], orientation="h",
                marker=dict(color=bar_colors, line=dict(color="rgba(0,0,0,0)", width=0)),
                text=["{:.1f}".format(v) for v in df_p["Product. (t/h)"]],
                textposition="outside", textfont=dict(family=FONT, size=10, color=COAL),
                hovertemplate="<b>%{y}</b><br>%{x:.2f} t/h<extra></extra>",
            ))
            fig2.add_vline(x=avg, line=dict(color=SMOKE, width=1.5, dash="dot"),
                           annotation=dict(text=" Promedio {:.1f}".format(avg),
                                           font=dict(family=FONT, size=10, color=SMOKE),
                                           xanchor="left"))
            fig2.update_layout(
                **plot_bg,
                xaxis=dict(title="t/h", **axis_fmt),
                yaxis=dict(**axis_fmt),
                height=380, margin=margins, showlegend=False,
                hoverlabel=dict(bgcolor=COAL, font_size=12, font_family=FONT, font_color=SNOW),
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── DISTRIBUCIÓN TIEMPO ───────────────────────────────────────────────
    with col2:
        section_header("🕐", "Distribución del Tiempo", "Composición de horas del programa mensual")
        cols_needed = ["Tiempo lam. (h)", "Paradas setups (h)", "Paradas imprevistas (h)", "Mtto pro. (h)"]
        if all(c in df_clean.columns for c in cols_needed):
            vals   = [df_clean[c].sum() for c in cols_needed]
            labels = ["Laminación efectiva", "Paradas setup", "Paradas imprevistas", "Mantenimiento"]
            colors_dona = [SAGE, GOLD, RED, SMOKE]
            total_h = sum(vals)

            fig3 = go.Figure(go.Pie(
                labels=labels, values=vals, hole=0.62,
                marker=dict(colors=colors_dona, line=dict(color=ICE, width=2)),
                textinfo="percent", textfont=dict(family=FONT, size=11, color=SNOW),
                hovertemplate="<b>%{label}</b><br>%{value:.1f} h<br>%{percent}<extra></extra>",
                sort=False,
            ))
            fig3.update_layout(
                **plot_bg,
                height=380, margin=dict(l=8, r=8, t=16, b=16),
                legend=dict(orientation="v", font=dict(family=FONT, size=11, color=COAL),
                            x=1.02, y=0.5, xanchor="left"),
                annotations=[dict(
                    text="<b style='font-family:DM Sans'>{:.0f}h</b><br><span style='color:#9B9B8E;font-size:11px'>Total</span>".format(total_h),
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(family=FONT, size=16, color=COAL),
                )],
                hoverlabel=dict(bgcolor=COAL, font_size=12, font_family=FONT, font_color=SNOW),
            )
            st.plotly_chart(fig3, use_container_width=True)

    # ── TONELADAS POR MATERIAL ────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    section_header("📦", "Volumen por Material", "Toneladas programadas por cada referencia")
    if "Cantidad (t) Programada" in df_clean.columns:
        df_t = df_clean[["Material", "Cantidad (t) Programada"]].copy()
        df_t["Mat"] = df_t["Material"].str[:24]
        df_t = df_t.sort_values("Cantidad (t) Programada", ascending=False)

        fig4 = go.Figure(go.Bar(
            x=df_t["Mat"], y=df_t["Cantidad (t) Programada"],
            marker=dict(
                color=df_t["Cantidad (t) Programada"],
                colorscale=[[0, BONE], [0.4, GOLD], [0.75, BLUE], [1, COAL]],
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=["{:,.0f} t".format(v) for v in df_t["Cantidad (t) Programada"]],
            textposition="outside", textfont=dict(family=FONT, size=9, color=SMOKE),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} t<extra></extra>",
        ))
        fig4.update_layout(
            **plot_bg,
            xaxis=dict(tickangle=-38, **axis_fmt),
            yaxis=dict(title="Toneladas", **axis_fmt),
            height=320, margin=dict(l=8, r=8, t=12, b=90),
            showlegend=False, coloraxis_showscale=False,
            hoverlabel=dict(bgcolor=COAL, font_size=12, font_family=FONT, font_color=SNOW),
        )
        st.plotly_chart(fig4, use_container_width=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="background:#131310;padding:1.8rem 1.5rem 1.2rem;border-bottom:1px solid #2E2E26;">'
        '<img src="' + APR_LOGO + '" width="110" style="filter:brightness(0) invert(1);display:block;margin:0 auto 1rem;" onerror="this.style.display=\'none\'"/>'
        '<div style="text-align:center;font-size:0.62rem;color:#4B4B40;letter-spacing:0.14em;text-transform:uppercase;font-family:\'DM Sans\',sans-serif;">Sistema de Programación</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown("<div style='padding:1.2rem 1.2rem 0;'>", unsafe_allow_html=True)
    st.markdown("#### 📁 Archivo de entrada")
    uploaded = st.file_uploader("Programa TREN MORGAN (.xlsx)", type=["xlsx"], key="morgan", label_visibility="collapsed")
    st.markdown("#### 📅 Parámetros")
    start_date = st.date_input("Fecha inicio", value=date.today(), label_visibility="collapsed")
    start_time_text = st.text_input("Hora inicio (HH:MM)", value="00:00", max_chars=5)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        '<div style="padding:0 1.2rem 1.2rem;font-size:0.7rem;color:#4B4B40;line-height:2;">'
        '<div style="color:#6B6B5E;font-weight:600;font-size:0.62rem;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:0.5rem;">Modelos Activos</div>'
        '🤖 XGBoost · R² = <span style="color:#C8860A;font-weight:600;">0.9998</span><br>'
        '🌲 Random Forest · R² = <span style="color:#C8860A;font-weight:600;">0.9922</span><br>'
        '⚙️ Optimizador Held-Karp<br>'
        '📅 Scheduler Secuencial 24h'
        '</div>',
        unsafe_allow_html=True,
    )
    generar = st.button("⚡ Generar Programación")

month = start_date.month
year  = start_date.year

# ── MAIN ──────────────────────────────────────────────────────────────────────
if uploaded is None:
    st.markdown(
        '<div class="welcome-card">'
        '<div class="welcome-icon">🏭</div>'
        '<div class="welcome-title">Bienvenido a GEPA-LAMIN</div>'
        '<p class="welcome-sub">Carga el archivo Excel del programa de laminación del <strong>Tren Morgan</strong> en el panel izquierdo y presiona <strong>Generar Programación</strong> para obtener el cronograma optimizado con inteligencia artificial.</p>'
        '<div class="welcome-chips">'
        '<span class="chip">📊 Predicción ML</span>'
        '<span class="chip">⚙️ Optimización Held-Karp</span>'
        '<span class="chip">📅 Cronograma automático</span>'
        '<span class="chip">📥 Exportación Excel</span>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
else:
    try:
        df_preview = pd.read_excel(uploaded, engine="openpyxl")
        uploaded.seek(0)
        _, enc, _, _, setup_lk, _, _, _, _ = load_models()
        df_vp = validate_input_df(df_preview)
        df_vp = optimize_campaign_order(df_vp, tipo_cod=0, encoders=enc, setup_lookup=setup_lk)
        section_header("📋", "Orden Optimizado de Materiales", str(len(df_vp)) + " materiales · secuencia Held-Karp")
        st.dataframe(
            df_vp[["material","cantidad_t"]].rename(columns={"material":"Material","cantidad_t":"Cantidad (t)"}),
            use_container_width=True, height=190,
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

        with st.spinner("Generando cronograma con IA · puede tomar 20-40 s..."):
            try:
                import requests
                uploaded.seek(0)
                resp = requests.post(
                    API_URL,
                    files={"file_morgan": ("morgan.xlsx", uploaded.getvalue())},
                    data={"month": month, "year": year, "initial_start": initial_start.isoformat(sep=" ")},
                    timeout=120,
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

            render_kpis(df_clean, df_over)

            has_over = len(df_over) > 0
            over_h   = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0.0

            tab1, tab2 = st.tabs(["  📅  Cronograma  ", "  📊  Dashboard  "])

            with tab1:
                section_header("📅", "Cronograma de Producción", "{:02d}/{} · {} órdenes".format(month, year, len(df_clean)))
                st.dataframe(df_clean, use_container_width=True, height=440)
                if has_over:
                    st.markdown(
                        '<div class="overflow-alert">'
                        '<span style="font-size:1.1rem">⚠️</span>'
                        '<div><strong>Advertencia de Overflow:</strong> El programa excede la capacidad mensual en <strong>'
                        + "{:.1f} horas".format(over_h) +
                        '</strong>. Se recomienda diferir órdenes al mes siguiente.</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("<br>", unsafe_allow_html=True)
                c1, c2, c3 = st.columns([1.2, 1.6, 1.2])
                with c2:
                    st.download_button(
                        label="📥 Descargar cronograma {:02d}/{}".format(month, year),
                        data=excel_bytes, file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            with tab2:
                render_dashboard(df_clean, month, year)

# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="gepa-footer">'
    '<div class="footer-left">'
    '<div class="footer-title">GEPA-LAMIN</div>'
    '<div class="footer-sub">Sistema Predictivo de Programación de Producción · Especialización en Analítica Estratégica de Datos · 2026</div>'
    '</div>'
    '<div class="footer-right">'
    '<div class="footer-team">Angie Pérez · Manuel Quintero<br>Javier Ortiz · Jhon Patiño</div>'
    '<img src="' + UPTC_LOGO + '" height="34" style="filter:brightness(0) invert(1);opacity:0.7;" onerror="this.style.display=\'none\'"/>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)