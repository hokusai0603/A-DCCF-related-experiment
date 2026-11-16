#!/usr/bin/env bash
# One P0 4.5 #4 run at a given reporting period: set period in all configs, restart the stack,
# re-verify UEs (#1/#2), subscribe (4 groups), 5 pps ping per UE, analyse 10 min (#3/#4),
# count UPF "dropping duplicate window" logs. VMs must already be booted (testbed.sh boot).
# usage: p0_period_run.sh <period_s> <tag>
set -u
P=$1; TAG=$2
R=$HOME/Research-data-collection; S=$R/scripts/testbed.sh; INFRA=$HOME/free5gc-NWDAF/5G_Infrastructure
# STACK=new (default): fixed UPF/SMF/NWDAF via newstack.sh; STACK=old: the May/Mar/Apr binaries
STACK=${STACK:-new}; N=$R/scripts/newstack.sh
if [ "$STACK" = new ]; then C=$N; NLOG="~/mve-bin/nwdaf.log"; ULOG="~/mve-upf-run.out"; else C=$S; NLOG="~/nwdaf.log"; ULOG="~/upf-run.out"; fi
OUT=$R/p0/run-$TAG; mkdir -p "$OUT"
avail=$(df --output=avail -BG ~ | tail -1 | tr -dc 0-9); echo "disk avail ${avail}G"
[ "$avail" -lt 8 ] && { echo "STOP: disk < 8 GB (rule 8)"; exit 2; }
"$R/scripts/set_period.sh" "$P"
[ "$STACK" = new ] && { $N gen >/dev/null; $N deploy >/dev/null; }
$S stop-consumer; $S stop-ran; $C stop-nwdaf; $C stop-core; $C stop-upf; sleep 2
$C start-upf; $C start-core; sleep 3; $C start-nwdaf; $S start-ran; sleep 30
for attempt in 1 2; do
  V=$(python3 "$R/scripts/p0_verify_ues.py" --out "$R/p0/ue_check.csv"); echo "$V" | tail -3
  echo "$V" | grep -q "new UEs: 40  #1 pass 40  #2 pass 40" && echo "$V" | grep -q "existing UEs: 6  #1 pass 6  #2 pass 6" && break
  [ $attempt = 2 ] && { echo "STOP: #1/#2 not 46/46 after RAN restart"; exit 3; }
  echo "UE check failed, restarting RAN once"; $S stop-ran; $S start-ran; sleep 30
done
cp "$R/p0/ue_check.csv" "$OUT/"
SINCE=$(date -u +%FT%TZ); $S start-consumer >/dev/null; echo "subscribed at/after $SINCE"
$S start-ping 720
START=$(date -u -d "+40 sec" +%FT%TZ); END=$(date -u -d "+640 sec" +%FT%TZ)
echo "window $START .. $END"
while [ "$(date -u +%s)" -lt $(( $(date -u -d "$END" +%s) + 15 )) ]; do sleep 10; done
python3 "$R/scripts/p0_check_collection.py" --period "$P" --nwdaf-log "$NLOG" --upf-log "$ULOG" --since "$SINCE" --start "$START" --end "$END" --out "$OUT/collection_check.csv" | tee "$OUT/summary.txt"
s=$(date -u -d "$START" +%H:%M); for v in UPF-EES UPF-EES2; do
  (cd "$INFRA/$v" && vagrant ssh -c "echo \"\$(hostname) drop-logs since $SINCE: \$(sed 's/\x1b\[[0-9;]*m//g' $ULOG | awk -v s=$SINCE '\$1>=s' | grep -ac 'dropping duplicate window')\"" 2>/dev/null)
done | tee -a "$OUT/summary.txt"
mongosh --quiet mongodb://127.0.0.1/free5gc --eval "db['nwdaf.upfTrafficData'].aggregate([{\$match:{timestamp:{\$gte:new Date('$START'),\$lt:new Date('$END')}}},{\$group:{_id:{\$ifNull:['\$ulNbOfPackets',0]},n:{\$sum:1}}},{\$sort:{_id:1}}]).forEach(d=>print('ulPkts/window',d._id,'count',d.n))" | tee -a "$OUT/summary.txt"
echo "RUN-DONE $TAG"
