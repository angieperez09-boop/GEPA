import calendar
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Union


def run_scheduler(
    df: pd.DataFrame,
    preds: pd.DataFrame,
    month: int,
    year: int,
    horas_por_dia: int = 24,
    distribute_over_month: bool = False,
    initial_start: Optional[Union[datetime, str]] = None,
) -> pd.DataFrame:
    """Basic sequential scheduler.

    - df: validated input df with `cantidad_t` column
    - preds: DataFrame with columns `product_t_h`, `tiempo_lam_h`, `mtto_h`, `setup_h`, `util_pct`

    Sequence rule:
    - The first material starts at `initial_start`.
    - Each material finishes after its own duration, preferring `tiempo_dias` when present.
    - The next material starts at the previous finish plus the previous material's setup time.
    """
    df = df.reset_index(drop=True).copy()
    preds = preds.reset_index(drop=True).copy()

    # ensure expected columns (tiempo_lam_h will be computed below)
    for c in ["product_t_h", "mtto_h", "setup_h"]:
        if c not in preds.columns:
            preds[c] = 0.0

    schedule_rows = []
    month_start = datetime(year, month, 1, 0, 0)
    last_day = calendar.monthrange(year, month)[1]
    fin_mes = datetime(year, month, last_day, 23, 59)
    days_in_month = last_day

    if isinstance(initial_start, str):
        try:
            initial_start = pd.to_datetime(initial_start).to_pydatetime()
        except Exception:
            initial_start = None

    # Sequential single-block scheduling per material
    current = initial_start if isinstance(initial_start, datetime) else month_start
    total_rows = len(df)
    if total_rows == 0:
        return pd.DataFrame(schedule_rows)

    for idx, row in df.iterrows():
        cantidad = float(row.get("cantidad_t", 0.0))
        product_t_h = float(preds.loc[idx, "product_t_h"]) if idx in preds.index else 1.0
        tiempo_dias = row.get("tiempo_dias", None)
        try:
            tiempo_dias = float(tiempo_dias) if tiempo_dias is not None and pd.notna(tiempo_dias) else None
        except Exception:
            tiempo_dias = None
        tiempo_lam_h = (tiempo_dias * 24.0) if tiempo_dias is not None and tiempo_dias > 0 else ((cantidad / product_t_h) if product_t_h > 0 else 0.0)
        mtto_h = float(preds.loc[idx, "mtto_h"]) if idx in preds.index else 0.0
        setup_h = float(preds.loc[idx, "setup_h"]) if idx in preds.index else 0.0
        paradas_imprev_h = float(preds.loc[idx, "paradas_imprev_h"]) if ("paradas_imprev_h" in preds.columns and idx in preds.index) else 0.0
        util_pct = float(preds.loc[idx, 'util_pct']) if ("util_pct" in preds.columns and idx in preds.index) else 0.0
        util_pct_display = (util_pct * 100.0) if util_pct <= 1.5 else util_pct

        # Schedule every order in full — never truncate or drop rows. If the
        # cumulative time spills past fin_mes, the schedule simply continues
        # into the following month; a warning row is appended at the end.
        start = current
        finish = start + timedelta(hours=tiempo_lam_h)
        block_hours = (finish - start).total_seconds() / 3600.0

        raw_t_per_day = product_t_h * horas_por_dia
        effective_t_per_day = product_t_h * util_pct * horas_por_dia if util_pct and util_pct > 0 else raw_t_per_day
        schedule_rows.append({
            "t/día": round(raw_t_per_day, 1),
            "t/día efectiva": round(effective_t_per_day, 1),
            "CODIGO": row.get("codigo", row.get("material")),
            "Material": row.get("material"),
            "Cantidad (t) Programada": round(cantidad, 3),
            "Mtto pro. (h)": round(mtto_h, 3),
            "Inicio": start.strftime("%Y-%m-%d %H:%M"),
            "Fin": finish.strftime("%Y-%m-%d %H:%M"),
            "Product. (t/h)": product_t_h,
            "Tiempo lam. (h)": round(block_hours, 3),
            "Tiempo (días)": round((block_hours / 24.0), 3),
            "Índice de utilización (%)": round(util_pct_display, 1),
            "Paradas setups (h)": round(setup_h, 3),
            "Paradas imprevistas (h)": round(paradas_imprev_h, 3),
        })

        # next start = Fin_prev + Paradas_setup_prev + Mtto_pro_prev
        current = finish + timedelta(hours=setup_h + mtto_h)

    # If the total schedule exceeds the calendar month, surface that explicitly
    # instead of silently dropping orders.
    if current > fin_mes:
        overflow_h = (current - fin_mes).total_seconds() / 3600.0
        schedule_rows.append({
            "t/día": 0,
            "t/día efectiva": 0,
            "CODIGO": "⚠",
            "Material": f"OVERFLOW +{overflow_h:.1f}h fuera del mes",
            "Cantidad (t) Programada": 0,
            "Mtto pro. (h)": 0,
            "Inicio": fin_mes.strftime("%Y-%m-%d %H:%M"),
            "Fin": current.strftime("%Y-%m-%d %H:%M"),
            "Product. (t/h)": 0,
            "Tiempo lam. (h)": round(overflow_h, 3),
            "Tiempo (días)": round(overflow_h / 24.0, 3),
            "Índice de utilización (%)": 0,
            "Paradas setups (h)": 0,
            "Paradas imprevistas (h)": 0,
        })

    schedule_df = pd.DataFrame(schedule_rows)
    # ensure 'Tiempo (días)' appears as the last column for readability
    if 'Tiempo (días)' in schedule_df.columns:
        cols = [c for c in schedule_df.columns if c != 'Tiempo (días)'] + ['Tiempo (días)']
        schedule_df = schedule_df[cols]
    return schedule_df
