#!/usr/bin/env bash
# Option (c) (user-approved 2026-11-10): run the MVE on the fixed UPF / SMF / NWDAF builds
# without touching the old binaries (~/free5gc/bin, ~/NWDAF/bin stay as they are).
#   UPF   : ~/go-upf @ 682b469 (PR #79 head), built statically on the host
#   SMF   : 5GC:~/ees-audit-20261021/smf  (official main 0e2c7be + local multi-AN/threshold mods)
#   NWDAF : 5GC:~/ees-audit-20261027/nwdaf (codex/nwdaf-smf-main-compat, 2026-10-26 build)
# Other core NFs are the existing free5GC v4.1.0 binaries (same as the 2026-10-21 validation).
# Runtime configs are DERIVED from config/5GC (source of truth) by `gen`:
#   smfcfg  : urrThreshold 0 (new SMF arms the volume trigger only when > 0), nupfEe* keys dropped
#   nwdafcfg: + smf.pduSessionIds (all MVE SUPIs -> PSI 1, verified with nr-cli ps-list)
#   UPF-EES*: ees.listenAddr -> ees.ip/port; periodSec/parquetDir dropped (not in this build)
# PERIOD=<s> newstack.sh gen : P1 override of samplingInterval (-> repPeriod) and urrPeriod in the
#   DERIVED configs only (config/5GC stays untouched).
# usage: newstack.sh gen | deploy | start-upf | start-core | start-adrf | start-nwdaf | stop-upf | stop-core | stop-adrf | stop-nwdaf | status
set -uo pipefail
INFRA=${INFRA:-$HOME/free5gc-NWDAF/5G_Infrastructure}
R=$HOME/Research-data-collection; G=$R/newstack
UPF_BIN=${UPF_BIN:-$G/bin/upf-682b469}
vssh() { (cd "$INFRA/$1" && vagrant ssh -c "$2" 2>/dev/null); }

case "${1:-}" in
gen)
  mkdir -p "$G"
  python3 - "$INFRA/config/5GC" "$G" "${PERIOD:-}" <<'EOF'
import re, sys, pathlib, yaml
src, out, per = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
s = (src / "smfcfg.yaml").read_text()
if per:
    s, k = re.subn(r"(?m)^  urrPeriod: [0-9]+", f"  urrPeriod: {per}", s); assert k == 1
s = re.sub(r"(?m)^  urrThreshold: .*$", "  urrThreshold: 0 # derived for new SMF: 0 = no volume-threshold trigger", s)
s = re.sub(r"(?m)^  nupfEe(NfId|ReqTimeout|MaxRetries):.*\n", "", s)
(out / "smfcfg.yaml").write_text("# DERIVED by Research-data-collection/scripts/newstack.sh gen from config/5GC/smfcfg.yaml\n" + s)
n = (src / "nwdafcfg.yaml").read_text()
if per:
    n, k = re.subn(r"(?m)^(      samplingInterval: )[0-9]+", rf"\g<1>{per}", n); assert k == 1
supis = [f"imsi-2089300000{i:05d}" for i in [1, 2, 3, 4, 5, 6] + list(range(101, 121)) + list(range(201, 221))]
block = "    pduSessionIds: # derived: PSI 1 for every MVE SUPI (nr-cli ps-list)\n" + "".join(f"      {x}: 1\n" for x in supis)
n, k = re.subn(r"(?m)^(    subscriptionDuration: .*\n)", r"\1" + block.replace("\\", "\\\\"), n)
assert k == 1
(out / "nwdafcfg.yaml").write_text("# DERIVED by Research-data-collection/scripts/newstack.sh gen from config/5GC/nwdafcfg.yaml\n" + n)
for f in ("UPF-EES.yaml", "UPF-EES2.yaml"):
    c = yaml.safe_load((src / f).read_text())
    ip, port = c["ees"]["listenAddr"].rsplit(":", 1)
    c["ees"] = {"enabled": True, "ip": ip, "port": int(port)}
    c["logger"]["level"] = "info"
    c["description"] = "DERIVED by newstack.sh gen from config/5GC/" + f
    (out / f).write_text(yaml.safe_dump(c, sort_keys=False))
for f in ("smfcfg.yaml", "nwdafcfg.yaml"):
    yaml.safe_load((out / f).read_text())
print("generated:", sorted(p.name for p in out.glob("*.yaml")), "period override:", per or "none")
EOF
  ;;
deploy)
  # copy binaries/configs into ~/mve-bin (old binaries untouched)
  for v in UPF-EES UPF-EES2; do
    cat "$UPF_BIN" | vssh $v 'mkdir -p ~/mve-bin && cat > ~/mve-bin/upf && chmod +x ~/mve-bin/upf && sha256sum ~/mve-bin/upf | cut -c1-16'
    cat "$G/$v.yaml" | vssh $v 'cat > ~/mve-bin/upfcfg.yaml && echo "$(hostname): cfg ok"'
  done
  vssh 5GC 'mkdir -p ~/mve-bin && cp ~/ees-audit-20261021/smf ~/mve-bin/smf && cp ~/ees-audit-20261027/nwdaf ~/mve-bin/nwdaf && sha256sum ~/mve-bin/smf ~/mve-bin/nwdaf | cut -c1-16'
  cat "$G/smfcfg.yaml" | vssh 5GC 'cat > ~/mve-bin/smfcfg.yaml'
  cat "$G/nwdafcfg.yaml" | vssh 5GC 'cat > ~/mve-bin/nwdafcfg.yaml && echo "5GC: cfgs ok"'
  ;;
