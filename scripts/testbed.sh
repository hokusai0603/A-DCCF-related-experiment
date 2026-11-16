#!/usr/bin/env bash
# Start/stop the MVE testbed services inside already-booted VMs.
# VMs must be booted with `vagrant up` in their own directory (EXECUTION_GUIDE rule 3)
# and have had /vagrant/setup.sh run once after boot.
# Never touches I-UPF / I-UPF2 (rule 2).
#
# usage: testbed.sh mount                 # fix vboxsf mounts in 5GC (mount.vboxsf cwd quirk)
#        testbed.sh start-upf | start-core | start-nwdaf | start-ran
#        testbed.sh stop-ran | stop-nwdaf | stop-core | stop-upf
#        testbed.sh status
set -uo pipefail
INFRA=${INFRA:-$HOME/free5gc-NWDAF/5G_Infrastructure}

vssh() { (cd "$INFRA/$1" && vagrant ssh -c "$2" 2>/dev/null); }
CF=${CONSUMER:-consumer-mve.json}

case "${1:-}" in
boot)
  # vagrant up (rule 3) the 7 MVE VMs one at a time, run setup.sh, then the runtime fixes.
  for v in 5GC UPF-EES UPF-EES2 MEC MEC2 gNB gNB2; do
    (cd "$INFRA/$v" && timeout 300 vagrant up --no-provision >/dev/null 2>&1; echo "$v: $(vagrant status 2>/dev/null | sed -n 3p | awk '{print $2}')")
  done
  for v in 5GC UPF-EES UPF-EES2 MEC MEC2 gNB gNB2; do vssh $v '/vagrant/setup.sh >/dev/null 2>&1 || true'; done
  "$0" mount; "$0" dn-routes; "$0" ntp
  ;;
halt)
  for v in gNB gNB2 MEC MEC2 5GC UPF-EES UPF-EES2; do
    (cd "$INFRA/$v" && timeout 150 vagrant halt >/dev/null 2>&1; echo "$v: $(vagrant status 2>/dev/null | sed -n 3p | awk '{print $2}')")
  done
  ;;
mount)
  # Guest mount.vboxsf (GA 6.1.50) resolves the share name against the cwd, so
  # `mount -t vboxsf adrf /adrf` fails when ~/adrf exists. Mount from an empty dir.
  vssh 5GC 'mkdir -p /tmp/vbsf_empty && cd /tmp/vbsf_empty && for p in vagrant:/vagrant config:/config NWDAF:/NWDAF daisy:/daisy adrf:/adrf; do n=${p%%:*}; d=${p#*:}; sudo mkdir -p $d; mountpoint -q $d || sudo mount -t vboxsf -o uid=1000,gid=1000,_netdev $n $d; done; mount | grep -c vboxsf'
  # MongoDB runs on the host (140.113.110.82). 5GC/setup.sh moves the default route to
  # 192.168.105.1, which cannot reach the host ("no route to host"); reach it via VBox NAT.
  vssh 5GC 'sudo ip route replace 140.113.110.82/32 via 10.0.2.2 dev enp0s3; timeout 3 bash -c "</dev/tcp/140.113.110.82/27017" && echo mongo reachable'
  ;;
dn-routes)
  # UE -> DN path without I-UPF/I-UPF2. MEC/MEC2 setup.sh route the UE pools via
  # 192.168.200.20/.31 (I-UPF/I-UPF2 N6, must stay off), and UPF-EES/UPF-EES2 egress
  # (enp0s10, 192.168.106.10/109.111) points at gateways that do not exist.
  # All VM NICs are bridged onto the same eno1 L2 segment, so on-link host routes work;
  # UPF-EES*/setup.sh already MASQUERADEs UE traffic out of enp0s10. Runtime only.
  vssh UPF-EES  'sudo ip route replace 192.168.200.25/32 dev enp0s10 && echo "$(hostname): 200.25 on-link"'
  vssh MEC      'sudo ip route replace 192.168.106.10/32 dev enp0s8 && echo "$(hostname): 106.10 on-link"'
  vssh UPF-EES2 'sudo ip route replace 192.168.200.35/32 dev enp0s10 && echo "$(hostname): 200.35 on-link"'
  vssh MEC2     'sudo ip route replace 192.168.109.111/32 dev enp0s8 && echo "$(hostname): 109.111 on-link"'
  ;;
ntp)
  # 待確認 #5: in 5GC/gNB/gNB2/MEC/MEC2 NTP is off (virtualbox-guest-utils.service conflicts with
  # systemd-timesyncd and its own sync left the clocks ~0.4-1.5 s behind). Start timesyncd
  # (this stops VBoxService; vboxsf mounts stay) and reach ntp.ubuntu.com via the VBox NAT,
  # because setup.sh points the default route at gateways that do not exist. UPF-EES* already sync.
  for v in 5GC gNB gNB2 MEC MEC2; do
    vssh $v 'for ip in $(getent ahostsv4 ntp.ubuntu.com | awk "{print \$1}" | sort -u); do sudo ip route replace $ip/32 via 10.0.2.2 dev enp0s3; done; sudo timedatectl set-ntp true; sudo systemctl restart systemd-timesyncd; for i in $(seq 20); do [ "$(timedatectl show -p NTPSynchronized --value)" = yes ] && break; sleep 1; done; echo "$(hostname): NTPSynchronized=$(timedatectl show -p NTPSynchronized --value)"'
  done
  ;;
