#!/usr/bin/env bash
# P2 one run (PREREGISTRATION 2.1-2.3): clean restart of the fixed stack at the 1 s period
# (newstack.sh gen without PERIOD; ADRF NOT started), verify 46/46 UEs, iperf3 servers on MEC/MEC2
# (one port per UE), subscribe the 4 groups, play the schedule traces/schedules/<scn>-seed<seed>.json
# from T0 for DUR s with scripts/p2_ue_runner.py in gNB/gNB2, then fetch iperf3 JSON, NWDAF
# subscription log and UPF drop-log counts, export MongoDB nwdaf.upfTrafficData -> parquet
# (scripts/p2_export.py) and, only after the export round-trip check, delete this run's records.
# usage: p2_run.sh <S1|S2|S3|S4> <seed> <attempt> [dur_s]      (dur_s < 1800 only for the pilot)
# exit: 0 valid, 10 invalid (quality rule), 2 disk, 3 UEs, 4 transfer, 5 runner, 6 export
set -u
SCN=$1; SEED=$2; ATT=$3; DUR=${4:-1800}
R=$HOME/Research-data-collection; S=$R/scripts/testbed.sh; N=$R/scripts/newstack.sh
INFRA=$HOME/free5gc-NWDAF/5G_Infrastructure
vssh() { (cd "$INFRA/$1" && vagrant ssh -c "$2" 2>/dev/null); }
RUN=$SCN-seed$SEED; [ "$DUR" != 1800 ] && RUN=pilot-$RUN-d$DUR
D=$R/traces/$RUN/a$ATT; SCHED=$R/traces/schedules/$SCN-seed$SEED.json
[ -e "$D" ] && { echo "STOP: $D exists"; exit 4; }
mkdir -p "$D"; exec > >(tee -a "$D/run.log") 2>&1
avail=$(df --output=avail -BG ~ | tail -1 | tr -dc 0-9); echo "[$RUN a$ATT] $(date -u +%FT%TZ) disk avail ${avail}G"
[ "$avail" -lt 8 ] && { echo "STOP: disk < 8 GB (rule 8)"; exit 2; }

# --- clean restart (fresh subscriptions per run), 1 s period from config/5GC
$S stop-consumer >/dev/null; $S stop-ran >/dev/null
for v in gNB gNB2; do vssh $v 'pkill -f p2_ue_runner.py; pkill -x iperf3; pkill -x ping; true'; done
$N stop-nwdaf >/dev/null; $N stop-adrf >/dev/null; $N stop-core >/dev/null; $N stop-upf >/dev/null; sleep 2
$N start-upf; $N start-core; sleep 2; $N start-nwdaf; $S start-ran; sleep 30
for attempt in 1 2; do
  V=$(python3 "$R/scripts/p0_verify_ues.py" --out "$D/ue_check.csv"); echo "$V" | tail -2
  echo "$V" | grep -q "new UEs: 40  #1 pass 40  #2 pass 40" && echo "$V" | grep -q "existing UEs: 6  #1 pass 6  #2 pass 6" && break
  [ $attempt = 2 ] && { echo "STOP: #1/#2 not 46/46 after RAN restart"; exit 3; }
  echo "UE check failed, restarting RAN once"; $S stop-ran; $S start-ran; sleep 30
done

# --- iperf3 servers: port 5201+i for the i-th UE of the slice (SUPI order)
for p in MEC:192.168.200.25 MEC2:192.168.200.35; do
  vssh ${p%%:*} 'pkill -x iperf3; sleep 0.5; mkdir -p ~/p2srv && rm -f ~/p2srv/*; for port in $(seq 5201 5223); do (setsid nohup iperf3 -s -p $port -i 0 > ~/p2srv/$port.log 2>&1 < /dev/null &); done; sleep 1; echo "$(hostname) iperf3 servers: $(pgrep -c -x iperf3)"'
done

# --- per-gNB plans (UE IP from this run's ue_check.csv)
python3 - "$SCHED" "$D/ue_check.csv" "$D" "$DUR" <<'EOF'
import csv, json, sys
sched, uec, d, dur = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3], float(sys.argv[4])
ip = {r["supi"]: r["ue_ip"] for r in csv.DictReader(open(uec))}
srv = {1: "192.168.200.25", 2: "192.168.200.35"}; port = {1: 5201, 2: 5201}; plans = {1: [], 2: []}
for u in sched["ues"]:
    sl = u["slice"]
    segs = [[s, min(e, dur), r] for s, e, r in u["segments"] if s < dur]
    plans[sl].append(dict(supi=u["supi"], ue_ip=ip[u["supi"]], server=srv[sl], port=port[sl], segments=segs)); port[sl] += 1
