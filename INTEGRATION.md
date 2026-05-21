# Integración: modelos XGBoost /RandomForest con aplicativo web

## Resumen
- Objetivo: Permitir que un usuario suba dos archivos Excel (uno por planta: "TREN MORGAN" y "TREN 450") con columnas `material`, `VENTA DIRECTA` (t), `MATERIA PRIMA` (t) y `STOCK` (t) y devolver, para cada planta, una tabla de programación de fabricación con las mismas columnas visibles en las imágenes de referencia más columnas de scheduling (inicio, fin, product. t/h, tiempo lam., mtto, setups, índice de utilización, etc.).
- Enfoque: Exponer una API REST (FastAPI) que reciba los Excel, aplique el preprocesado coherente con `notebooks/laminacion_pipeline.ipynb`, ejecute inferencia con los modelos (XGBoost y RandomForest) y una lógica de scheduling para producir la tabla final y permitir su descarga.

## Arquitectura propuesta
- Frontend: aplicación ligera (Streamlit o React) para subir archivos, seleccionar mes/año y lanzar la generación.
- Backend: FastAPI que:
  - recibe archivos Excel (multipart/form-data),
  - valida y transforma con `pandas` (usar `engine='openpyxl'` para `.xlsx`),
  - carga modelos desde `models/` y encoders desde `models/encoders.joblib`,
  - ejecuta inferencia y el scheduler, y
  - devuelve JSON con un preview y un link/archivo Excel con la tabla completa.
- Artefactos:
  - `models/rf.joblib`
  - `models/xgb.joblib` (o `models/xgb.model` según método de guardado)
  - `models/encoders.joblib`
  - `outputs/` para tablas generadas

## Formato de entrada (Excel)
- Requisitos de la hoja:
  - Columnas (case-insensitive): `material`, `VENTA DIRECTA`, `MATERIA PRIMA`, `STOCK`.
  - Valores numéricos en toneladas.
  - Un archivo = una planta (o permitir múltiples hojas y procesar la primera).
- Validaciones a realizar al recibir:
  - Presencia de columnas obligatorias.
  - Tipos numéricos y no-negatividad donde aplique.
  - Mapeo de `material` a `CODIGO` mediante un diccionario o fichero maestro.

## Preprocesado y features
- Reusar las funciones de `notebooks/laminacion_pipeline.ipynb`: `leer_hoja()`, `leer_params_hoja()` y `_find_special_rows()` para asegurar consistencia.
- Transformaciones mínimas:
  - Normalizar nombres (strip, upper/lower según convenga).
  - Calcular `cantidad_t`, `stock_t`, `venta_directa_t`, `materia_prima_t`.
  - Añadir columnas temporales: `mes`, `anio`.
  - Aplicar label encoding para `material` con encoder guardado.
- Guardar el pipeline de transformación (scaler/encoder) junto a los modelos en `models/`.

## Modelos y formato de salida de inferencia
- Modelos esperados:
  - RandomForest (`rf.joblib`) — para predicción de tiempos o tasas.
  - XGBoost (`xgb.joblib` o `xgb.model`) — para predicción de `product_t_h`, `tiempo_lam_h`, `mtto_h`, `setup_h`, `util_pct`.
- Por fila, los modelos deben devolver un diccionario similar a:
  ```json
  {"product_t_h": 68.39, "tiempo_lam_h": 17.85, "mtto_h": 4.0, "setup_h": 0.5, "util_pct": 73.3}
  ```
- Estrategia de combinación: promediar predicciones de RF y XGB o usar un meta-modelo de stacking si existe.

## Lógica de scheduling (algoritmo básico)
- Parámetros de entrada:
  - `horas_por_dia` (p. ej. 24 o 16 si hay turnos), `turnos`, calendario de días laborables.
- Pasos:
  1. Ordenar materiales por prioridad (por ejemplo `VENTA DIRECTA` descendente o por regla de negocio).
  2. Para cada material:
     - `horas_produccion = cantidad_t / product_t_h`
     - `horas_totales = horas_produccion + setup_h + mtto_h` (según reglas)
     - Asignar `inicio` = próximo slot disponible; respetar ventanas de mtto y no solapar.
     - Calcular `fin` = `inicio` + `horas_totales`.
  3. Calcular `indice_utilizacion = horas_produccion / (horas_disponibles_periodo) * 100`.
