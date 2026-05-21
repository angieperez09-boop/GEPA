import warnings
warnings.filterwarnings('ignore')
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import r2_score, mean_squared_error
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
from joblib import dump


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
GOLD = ROOT / 'models' / 'data' / 'gold' / 'laminacion.parquet'
MODELS_DIR = ROOT / 'models' / 'artifacts'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET = 'productividad_t_h'

from controllers.config import get_family
from controllers.utils.parsers import canonical_setup_duration, canonical_mtto_duration, lookup_util_pct

print('Loading data:', GOLD)
df = pd.read_parquet(GOLD)
print('Data shape:', df.shape)

if TARGET not in df.columns:
    raise SystemExit(f'Target {TARGET} not found in data')

# Learn setup from family transitions, then keep only canonical 4h/8h values.
if all(c in df.columns for c in ['paradas_setup_h', 'anio', 'mes_num', 'tipo_cod', 'producto']):
    setup_source = df.copy()
    setup_source['_row_order'] = np.arange(len(setup_source))
    setup_source = setup_source.sort_values(['anio', 'mes_num', 'tipo_cod', '_row_order'])
    setup_source['family'] = setup_source['producto'].astype(str).map(get_family)
    setup_source['next_family'] = setup_source.groupby(['anio', 'mes_num', 'tipo_cod'])['family'].shift(-1)

    setup_lookup = (
        setup_source[
            (setup_source['paradas_setup_h'] > 0)
            & setup_source['next_family'].notna()
            & (setup_source['family'] != setup_source['next_family'])
        ]
        .groupby(['tipo_cod', 'family', 'next_family'])['paradas_setup_h']
        .median()
        .map(canonical_setup_duration)
    )

    if len(setup_lookup) > 0:
        dump(setup_lookup, MODELS_DIR / 'setup_lookup.joblib')
        print('setup_lookup saved:', len(setup_lookup), 'entries')
        print(setup_lookup.to_string())

# Learn maintenance as a monthly profile, capped at 3 events per month.
if all(c in df.columns for c in ['mtto_h', 'anio', 'mes_num', 'tipo_cod', 'producto']):
    mtto_source = df.copy()
    mtto_source['_row_order'] = np.arange(len(mtto_source))
    mtto_source = mtto_source.sort_values(['anio', 'mes_num', 'tipo_cod', '_row_order'])
    monthly_counts = (
        mtto_source[mtto_source['mtto_h'] > 0]
        .groupby(['anio', 'mes_num', 'tipo_cod'])
        .size()
        .reset_index(name='count')
    )
    monthly_counts['count'] = monthly_counts['count'].clip(upper=3)
    mtto_count_lookup = monthly_counts.groupby(['tipo_cod', 'mes_num'])['count'].median().astype(int)

    mtto_duration_lookup = (
        mtto_source[mtto_source['mtto_h'] > 0]
        .groupby(['tipo_cod', 'mes_num'])['mtto_h']
        .median()
        .map(canonical_mtto_duration)
    )

    mtto_lookup = {'count': mtto_count_lookup, 'duration': mtto_duration_lookup}
    dump(mtto_lookup, MODELS_DIR / 'mtto_lookup.joblib')
    print('mtto_lookup saved: count=', len(mtto_count_lookup), 'duration=', len(mtto_duration_lookup))
    print('mtto count lookup:')
    print(mtto_count_lookup.to_string())
    print('mtto duration lookup:')
    print(mtto_duration_lookup.to_string())

# util lookup: median utilization per family (tipo_cod, family)
if 'iu' in df.columns or 'iu_teorico' in df.columns:
    util_col = 'iu' if 'iu' in df.columns else 'iu_teorico'
    util_df = df.copy()
    util_df['family'] = util_df['producto'].astype(str).map(get_family)
    util_lookup = (
        util_df[~util_df[util_col].isna()]
        .groupby(['tipo_cod', 'family'])[util_col]
        .median()
    )
    dump(util_lookup, MODELS_DIR / 'util_lookup.joblib')
    print('util_lookup saved:', len(util_lookup), 'entries')
    print(util_lookup.to_string())

    # also build a product-level utilization lookup (per producto)
    util_product_lookup = (
        util_df[~util_df[util_col].isna()]
        .groupby(['tipo_cod', 'producto'])[util_col]
        .median()
    )
    dump(util_product_lookup, MODELS_DIR / 'util_product_lookup.joblib')
    print('util_product_lookup saved:', len(util_product_lookup), 'entries')
    print(util_product_lookup.to_string())

# Learn utilization as a family-based constant per plant/family.
util_col = 'iu_teorico' if 'iu_teorico' in df.columns else ('iu' if 'iu' in df.columns else None)
if util_col is not None and all(c in df.columns for c in ['tipo_cod', 'producto']):
    util_source = df.copy()
    util_source['family'] = util_source['producto'].astype(str).map(get_family)
    util_lookup = (
        util_source.groupby(['tipo_cod', 'family'])[util_col]
        .median()
    )
    dump(util_lookup, MODELS_DIR / 'util_lookup.joblib')
    print('util_lookup saved:', len(util_lookup), 'entries')
    print(util_lookup.to_string())

# El setup es la parada de transición entre familias: ocurre una sola vez tras la
# última orden de la familia saliente. En el Excel aparece en una fila aleatoria
# del grupo; lo movemos a la ÚLTIMA fila para coherencia en el entrenamiento.
if all(c in df.columns for c in ['paradas_setup_h', 'mes_num', 'tipo_cod', 'producto']):
    def _setup_to_last(x):
        total = x.sum()
        result = pd.Series(0.0, index=x.index)
        if total > 0:
            result.iloc[-1] = total
        return result
    df['paradas_setup_h'] = df.groupby(
        ['producto', 'mes_num', 'tipo_cod']
    )['paradas_setup_h'].transform(_setup_to_last)
    if 'paradas_imprev_h' in df.columns:
        df['paradas_total_h'] = df['paradas_setup_h'] + df['paradas_imprev_h']
    if 'tiempo_lam_h' in df.columns and 'paradas_total_h' in df.columns:
        df['tiempo_productivo_h'] = (df['tiempo_lam_h'] - df['paradas_total_h']).clip(lower=0)

