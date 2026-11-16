#!/usr/bin/env bash
# P2 all runs: seeds 1,2,3 x scenarios S1..S4 (seed-major, so time-of-day drift is not confounded
# with the scenario). Per run: attempt 1; if the quality rule (PREREGISTRATION 2.3) fails, up to 2
# re-runs; if all 3 fail, the LAST attempt is kept as the run's trace and flagged invalid.
# Any other failure (disk < 8 GB, UEs, transfer, runner, export) stops everything (exit != 0).
# Resumable: runs with traces/<run>/FINAL.json are skipped; attempt numbers continue after the
# existing a<N> directories (move an aborted attempt away, e.g. to aborted-a<N>, before resuming).
# usage: setsid nohup scripts/p2_all.sh > traces/p2_all.log 2>&1 < /dev/null &
set -u
R=$HOME/Research-data-collection
grep -qE "^  urrPeriod: 1 " $R/newstack/smfcfg.yaml && grep -qE "^      samplingInterval: 1 " $R/newstack/nwdafcfg.yaml \
  || { echo "ALL-STOP: derived configs are not at 1 s (run newstack.sh gen && deploy)"; exit 1; }
for SEED in 1 2 3; do
  for SCN in S1 S2 S3 S4; do
    RUN=$SCN-seed$SEED; RD=$R/traces/$RUN
    [ -f "$RD/FINAL.json" ] && { echo "skip $RUN (final)"; continue; }
    final=""
    while :; do
      n=$(ls -d "$RD"/a[0-9]* 2>/dev/null | wc -l); ATT=$(( n + 1 ))
      if [ "$n" -ge 3 ]; then final=$n; valid=false; break; fi
      echo "=== $RUN attempt $ATT $(date -u +%FT%TZ)"
      "$R/scripts/p2_run.sh" "$SCN" "$SEED" "$ATT"; rc=$?
      if [ $rc = 0 ]; then final=$ATT; valid=true; break; fi
      if [ $rc != 10 ]; then echo "ALL-STOP at $RUN a$ATT rc=$rc $(date -u +%FT%TZ)"; exit $rc; fi
      echo "$RUN a$ATT invalid (quality rule), re-running"
    done
    python3 -c "import json; json.dump(dict(run='$RUN', final_attempt=$final, valid=$( [ $valid = true ] && echo True || echo False ), attempts=$(ls -d "$RD"/a[0-9]* | wc -l), rule='PREREGISTRATION 2.3: up to 2 re-runs; if still invalid the last attempt is kept and flagged'), open('$RD/FINAL.json','w'), indent=1)"
    echo "FINAL $RUN a$final valid=$valid"
  done
done
echo "ALL-DONE $(date -u +%FT%TZ)"
