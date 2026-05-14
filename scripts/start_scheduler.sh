#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PID_FILE="run/grid_signal.pid"
LOG_FILE="logs/grid_signal.log"
OUT_FILE="logs/grid_signal.out"

mkdir -p run logs

if [[ -f "${PID_FILE}" ]]; then
  existing_pid="$(cat "${PID_FILE}")"
  if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "NeuralGridSignal scheduler is already running: pid=${existing_pid}"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

if command -v setsid >/dev/null 2>&1; then
  nohup setsid python3 -m neural_grid_signal --schedule --log-file "${LOG_FILE}" "$@" >> "${OUT_FILE}" 2>&1 &
else
  nohup python3 -m neural_grid_signal --schedule --log-file "${LOG_FILE}" "$@" >> "${OUT_FILE}" 2>&1 &
fi
pid="$!"
echo "${pid}" > "${PID_FILE}"

echo "NeuralGridSignal scheduler started: pid=${pid}"
echo "log=${LOG_FILE}"
echo "stdout=${OUT_FILE}"