start-upf)
  for v in UPF-EES UPF-EES2; do
    vssh $v 'pgrep -x upf >/dev/null && echo "$(hostname): an upf is already running" || { cd ~/mve-bin && (setsid nohup sudo -E ./upf -c ./upfcfg.yaml -l upf.log > ~/mve-upf-run.out 2>&1 < /dev/null &); sleep 2; echo "$(hostname): new upf pids=$(pgrep -x upf | tr "\n" " ")"; }'
  done
  ;;
start-core)
  # like ~/free5gc/run.sh, but SMF = ~/mve-bin/smf with the derived config
  vssh 5GC 'pgrep -x amf >/dev/null && { echo "core already running"; exit 0; }
    cd ~/free5gc && cp -r /config/* config/ && L=~/free5gc/log/mve-$(date +%Y%m%d_%H%M%S) && mkdir -p $L && echo $L > ~/mve-bin/core-log-dir
    mongosh --quiet free5gc --eval "db.NfProfile.drop(); db[\"applicationData.influenceData.subsToNotify\"].drop(); db[\"applicationData.subsToNotify\"].drop(); db[\"policyData.subsToNotify\"].drop(); db[\"exposureData.subsToNotify\"].drop()" >/dev/null 2>&1 || mongo free5gc --quiet --eval "db.NfProfile.drop()" >/dev/null 2>&1
    export GIN_MODE=release
    for nf in nrf amf smf udr pcf udm nssf ausf; do
      if [ $nf = smf ]; then (setsid nohup ~/mve-bin/smf -c ~/mve-bin/smfcfg.yaml -l $L/free5gc.log > $L/smf.out 2>&1 < /dev/null &)
      else (setsid nohup ./bin/$nf -c ./config/${nf}cfg.yaml -l $L/free5gc.log > $L/$nf.out 2>&1 < /dev/null &); fi
      sleep 0.2
    done; sleep 4; echo "core up: $(pgrep -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf" | wc -l)/8, smf=$(readlink /proc/$(pgrep -x smf)/exe)"'
  ;;
start-nwdaf)
  vssh 5GC 'pgrep -x nwdaf >/dev/null && echo "nwdaf already running" || { cd ~/NWDAF && (setsid nohup ~/mve-bin/nwdaf --config ~/mve-bin/nwdafcfg.yaml -l ~/mve-bin/nwdaf.log > ~/mve-bin/nwdaf.out 2>&1 < /dev/null &); sleep 3; echo "nwdaf: $(readlink /proc/$(pgrep -x nwdaf)/exe)"; }'
  ;;
start-adrf)
  # P1 (user decision 2026-11-10): run the ADRF with the existing config/5GC/adrfcfg.yaml
  # (start-core copies /config/* into ~/free5gc/config). Mongo db "adrf" on the host.
  vssh 5GC 'pgrep -x adrf >/dev/null && echo "adrf already running" || { cd ~/adrf && cp /config/adrfcfg.yaml ~/free5gc/config/adrfcfg.yaml && (setsid nohup ./bin/adrf --config ~/free5gc/config/adrfcfg.yaml > ~/mve-bin/adrf.out 2>&1 < /dev/null &); sleep 3; echo "adrf: $(readlink /proc/$(pgrep -x adrf)/exe)"; timeout 3 bash -c "</dev/tcp/192.168.107.5/9888" && echo "adrf :9888 listening"; }'
  ;;
stop-adrf) vssh 5GC 'pkill -INT -x adrf; sleep 2; pkill -x adrf; echo adrf stopped' ;;
stop-nwdaf) vssh 5GC 'pkill -INT -x nwdaf; sleep 2; pkill -x nwdaf; echo nwdaf stopped' ;;
stop-core)
  vssh 5GC 'for nf in ausf nssf udm pcf udr smf amf nrf; do pkill -INT -x $nf; done; sleep 3; pkill -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf"; sleep 1; pgrep -l -x "nrf|amf|smf|udr|pcf|udm|nssf|ausf" || echo core stopped'
  ;;
stop-upf)
  for v in UPF-EES UPF-EES2; do vssh $v 'sudo pkill -INT -x upf; sleep 2; sudo pkill -x upf; pgrep -x upf || echo "$(hostname) upf stopped"'; done
  ;;
status)
  vssh 5GC 'for p in smf nwdaf amf adrf; do echo "5GC $p -> $(readlink /proc/$(pgrep -x $p | head -1)/exe 2>/dev/null)"; done'
  for v in UPF-EES UPF-EES2; do vssh $v 'echo "$(hostname) upf -> $(sudo readlink /proc/$(pgrep -x upf | head -1)/exe 2>/dev/null)"'; done
  ;;
*) sed -n 2,15p "$0"; exit 1 ;;
esac
