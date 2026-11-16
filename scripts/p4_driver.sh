#!/usr/bin/env bash
# P4 driver: run the full sim/run_grid sweep (default options, PREREGISTRATION + section 7),
# resume on failure (run_grid caches every task), then run the independent cross-check.
# Meant to run detached so it survives the Claude session:
#   cd ~/Research-data-collection && mkdir -p results && \
#   setsid nohup scripts/p4_driver.sh > results/driver.log 2>&1 < /dev/null &
# Status: results/STATUS  (RUNNING attempt N | DONE | FAILED <reason>)
set -u
cd "$(dirname "$0")/.." || exit 1
PY=${PY:-/home/king25158986/daisy-env/bin/python3}
OUT=results
MAX_ATTEMPTS=3
mkdir -p "$OUT"
ts() { date '+%Y-%m-%dT%H:%M:%S'; }
echo "$$" > "$OUT/driver.pid"

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  avail=$(df --output=avail -k ~ | tail -1)
  if [ "$avail" -lt $((8 * 1024 * 1024)) ]; then
    echo "FAILED disk below 8 GB ($avail kB)" > "$OUT/STATUS"; echo "$(ts) disk low, stop"; exit 1
  fi
  echo "RUNNING attempt $attempt" > "$OUT/STATUS"
  echo "$(ts) run_grid attempt $attempt start"
  "$PY" -m sim.run_grid --out "$OUT" >> "$OUT/run_grid.log" 2>&1 < /dev/null
  rc=$?
  echo "$(ts) run_grid attempt $attempt exit $rc"
  if [ $rc -eq 0 ] && grep -q 'run_grid: DONE' "$OUT/run_grid.log"; then
    echo "RUNNING check_outputs" > "$OUT/STATUS"
    "$PY" -m sim.check_outputs "$OUT" > "$OUT/check_outputs.log" 2>&1 < /dev/null
    crc=$?
    echo "$(ts) check_outputs exit $crc"
    if [ $crc -eq 0 ]; then echo "DONE" > "$OUT/STATUS"; else echo "FAILED check_outputs exit $crc" > "$OUT/STATUS"; fi
    exit $crc
  fi
  sleep 10
done
echo "FAILED run_grid after $MAX_ATTEMPTS attempts" > "$OUT/STATUS"
exit 1
