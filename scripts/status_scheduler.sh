#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PID_FILE="run/grid_signal.pid"
LOG_FILE="logs/grid_signal.log"
OUT_FILE="logs/grid_signal.out"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "NeuralGridSignal scheduler: stopped"
  exit 0
fi

pid="$(cat "${PID_FILE}")"
if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
  echo "NeuralGridSignal scheduler: running pid=${pid}"
else
  echo "NeuralGridSignal scheduler: stopped stale_pid=${pid}"
  exit 0
fi

echo "log=${LOG_FILE}"
echo "stdout=${OUT_FILE}"

if [[ -f "${LOG_FILE}" ]]; then
  echo "--- recent log ---"
  tail -n 20 "${LOG_FILE}"
elif [[ -f "${OUT_FILE}" ]]; then
  echo "--- recent stdout ---"
  tail -n 20 "${OUT_FILE}"
fi
