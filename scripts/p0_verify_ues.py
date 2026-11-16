#!/usr/bin/env python3
"""P0 acceptance 4.5 #1 and #2 for every UE.

#1 core log (latest ~/free5gc/log/<ts>/free5gc.log in 5GC):
     AMF "Handle Registration Complete" and SMF "Allocated PDUAdress[ip]" per SUPI,
     no Registration Reject / PDU establishment reject for the SUPI;
   UERANSIM: `nr-cli <imsi> -e ps-list` is PS-ACTIVE with the same IP, that IP sits on
     a uesimtunX in the gNB VM and lies in the slice's pool.
#2 `ping -I <uesimtunX> -c 3 <MEC>` from the gNB VM (equivalent to nr-binder <ip>:
     nr-binder's LD_PRELOAD is not honoured by the capability-bearing ping binary).

usage: p0_verify_ues.py [--out p0/ue_check.csv] [--no-ping]
"""
import argparse
import csv
import ipaddress
import re
import subprocess
import sys

INFRA = "/home/king25158986/free5gc-NWDAF/5G_Infrastructure"
SLICES = {
    "gNB": dict(pool="10.10.0.0/24", mec="192.168.200.25", sd="010203",
                supis=[1, 2, 3] + list(range(101, 121))),
    "gNB2": dict(pool="10.100.0.0/24", mec="192.168.200.35", sd="112233",
                 supis=[4, 5, 6] + list(range(201, 221))),
}


def vssh(vm, cmd, timeout=600):
    r = subprocess.run(["vagrant", "ssh", "-c", cmd], cwd=f"{INFRA}/{vm}",
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout


def supi(n):
    return f"imsi-2089300000{n:05d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/home/king25158986/Research-data-collection/p0/ue_check.csv")
    ap.add_argument("--no-ping", action="store_true")
    a = ap.parse_args()

    log = vssh("5GC", r'''L=$(ls -td ~/free5gc/log/*/ | head -1)/free5gc.log; echo "LOG $L"; sed "s/\x1b\[[0-9;]*m//g" $L | grep -aE "Handle Registration Complete|Allocated PDUAdress|Registration Reject|Reject|reject" | grep -a "imsi-"''')
    logfile = log.splitlines()[0] if log else ""
    reg, pdu_ip, rej = set(), {}, {}
    for ln in log.splitlines():
        m = re.search(r"imsi-(\d{15})", ln)
        if not m:
            continue
        s = "imsi-" + m.group(1)
        if "Handle Registration Complete" in ln:
            reg.add(s)
        elif "Allocated PDUAdress" in ln:
            pdu_ip[s] = re.search(r"PDUAdress\[([\d.]+)\]", ln).group(1)  # last one wins
        elif re.search(r"[Rr]eject", ln):
            rej.setdefault(s, ln[:200])

    rows = []
    for vm, cfg in SLICES.items():
        ues = " ".join(supi(n) for n in cfg["supis"])
        out = vssh(vm, f'''cd ~/UERANSIM/build; for u in {ues}; do echo "UE $u $(./nr-cli $u -e ps-list 2>&1 | tr '\\n' ' ')"; done; ip -4 -o addr show | awk '/uesimtun/{{print "TUN", $2, $4}}' ''')
        tun_of = {}
        ps = {}
        for ln in out.splitlines():
            if ln.startswith("TUN "):
                _, tun, cidr = ln.split()
                tun_of[cidr.split("/")[0]] = tun
            elif ln.startswith("UE "):
                _, s, rest = ln.split(" ", 2)
                st = re.search(r"state: (\S+)", rest)
                ip = re.search(r"address: ([\d.]+)", rest)
                ps[s] = (st.group(1) if st else "NONE", ip.group(1) if ip else "")
        ping = {}
        if not a.no_ping:
            tuns = [tun_of[ip] for (_, ip) in ps.values() if ip in tun_of]
            pout = vssh(vm, "for t in %s; do echo \"PING $t $(ping -I $t -c 3 -i 0.3 -W 2 %s | grep -o '[0-9]* received' | cut -d' ' -f1)\"; done"
                        % (" ".join(tuns), cfg["mec"]))
            for ln in pout.splitlines():
                if ln.startswith("PING "):
                    p = ln.split()
                    ping[p[1]] = int(p[2]) if len(p) > 2 and p[2].isdigit() else 0
        net = ipaddress.ip_network(cfg["pool"])
        for n in cfg["supis"]:
            s = supi(n)
            st, ip = ps.get(s, ("MISSING", ""))
            tun = tun_of.get(ip, "")
            in_pool = bool(ip) and ipaddress.ip_address(ip) in net
            rx = ping.get(tun, "") if tun else ""
            ok1 = s in reg and pdu_ip.get(s) == ip and st == "PS-ACTIVE" and bool(tun) and in_pool and s not in rej
            ok2 = rx == 3 if not a.no_ping else ""
            rows.append(dict(supi=s, gnb=vm, sd=cfg["sd"], new=n >= 100,
                             core_reg_complete=s in reg, core_pdu_ip=pdu_ip.get(s, ""),
                             ue_state=st, ue_ip=ip, tun=tun, in_pool=in_pool,
                             core_reject=rej.get(s, ""), ping_rx_of_3=rx, mec=cfg["mec"],
                             acc1=ok1, acc2=ok2))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    new = [r for r in rows if r["new"]]
    old = [r for r in rows if not r["new"]]
    print(f"core log: {logfile}")
    print(f"new UEs: {len(new)}  #1 pass {sum(r['acc1'] for r in new)}  #2 pass {sum(r['acc2'] is True for r in new)}")
    print(f"existing UEs: {len(old)}  #1 pass {sum(r['acc1'] for r in old)}  #2 pass {sum(r['acc2'] is True for r in old)}")
    for r in rows:
        if not (r["acc1"] and (a.no_ping or r["acc2"])):
            print("FAIL", {k: r[k] for k in ("supi", "core_reg_complete", "core_pdu_ip", "ue_state", "ue_ip", "tun", "in_pool", "ping_rx_of_3", "core_reject")})
    print(f"wrote {a.out}")


if __name__ == "__main__":
    sys.exit(main())
