import warnings
warnings.filterwarnings('ignore')

import os, sys, pathlib, re, base64, io, calendar
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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] {
  font-family: 'Inter', -apple-system, sans-serif;
  background: #0F172A;
}
.block-container { padding-top: 0 !important; padding-bottom: 3rem !important; max-width:100%!important; }

/* ════════════════════════════════════════════════
   TOPBAR
════════════════════════════════════════════════ */
.topbar {
  background: linear-gradient(90deg,#0F172A 0%,#1a2744 60%,#0F172A 100%);
  border-bottom: 1px solid #1E293B;
  padding: 0 2.5rem;
  height: 64px;
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 0;
}
.topbar::after {
  content:"";
  position:absolute; left:0; right:0;
  height:3px;
  background: linear-gradient(90deg,transparent 0%,#DC2626 30%,#F87171 50%,#DC2626 70%,transparent 100%);
  top:64px;
}
.tb-left  { display:flex; align-items:center; gap:1rem; }
.tb-title { font-size:1.15rem; font-weight:900; color:#F8FAFC; letter-spacing:-0.3px; }
.tb-dot   { color:#334155; }
.tb-sub   { font-size:0.72rem; color:#475569; font-weight:400; }
.tb-right { display:flex; align-items:center; gap:0.5rem; }
.badge {
  font-size:0.58rem; font-weight:800; letter-spacing:1px; text-transform:uppercase;
  padding:0.22rem 0.65rem; border-radius:4px; display:inline-flex; align-items:center; gap:0.3rem;
}
.badge-red   { background:#DC2626; color:#fff; }
.badge-ghost { border:1px solid #1E293B; color:#475569; }

/* ════════════════════════════════════════════════
   PAGE BACKGROUND  (contenido principal)
════════════════════════════════════════════════ */
.main-wrap {
  background:#F1F5F9;
  border-radius: 16px; padding: 1.5rem 1.7rem;
  border: 1px solid var(--bone);
  box-shadow: 0 2px 8px rgba(0,0,0,0.05), 0 8px 24px rgba(0,0,0,0.04);

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

# ── TOPBAR ────────────────────────────────────────────────────────────────────
st.markdown(
  f'<div class="topbar">'
  f'<div class="tb-left">'
  f'<img src="{APR_LOGO}" height="32" style="filter:brightness(0) invert(1);" onerror="this.style.display:none"/>'
  f'<span class="tb-dot" style="font-size:1.4rem;opacity:.25">|</span>'
  f'<span class="tb-title">GEPA-LAMIN</span>'
  f'<span class="tb-dot" style="font-size:.8rem;opacity:.2">·</span>'
  f'<span class="tb-sub">Sistema Predictivo de Programación de Producción &nbsp;·&nbsp; Trenes Laminadores &nbsp;·&nbsp; Acerías PazdelRío</span>'
  f'</div>'
  f'<div class="tb-right">'
  f'<span class="badge badge-red">⚡ ML Powered</span>'
  f'<span class="badge badge-ghost">Sogamoso, Colombia</span>'
  f'</div></div>',
    unsafe_allow_html=True,
)


# ── MODELS ────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_models():
    try:
        from joblib import load as jload
        d = ROOT / 'models' / 'artifacts'
        xgb  = jload(d/'xgb.joblib')  if (d/'xgb.joblib').exists()  else None
        enc  = jload(d/'encoders.joblib') if (d/'encoders.joblib').exists() else None
        fcol = jload(d/'feature_cols.joblib') if (d/'feature_cols.joblib').exists() else []
        mtto = jload(d/'mtto_lookup.joblib') if (d/'mtto_lookup.joblib').exists() else None
        setup= jload(d/'setup_lookup.joblib') if (d/'setup_lookup.joblib').exists() else None
        ilkp = jload(d/'imprevistas_lookup.joblib') if (d/'imprevistas_lookup.joblib').exists() else None
        imod = jload(d/'imprevistas_model.joblib') if (d/'imprevistas_model.joblib').exists() else None
        util = jload(d/'util_lookup.joblib') if (d/'util_lookup.joblib').exists() else None
        utp  = jload(d/'util_product_lookup.joblib') if (d/'util_product_lookup.joblib').exists() else None
        return xgb, enc, fcol, mtto, setup, ilkp, imod, util, utp
    except Exception:
        return (None,)*9


def parse_start_time(raw):
    c = raw.strip()
    if not re.fullmatch(r"\d{2}:\d{2}", c):
        raise ValueError("Formato HH:MM requerido.")
    h, m = int(c[:2]), int(c[3:])
    if not (0<=h<=23 and 0<=m<=59):
        raise ValueError("Hora fuera de rango.")
    return time(h, m)


# ── UI HELPERS ────────────────────────────────────────────────────────────────
def sec(label, color="#DC2626"):
    st.markdown(
        f'<div class="sec-row">'
        f'<div class="sec-dot" style="background:{color};"></div>'
        f'<span class="sec-name">{label}</span>'
        f'<div class="sec-line"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

def ch(title, meta="", tags=None):
    tag_html = ""
    if tags:
        for txt, bg, tc in tags:
            tag_html += f'<span class="chart-tag" style="background:{bg};color:{tc};">{txt}</span>'
    st.markdown(
        f'<div class="chart-card-head">'
        f'<div><div class="cct">{title}</div><div class="ccm">{meta}</div></div>'
        f'<div class="cca">{tag_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def kpi_card(col, icon, num, unit, label, stripe, icon_bg, icon_fg, ctx="", ctx_cls="",
             prog_pct=None, prog_color=""):
    prog_html = ""
    if prog_pct is not None:
        fill = min(max(float(prog_pct), 0), 100)
        prog_html = (
            f'<div class="kpi-prog-bg">'
            f'<div class="kpi-prog-fill" style="width:{fill:.1f}%;background:{prog_color};"></div>'
            f'</div>'
        )
    col.markdown(
        f'<div class="kpi-card">'
        f'<div class="kpi-stripe" style="background:{stripe};"></div>'
        f'<div class="kpi-icon-box" style="background:{icon_bg};color:{icon_fg};">{icon}</div>'
        f'<div class="kpi-ey">{label}</div>'
        f'<div class="kpi-num">{num}<span class="kpi-u">&thinsp;{unit}</span></div>'
        f'{prog_html}'
        f'<div class="kpi-hr"></div>'
        f'<div class="kpi-cx {ctx_cls}">{ctx}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── KPI ROW ───────────────────────────────────────────────────────────────────
def render_kpis(df_clean, df_over, month, year):
    total_t   = df_clean["Cantidad (t) Programada"].sum()   if "Cantidad (t) Programada" in df_clean.columns else 0
    total_h   = df_clean["Tiempo lam. (h)"].sum()           if "Tiempo lam. (h)" in df_clean.columns        else 0
    util_mean = df_clean["Índice de utilización (%)"].mean()if "Índice de utilización (%)" in df_clean.columns else 0
    n_mats    = len(df_clean)
    has_over  = len(df_over) > 0
    over_h    = float(df_over["Tiempo lam. (h)"].sum()) if has_over else 0.0
    avail_h   = calendar.monthrange(year, month)[1] * 24
    pct_uso   = min(total_h / avail_h * 100, 100) if avail_h > 0 else 0

    c1,c2,c3,c4,c5 = st.columns(5)
    kpi_card(c1,"🏭", f"{total_t:,.0f}","t",
             "Toneladas Programadas","#DC2626","#FEF2F2","#DC2626",
             f"📦 {n_mats} órdenes de producción")
    kpi_card(c2,"⏱", f"{total_h:,.1f}","h",
             "Horas de Laminación","#2563EB","#EFF6FF","#2563EB",
             f"📅 {pct_uso:.0f}% de {avail_h:,} h disponibles",
             prog_pct=pct_uso, prog_color="#2563EB")
    kpi_card(c3,"📈", f"{util_mean:.1f}","%",
             "Utilización Promedio","#F59E0B","#FFFBEB","#D97706",
             "⚙️ eficiencia operativa del programa","warn" if util_mean < 70 else "ok",
             prog_pct=util_mean, prog_color=("#DC2626" if util_mean < 70 else "#059669"))
    kpi_card(c4,"📋", str(n_mats),"",
             "Materiales","#64748B","#F1F5F9","#475569",
             "🔢 órdenes en el programa mensual")
    kpi_card(c5,
             "⚠️" if has_over else "✅",
             "SÍ" if has_over else "NO","",
             "Overflow Mensual",
             "#DC2626" if has_over else "#059669",
             "#FEF2F2" if has_over else "#F0FDF4",
             "#DC2626" if has_over else "#059669",
             f"▲ {over_h:.1f} h por encima de la capacidad" if has_over else "✓ Dentro de la capacidad mensual",
             "err" if has_over else "ok")

    return total_t, total_h, util_mean, n_mats, has_over, over_h


# ── GANTT ─────────────────────────────────────────────────────────────────────
def render_gantt(df_clean, month, year):
    import plotly.graph_objects as go
    from datetime import timedelta as _td
    if "Inicio" not in df_clean.columns or "Fin" not in df_clean.columns:
        return
    PAL = ["#DC2626","#2563EB","#F59E0B","#059669","#7C3AED","#0891B2",
           "#BE185D","#65A30D","#9333EA","#EA580C","#0F766E","#B45309"]
    df_g = df_clean.copy()
    df_g["Inicio"] = pd.to_datetime(df_g["Inicio"], errors="coerce")
    df_g["Fin"]    = pd.to_datetime(df_g["Fin"],    errors="coerce")
    df_g = df_g.dropna(subset=["Inicio","Fin"])
    df_g["Mat"] = df_g["Material"].str[:32]

    bases, dur_ms, texts, custom = [], [], [], []
    for _, r in df_g.iterrows():
        t0_ms = int(r["Inicio"].timestamp() * 1000)
        t1_ms = int(r["Fin"].timestamp() * 1000)
        bases.append(t0_ms)
        dur_ms.append(t1_ms - t0_ms)
        texts.append(r["Inicio"].strftime("%d/%m"))
        custom.append([
            r["Inicio"].strftime("%d/%m/%Y %H:%M"),
            r["Fin"].strftime("%d/%m/%Y %H:%M"),
            f"{(r['Fin'] - r['Inicio']).total_seconds() / 3600:.1f}",
            f"{r.get('Cantidad (t) Programada', 0):,.0f}",
        ])
    colors = [PAL[i % len(PAL)] for i in range(len(df_g))]

    fig = go.Figure(go.Bar(
        x=dur_ms, y=df_g["Mat"].tolist(), orientation="h",
        base=bases,
        marker=dict(color=colors, line=dict(color="white", width=.6)),
        showlegend=False,
        text=texts, textposition="inside",
        textfont=dict(size=8, color="rgba(255,255,255,.8)"),
        customdata=custom,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Inicio: %{customdata[0]}<br>"
            "Fin: %{customdata[1]}<br>"
            "Duración: %{customdata[2]} h<br>"
            "Cantidad: %{customdata[3]} t<extra></extra>"
        ),
    ))

    # Day-boundary vlines — ISO strings are safe for date axis
    t_min, t_max = df_g["Inicio"].min(), df_g["Fin"].max()
    day = t_min.normalize() + _td(days=1)
    while day <= t_max:
        fig.add_vline(x=day.isoformat(), line_dash="dot",
                      line_color="#E2E8F0", line_width=1.2)
        day += _td(days=1)

    fig.update_layout(
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        height=max(360, len(df_g) * 32 + 100),
        margin=dict(l=10, r=20, t=10, b=54),
        xaxis=dict(type="date", tickformat="%d/%m<br>%H:%M", dtick=86400000,
                   gridcolor="#F1F5F9", zeroline=False,
                   tickfont=dict(size=9, color="#475569")),
        yaxis=dict(autorange="reversed", tickfont=dict(size=9.5, color="#1E293B")),
        bargap=0.25,
        hoverlabel=dict(bgcolor="#fff", font_size=12, bordercolor="#E2E8F0", font_color="#0F172A"),
    )
    ch(f"Cronograma de producción — {calendar.month_name[month]} {year}",
       f"{len(df_g)} materiales · cada barra = un bloque de laminación continua",
       tags=[("GANTT","#F1F5F9","#64748B"),("Eje X = fechas reales","#EFF6FF","#2563EB")])
    st.plotly_chart(fig, use_container_width=True)


# ── DASHBOARD ─────────────────────────────────────────────────────────────────
def render_dashboard(df_clean, month, year):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    R="#DC2626"; B="#2563EB"; A="#F59E0B"; G="#059669"
    N="#0F172A"; N2="#1E293B"; W="#FFFFFF"; GR="#F8FAFC"; BR="#E2E8F0"
    T2="#475569"; T3="#94A3B8"
    HOVER_STYLE = dict(bgcolor=W, font_size=11, bordercolor=BR, font_color=N)

    days    = calendar.monthrange(year,month)[1]
    avail_h = days*24

    # ── Combo ────────────────────────────────────────────────────────────────
    sec("Producción &amp; Eficiencia", "#DC2626")
    if "Cantidad (t) Programada" in df_clean.columns and "Product. (t/h)" in df_clean.columns:
        df_c = df_clean[["Material","Cantidad (t) Programada","Product. (t/h)"]].copy()
        df_c["Mat"] = df_c["Material"].str[:15]
        fig = make_subplots(specs=[[{"secondary_y":True}]])
        fig.add_trace(go.Bar(
            x=df_c["Mat"], y=df_c["Cantidad (t) Programada"],
            name="Toneladas (t)",
            marker=dict(color=R, opacity=.9, line=dict(color=W,width=.5)),
            text=df_c["Cantidad (t) Programada"].round(0).astype(int),
            textposition="inside", textfont=dict(size=9,color=W),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} t<extra></extra>",
        ), secondary_y=False)
        fig.add_trace(go.Scatter(
            x=df_c["Mat"], y=df_c["Product. (t/h)"],
            name="Productividad (t/h)", mode="lines+markers",
            line=dict(color=N,width=2.5),
            marker=dict(color=W,size=9,line=dict(color=N,width=2.5)),
            hovertemplate="<b>%{x}</b><br>%{y:.1f} t/h<extra></extra>",
        ), secondary_y=True)
        fig.update_layout(
            plot_bgcolor=W, paper_bgcolor=W, height=295,
            legend=dict(orientation="h",yanchor="bottom",y=1.01,xanchor="right",x=1,
                        font=dict(size=10.5,color=N2),bgcolor="rgba(0,0,0,0)",
                        bordercolor=BR,borderwidth=1),
            margin=dict(l=20,r=20,t=46,b=56),
            xaxis=dict(tickangle=-30,tickfont=dict(size=8.5,color=T2),gridcolor=GR,zeroline=False),
            yaxis=dict(title="Toneladas (t)",title_font=dict(size=10,color=R),
                       gridcolor=GR,zeroline=False,tickfont=dict(size=9,color=T3)),
            yaxis2=dict(title="Productividad (t/h)",title_font=dict(size=10,color=N2),
                        zeroline=False,tickfont=dict(size=9,color=T3),overlaying="y",side="right"),
            bargap=.3, hoverlabel=dict(bgcolor=W,font_size=12,bordercolor=BR,font_color=N),
        )
        ch("Toneladas programadas y productividad por material",
           f"{calendar.month_name[month]} {year}",
           tags=[("Barras = toneladas","#FEF2F2","#DC2626"),
                 ("Línea = t/h","#F1F5F9","#475569")])
        st.plotly_chart(fig, use_container_width=True)

    # ── Fila inferior ────────────────────────────────────────────────────────
    sec("Tiempo &nbsp;·&nbsp; Capacidad &nbsp;·&nbsp; Paradas", "#2563EB")
    c1,c2,c3 = st.columns([1.3,1,1])

    with c1:
        if "Tiempo lam. (h)" in df_clean.columns:
            df_t = df_clean[["Material","Tiempo lam. (h)"]].copy()
            df_t["Mat"] = df_t["Material"].str[:20]
            df_t = df_t.sort_values("Tiempo lam. (h)",ascending=True).tail(10)
            total_lam = df_clean["Tiempo lam. (h)"].sum()
            fig_h = go.Figure(go.Bar(
                x=df_t["Tiempo lam. (h)"], y=df_t["Mat"], orientation="h",
                marker=dict(color=df_t["Tiempo lam. (h)"],
                            colorscale=[[0,"#BFDBFE"],[.5,"#3B82F6"],[1,"#1E3A8A"]],
                            showscale=False),
                text=df_t["Tiempo lam. (h)"].apply(lambda v:f"{v:.1f} h"),
                textposition="outside",textfont=dict(size=9,color=T2),
                hovertemplate="<b>%{y}</b><br>%{x:.1f} h<extra></extra>",
            ))
            fig_h.add_vline(x=total_lam/max(len(df_clean),1),
                            line_dash="dot",line_color=R,line_width=1.5,opacity=.45)
            fig_h.update_layout(
                plot_bgcolor=W, paper_bgcolor=W, height=335,
                margin=dict(l=10,r=65,t=46,b=20),
                xaxis=dict(showgrid=True,gridcolor=GR,zeroline=False,tickfont=dict(size=9,color=T3)),
                yaxis=dict(tickfont=dict(size=9,color=N2)),
                annotations=[dict(text=f"Total: <b>{total_lam:.1f} h</b>",
                                  xref="paper",yref="paper",x=0,y=1.07,
                                  showarrow=False,font=dict(size=11,color=T2))],
            )
            ch("Tiempo de laminación por material","horas efectivas",
               tags=[("Top 10","#EFF6FF","#2563EB")])
            st.plotly_chart(fig_h, use_container_width=True)

    with c2:
        if "Tiempo lam. (h)" in df_clean.columns:
            total_h_v = df_clean["Tiempo lam. (h)"].sum()
            ocup = min(total_h_v/avail_h*100,100)
            g_c = R if ocup>=95 else (A if ocup>=75 else B)
            ch("Ocupación del mes",f"{days} días · {avail_h} h disponibles")
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=ocup,
                delta=dict(reference=75,suffix=" pts vs. meta",font=dict(size=11),relative=False),
                number=dict(suffix="%",font=dict(size=26,color=N),valueformat=".1f"),
                gauge=dict(
                    shape="angular",
                    axis=dict(range=[0,100],tickfont=dict(size=8.5),
                              tickvals=[0,25,50,75,100],ticktext=["0","25","50","75","100"]),
                    bar=dict(color=g_c,thickness=.3),bgcolor=W,borderwidth=0,
                    steps=[dict(range=[0,75],color="#EFF6FF"),
                           dict(range=[75,90],color="#FEFCE8"),
                           dict(range=[90,100],color="#FEF2F2")],
                    threshold=dict(line=dict(color=R,width=3),thickness=.85,value=95),
                ),
            ))
            fig_g.update_layout(height=210,margin=dict(l=15,r=15,t=28,b=0),paper_bgcolor=W)
            st.plotly_chart(fig_g, use_container_width=True)

            ch("Progresión acumulada","horas por orden")
            df_cum = df_clean[["Tiempo lam. (h)"]].copy().reset_index(drop=True)
            df_cum["Acum"] = df_cum["Tiempo lam. (h)"].cumsum()
            fig_tr = go.Figure()
            fig_tr.add_hline(y=avail_h,line_dash="dash",line_color=R,line_width=1.5,opacity=.5,
                             annotation_text="Cap.",annotation_position="top right",
                             annotation_font=dict(size=8,color=R))
            fig_tr.add_trace(go.Scatter(
                x=list(range(len(df_cum))),y=df_cum["Acum"],
                mode="lines",line=dict(color=B,width=2.5),
                fill="tozeroy",fillcolor="rgba(37,99,235,.07)",
                hovertemplate="Orden %{x}<br><b>%{y:.1f} h</b><extra></extra>",
            ))
            fig_tr.update_layout(
                height=118,margin=dict(l=40,r=15,t=36,b=24),
                plot_bgcolor=W,paper_bgcolor=W,showlegend=False,
                xaxis=dict(showticklabels=False,showgrid=False,zeroline=False),
                yaxis=dict(gridcolor=GR,tickfont=dict(size=8,color=T3),zeroline=False),
            )
            st.plotly_chart(fig_tr, use_container_width=True)

    with c3:
        pcols=["Paradas setups (h)","Paradas imprevistas (h)","Mtto pro. (h)"]
        if all(c in df_clean.columns for c in pcols) and "Tiempo lam. (h)" in df_clean.columns:
            lam_h=df_clean["Tiempo lam. (h)"].sum()
            s_h=df_clean["Paradas setups (h)"].sum()
            i_h=df_clean["Paradas imprevistas (h)"].sum()
            m_h=df_clean["Mtto pro. (h)"].sum()
            tp=s_h+i_h+m_h; tt=lam_h+tp
            pct_p=(tp/tt*100) if tt>0 else 0
            g_c2=R if pct_p>=25 else (A if pct_p>=10 else G)
            ch("Índice de paradas","% sobre tiempo total")
            fig_g2=go.Figure(go.Indicator(
                mode="gauge+number",
                value=pct_p,
                number=dict(suffix="%",font=dict(size=26,color=N),valueformat=".1f"),
                gauge=dict(
                    shape="angular",
                    axis=dict(range=[0,50],tickfont=dict(size=8.5),
                              tickvals=[0,10,25,50],ticktext=["0","10","25","50"]),
                    bar=dict(color=g_c2,thickness=.3),bgcolor=W,borderwidth=0,
                    steps=[dict(range=[0,10],color="#F0FDF4"),
                           dict(range=[10,25],color="#FEFCE8"),
                           dict(range=[25,50],color="#FEF2F2")],
                    threshold=dict(line=dict(color=R,width=3),thickness=.85,value=25),
                ),
            ))
            fig_g2.update_layout(height=210,margin=dict(l=15,r=15,t=28,b=0),paper_bgcolor=W)
            st.plotly_chart(fig_g2, use_container_width=True)

            ch("Distribución de paradas",f"total: {tp:.0f} h")
            fig_p=go.Figure(go.Bar(
                x=["Setups","Imprevistas","Mantenimiento"],y=[s_h,i_h,m_h],
                marker_color=[N2,R,A],
                text=[f"{v:.1f} h" for v in [s_h,i_h,m_h]],
                textposition="outside",textfont=dict(size=9,color=T2),
                hovertemplate="<b>%{x}</b><br>%{y:.1f} h<extra></extra>",
            ))
            fig_p.update_layout(
                height=118,margin=dict(l=20,r=20,t=36,b=18),
                plot_bgcolor=W,paper_bgcolor=W,showlegend=False,
                yaxis=dict(showticklabels=False,showgrid=False,zeroline=False),
                xaxis=dict(tickfont=dict(size=9,color=N2),zeroline=False),
                bargap=.4,
            )
            st.plotly_chart(fig_p, use_container_width=True)

    # ── Distribución & Mix ────────────────────────────────────────────────────
    sec("Distribución &amp; Mix de Producción", "#7C3AED")
    PAL12 = [R,B,A,G,"#7C3AED","#0891B2","#BE185D","#65A30D","#9333EA","#EA580C","#0F766E","#B45309"]

    df_dist = df_clean.copy()
    df_dist["Familia"] = df_dist["Material"].apply(get_family)

    cA, cB = st.columns([1.5, 1])

    # ── Carga semanal ─────────────────────────────────────────────────────────
    with cA:
        if "Inicio" in df_clean.columns and "Cantidad (t) Programada" in df_clean.columns:
            df_w = df_clean.copy()
            df_w["Inicio"] = pd.to_datetime(df_w["Inicio"], errors="coerce")
            df_w["SemMes"] = df_w["Inicio"].apply(
                lambda d: f"Semana {(d.day-1)//7+1}" if pd.notna(d) else "?"
            )
            weekly = df_w.groupby("SemMes")[["Cantidad (t) Programada","Tiempo lam. (h)"]].sum().reset_index()
            weekly = weekly.sort_values("SemMes")
            fig_sw = make_subplots(specs=[[{"secondary_y": True}]])
            fig_sw.add_trace(go.Bar(
                x=weekly["SemMes"], y=weekly["Cantidad (t) Programada"],
                name="Toneladas", marker=dict(color=B, opacity=.85, line=dict(color=W, width=.5)),
                text=weekly["Cantidad (t) Programada"].round(0).astype(int),
                textposition="inside", textfont=dict(size=9, color=W),
                constraintext="inside", insidetextanchor="middle",
                hovertemplate="<b>%{x}</b><br>%{y:,.0f} t<extra></extra>",
            ), secondary_y=False)
            fig_sw.add_trace(go.Scatter(
                x=weekly["SemMes"], y=weekly["Tiempo lam. (h)"],
                name="Horas lam.", mode="lines+markers",
                line=dict(color=A, width=2.5),
                marker=dict(color=W, size=9, line=dict(color=A, width=2.5)),
                hovertemplate="<b>%{x}</b><br>%{y:.1f} h<extra></extra>",
            ), secondary_y=True)
            fig_sw.update_layout(
                plot_bgcolor=W, paper_bgcolor=W, height=260,
                margin=dict(l=20, r=20, t=46, b=36),
                legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1,
                            font=dict(size=10, color=N2), bgcolor="rgba(0,0,0,0)",
                            bordercolor=BR, borderwidth=1),
                xaxis=dict(tickfont=dict(size=10, color=T2), gridcolor=GR, zeroline=False),
                yaxis=dict(title="Toneladas (t)", title_font=dict(size=9, color=B),
                           gridcolor=GR, zeroline=False, tickfont=dict(size=9, color=T3)),
                yaxis2=dict(title="Horas lam.", title_font=dict(size=9, color=A),
                            zeroline=False, tickfont=dict(size=9, color=T3),
                            overlaying="y", side="right"),
                bargap=.35,
                hoverlabel=HOVER_STYLE,
            )
            ch("Carga semanal", "toneladas y horas por semana del mes",
               tags=[("Barras = t","#EFF6FF","#2563EB"),("Línea = h","#FFFBEB","#D97706")])
            st.plotly_chart(fig_sw, use_container_width=True)

    # ── Donut composición ─────────────────────────────────────────────────────
    with cB:
        if "Cantidad (t) Programada" in df_clean.columns:
            df_d = df_dist
            fam_tons = df_d.groupby("Familia")["Cantidad (t) Programada"].sum().reset_index()
            fam_tons = fam_tons.sort_values("Cantidad (t) Programada", ascending=False)
            total_t_d = fam_tons["Cantidad (t) Programada"].sum()
            fam_pcts = (fam_tons["Cantidad (t) Programada"] / total_t_d
                        if total_t_d > 0
                        else pd.Series(0.0, index=fam_tons.index))
            donut_txt = [f"{p:.0%}" if p >= 0.03 else "" for p in fam_pcts]
            fig_do = go.Figure(go.Pie(
                labels=fam_tons["Familia"],
                values=fam_tons["Cantidad (t) Programada"],
                hole=0.58,
                marker=dict(colors=PAL12[:len(fam_tons)],
                            line=dict(color=W, width=2)),
                text=donut_txt,
                textinfo="text",
                textposition="inside",
                automargin=True,
                textfont=dict(size=9, color=W),
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} t &nbsp;(%{percent})<extra></extra>",
                showlegend=True,
            ))
            fig_do.update_layout(
                paper_bgcolor=W, height=260,
                margin=dict(l=10, r=10, t=46, b=10),
                legend=dict(
                    orientation="v", x=1.0, y=0.5,
                    xanchor="left", yanchor="middle",
                    font=dict(size=8, color=N), bgcolor="rgba(0,0,0,0)",
                    tracegroupgap=2,
                ),
                hoverlabel=HOVER_STYLE,
                annotations=[dict(
                    text=f"<b>{total_t_d:,.0f}</b><br><span style='font-size:9px'>t total</span>",
                    x=0.5, y=0.5, font=dict(size=14, color=N), showarrow=False,
                )],
            )
            ch("Composición del programa", "% toneladas por familia de material")
            st.plotly_chart(fig_do, use_container_width=True)

    cC, cD = st.columns([1, 1.5])

    # ── Scatter productividad vs cantidad ─────────────────────────────────────
    with cC:
        if "Cantidad (t) Programada" in df_clean.columns and "Product. (t/h)" in df_clean.columns:
            df_sc = df_dist
            unique_fams = df_sc["Familia"].unique().tolist()
            fam_color = {f: PAL12[i % len(PAL12)] for i, f in enumerate(unique_fams)}
            sc_colors = df_sc["Familia"].map(fam_color).tolist()
            bubble_sizes = (df_sc["Tiempo lam. (h)"].clip(upper=200) / 5).clip(lower=8).tolist()
            mean_t = df_sc["Cantidad (t) Programada"].mean()
            mean_p = df_sc["Product. (t/h)"].mean()
            fig_sc = go.Figure(go.Scatter(
                x=df_sc["Cantidad (t) Programada"],
                y=df_sc["Product. (t/h)"],
                mode="markers",
                marker=dict(color=sc_colors, size=bubble_sizes,
                            sizemode="diameter", opacity=.8,
                            line=dict(color=W, width=1)),
                text=df_sc["Material"],
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Cantidad: %{x:,.0f} t<br>"
                    "Productividad: %{y:.1f} t/h<extra></extra>"
                ),
            ))
            fig_sc.add_hline(y=mean_p, line_dash="dot", line_color=T3, line_width=1,
                             annotation_text=f"media {mean_p:.1f} t/h",
                             annotation_font=dict(size=8, color=T3),
                             annotation_position="top right")
            fig_sc.add_vline(x=mean_t, line_dash="dot", line_color=T3, line_width=1,
                             annotation_text=f"media {mean_t:,.0f} t",
                             annotation_font=dict(size=8, color=T3),
                             annotation_position="top right")
            fig_sc.update_layout(
                plot_bgcolor=W, paper_bgcolor=W, height=310,
                margin=dict(l=20, r=20, t=46, b=30),
                xaxis=dict(title="Cantidad (t)", title_font=dict(size=9, color=T2),
                           gridcolor=GR, zeroline=False, tickfont=dict(size=8, color=T3)),
                yaxis=dict(title="Productividad (t/h)", title_font=dict(size=9, color=T2),
                           gridcolor=GR, zeroline=False, tickfont=dict(size=8, color=T3)),
                hoverlabel=HOVER_STYLE,
            )
            ch("Productividad vs Cantidad", "burbuja = horas de laminación",
               tags=[("Cuadrante sup-der = ideal","#F0FDF4","#059669")])
            st.plotly_chart(fig_sc, use_container_width=True)

    # ── Heatmap calendario ────────────────────────────────────────────────────
    with cD:
        if "Inicio" in df_clean.columns and "Tiempo lam. (h)" in df_clean.columns:
            df_h = df_clean.copy()
            df_h["Inicio"] = pd.to_datetime(df_h["Inicio"], errors="coerce")
            df_h["Dia"] = df_h["Inicio"].dt.day
            n_days = calendar.monthrange(year, month)[1]
            daily_h = df_h.groupby("Dia")["Tiempo lam. (h)"].sum().reindex(
                range(1, n_days + 1), fill_value=0
            )
            first_dow = calendar.monthrange(year, month)[0]  # Mon=0
            cells = [None] * first_dow + daily_h.tolist()
            while len(cells) % 7:
                cells.append(None)
            grid = [cells[i:i+7] for i in range(0, len(cells), 7)]
            day_nums = [None] * first_dow + list(range(1, n_days + 1))
            while len(day_nums) % 7:
                day_nums.append(None)
            day_grid = [day_nums[i:i+7] for i in range(0, len(day_nums), 7)]
            txt_grid = [
                [str(d) if d is not None else "" for d in row]
                for row in day_grid
            ]
            fig_cal = go.Figure(go.Heatmap(
                z=grid,
                text=txt_grid,
                texttemplate="%{text}",
                textfont=dict(size=11, color=N),
                colorscale=[[0,"#F0F9FF"],[0.4,"#3B82F6"],[1,"#1E3A8A"]],
                showscale=True,
                colorbar=dict(title="h", thickness=12, len=0.7,
                              tickfont=dict(size=8, color=T2)),
                hoverongaps=False,
                hovertemplate="Día %{text}: %{z:.1f} h<extra></extra>",
            ))
            fig_cal.update_layout(
                paper_bgcolor=W, height=310,
                margin=dict(l=10, r=50, t=46, b=20),
                xaxis=dict(tickvals=list(range(7)),
                           ticktext=["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"],
                           tickfont=dict(size=9, color=T2), zeroline=False, showgrid=False),
                yaxis=dict(autorange="reversed", showticklabels=False, showgrid=False),
                hoverlabel=HOVER_STYLE,
            )
            ch(f"Carga diaria — {calendar.month_name[month]} {year}",
               "horas de laminación por día",
               tags=[("Más oscuro = más cargado","#EFF6FF","#2563EB")])
            st.plotly_chart(fig_cal, use_container_width=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        f'<div class="sb-logo-area">'
        f'<img src="{APR_LOGO}" width="95" style="filter:brightness(0) invert(1);" onerror="this.style.display:none"/>'
        f'<div style="margin-top:.5rem;font-size:.58rem;color:#334155;letter-spacing:1.8px;font-weight:800;text-transform:uppercase;">Sistema de Programación</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)
    st.markdown('<span class="sb-label">Flujo de trabajo</span>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "① Cargar programa Excel (.xlsx)",
        type=["xlsx"], key="morgan", label_visibility="visible",
    )
    file_ok = uploaded is not None

    st.markdown('<span class="sb-label">Parámetros de inicio</span>', unsafe_allow_html=True)
    start_date      = st.date_input("② Fecha de inicio", value=date.today(), label_visibility="visible")
    start_time_text = st.text_input("③ Hora de inicio (HH:MM)", value="00:00", max_chars=5)

    st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)
    st.markdown('<span class="sb-label">Modelos activos</span>', unsafe_allow_html=True)
    for nm, sc in [("XGBoost","R² = 0.9998"),("Random Forest","R² = 0.9922"),
                   ("Optimizador","Held-Karp"),("Scheduler","Secuencial 24h")]:
        st.markdown(
            f'<div class="mb"><span class="mb-n">{nm}</span><span class="mb-s">{sc}</span></div>',
            unsafe_allow_html=True,
        )
    st.markdown('<hr class="sb-divider"/>', unsafe_allow_html=True)
    generar = st.button("⚡  Generar Programación", disabled=not file_ok)

month = start_date.month
year  = start_date.year

# ── MAIN ──────────────────────────────────────────────────────────────────────
if uploaded is None:
    st.markdown(
        '<div class="hero-outer">'
        '<div class="hero-pre">Acerías PazdelRío · Sogamoso, Colombia</div>'
        '<div class="hero-title">Programación<br><span>inteligente</span> de producción</div>'
        '<div class="hero-sub">'
        'Optimiza automáticamente el cronograma mensual del Tren Morgan usando modelos de '
        'Machine Learning entrenados con datos históricos de producción.'
        '</div>'
        '<div class="step-row">'
        '<div class="step-box" data-n="01">'
        '<div class="step-ico">📂</div>'
        '<div class="step-nm">Cargar archivo</div>'
        '<div class="step-ds">Sube el programa Excel del Tren Morgan desde el panel izquierdo</div>'
        '</div>'
        '<div class="step-box" data-n="02">'
        '<div class="step-ico">📅</div>'
        '<div class="step-nm">Configurar</div>'
        '<div class="step-ds">Define la fecha y hora de inicio del programa mensual</div>'
        '</div>'
        '<div class="step-box" data-n="03">'
        '<div class="step-ico">⚡</div>'
        '<div class="step-nm">Generar</div>'
        '<div class="step-ds">Presiona el botón rojo y obtén el cronograma optimizado con IA</div>'
        '</div>'
        '<div class="step-box" data-n="04">'
        '<div class="step-ico">📊</div>'
        '<div class="step-nm">Analizar</div>'
        '<div class="step-ds">Explora el dashboard y descarga el resultado en Excel</div>'
        '</div>'
        '</div>'
        '<div class="feat-row">'
        '<div class="feat-pill">📊 Predicción ML de productividad</div>'
        '<div class="feat-pill">⚙️ Optimización Held-Karp</div>'
        '<div class="feat-pill">📅 Cronograma automático</div>'
        '<div class="feat-pill">📥 Exportación Excel</div>'
        '<div class="feat-pill">🤖 XGBoost R²=0.9998</div>'
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
        st.markdown(
            f'<div class="tbl-head">'
            f'<span class="tbl-t">Orden optimizado de materiales</span>'
            f'<span class="tbl-m">{len(df_vp)} órdenes · listo para programar</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.dataframe(
            df_vp[["material","cantidad_t"]].rename(
                columns={"material":"Material","cantidad_t":"Cantidad (t)"}),
            use_container_width=True, height=175,
        )
    except Exception as e:
        st.markdown(
            f'<div class="alert warn">⚠️ &nbsp;Vista previa no disponible: {e}</div>',
            unsafe_allow_html=True,
        )

    if generar:
        try:
            t_inicio = parse_start_time(start_time_text)
        except ValueError as ve:
            st.markdown(f'<div class="alert err">✕ &nbsp;{ve}</div>', unsafe_allow_html=True)
            st.stop()

        initial_start = datetime.combine(start_date, t_inicio)
        with st.spinner("Procesando con los modelos de ML…"):
            try:
                import requests
                uploaded.seek(0)
                resp = requests.post(
                    API_URL,
                    files={"file_morgan":("morgan.xlsx", uploaded.getvalue())},
                    data={"month":month,"year":year,
                          "initial_start":initial_start.isoformat(sep=" ")},
                    timeout=90,
                )
            except Exception as ce:
                st.markdown(f'<div class="alert err">✕ &nbsp;No se pudo conectar: {ce}</div>', unsafe_allow_html=True)
                st.stop()

        if resp.status_code != 200:
            st.markdown(f'<div class="alert err">✕ &nbsp;Error API {resp.status_code}: {resp.text[:300]}</div>', unsafe_allow_html=True)
            st.stop()

        for res in resp.json().get("results",[]):
            excel_b64 = res.get("excel_b64")
            filename  = res.get("filename","cronograma.xlsx")
            if not excel_b64: continue

            excel_bytes = base64.b64decode(excel_b64)
            df = pd.read_excel(io.BytesIO(excel_bytes))
            if "t/día efectiva" in df.columns:
                df["t/día"] = df["t/día efectiva"]
                df = df.drop(columns=["t/día efectiva"], errors="ignore")

            overflow_mask = df["Material"].astype(str).str.contains("OVERFLOW", na=False)
            df_clean = df[~overflow_mask]
            df_over  = df[overflow_mask]

            render_kpis(df_clean, df_over, month, year)

            tab1, tab2 = st.tabs(["📅  Cronograma", "📊  Dashboard Analítico"])

            with tab1:
                render_gantt(df_clean, month, year)
                if len(df_over) > 0:
                    over_h = float(df_over["Tiempo lam. (h)"].sum())
                    st.markdown(
                        f'<div class="alert err">⚠️ &nbsp;<strong>Overflow detectado:</strong> '
                        f'el programa excede la capacidad mensual en <strong>{over_h:.1f} horas</strong>. '
                        f'Se recomienda diferir algunas órdenes al mes siguiente.</div>',
                        unsafe_allow_html=True,
                    )
                with st.expander("Ver tabla completa del cronograma"):
                    st.dataframe(df_clean, use_container_width=True, height=360)
                total_rows_clean = len(df_clean)
                st.markdown(
                    f'<div class="export-card">'
                    f'<div class="ec-left">'
                    f'<div class="ec-title">Cronograma listo para exportar</div>'
                    f'<div class="ec-meta">{filename}&nbsp;&nbsp;·&nbsp;&nbsp;'
                    f'{total_rows_clean} órdenes&nbsp;&nbsp;·&nbsp;&nbsp;'
                    f'{calendar.month_name[month]} {year}</div>'
                    f'</div>'
                    f'<div class="ec-icon">📊</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                _, dc, _ = st.columns([1, 2, 1])
                with dc:
                    st.download_button(
                        label=f"📥  Descargar Excel — {calendar.month_name[month]} {year}",
                        data=excel_bytes, file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )

            with tab2:
                render_dashboard(df_clean, month, year)


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown(
    f'<div class="footer">'
    f'<div><strong>GEPA-LAMIN</strong> &nbsp;·&nbsp; Sistema Predictivo de Programación de Producción'
    f' &nbsp;·&nbsp; Especialización en Analítica Estratégica de Datos &nbsp;·&nbsp; 2026</div>'
    f'<div style="display:flex;align-items:center;gap:1rem;">'
    f'<span>Pérez &nbsp;·&nbsp; Quintero &nbsp;·&nbsp; Ortiz &nbsp;·&nbsp; Patiño</span>'
    f'<img src="{UPTC_LOGO}" height="26" style="filter:brightness(0) invert(1);opacity:.4;" onerror="this.style.display=\'none\'"/>'
    f'</div></div>',
    unsafe_allow_html=True,
)
