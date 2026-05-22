from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import base64
import io
import logging
import pandas as pd
import numpy as np
import os
from joblib import load
from io import BytesIO
from datetime import datetime

from controllers.utils.parsers import (
    validate_input_df, featurize, lookup_setup_duration,
    lookup_monthly_mtto_profile, allocate_monthly_mtto,
    lookup_util_pct, match_to_canonical,
)
from controllers.scheduler import run_scheduler
from controllers.config import get_family
from controllers.optimizer import optimize_campaign_order

app = FastAPI(title="GEPA Scheduling API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "artifacts")


@app.on_event("startup")
def load_artifacts():
    app.state.models = {}
    app.state.encoders = None
    try:
        for fname in os.listdir(MODEL_DIR):
            if not fname.lower().endswith('.joblib'):
                continue
            path = os.path.join(MODEL_DIR, fname)
            try:
                obj = load(path)
                app.state.models[fname] = obj
            except Exception:
                app.state.models[fname] = None
    except Exception:
        app.state.models = {}

    app.state.rf = app.state.models.get('rf.joblib') or app.state.models.get('rf_model.joblib')
    app.state.xgb = app.state.models.get('xgb.joblib') or app.state.models.get('xgb_model.joblib')
    if 'encoders.joblib' in app.state.models:
        app.state.encoders = app.state.models.get('encoders.joblib')
    app.state.mtto_lookup = app.state.models.get('mtto_lookup.joblib')
    app.state.setup_lookup = app.state.models.get('setup_lookup.joblib')
    app.state.util_lookup = app.state.models.get('util_lookup.joblib')
    app.state.util_product_lookup = app.state.models.get('util_product_lookup.joblib')
    app.state.imprevistas_lookup = app.state.models.get('imprevistas_lookup.joblib')
    app.state.imprevistas_model = app.state.models.get('imprevistas_model.joblib')


@app.post("/predict/schedule")
async def schedule(
    month: int = Form(...),
    year: int = Form(...),
    initial_start: str = Form(None),
    file_morgan: UploadFile = File(...),
):
    files = {"TREN_MORGAN": file_morgan}
    results = []

    rf = getattr(app.state, "rf", None)
    xgb = getattr(app.state, "xgb", None)
    encoders = getattr(app.state, "encoders", None)
    mtto_lookup = getattr(app.state, "mtto_lookup", None)
    util_lookup = getattr(app.state, "util_lookup", None)
    setup_lookup = getattr(app.state, "setup_lookup", None)
    imprevistas_lookup = getattr(app.state, "imprevistas_lookup", None)

    for plant_name, upload in files.items():
        try:
            content = await upload.read()
            df = pd.read_excel(BytesIO(content), engine="openpyxl")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error leyendo Excel para {plant_name}: {e}")

        try:
            df_valid = validate_input_df(df)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Validación falló para {plant_name}: {e}")

        df_valid = optimize_campaign_order(
            df_valid,
            tipo_cod=0 if 'MORGAN' in plant_name else 1,
            encoders=encoders,
            setup_lookup=setup_lookup,
        )

        X, df_feat = featurize(df_valid, month, year)

        X_for_model = X.copy()
        if encoders is not None:
            try:
                if hasattr(encoders, "transform"):
                    X_arr = encoders.transform(X_for_model)
                    try:
                        X_for_model = pd.DataFrame(X_arr)
                    except Exception:
                        X_for_model = X_arr
                elif isinstance(encoders, dict) and 'producto' in encoders:
                    le = encoders['producto']
                    matched = X_for_model['producto'].apply(lambda m: match_to_canonical(m, le.classes_))
                    X_for_model = X_for_model.copy()
                    X_for_model['producto_cod'] = le.transform(matched)
            except Exception:
                X_for_model = X.copy()

        X_for_model = X_for_model.copy()
        X_for_model['tipo_cod'] = 0 if 'MORGAN' in plant_name else 1

        matched_list = matched.tolist() if 'matched' in locals() else X['producto'].tolist()
        familias = [get_family(m) for m in matched_list]

        feature_cols_path = os.path.join(MODEL_DIR, 'feature_cols.joblib')
        if os.path.exists(feature_cols_path):
            try:
                feature_cols = load(feature_cols_path)
            except Exception:
                feature_cols = ['producto_cod', 'cantidad_t', 'mes_num', 'anio']
        else:
            feature_cols = ['producto_cod', 'cantidad_t', 'mes_num', 'anio']

        for c in feature_cols:
            if c not in X_for_model.columns:
                X_for_model[c] = 0

        X_model_input = X_for_model[feature_cols].copy().fillna(0)

        if xgb is not None:
            try:
                product = xgb.predict(X_model_input.values)
            except Exception:
                product = np.full(len(X), 50.0)
        else:
            product = np.full(len(X), 50.0)

        tipo_cod_val = 0 if 'MORGAN' in plant_name else 1
        productos = matched_list
        mtto = np.zeros(len(productos))
        if mtto_lookup is not None:
            mtto_count, mtto_duration = lookup_monthly_mtto_profile(mtto_lookup, tipo_cod_val, month)
            mtto = allocate_monthly_mtto(productos, mtto_count, mtto_duration)

        setup = np.zeros(len(productos))
        if setup_lookup is not None:
            for i in range(len(productos)):
                is_transition = (i < len(familias) - 1) and (familias[i] != familias[i + 1])
                if is_transition:
                    setup[i] = lookup_setup_duration(
                        setup_lookup,
                        tipo_cod_val,
                        matched_list[i],
                        familias[i],
                        familias[i + 1],
                    )

        imprevistas = np.zeros(len(productos))
        if app.state.imprevistas_model is not None:
            try:
                imp_feat_cols = [c for c in ['tipo_cod', 'producto_cod', 'mes_num', 'anio', 'hora_inicio', 'dia_semana'] if c in X_for_model.columns]
                X_imp_in = X_for_model[imp_feat_cols].copy().fillna(0)
                imprevistas = app.state.imprevistas_model.predict(X_imp_in.values if hasattr(app.state.imprevistas_model, 'predict') else X_imp_in)
                imprevistas = np.nan_to_num(imprevistas, 0.0)
            except Exception:
                imprevistas = np.zeros(len(productos))
        elif imprevistas_lookup is not None:
            for i in range(len(productos)):
                key = (tipo_cod_val, productos[i], month)
                try:
                    imprevistas[i] = float(imprevistas_lookup.get(key, 0.0))
                except Exception:
                    imprevistas[i] = 0.0

        preds_df = pd.DataFrame({
            "product_t_h": product,
            "mtto_h": mtto,
            "setup_h": setup,
            "paradas_imprev_h": imprevistas,
            "util_pct": [lookup_util_pct({'family': util_lookup, 'product': app.state.util_product_lookup}, tipo_cod_val, familias[i], productos[i], 0.0) for i in range(len(productos))],
        })

        cantidad = df_feat.get("cantidad_t")
        preds_df = preds_df.reset_index(drop=True)
        if "product_t_h" in preds_df.columns:
            preds_df["product_t_h"] = pd.to_numeric(preds_df["product_t_h"], errors="coerce").fillna(0.0)
            tiempo = []
            for i in range(len(preds_df)):
                try:
                    cant = float(cantidad.iloc[i]) if cantidad is not None else 0.0
                except Exception:
                    cant = 0.0
                prod = float(preds_df.at[i, 'product_t_h'])
                tiempo.append(cant / prod if prod > 0 else 0.0)
            preds_df["tiempo_lam_h"] = tiempo

        try:
            if 'util_pct' in preds_df.columns and 'tiempo_lam_h' in preds_df.columns:
                util_vals = pd.to_numeric(preds_df['util_pct'], errors='coerce').fillna(0.0)
                tiempo_vals = pd.to_numeric(preds_df['tiempo_lam_h'], errors='coerce').fillna(0.0)
                mask = (util_vals > 0) & (tiempo_vals >= 0)
                computed = np.zeros(len(preds_df))
                computed[mask] = (tiempo_vals[mask] / util_vals[mask]) - tiempo_vals[mask]
                computed = np.where(np.isfinite(computed) & (computed >= 0), computed, preds_df.get('paradas_imprev_h', 0.0))
                preds_df['paradas_imprev_h'] = computed
        except Exception:
            pass

        initial_start_dt = None
        if initial_start:
            try:
                initial_start_dt = datetime.fromisoformat(initial_start)
            except Exception:
                initial_start_dt = None

        schedule_df = run_scheduler(df_feat, preds_df, month, year, initial_start=initial_start_dt)

        out_name = f"{plant_name}_schedule_{year}-{month:02d}.xlsx"
        buffer = io.BytesIO()
        schedule_df.to_excel(buffer, index=False)
        buffer.seek(0)
        excel_b64 = base64.b64encode(buffer.read()).decode()

        results.append({
            "plant": plant_name,
            "filename": out_name,
            "excel_b64": excel_b64,
            "preview": schedule_df.head(10).to_dict(orient="records"),
            "total_rows": int(len(schedule_df)),
        })

    return {"status": "ok", "results": results}


@app.get("/models/info")
def models_info():
    try:
        files = [f for f in os.listdir(MODEL_DIR) if f.lower().endswith('.joblib')]
    except Exception:
        files = []
    loaded = getattr(app.state, 'models', {}) or {}
    return {
        "files": files,
        "loaded_keys": [k for k, v in loaded.items() if v is not None],
        "failed_keys": [k for k, v in loaded.items() if v is None],
        "models_dir": MODEL_DIR,
    }
