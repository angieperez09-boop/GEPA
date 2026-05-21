import re
import pandas as pd
import numpy as np
from typing import Tuple

REQUIRED_COLS = ["codigo", "material", "cantidad_t"]

OPTIONAL_TIME_COLS = ["tiempo_dias", "tiempo (días)", "tiempo (dias)", "tiempo_dia", "t_dia"]


_ALNUM_RE = re.compile(r'[^a-z0-9]')


def _alnum(s) -> str:
    return _ALNUM_RE.sub('', str(s).lower())


def match_to_canonical(material, le_classes) -> str:
    """Map a raw material name to its canonical class from a LabelEncoder.

    Strategy: alphanumeric-only normalized exact match, then substring match
    in either direction. Falls back to the first class if nothing matches.
    """
    if le_classes is None or len(le_classes) == 0:
        return str(material)
    known = {_alnum(c): c for c in le_classes}
    m = _alnum(material)
    if m in known:
        return known[m]
    for nk, cls in known.items():
        if nk in m or m in nk:
            return cls
    return le_classes[0]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    # normalize column names to lowercase stripped
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def validate_input_df(df: pd.DataFrame) -> pd.DataFrame:
    df2 = _normalize_columns(df)

    optional_renames = {}
    for col in list(df2.columns):
        normalized = col.replace(" ", "")
        if normalized in {"tiempo(días)", "tiempo(dias)", "tiempodias", "tiempo_dias", "t/día", "t/dia", "t_dia"}:
            optional_renames[col] = "tiempo_dias"
    if optional_renames:
        df2 = df2.rename(columns=optional_renames)

    missing = [c for c in REQUIRED_COLS if c not in df2.columns]
    if missing:
        # attempt heuristic mapping for common column names
        cols = list(df2.columns)
        candidates = {
            'codigo': ['codigo', 'cod', 'código', 'codigo_material'],
            'material': ['material', 'descripcion', 'producto', 'producto_cod'],
            'cantidad_t': ['cantidad', 'cantidad (t)', 'cantidad (t) programada', 'cantidad_t', 'cantidad programada', 'cantidad_programada'],
        }

        renamed = {}
        for req in missing:
            found = None
            for cand in candidates.get(req, []):
                for col in cols:
                    if cand in col:
                        found = col
                        break
                if found:
                    break
            if found:
                renamed[found] = req

        if renamed:
            df2 = df2.rename(columns=renamed)
            missing = [c for c in REQUIRED_COLS if c not in df2.columns]

        if missing:
            raise ValueError(f"Faltan columnas obligatorias: {missing}")
    # basic numeric type checks for important numeric columns when present
    for col in ["cantidad_t", "tiempo_dias"]:
        if col in df2.columns:
            if not pd.api.types.is_numeric_dtype(df2[col]):
                try:
                    df2[col] = pd.to_numeric(df2[col], errors="raise")
                except Exception:
                    raise ValueError(f"La columna '{col}' debe ser numérica")
            if (df2[col] < 0).any():
                raise ValueError(f"La columna '{col}' contiene valores negativos")
    return df2


