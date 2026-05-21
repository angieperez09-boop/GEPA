# PROJECT-GEPA

Pipeline de datos (estilo *lakehouse*) organizado por capas **raw → bronze → silver → gold**.

> Nota: Este repo ignora la carpeta `data/` completa por defecto (ver `.gitignore`). Si quieres versionar muestras pequeñas, se recomienda almacenarlas en otra ruta (por ejemplo `sample_data/`) o usar una herramienta tipo DVC.

## Descripción del proyecto

Este proyecto implementa un **pipeline de transformación de datos** para el proceso de **laminación**, llevando datasets desde una capa de aterrizaje (**raw**) hasta conjuntos de datos listos para análisis/consumo (**gold**).

En la práctica, el notebook principal:
- **Lee** archivos fuente desde `data/raw/`.
- **Estandariza y depura** en `data/bronze/` (formatos, nulos, nombres de columnas, calidad básica).
- **Conforma** datos en `data/silver/` (tipos finales, uniones, reglas de negocio).
- **Publica** salidas en `data/gold/` (tablas/agregados listos para BI, reporting o análisis).

El punto de entrada actual es `notebooks/laminacion_pipeline.ipynb`.

## Estructura del proyecto (MVC)

```
PROJECT-GEPA/
  controllers/                # Capa de control: API + lógica de negocio
    api.py                    # FastAPI app (POST /predict/schedule)
    scheduler.py              # Ensamblado del cronograma
    optimizer.py              # Reordenamiento óptimo por familias (Held-Karp)
    config.py
    utils/parsers.py
  views/                      # Capa de presentación: UI Streamlit
    streamlit_app.py
    components/
  models/                     # Capa de datos: artefactos + datasets + ETL + entrenamiento
    artifacts/                # *.joblib (xgb, rf, encoders, lookups)
    data/
      raw/  bronze/  silver/  gold/
    etl/                      # notebooks de transformación raw→gold
    training/                 # notebooks y scripts de entrenamiento ML
  outputs/                    # Cronogramas generados (.xlsx)
```

### Arranque

```zsh
# Backend
.venv/bin/python3 -m uvicorn controllers.api:app --port 8000

# Frontend
.venv/bin/python3 -m streamlit run views/streamlit_app.py

# O ambos a la vez
./run_services.sh
```

### Capas (convención)
- **raw**: datos “tal cual” llegan (sin transformación o mínima).
- **bronze**: limpieza ligera / estandarización básica.
- **silver**: datos conformados (tipos, joins, reglas de negocio).
- **gold**: agregados/listos para consumo (reporting/BI/ML).

## Cómo ejecutar

### Opción A: desde VS Code (recomendado)
1. Abre `notebooks/laminacion_pipeline.ipynb`.
2. Selecciona un *kernel* de Python (idealmente uno dentro de `.venv/`).
3. Ejecuta las celdas en orden.

### Opción B: crear un entorno virtual
Si aún no tienes entorno:

```zsh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

Luego instala dependencias según tu caso:
- Si el proyecto usa `requirements.txt`, instálalo.
- Si usa `pyproject.toml`/Poetry, usa Poetry.
- Si usa notebooks “sueltos”, instala lo necesario (pandas, numpy, etc.) conforme aparezcan imports.

> Si quieres, puedo detectar imports del notebook y generarte un `requirements.txt` mínimo reproducible.

## Datos y versionado

- `data/` está ignorado para evitar subir datasets grandes a Git.
- Sugerencias para trabajar con datos:
  - Mantener **esquemas** y **contratos** (nombres de columnas, tipos) documentados.
  - Guardar resultados importantes como artefactos (por ejemplo en `data/gold/`), pero fuera de git.
  - Para colaboración con datos: usar DVC/LakeFS o buckets (S3/GCS/Azure).

## Notas
- macOS y archivos de editor (`.DS_Store`, `.vscode/`, `.idea/`) se ignoran por defecto.
- Los checkpoints de Jupyter (`.ipynb_checkpoints/`) también.
