"""Campaign ordering optimizer.

Given a list of materials in arbitrary order, this module reorders them to
minimize the total family-transition setup time. It groups rows by family
(each grosor is its own family), picks the optimal family sequence via a
Held-Karp DP on the directed setup-cost matrix, and orders materials within
each family by tonnage descending.
"""
from typing import Optional

import numpy as np
import pandas as pd

from controllers.config import get_family
from controllers.utils.parsers import match_to_canonical


def _held_karp(cost: np.ndarray) -> list:
    """Min-cost Hamiltonian path through all N nodes (open-ended TSP).

    Returns the ordered list of node indices that minimizes the sum of
    consecutive directed transitions. O(N^2 * 2^N) time.
    """
    n = cost.shape[0]
    if n == 0:
        return []
    if n == 1:
        return [0]

    dp = {}
    for i in range(n):
        dp[(1 << i, i)] = (0.0, -1)

    for mask in range(1, 1 << n):
        for last in range(n):
            if not (mask & (1 << last)):
                continue
            key = (mask, last)
            if key not in dp:
                continue
            cur_cost = dp[key][0]
            for nxt in range(n):
                if mask & (1 << nxt):
                    continue
                new_mask = mask | (1 << nxt)
                new_cost = cur_cost + float(cost[last][nxt])
                new_key = (new_mask, nxt)
                if new_key not in dp or dp[new_key][0] > new_cost:
                    dp[new_key] = (new_cost, last)

    full = (1 << n) - 1
    best_cost = float('inf')
    best_end = 0
    for i in range(n):
        entry = dp.get((full, i))
        if entry is not None and entry[0] < best_cost:
            best_cost = entry[0]
            best_end = i

    path = []
    mask = full
    cur = best_end
    while cur != -1:
        path.append(cur)
        prev = dp[(mask, cur)][1]
        mask ^= (1 << cur)
        cur = prev
    path.reverse()
    return path


def _build_cost_matrix(families: list, setup_lookup, tipo_cod: int) -> np.ndarray:
    n = len(families)
    cost = np.zeros((n, n), dtype=float)

    median_val = 4.0
    if setup_lookup is not None:
        try:
            plant_slice = setup_lookup.loc[tipo_cod]
            median_val = float(plant_slice.median())
        except Exception:
            pass

    for i, fi in enumerate(families):
        for j, fj in enumerate(families):
            if i == j or fi == fj:
                cost[i][j] = 0.0
                continue
            val = None
            if setup_lookup is not None:
                try:
                    val = setup_lookup.get((tipo_cod, fi, fj))
                except Exception:
                    val = None
            cost[i][j] = float(val) if val is not None and not pd.isna(val) else median_val

    return cost


def optimize_campaign_order(
    df_valid: pd.DataFrame,
    tipo_cod: int,
    encoders: Optional[dict],
    setup_lookup,
) -> pd.DataFrame:
    """Reorder df rows so families form contiguous campaigns ordered to
    minimize total setup time. Within a family, sort by cantidad_t desc
    (large lots first — industrial best practice when intra-family setup
    is zero). Never alters cantidades nor drops rows.
    """
    if df_valid is None or len(df_valid) == 0:
        return df_valid

    df = df_valid.copy().reset_index(drop=True)

    le_classes = None
    if isinstance(encoders, dict) and 'producto' in encoders:
        le_classes = list(encoders['producto'].classes_)

    materials = df['material'].astype(str).tolist() if 'material' in df.columns else []
    canonicals = [match_to_canonical(m, le_classes) for m in materials]
    families = [get_family(c) for c in canonicals]
    df['_family'] = families

    unique_families = list(dict.fromkeys(families))
    in_rows = len(df)

    if len(unique_families) <= 1:
        if 'cantidad_t' in df.columns:
            df = df.sort_values('cantidad_t', ascending=False, kind='mergesort').reset_index(drop=True)
        if len(df) != in_rows:
            raise RuntimeError(f"optimizer dropped rows: {in_rows} → {len(df)}")
        return df.drop(columns=['_family'], errors='ignore')

    cost = _build_cost_matrix(unique_families, setup_lookup, tipo_cod)
    path_indices = _held_karp(cost)
    ordered_families = [unique_families[i] for i in path_indices]
    family_rank = {fam: r for r, fam in enumerate(ordered_families)}

    df['_rank'] = df['_family'].map(family_rank)
    sort_cols = ['_rank']
    ascending = [True]
    if 'cantidad_t' in df.columns:
        sort_cols.append('cantidad_t')
        ascending.append(False)
    df = df.sort_values(sort_cols, ascending=ascending, kind='mergesort').reset_index(drop=True)
    if len(df) != in_rows:
        raise RuntimeError(f"optimizer dropped rows: {in_rows} → {len(df)}")
    return df.drop(columns=['_family', '_rank'], errors='ignore')
