import warnings
warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
from joblib import dump

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / 'models' / 'data' / 'gold' / 'laminacion.parquet'
MODELS_DIR = ROOT / 'models' / 'artifacts'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

print('Loading data:', GOLD)
df = pd.read_parquet(GOLD)
print('Data shape:', df.shape)

# determine target
if 'productividad_t_h' in df.columns:
    y = df['productividad_t_h']
elif 'tiempo_lam_h' in df.columns and 'cantidad_t' in df.columns:
    y = df['cantidad_t'] / df['tiempo_lam_h']
else:
    raise SystemExit('No valid target found in parquet')

# build minimal features
features = []
if 'producto' in df.columns:
    le = LabelEncoder()
    df['producto_cod'] = le.fit_transform(df['producto'].astype(str))
    features.append('producto_cod')
else:
    le = None

for f in ['cantidad_t', 'mes_num', 'anio']:
    if f in df.columns:
        features.append(f)

if len(features) == 0:
    raise SystemExit('No minimal features found in parquet')

X = df[features].copy()

# simple fill NA
X = X.fillna(0)

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print('Training XGBoost minimal...')
xgb_model = xgb.XGBRegressor(n_estimators=200, max_depth=6, learning_rate=0.05, n_jobs=-1, verbosity=0)
xgb_model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
print('XGBoost trained')

print('Training RandomForest minimal...')
rf_model = RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=42, n_jobs=-1)
rf_model.fit(X_train, y_train)
print('RandomForest trained')

# Save models (overwrite existing standard names so API picks them up)
dump(xgb_model, MODELS_DIR / 'xgb.joblib')
dump(rf_model, MODELS_DIR / 'rf.joblib')
if le is not None:
    dump({'producto': le}, MODELS_DIR / 'encoders.joblib')

print('Saved minimal models to', MODELS_DIR)
