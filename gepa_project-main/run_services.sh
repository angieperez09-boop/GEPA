#!/usr/bin/env bash
set -euo pipefail

# Run both FastAPI (uvicorn) and Streamlit for the project in background
# Usage: ./run_services.sh

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
ACTIVATE="$VENV/bin/activate"

if [ -f "$ACTIVATE" ]; then
  # shellcheck disable=SC1090
  source "$ACTIVATE"
else
  echo "Virtualenv activate not found at $ACTIVATE"
  echo "Please create a virtualenv at .venv and install requirements."
  exit 1
fi

LOGS="$ROOT/logs"
mkdir -p "$LOGS"

echo "Stopping any processes on ports 8000 and 8501..."
set +e
PIDS_8000=$(lsof -tiTCP:8000 -sTCP:LISTEN -n -P || true)
if [ -n "$PIDS_8000" ]; then
  echo "Killing PID(s) on 8000: $PIDS_8000"
  kill -9 $PIDS_8000 || true
fi
PIDS_8501=$(lsof -tiTCP:8501 -sTCP:LISTEN -n -P || true)
if [ -n "$PIDS_8501" ]; then
  echo "Killing PID(s) on 8501: $PIDS_8501"
  kill -9 $PIDS_8501 || true
fi
set -e

echo "Starting Uvicorn (FastAPI) on port 8000..."
nohup uvicorn controllers.api:app --reload --port 8000 > "$LOGS/uvicorn.log" 2>&1 &
echo $! > "$ROOT/uvicorn.pid"

sleep 1

echo "Starting Streamlit on port 8501..."
nohup streamlit run views/streamlit_app.py --server.port 8501 > "$LOGS/streamlit.log" 2>&1 &
echo $! > "$ROOT/streamlit.pid"

echo "Started services."
echo "Uvicorn PID: $(cat "$ROOT/uvicorn.pid")"
echo "Streamlit PID: $(cat "$ROOT/streamlit.pid")"
echo "Uvicorn URL: http://127.0.0.1:8000"
echo "Streamlit URL: http://127.0.0.1:8501"
echo "Logs: $LOGS"

exit 0
