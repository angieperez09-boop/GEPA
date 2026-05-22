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
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
  --coal:    #111110;
  --dark:    #1E1E18;
  --steel:   #2A2A22;
  --mid:     #3A3A30;
  --crimson: #C0271D;
  --ember:   #D4380D;
  --gold:    #B8780A;
  --sage:    #1E5C3A;
  --teal:    #0F5F5A;
  --navy:    #1A3A5C;
  --ice:     #F4F4EF;
  --snow:    #FAFAF7;
  --mist:    #ECEEE8;
  --bone:    #DCDDD6;
  --ash:     #B0B0A0;
  --text:    #1A1A15;
  --text2:   #4A4A3E;
  --text3:   #6E6E60;
}

html, body, [class*="css"], .stApp {
  font-family: 'DM Sans', sans-serif !important;
  background: var(--ice) !important;
  color: var(--text) !important;
}

/* ── SIDEBAR ─────────────────────────────────────── */
[data-testid="stSidebar"] { background: var(--coal) !important; border-right: 1px solid #222218; }
[data-testid="stSidebar"] > div { padding: 0 !important; }
section[data-testid="stSidebar"] { min-width: 270px !important; transform: none !important; display: block !important; }
[data-testid="collapsedControl"] { display: flex !important; visibility: visible !important; }
[data-testid="stSidebar"] * { color: #D8D8CC !important; }
[data-testid="stSidebar"] h4 {
  color: #6E6E60 !important;
  font-size: 0.62rem !important; letter-spacing: 0.13em;
  text-transform: uppercase; margin: 1.4rem 0 0.5rem !important;
  font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stSidebar"] input {
  background: #1A1A14 !important;
  color: #E8E8DC !important;
  border: 1.5px solid #303028 !important;
  border-radius: 8px !important;
}
[data-testid="stSidebar"] input:focus { border-color: var(--crimson) !important; }
[data-testid="stSidebar"] .stFileUploader {
  background: #161612 !important;
  border: 1.5px dashed #303028 !important;
  border-radius: 12px !important;
  transition: border-color 0.2s;
}
[data-testid="stSidebar"] .stFileUploader:hover { border-color: var(--crimson) !important; }
[data-testid="stSidebar"] small { color: #505048 !important; }
[data-testid="stSidebar"] hr { border-color: #222218 !important; margin: 1rem 0 !important; }
[data-testid="stSidebar"] p { color: #9898888 !important; }
[data-testid="stSidebar"] span { color: #C8C8BC !important; }
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzoneInstructions"] * { color: #585850 !important; }

/* ── BLOCK CONTAINER ─────────────────────────────── */
.block-container { padding: 0 2.5rem 3rem !important; max-width: 100% !important; }

/* ── HEADER ──────────────────────────────────────── */
.gepa-header {
  background: linear-gradient(135deg, #0E0E0A 0%, #1A1A12 50%, #0E0E0A 100%);
  padding: 1.5rem 2.5rem;
  border-bottom: 2px solid var(--crimson);
  display: flex; align-items: center; justify-content: space-between;
  margin: 0 -2.5rem 2.5rem;
  box-shadow: 0 4px 32px rgba(0,0,0,0.4);
}
.gepa-header-left { display: flex; align-items: center; gap: 1.6rem; }
.gepa-title h1 {
  font-family: 'Syne', sans-serif;
  color: #F0F0E8; font-size: 2rem; font-weight: 800;
  margin: 0; letter-spacing: -0.03em; line-height: 1;
}
.gepa-title p { color: #5A5A50; font-size: 0.75rem; margin: 0.35rem 0 0; letter-spacing: 0.08em; text-transform: uppercase; }
.gepa-badge {
  background: var(--crimson); color: #F8F8F2;
  padding: 0.28rem 0.85rem; border-radius: 999px;
  font-size: 0.62rem; font-weight: 700; letter-spacing: 0.14em;
  text-transform: uppercase; font-family: 'Syne', sans-serif;
  box-shadow: 0 2px 8px rgba(192,39,29,0.4);
}
.header-meta strong { color: #9898888; font-size: 0.82rem; display: block; }
.header-meta span   { color: #454540; font-size: 0.7rem; }

/* ── KPI CARDS ───────────────────────────────────── */
.kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 1.2rem; margin-bottom: 2rem; }
.kpi-card {
  background: var(--snow);
  border-radius: 16px; padding: 1.5rem 1.7rem;
  border: 1px solid var(--bone);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.04);
  position: relative; overflow: hidden;
}
.kpi-card::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
}
.kpi-card.c-dark::before  { background: linear-gradient(90deg,#2A2A22,#3A3A30); }
.kpi-card.c-gold::before  { background: linear-gradient(90deg,#B8780A,#D4A010); }
.kpi-card.c-green::before { background: linear-gradient(90deg,#1E5C3A,#2D8A5A); }
.kpi-card.c-red::before   { background: linear-gradient(90deg,#C0271D,#D4380D); }
.kpi-icon { font-size: 1.4rem; margin-bottom: 0.9rem; }
.kpi-label {
  font-size: 0.68rem; color: var(--text3);
  font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.1em; margin-bottom: 0.45rem;
}
.kpi-value {
  font-family: 'Syne', sans-serif;
  font-size: 2.2rem; font-weight: 700;
  color: var(--text); line-height: 1; letter-spacing: -0.04em;
}
.kpi-sub { font-size: 0.72rem; color: var(--text3); margin-top: 0.4rem; font-weight: 400; }

/* ── SECTION HEADER ──────────────────────────────── */
.sec-wrap { display:flex; align-items:center; gap:0.9rem; margin:0.5rem 0 1.4rem; }
.sec-dot { width:4px; height:32px; background:var(--crimson); border-radius:2px; flex-shrink:0; }
.sec-title {
  font-family: 'Syne', sans-serif;
  font-size: 0.9rem; font-weight: 700;
  color: var(--text); letter-spacing: 0.04em; text-transform: uppercase;
}
.sec-sub { font-size: 0.72rem; color: var(--text3); margin-top: 0.15rem; }

/* ── OVERFLOW ────────────────────────────────────── */
.overflow-alert {
  background: #FEF1F0; border-left: 3px solid var(--crimson);
  border-radius: 0 12px 12px 0; padding: 1rem 1.4rem;
  color: #7A1A14; font-size: 0.87rem; margin: 1.2rem 0;
  box-shadow: 0 2px 8px rgba(192,39,29,0.08);
}

/* ── WELCOME ─────────────────────────────────────── */
.welcome-card {
  background: var(--snow); border-radius: 20px;
  padding: 4.5rem 3rem; text-align: center;
  border: 1px solid var(--bone);
  box-shadow: 0 4px 32px rgba(0,0,0,0.06); margin: 2rem 0;
}
.welcome-title { font-family:'Syne',sans-serif; font-size:1.7rem; font-weight:800; color:var(--text); margin-bottom:0.8rem; letter-spacing:-0.02em; }
.welcome-sub { color:var(--text2); max-width:460px; margin:0 auto 2rem; font-size:0.9rem; line-height:1.65; }
.welcome-chips { display:flex; justify-content:center; gap:0.7rem; flex-wrap:wrap; }
.chip { background:var(--mist); color:var(--text2); padding:0.4rem 1rem; border-radius:999px; font-size:0.78rem; font-weight:500; border:1px solid var(--bone); }

/* ── BUTTON ──────────────────────────────────────── */
.stButton>button {
  background: var(--crimson) !important; color: #F8F8F2 !important;
  border: none !important; border-radius: 10px !important;
  font-weight: 600 !important; padding: 0.65rem 1.5rem !important;
  font-size: 0.88rem !important; width: 100% !important;
  font-family: 'DM Sans', sans-serif !important;
  box-shadow: 0 2px 12px rgba(192,39,29,0.35) !important;
  transition: all 0.2s !important; letter-spacing: 0.02em;
}
.stButton>button:hover { background: var(--ember) !important; box-shadow: 0 4px 16px rgba(192,39,29,0.45) !important; }

/* ── TABS ────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
  background: var(--mist); border-radius: 12px; padding: 4px;
  border: 1px solid var(--bone); gap: 4px;
}
[data-testid="stTabs"] [role="tab"] {
  border-radius: 9px !important; font-family: 'DM Sans', sans-serif !important;
  font-weight: 500 !important; font-size: 0.85rem !important;
  color: var(--text3) !important; padding: 0.5rem 1.4rem !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  background: var(--snow) !important; color: var(--text) !important;
  box-shadow: 0 1px 6px rgba(0,0,0,0.09) !important;
}

/* ── DATAFRAME ───────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 12px !important; border: 1px solid var(--bone) !important; overflow: hidden !important; }
[data-testid="stDataFrame"] th { background: var(--steel) !important; color: #E0E0D4 !important; font-family:'DM Sans',sans-serif !important; font-size:0.78rem !important; }

/* ── FOOTER ──────────────────────────────────────── */
.gepa-footer {
  background: var(--coal); border-top: 1px solid #222218;
  padding: 1.2rem 2.5rem; margin: 3rem -2.5rem 0;
  display: flex; align-items: center; justify-content: space-between;
}
.footer-title { font-family:'Syne',sans-serif; color:#D0D0C4; font-size:0.88rem; font-weight:700; }
.footer-sub   { color:#404038; font-size:0.7rem; margin-top:0.2rem; }
.footer-team  { color:#404038; font-size:0.7rem; text-align:right; line-height:1.6; }

/* ── HIDE STREAMLIT ──────────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ── HEADER ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="gepa-header">'
    '<div class="gepa-header-left">'
    '<img src="' + APR_LOGO + '" height="50" style="filter:brightness(0) invert(1);flex-shrink:0;" onerror="this.style.display:\'none\'"/>'
    '<div class="gepa-title">'
    '<h1>GEPA-LAMIN</h1>'
    '<p>Sistema Predictivo de Programación · Trenes Laminadores</p>'
    '</div>'
    '</div>'
    '<div style="display:flex;align-items:center;gap:1.4rem;">'
    '<span class="gepa-badge">ML POWERED</span>'
    '<div class="header-meta">'
    '<strong>Acerías PazdelRío</strong>'
    '<span>Sogamoso · Boyacá · Colombia</span>'
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


def sec_header(title, sub=""):
    sub_html = '<div class="sec-sub">' + sub + '</div>' if sub else ''
    st.markdown(
        '<div class="sec-wrap"><div class="sec-dot"></div>'
        '<div><div class="sec-title">' + title + '</div>' + sub_html + '</div></div>',
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
        '<div class="kpi-card c-dark"><div class="kpi-icon">📦</div>'
        '<div class="kpi-label">Toneladas Programadas</div>'
        '<div class="kpi-value">' + "{:,.0f}".format(total_t) + '</div>'
        '<div class="kpi-sub">' + str(n_mats) + ' órdenes · Tren Morgan</div></div>'
        '<div class="kpi-card c-gold"><div class="kpi-icon">⏱</div>'
        '<div class="kpi-label">Horas de Laminación</div>'
        '<div class="kpi-value">' + "{:,.1f}".format(total_h) + '</div>'
        '<div class="kpi-sub">de 744 h disponibles en el mes</div></div>'
        '<div class="kpi-card c-green"><div class="kpi-icon">📊</div>'
        '<div class="kpi-label">Utilización Promedio</div>'
        '<div class="kpi-value">' + "{:.1f}%".format(util_mean) + '</div>'
        '<div class="kpi-sub">índice de eficiencia operativa</div></div>'
        '<div class="kpi-card ' + ('c-red' if has_over else 'c-green') + '"><div class="kpi-icon">' + ('⚠️' if has_over else '✅') + '</div>'
        '<div class="kpi-label">Overflow Mensual</div>'
        '<div class="kpi-value" style="color:' + ('#C0271D' if has_over else '#1E5C3A') + '">'
        + ('SÍ' if has_over else 'NO') + '</div>'
        '<div class="kpi-sub">' + ("{:.1f} h fuera del mes".format(over_h) if has_over else "Programa dentro del mes") + '</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    return total_t, total_h, util_mean, n_mats, has_over, over_h


def render_dashboard(df_clean, month, year):
    import plotly.graph_objects as go

    FONT  = "DM Sans, sans-serif"
    TEXT  = "#1A1A15"
    TEXT2 = "#4A4A3E"
    TEXT3 = "#6E6E60"
    SNOW  = "#FAFAF7"
    ICE   = "#F4F4EF"
    BONE  = "#DCDDD6"
    RED   = "#C0271D"
    GOLD  = "#B8780A"
    SAGE  = "#1E5C3A"
    NAVY  = "#1A3A5C"
    TEAL  = "#0F5F5A"

    # 15 colores distintos y vibrantes
    PAL = ["#C0271D","#1A3A5C","#B8780A","#1E5C3A","#0F5F5A",
           "#6B2D8B","#7C4D2A","#1D6E4A","#8B3A1A","#2A5A8B",
           "#5C1A4A","#1A5C4A","#8B6A1A","#1A4A6A","#6A3A1A"]

    hover_bg = dict(bgcolor=TEXT, font_size=13, font_family=FONT, font_color="#F0F0E8", bordercolor=TEXT)
    plot_bg  = dict(plot_bgcolor=SNOW, paper_bgcolor=ICE)
    axis_x   = dict(gridcolor=BONE, linecolor=BONE, zeroline=False,
                    tickfont=dict(family=FONT, size=11, color=TEXT3),
                    title_font=dict(family=FONT, size=11, color=TEXT2))
    axis_y   = dict(gridcolor=BONE, linecolor=BONE, zeroline=False,
                    tickfont=dict(family=FONT, size=11, color=TEXT2),
                    title_font=dict(family=FONT, size=11, color=TEXT2))
    leg_fmt  = dict(font=dict(family=FONT, size=11, color=TEXT2),
                    bgcolor="rgba(255,255,255,0.85)", bordercolor=BONE, borderwidth=1)
    margins  = dict(l=12, r=12, t=20, b=40)

    # ── GANTT ─────────────────────────────────────────────────────────────
    sec_header("Cronograma Gantt", "Línea de tiempo de producción · " + "{:02d}/{}".format(month, year))
    if "Inicio" in df_clean.columns and "Fin" in df_clean.columns:
        df_g = df_clean.copy()
        df_g["Inicio"] = pd.to_datetime(df_g["Inicio"], errors="coerce")
        df_g["Fin"]    = pd.to_datetime(df_g["Fin"],    errors="coerce")
        df_g = df_g.dropna(subset=["Inicio","Fin"]).reset_index(drop=True)
        df_g["Mat"] = df_g["Material"].str[:30]
        t0 = df_g["Inicio"].min()

        fig = go.Figure()
        for i, row in df_g.iterrows():
            dur  = (row["Fin"] - row["Inicio"]).total_seconds() / 3600
            base = (row["Inicio"] - t0).total_seconds() / 3600
            col  = PAL[i % len(PAL)]
            cant = row.get("Cantidad (t) Programada", 0)
            fig.add_trace(go.Bar(
                x=[dur], y=[row["Mat"]], orientation="h", base=[base],
                marker=dict(color=col, opacity=0.88, line=dict(color="rgba(0,0,0,0.12)", width=0.8)),
                showlegend=False,
                hovertemplate=(
                    "<b>" + str(row["Mat"]) + "</b><br>"
                    "Inicio: <b>" + str(row["Inicio"])[:16] + "</b><br>"
                    "Fin: <b>" + str(row["Fin"])[:16] + "</b><br>"
                    "Duración: <b>{:.1f} h</b><br>".format(dur) +
                    "Toneladas: <b>{:,.0f} t</b>".format(cant) +
                    "<extra></extra>"
                ),
            ))
        fig.update_layout(
            **plot_bg,
            xaxis=dict(title="Horas desde inicio", **axis_x),
            yaxis=dict(autorange="reversed", **axis_y),
            height=max(400, len(df_g) * 32 + 80),
            margin=margins, bargap=0.28,
            hoverlabel=hover_bg,
            dragmode=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="large")

    # ── PRODUCTIVIDAD ─────────────────────────────────────────────────────
    with col1:
        sec_header("Productividad por Material", "t/h predichas · modelo XGBoost R²=0.9998")
        if "Product. (t/h)" in df_clean.columns:
            df_p = df_clean[["Material","Product. (t/h)"]].drop_duplicates("Material").copy()
            df_p["Mat"] = df_p["Material"].str[:24]
            df_p = df_p.sort_values("Product. (t/h)")
            avg  = df_p["Product. (t/h)"].mean()
            cols = [RED if v < avg * 0.93 else (GOLD if v < avg * 1.04 else SAGE) for v in df_p["Product. (t/h)"]]

            fig2 = go.Figure(go.Bar(
                x=df_p["Product. (t/h)"], y=df_p["Mat"], orientation="h",
                marker=dict(color=cols, opacity=0.9, line=dict(color="rgba(0,0,0,0.08)", width=0.5)),
                hovertemplate="<b>%{y}</b><br>Productividad: <b>%{x:.2f} t/h</b><extra></extra>",
            ))
            fig2.add_vline(
                x=avg, line=dict(color=TEXT3, width=1.5, dash="dot"),
                annotation=dict(text=" Prom. {:.1f}".format(avg), font=dict(family=FONT, size=10, color=TEXT3), xanchor="left"),
            )
            fig2.update_layout(
                **plot_bg,
                xaxis=dict(title="t/h", **axis_x),
                yaxis=dict(**axis_y),
                height=380, margin=margins, showlegend=False,
                hoverlabel=hover_bg,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── DONA ──────────────────────────────────────────────────────────────
    with col2:
        sec_header("Distribución del Tiempo", "Composición de horas del programa mensual")
        cols_needed = ["Tiempo lam. (h)","Paradas setups (h)","Paradas imprevistas (h)","Mtto pro. (h)"]
        if all(c in df_clean.columns for c in cols_needed):
            vals   = [df_clean[c].sum() for c in cols_needed]
            labels = ["Laminación efectiva","Paradas setup","Paradas imprevistas","Mantenimiento"]
            clrs   = [SAGE, GOLD, RED, TEXT3]
            total_h = sum(vals)

            fig3 = go.Figure(go.Pie(
                labels=labels, values=vals, hole=0.60,
                marker=dict(colors=clrs, line=dict(color=ICE, width=3)),
                textinfo="percent",
                textfont=dict(family=FONT, size=11, color="#FAFAF7"),
                hovertemplate="<b>%{label}</b><br>%{value:.1f} h · %{percent}<extra></extra>",
                sort=False,
                pull=[0.03, 0, 0, 0],
            ))
            fig3.update_layout(
                **plot_bg,
                height=380,
                margin=dict(l=8, r=8, t=16, b=16),
                legend=dict(orientation="v", font=dict(family=FONT, size=11, color=TEXT2),
                            x=1.02, y=0.5, xanchor="left", **{k:v for k,v in leg_fmt.items() if k != "font"}),
                annotations=[dict(
                    text="<b>{:.0f}</b><br>horas".format(total_h),
                    x=0.5, y=0.5, showarrow=False,
                    font=dict(family=FONT, size=15, color=TEXT),
                )],
                hoverlabel=hover_bg,
            )
            st.plotly_chart(fig3, use_container_width=True)

    # ── TONELADAS ─────────────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    sec_header("Volumen por Material", "Toneladas programadas por referencia")
    if "Cantidad (t) Programada" in df_clean.columns:
        df_t = df_clean[["Material","Cantidad (t) Programada"]].drop_duplicates("Material").copy()
        df_t["Mat"] = df_t["Material"].str[:26]
        df_t = df_t.sort_values("Cantidad (t) Programada", ascending=False)
        bar_cols = [PAL[i % len(PAL)] for i in range(len(df_t))]

        fig4 = go.Figure(go.Bar(
            x=df_t["Mat"], y=df_t["Cantidad (t) Programada"],
            marker=dict(color=bar_cols, opacity=0.88, line=dict(color="rgba(0,0,0,0.08)", width=0.5)),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} t<extra></extra>",
        ))
        fig4.update_layout(
            **plot_bg,
            xaxis=dict(tickangle=-38, **axis_x),
            yaxis=dict(title="Toneladas (t)", **axis_y),
            height=320, margin=dict(l=12, r=12, t=20, b=100),
            showlegend=False,
            hoverlabel=hover_bg,
        )
        st.plotly_chart(fig4, use_container_width=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<div style="background:#090908;padding:2rem 1.5rem 1.5rem;border-bottom:1px solid #1E1E18;">'
        '<img src="' + APR_LOGO + '" width="108" style="filter:brightness(0) invert(1);display:block;margin:0 auto 1rem;" onerror="this.style.display:\'none\'"/>'
        '<div style="text-align:center;font-size:0.6rem;color:#3A3A32;letter-spacing:0.16em;text-transform:uppercase;">Sistema de Programación</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div style="padding:1.4rem 1.4rem 0;">', unsafe_allow_html=True)
    st.markdown("#### 📁 Archivo de entrada")
    uploaded = st.file_uploader("Programa TREN MORGAN (.xlsx)", type=["xlsx"], key="morgan", label_visibility="collapsed")
    st.markdown("#### 📅 Parámetros")
    start_date = st.date_input("Fecha inicio", value=date.today(), label_visibility="collapsed")
    start_time_text = st.text_input("Hora inicio (HH:MM)", value="00:00", max_chars=5)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(
        '<div style="padding:0 1.4rem 1.4rem;">'
        '<div style="font-size:0.6rem;color:#3A3A32;font-weight:600;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:0.8rem;">Modelos Activos</div>'
        '<div style="font-size:0.77rem;line-height:2.1;color:#787870;">'
        '🤖 XGBoost · <span style="color:#B8780A;font-weight:600;">R² = 0.9998</span><br>'
        '🌲 Random Forest · <span style="color:#B8780A;font-weight:600;">R² = 0.9922</span><br>'
        '⚙️ Optimizador Held-Karp<br>'
        '📅 Scheduler Secuencial 24h'
        '</div></div>',
        unsafe_allow_html=True,
    )
    generar = st.button("⚡ Generar Programación")

month = start_date.month
year  = start_date.year

# ── MAIN ──────────────────────────────────────────────────────────────────────
if uploaded is None:
    st.markdown(
        '<div class="welcome-card">'
        '<div style="font-size:3.5rem;margin-bottom:1.5rem;">🏭</div>'
        '<div class="welcome-title">Bienvenido a GEPA-LAMIN</div>'
        '<p class="welcome-sub">Carga el archivo Excel del programa de laminación del <strong>Tren Morgan</strong> en el panel izquierdo y presiona <strong>Generar Programación</strong> para obtener el cronograma optimizado con inteligencia artificial.</p>'
        '<div class="welcome-chips">'
        '<span class="chip">📊 Predicción ML</span>'
        '<span class="chip">⚙️ Optimización Held-Karp</span>'
        '<span class="chip">📅 Cronograma automático</span>'
        '<span class="chip">📥 Exportación Excel</span>'
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
        sec_header("Orden Optimizado", str(len(df_vp)) + " materiales · secuencia Held-Karp")
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

        with st.spinner("Generando cronograma con IA · puede tomar 20–40 s..."):
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
                sec_header("Cronograma de Producción", "{:02d}/{} · {} órdenes".format(month, year, len(df_clean)))
                st.dataframe(df_clean, use_container_width=True, height=440)
                if has_over:
                    st.markdown(
                        '<div class="overflow-alert"><strong>⚠️ Overflow:</strong> El programa excede la capacidad mensual en <strong>'
                        + "{:.1f} horas".format(over_h) +
                        '</strong>. Diferir órdenes al mes siguiente.</div>',
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
    '<div><div class="footer-title">GEPA-LAMIN</div>'
    '<div class="footer-sub">Sistema Predictivo de Programación de Producción · Especialización en Analítica Estratégica de Datos · 2026</div></div>'
    '<div style="display:flex;align-items:center;gap:1.2rem;">'
    '<div class="footer-team">Angie Pérez · Manuel Quintero<br>Javier Ortiz · Jhon Patiño</div>'
    '<img src="' + UPTC_LOGO + '" height="32" style="filter:brightness(0) invert(1);opacity:0.6;" onerror="this.style.display:\'none\'"/>'
    '</div></div>',
    unsafe_allow_html=True,
)