# simple encoder for producto if present
encoders = {}
if 'producto' in df.columns:
    le = LabelEncoder()
    df['producto_cod'] = le.fit_transform(df['producto'].astype(str))
    encoders['producto'] = le

# Define candidate features
FEATURES_PLAN = [
    'tipo_cod', 'producto_cod', 'mes_num', 'anio', 'hora_inicio', 'dia_semana',
    # 'tiempo_lam_h' eliminado: = cantidad_t/productividad_t_h → leakage no-lineal
    # 'cantidad_t'   eliminado: productividad es propiedad del material/máquina, no del tamaño del pedido
    'mtto_h',
]
FEATURES_EJEC = [
    'paradas_setup_h', 'paradas_imprev_h', 'paradas_total_h',
    # 'tiempo_productivo_h' eliminado: = tiempo_lam_h - paradas (leakage)
    # 'duracion_real_h'     eliminado: ≈ tiempo_lam_h + paradas  (leakage)
]
FEATURES_ALL = FEATURES_PLAN + FEATURES_EJEC

# select features that exist
X = df[[c for c in FEATURES_ALL if c in df.columns]].copy()
if X.shape[1] == 0:
    raise SystemExit('No matching feature columns found in parquet. Columns available: ' + ','.join(df.columns.tolist()))

if TARGET not in df.columns:
    raise SystemExit(f'Target {TARGET} not found in data')

y = df[TARGET]

# Temporal split: train on 2025, test on 2026
train_mask = df['anio'] == 2025
test_mask  = df['anio'] == 2026
X_train, y_train = X[train_mask], y[train_mask]
X_test,  y_test  = X[test_mask],  y[test_mask]
print(f'Train (2025): {len(X_train)}  Test (2026): {len(X_test)}')

print('Training XGBoost...')
xgb_model = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, n_jobs=-1, verbosity=0)
xgb_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
xgb_pred = xgb_model.predict(X_test)
print(f'XGBoost → R²={r2_score(y_test, xgb_pred):.4f}  RMSE={mean_squared_error(y_test, xgb_pred)**0.5:.4f} t/h')

print('Training RandomForest...')
rf_model = RandomForestRegressor(n_estimators=200, min_samples_leaf=5, max_features='sqrt', oob_score=True, random_state=42, n_jobs=-1)
rf_model.fit(X_train, y_train)
rf_pred = rf_model.predict(X_test)
print(f'RandomForest → R²={r2_score(y_test, rf_pred):.4f}  RMSE={mean_squared_error(y_test, rf_pred)**0.5:.4f} t/h  OOB={rf_model.oob_score_:.4f}')

# save models
dump(xgb_model, MODELS_DIR / 'xgb.joblib')
dump(rf_model, MODELS_DIR / 'rf.joblib')
if encoders:
    dump(encoders, MODELS_DIR / 'encoders.joblib')
dump(list(X.columns), MODELS_DIR / 'feature_cols.joblib')

# Train a model to predict unplanned stops (`paradas_imprev_h`) per material if present
if 'paradas_imprev_h' in df.columns:
    IMP_TARGET = 'paradas_imprev_h'
    imp_features = [c for c in ['tipo_cod', 'producto_cod', 'mes_num', 'anio', 'hora_inicio', 'dia_semana']]
    # ensure producto_cod present
    if 'producto_cod' not in df.columns and 'producto_cod' in X.columns:
        df['producto_cod'] = X['producto_cod']

    X_imp = df[[c for c in imp_features if c in df.columns]].copy()
    y_imp = df[IMP_TARGET].fillna(0.0)

    # temporal split
    X_imp_train, X_imp_test = X_imp[train_mask], X_imp[test_mask]
    y_imp_train, y_imp_test = y_imp[train_mask], y_imp[test_mask]

    if len(X_imp_train) > 10 and X_imp_train.shape[1] > 0:
        from sklearn.ensemble import RandomForestRegressor as RF
        imp_model = RF(n_estimators=150, min_samples_leaf=3, max_features='sqrt', random_state=42, n_jobs=-1)
        try:
            imp_model.fit(X_imp_train.fillna(0), y_imp_train)
            imp_pred = imp_model.predict(X_imp_test.fillna(0))
            print(f'Imprevistas model → R²={r2_score(y_imp_test, imp_pred):.4f}  RMSE={mean_squared_error(y_imp_test, imp_pred)**0.5:.4f} h')
            dump(imp_model, MODELS_DIR / 'imprevistas_model.joblib')
            print('imprevistas_model saved')
        except Exception as e:
            print('Failed to train imprevistas model:', e)
    else:
        print('Not enough data to train imprevistas model')

# imprevistas lookup: average unplanned stops per (tipo_cod, producto, mes_num)
if all(c in df.columns for c in ['paradas_imprev_h', 'tipo_cod', 'producto', 'mes_num']):
    imprevistas_lookup = (
        df[df['paradas_imprev_h'] > 0]
        .groupby(['tipo_cod', 'producto', 'mes_num'])['paradas_imprev_h']
        .mean()
    )
    dump(imprevistas_lookup, MODELS_DIR / 'imprevistas_lookup.joblib')
    print('imprevistas_lookup saved:', len(imprevistas_lookup), 'entries')

print('Saved models to', MODELS_DIR)
print('Feature columns:', list(X.columns))