def featurize(df: pd.DataFrame, month: int, year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (X, df_feat).

    X is a DataFrame of features for model input; df_feat is the dataframe used for scheduling (includes cantidad_t).
    Column names match training: 'producto' (raw string, encoded in main.py), 'mes_num', 'anio', 'cantidad_t'.
    """
    df2 = df.copy()
    # prefer already-normalized 'cantidad_t' (validate_input_df should have ensured it),
    # otherwise try common fallbacks
    if "cantidad_t" in df2.columns:
        df2["cantidad_t"] = df2["cantidad_t"].astype(float)
    else:
        fallback_cols = [c for c in ["venta directa", "cantidad", "cantidad (t)", "cantidad programada"] if c in df2.columns]
        if fallback_cols:
            df2["cantidad_t"] = df2[fallback_cols[0]].astype(float)
        else:
            df2["cantidad_t"] = 0.0
    df2["mes_num"] = month
    df2["anio"] = year
    if "tiempo_dias" not in df2.columns:
        df2["tiempo_dias"] = np.nan
    # expose material as 'producto' for encoder alignment in main.py
    df2["producto"] = df2["material"]

    X = df2[["producto", "cantidad_t", "mes_num", "anio", "tiempo_dias"]].copy()
    return X, df2


def canonical_setup_duration(value) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0

    if pd.isna(numeric) or numeric <= 0:
        return 0.0

    return 8.0 if numeric >= 6.0 else 4.0


def canonical_mtto_duration(value) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 0.0

    if pd.isna(numeric) or numeric <= 0:
        return 0.0

    return float(int(round(numeric)))


def lookup_setup_duration(setup_lookup, tipo_cod: int, current_product: str, current_family: str, next_family: str) -> float:
    if setup_lookup is None or not current_family or not next_family or current_family == next_family:
        return 0.0

    candidate_keys = [
        (tipo_cod, current_family, next_family),
        (tipo_cod, current_product, next_family),
        (tipo_cod, current_product),
    ]

    for key in candidate_keys:
        try:
            value = setup_lookup.get(key, None)
        except Exception:
            value = None

        if value is not None:
            return canonical_setup_duration(value)

    return 0.0


def lookup_mtto_duration(mtto_lookup, tipo_cod: int, current_product: str, current_family: str, next_product: str, next_family: str) -> float:
    if mtto_lookup is None or not next_product:
        return 0.0

    exact_lookup = None
    family_lookup = None
    if isinstance(mtto_lookup, dict):
        exact_lookup = mtto_lookup.get('exact')
        family_lookup = mtto_lookup.get('family')
    else:
        exact_lookup = mtto_lookup

    candidate_keys = [
        (tipo_cod, current_product, next_product),
        (tipo_cod, current_product, next_family),
        (tipo_cod, current_family, next_product),
        (tipo_cod, current_family, next_family),
    ]

    for lookup in (exact_lookup, family_lookup):
        if lookup is None:
            continue
        for key in candidate_keys:
            try:
                value = lookup.get(key, None)
            except Exception:
                value = None
            if value is not None:
                return canonical_mtto_duration(value)

    return 0.0


def lookup_monthly_mtto_profile(mtto_lookup, tipo_cod: int, month: int) -> tuple[int, float]:
    if mtto_lookup is None:
        return 0, 0.0

    try:
        count_lookup = mtto_lookup.get('count') if isinstance(mtto_lookup, dict) else None
        duration_lookup = mtto_lookup.get('duration') if isinstance(mtto_lookup, dict) else None
    except Exception:
        return 0, 0.0

    count = 0
    duration = 0.0

    if count_lookup is not None:
        try:
            count = int(round(float(count_lookup.get((tipo_cod, month), 0.0))))
        except Exception:
            count = 0

    if duration_lookup is not None:
        try:
            duration = canonical_mtto_duration(duration_lookup.get((tipo_cod, month), 0.0))
        except Exception:
            duration = 0.0

    count = max(0, min(3, count))
    return count, duration


def allocate_monthly_mtto(products, count: int, duration: float) -> np.ndarray:
    mtto = np.zeros(len(products), dtype=float)
    if count <= 0 or len(products) == 0:
        return mtto

    block_ends = [i for i in range(len(products)) if i == len(products) - 1 or products[i] != products[i + 1]]
    if not block_ends:
        return mtto

    if count >= len(block_ends):
        chosen_positions = block_ends
    elif count == 1:
        chosen_positions = [block_ends[-1]]
    else:
        raw_positions = np.linspace(0, len(block_ends) - 1, count)
        chosen_positions = []
        for pos in raw_positions:
            candidate = block_ends[int(round(pos))]
            if candidate not in chosen_positions:
                chosen_positions.append(candidate)
        if len(chosen_positions) < count:
            for candidate in block_ends:
                if candidate not in chosen_positions:
                    chosen_positions.append(candidate)
                if len(chosen_positions) >= count:
                    break

    for position in chosen_positions[:count]:
        mtto[position] = duration

    return mtto
 

def lookup_util_pct(util_lookups, tipo_cod: int, family: str, product: str = None, default: float = 0.0) -> float:
    """Return utilization index.

    util_lookups can be either:
    - a Series indexed by (tipo_cod, family) [legacy family-only lookup], or
    - a dict with keys 'family' and/or 'product' mapping to Series indexed by (tipo_cod, family) and (tipo_cod, producto) respectively.

    Preference order: product-level (if available and product provided) -> family-level -> default.
    """
    if util_lookups is None:
        return float(default)

    # normalize to dict form
    prod_lookup = None
    fam_lookup = None
    try:
        if isinstance(util_lookups, dict):
            prod_lookup = util_lookups.get('product')
            fam_lookup = util_lookups.get('family')
        else:
            # legacy: assume given Series is family-level
            fam_lookup = util_lookups
    except Exception:
        return float(default)

    # try product-level first
    if product and prod_lookup is not None:
        try:
            val = prod_lookup.get((tipo_cod, product), None)
            if val is not None and not pd.isna(val):
                return float(val)
        except Exception:
            pass

    # then family-level
    if family and fam_lookup is not None:
        try:
            val = fam_lookup.get((tipo_cod, family), None)
            if val is not None and not pd.isna(val):
                return float(val)
        except Exception:
            pass

    return float(default)