- Fechas: usar timestamps `YYYY-MM-DD HH:MM` y ajustar por turnos/fin de semana si aplica.
- Mejoras posibles: usar solucionadores CP/ILP o heurísticas para minimizar cambios de setup o cumplir restricciones de entrega.

## Formato de salida (tablas tipo imágenes)
- Columnas sugeridas (orden similar a las imágenes):
  - `t/dia` (si aplica), `CODIGO`, `MATERIAL`, `Cantidad (t) Programada`, `Mtto pro. (h)`, `Inicio`, `Fin`, `Product. (t/h)`, `Tiempo lam. (h)`, `Índice de utilización (%)`, `Paradas por setups (h)`.
- Exportación: `DataFrame.to_excel(...)` y `to_csv()`.
- Nombres de salida: `outputs/TREN_MORGAN_schedule_{YYYY-MM}.xlsx` y `outputs/TREN_450_schedule_{YYYY-MM}.xlsx`.

## API mínima (FastAPI)
- `POST /predict/schedule` — recibe `plant_id`, `month`, `year`, y archivo Excel (o múltiples archivos). Devuelve JSON con `preview` y `download_url`.
- `GET /models/info` — devuelve `model_name`, `version`, `features`.

### Ejemplo curl
```bash
curl -X POST "http://localhost:8000/predict/schedule" \
  -F "plant_id=morgan" \
  -F "month=1" -F "year=2026" \
  -F "file=@/path/to/TREN_MORGAN_input.xlsx"
```

### Snippet de endpoint (pseudocódigo Python)
```python
from fastapi import FastAPI, File, UploadFile, Form
import pandas as pd
from joblib import load

app = FastAPI()
rf = load("models/rf.joblib")
xgb = load("models/xgb.joblib")

@app.post("/predict/schedule")
async def schedule(plant_id: str = Form(...), month: int = Form(...), year: int = Form(...), file: UploadFile = File(...)):
    df = pd.read_excel(file.file, engine="openpyxl")
    validate(df)
    X = featurize(df, month, year)
    preds_rf = rf.predict(X)
    preds_xgb = xgb.predict(X)
    preds = combine(preds_rf, preds_xgb)
    schedule_df = run_scheduler(df, preds, month, year)
    out_path = f"outputs/{plant_id}_schedule_{year}-{month:02d}.xlsx"
    schedule_df.to_excel(out_path, index=False)
    return {"status":"ok", "download": out_path, "preview": schedule_df.head(10).to_dict(orient="records")}
```

## Frontend UX
- Opción rápida: Streamlit con dos campos de `file_uploader` (uno por planta), selección de mes/año y botón `Generar`.
- Mostrar preview, permitir descarga del Excel resultante.

## Dependencias recomendadas
- fastapi, uvicorn, pandas, openpyxl, joblib, scikit-learn, xgboost, streamlit (opcional frontend)

## Pruebas y validación
- Unit tests para `featurize()`, `validate()` y `run_scheduler()`.
- E2E: subir un Excel de ejemplo y comprobar que la salida coincide con la tabla objetivo (imágenes).

## Despliegue
- Local: `uvicorn app:app --reload --port 8000`.
- Docker: crear `Dockerfile` que instale dependencias y copie `models/` y `outputs/`.
- Producción: usar Gunicorn/Uvicorn workers, montar volumen para outputs o usar S3.

## Checklist rápida
- [ ] Guardar modelos y encoders en `models/` con `meta.json`.
- [ ] Implementar `app/utils/parsers.py` a partir del notebook.
- [ ] Implementar `app/scheduler.py` con la lógica descrita.
- [ ] Endpoint `POST /predict/schedule` y tests E2E.
- [ ] Prototipo frontend (Streamlit o React).

## Siguientes pasos sugeridos
1. Portar y reutilizar el parsing del notebook en `app/utils/parsers.py`.
2. Implementar el endpoint mínimo y probar con `data/raw/programa_laminacion_2025.xlsx`.
3. Crear un prototipo Streamlit para subir los Excel y descargar resultados.

---
Guía generada para integrar tus modelos con un aplicativo web; si quieres, puedo crear ahora el esqueleto de la API (`app/`) y el prototipo Streamlit.
