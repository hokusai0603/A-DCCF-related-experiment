#!/usr/bin/env bash
# Measure each MVE VM's clock offset vs the host (待確認 #5).
# One persistent SSH connection per VM (ControlMaster) so the bracketing round trip is small;
# offset = vm_time - midpoint(host_before, host_after), error bound = half the round trip.
# usage: clock_offsets.sh [samples]
set -u
INFRA=${INFRA:-$HOME/free5gc-NWDAF/5G_Infrastructure}
N=${1:-5}
TMP=$(mktemp -d)
trap 'for c in "$TMP"/*.cfg; do ssh -F "$c" -O exit default 2>/dev/null; done; rm -rf "$TMP"' EXIT
printf "%-9s %12s %10s %s\n" VM offset_ms rtt_ms timesync
for vm in 5GC UPF-EES UPF-EES2 gNB gNB2 MEC MEC2; do
  cfg=$TMP/$vm.cfg
  (cd "$INFRA/$vm" && vagrant ssh-config > "$cfg" 2>/dev/null) || continue
  printf '  ControlMaster auto\n  ControlPath %s/%s.sock\n  ControlPersist 60\n' "$TMP" "$vm" >> "$cfg"
  ssh -F "$cfg" default true 2>/dev/null
  best=""
  for _ in $(seq "$N"); do
    t0=$(date +%s.%N); tv=$(ssh -F "$cfg" default 'date +%s.%N' 2>/dev/null); t1=$(date +%s.%N)
    line=$(awk -v a="$t0" -v b="$t1" -v v="$tv" 'BEGIN{printf "%.1f %.1f", (v-(a+b)/2)*1000, (b-a)*1000}')
    rtt=${line#* }
    if [ -z "$best" ] || awk -v r="$rtt" -v b="${best#* }" 'BEGIN{exit !(r<b)}'; then best=$line; fi
  done
  ts=$(ssh -F "$cfg" default 'echo "ntp=$(timedatectl show -p NTPSynchronized --value 2>/dev/null) timesyncd=$(systemctl is-active systemd-timesyncd 2>/dev/null) chrony=$(systemctl is-active chrony 2>/dev/null) vboxservice=$(systemctl is-active vboxadd-service virtualbox-guest-utils 2>/dev/null | tr "\n" "/")"' 2>/dev/null)
  printf "%-9s %12s %10s %s\n" "$vm" "${best% *}" "${best#* }" "$ts"
done
echo "host: ntp=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"