start-upf)
  for v in UPF-EES UPF-EES2; do
    # setup.sh normally copies these; re-copy so config/5GC/UPF-EES*.yaml edits take effect
    vssh $v 'cp /config/$(hostname | sed "s/upf-ees/UPF-EES/").yaml ~/free5gc/config/; cp /vagrant/run.sh ~/free5gc/run.sh; cd ~/free5gc && pgrep -x upf >/dev/null && echo "upf already running" || { setsid nohup ./run.sh > ~/upf-run.out 2>&1 < /dev/null & sleep 2; pgrep -x upf >/dev/null && echo "$(hostname) upf started"; }'
  done
  ;;
start-core)
  # ~/free5gc/run.sh copies /config/* into config/ and starts nrf amf smf udr pcf udm nssf ausf.
  vssh 5GC 'cd ~/free5gc && pgrep -x amf >/dev/null && echo "core already running" || { setsid nohup ./run.sh > ~/core-run.out 2>&1 < /dev/null & sleep 6; pgrep -l -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf" | wc -l; }'
  ;;
start-nwdaf)
  vssh 5GC 'cp /config/nwdafcfg.yaml ~/free5gc/config/nwdafcfg.yaml; cd ~/NWDAF && pgrep -x nwdaf >/dev/null && echo "nwdaf already running" || { setsid nohup ./run_nwdaf.sh > ~/nwdaf-run.out 2>&1 < /dev/null & sleep 3; pgrep -x nwdaf >/dev/null && echo nwdaf started; }'
  ;;
start-ran)
  for v in gNB gNB2; do
    vssh $v 'cp /vagrant/run.sh ~/UERANSIM/run.sh; cd ~/UERANSIM && pgrep -x nr-gnb >/dev/null && echo "ran already running" || { setsid nohup ./run.sh > ~/ran-run.out 2>&1 < /dev/null & sleep 3; echo "$(hostname) gnb=$(pgrep -c -x nr-gnb) ue_procs=$(pgrep -c -x nr-ue)"; }'
  done
  ;;
start-consumer)
  # NWDAF UE_COMMUNICATION group subscription (default: all 4 groups, scripts/consumer-mve.json;
  # P1: CONSUMER=consumer-p1-<n>.json picks the group subset). All configs use .state-mve.json.
  cat "$(dirname "$0")/$CF" | vssh 5GC "mkdir -p ~/mve-consumer && cat > ~/mve-consumer/$CF && cp /NWDAF/nwdaf_uecomm_consumer/nwdaf_uecomm_consumer.py ~/mve-consumer/ && cd ~/mve-consumer && (setsid nohup python3 nwdaf_uecomm_consumer.py --config $CF run --auto-subscribe --target-mode group >> consumer.log 2>&1 < /dev/null &); sleep 5; cat .state-mve.json"
  ;;
stop-consumer)
  vssh 5GC "cd ~/mve-consumer 2>/dev/null && [ -f .state-mve.json ] && timeout 20 python3 nwdaf_uecomm_consumer.py --config $CF unsubscribe 2>&1 | tail -1; pkill -f 'nwdaf_uecomm_consumer.py --config consumer-'; echo consumer stopped"
  ;;
start-ping)
  # P0 #4 load: every UE pings its MEC at 5 pps for ${2:-720} s (ping -D logs in ~/p0ping/<tun>.txt)
  for p in gNB:192.168.200.25 gNB2:192.168.200.35; do
    vssh ${p%%:*} "mkdir -p ~/p0ping; rm -f ~/p0ping/*; for t in \$(ip -br link | awk '/uesimtun/{print \$1}'); do (setsid nohup ping -I \$t -i 0.2 -w ${2:-720} -D ${p#*:} > ~/p0ping/\$t.txt 2>&1 < /dev/null &); done; sleep 1; echo \"\$(hostname) pings: \$(pgrep -c -x ping)\""
  done
  ;;
stop-ran)
  for v in gNB gNB2; do vssh $v 'sudo pkill -INT -x nr-ue; sleep 2; sudo pkill -x nr-ue; pkill -x nr-gnb; sudo pkill -x nr-gnb; echo "$(hostname) stopped"'; done
  ;;
stop-nwdaf)
  vssh 5GC 'pkill -INT -x nwdaf; sleep 2; pkill -x nwdaf; echo nwdaf stopped'
  ;;
stop-core)
  vssh 5GC 'cd ~/free5gc && for nf in ausf nssf udm pcf udr smf amf nrf; do pkill -INT -x $nf; done; sleep 3; pgrep -l -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf" || echo core stopped'
  ;;
stop-upf)
  for v in UPF-EES UPF-EES2; do vssh $v 'sudo pkill -INT -x upf; sleep 2; pgrep -x upf || echo "$(hostname) upf stopped"'; done
  ;;
status)
  vssh 5GC 'echo "5GC: $(pgrep -l -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf|nwdaf" | awk "{print \$2}" | tr "\n" " ")"'
  for v in UPF-EES UPF-EES2; do vssh $v 'echo "$(hostname): upf=$(pgrep -c -x upf)"'; done
  for v in gNB gNB2; do vssh $v 'echo "$(hostname): gnb=$(pgrep -c -x nr-gnb) nr-ue=$(pgrep -c -x nr-ue) tun=$(ip -br link | grep -c uesimtun)"'; done
  ;;
*) sed -n 2,12p "$0"; exit 1 ;;
esac
