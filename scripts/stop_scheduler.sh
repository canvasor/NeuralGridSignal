#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PID_FILE="run/grid_signal.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "NeuralGridSignal scheduler is not running: pidfile missing"
  exit 0
fi

pid="$(cat "${PID_FILE}")"
if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
  rm -f "${PID_FILE}"
  echo "NeuralGridSignal scheduler is not running: stale pidfile removed"
  exit 0
fi

kill "${pid}"

for _ in {1..10}; do
  if ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${PID_FILE}"
    echo "NeuralGridSignal scheduler stopped: pid=${pid}"
    exit 0
  fi
  sleep 1
done

echo "NeuralGridSignal scheduler still running after SIGTERM: pid=${pid}"
echo "Use 'kill ${pid}' or inspect logs before forcing termination."
exit 1
