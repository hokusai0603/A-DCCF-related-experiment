#!/usr/bin/env bash
# P1 matrix: repPeriod {1,5,10,30} s x subscribed UEs {6,26,46}, 600 s per cell (user decision 2026-11-10).
# Period goes into the DERIVED configs only (PERIOD=<s> newstack.sh gen). Stops at the first failing cell.
# usage: p1_matrix.sh [periods...]     (default: 1 5 10 30); NUES env overrides "6 26 46"
set -u
R=$HOME/Research-data-collection; N=$R/scripts/newstack.sh
PERIODS=${*:-1 5 10 30}; NUES=${NUES:-6 26 46}
for P in $PERIODS; do
  PERIOD=$P $N gen && $N deploy >/dev/null || { echo "STOP: gen/deploy failed for period $P"; exit 1; }
  grep -hE "^  urrPeriod:|^      samplingInterval:" $R/newstack/smfcfg.yaml $R/newstack/nwdafcfg.yaml
  for U in $NUES; do
    T=p${P}-u${U}
    if [ -f "$R/cost/raw/$T.meta.json" ]; then echo "skip $T (done)"; continue; fi
    echo "=== CELL $T $(date -u +%FT%TZ)"
    "$R/scripts/p1_cell.sh" "$P" "$U" "$T" || { echo "MATRIX-STOP at $T"; exit 1; }
  done
done
echo "MATRIX-DONE"
