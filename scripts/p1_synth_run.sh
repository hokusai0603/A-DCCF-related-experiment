#!/usr/bin/env bash
# P1 synthetic linearity check (decision 2026-11-10): sink on 5GC 192.168.107.5:18080 (not NWDAF),
# sender on UPF-EES replaying the real request header with N = 1..46 real items, tcpdump on 5GC.
# Inputs from p1_synth_prep.py (cost/synth/). Output: cost/synth/synth.pcap.gz, synth_send.jsonl.
# usage: p1_synth_run.sh [reps] [ns]
set -u
R=$HOME/Research-data-collection; INFRA=$HOME/free5gc-NWDAF/5G_Infrastructure; O=$R/cost/synth
REPS=${1:-30}; NS=${2:-1,2,3,4,6,8,12,16,23,32,46}
vssh() { (cd "$INFRA/$1" && vagrant ssh -c "$2" 2>/dev/null); }
avail=$(df --output=avail -BG ~ | tail -1 | tr -dc 0-9); [ "$avail" -lt 8 ] && { echo "STOP: disk < 8 GB"; exit 2; }
cat "$R/scripts/p1_synth.py" | vssh 5GC 'mkdir -p ~/p1synth && cat > ~/p1synth/p1_synth.py'
cat "$R/scripts/p1_synth.py" | vssh UPF-EES 'mkdir -p ~/p1synth && cat > ~/p1synth/p1_synth.py'
cat "$O/items.txt" | vssh UPF-EES 'cat > ~/p1synth/items.txt; wc -l < ~/p1synth/items.txt'
RESP=$(cat "$O/resp.hex"); HDR=$(cat "$O/hdr.hex")
vssh 5GC "cd ~/p1synth && rm -f synth.pcap*; (sudo setsid nohup tcpdump -i any -s 0 -U -w synth.pcap 'tcp port 18080' > tcpdump.log 2>&1 < /dev/null &); (setsid nohup python3 p1_synth.py recv --bind 192.168.107.5 --port 18080 --resp-hex $RESP > recv.log 2>&1 < /dev/null &); sleep 2; ss -ltn | grep -c 18080"
vssh UPF-EES "cd ~/p1synth && python3 p1_synth.py send --host 192.168.107.5 --port 18080 --hdr-hex $HDR --items items.txt --corr corr-1 --ns $NS --reps $REPS --gap 0.1 --log synth_send.jsonl && wc -l synth_send.jsonl"
sleep 2
vssh 5GC 'sudo pkill -INT -x tcpdump; pkill -f "p1_synth.py rec[v]"; sleep 1; tail -2 ~/p1synth/tcpdump.log; gzip -1 -f ~/p1synth/synth.pcap'
(cd "$INFRA/5GC" && vagrant ssh -c 'cat ~/p1synth/synth.pcap.gz' 2>/dev/null) > "$O/synth.pcap.gz"
(cd "$INFRA/UPF-EES" && vagrant ssh -c 'cat ~/p1synth/synth_send.jsonl' 2>/dev/null) > "$O/synth_send.jsonl"
vssh 5GC 'sha256sum ~/p1synth/synth.pcap.gz | cut -c1-64'; sha256sum "$O/synth.pcap.gz" | cut -c1-64
echo SYNTH-DONE