for sl, vm in ((1, "gNB"), (2, "gNB2")):
    json.dump(dict(duration_s=dur, pkt_len=1200, scenario=sched["scenario"], seed=sched["seed"], ues=plans[sl]), open(f"{d}/plan-{vm}.json", "w"), indent=1)
    print(vm, "UEs", len(plans[sl]), "segments", sum(len(p["segments"]) for p in plans[sl]))
EOF

# --- subscribe, then start the runners at T0
SINCE=$(date -u +%FT%T.%3NZ); $S start-consumer >/dev/null; echo "[$RUN] subscribed at/after $SINCE"
T0=$(( $(date -u +%s) + 60 )); END=$(( T0 + ${DUR%.*} ))
for v in gNB gNB2; do
  cat "$R/scripts/p2_ue_runner.py" | vssh $v 'mkdir -p ~/p2 && rm -rf ~/p2/* && cat > ~/p2/p2_ue_runner.py'
  cat "$D/plan-$v.json" | vssh $v "cat > ~/p2/plan.json && (setsid nohup python3 ~/p2/p2_ue_runner.py --plan ~/p2/plan.json --t0 $T0 --out ~/p2/out > ~/p2/runner.out 2>&1 < /dev/null &); sleep 1; pgrep -f p2_ue_runner.py >/dev/null && echo \"\$(hostname) runner started\""
done
python3 -c "import json,sys; json.dump(dict(run='$RUN', scenario='$SCN', seed=$SEED, attempt=$ATT, duration_s=$DUR, since='$SINCE', t0=$T0, end=$END, schedule='traces/schedules/$SCN-seed$SEED.json'), open('$D/meta.json','w'), indent=1)"
echo "[$RUN] T0 $(date -u -d @$T0 +%FT%TZ)  end $(date -u -d @$END +%FT%TZ)"

# --- wait for the end, then for the runners to finish (last iperf3 result exchange)
while [ "$(date -u +%s)" -lt $(( END + 10 )) ]; do sleep 10; done
for v in gNB gNB2; do
  for i in $(seq 30); do vssh $v 'grep -q runner-done ~/p2/out/attempts.jsonl' && break; sleep 5; done
  vssh $v 'grep -q runner-done ~/p2/out/attempts.jsonl && echo "$(hostname) runner done" || { echo "$(hostname) runner NOT done"; pkill -f p2_ue_runner.py; pkill -x iperf3; }'
done
sleep 5
$S stop-consumer >/dev/null; echo "[$RUN] consumer unsubscribed $(date -u +%FT%TZ)"

# --- fetch iperf3 output (tgz in the VM, sha256 on both sides)
for v in gNB gNB2; do
  vssh $v 'cd ~/p2 && tar czf out.tgz out runner.out plan.json && sha256sum out.tgz | cut -c1-64' | tr -dc 0-9a-f > "$D/.sha"
  (cd "$INFRA/$v" && vagrant ssh -c "cat ~/p2/out.tgz" 2>/dev/null) > "$D/iperf3-$v.tgz"
  [ "$(sha256sum "$D/iperf3-$v.tgz" | cut -c1-64)" = "$(cat "$D/.sha")" ] || { echo "STOP: sha mismatch iperf3-$v.tgz"; exit 4; }
done; rm -f "$D/.sha"
for p in MEC MEC2; do vssh $p 'cd ~/p2srv && tar czf - *.log' > "$D/iperf3srv-$p.tgz"; done
vssh 5GC "grep -a 'SMF subscription created: supi=' ~/mve-bin/nwdaf.log" > "$D/nwdaf_subs.log"
for v in UPF-EES UPF-EES2; do
  vssh $v "echo \"\$(hostname) drop-logs since $SINCE: \$(sed 's/\x1b\[[0-9;]*m//g' ~/mve-upf-run.out | awk -v s=$SINCE '\$1>=s' | grep -ac 'dropping duplicate window')\""
done | tee "$D/upf_drops.txt"

# --- export + quality; delete this run's MongoDB records only after the round-trip check
python3 "$R/scripts/p2_export.py" --dir "$D"; rc=$?
[ $rc = 0 ] || [ $rc = 10 ] || { echo "STOP: export failed rc=$rc (MongoDB records kept)"; exit 6; }
echo "RUN-DONE $RUN a$ATT rc=$rc"; exit $rc
