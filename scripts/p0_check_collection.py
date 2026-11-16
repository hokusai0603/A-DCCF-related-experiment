#!/usr/bin/env python3
"""P0 acceptance 4.5 #3 and #4 (NWDAF subscriptions, MongoDB records, 1 s cadence).

#3 NWDAF log: one "SMF subscription created: supi=..., corrId=..." per SUPI after --since;
   UPF logs: distinct EES subscriptionIds notifying after --since (23 per UPF expected);
   MongoDB free5gc.nwdaf.upfTrafficData: records for every corrId in [start, end),
   record ipAddr == the UE IP of that SUPI (p0/ue_check.csv).
#4 per corrId in [start, end): record timestamp intervals (cadence), duplicate timestamps,
   missing seconds; nonzero-volume spacing (measurement granularity); packet conservation
   against the per-UE ping replies (ping -D prints replies only; every reply crossed the UPF UL path) (~/p0ping/<tun>.txt in the gNB VMs, ping -D timestamps).

usage: p0_check_collection.py --since 2026-11-10T07:24:29Z --start ... --end ... [--out p0/collection_check.csv]
"""
import argparse
import csv
import datetime as dt
import json
import re
import statistics as st
import subprocess
from collections import Counter, defaultdict

INFRA = "/home/king25158986/free5gc-NWDAF/5G_Infrastructure"
R = "/home/king25158986/Research-data-collection"


def vssh(vm, cmd):
    return subprocess.run(["vagrant", "ssh", "-c", cmd], cwd=f"{INFRA}/{vm}",
                          capture_output=True, text=True, timeout=900).stdout


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="subscription time (UTC ISO)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--period", type=int, default=1, help="configured reporting period (s)")
    ap.add_argument("--nwdaf-log", default="~/nwdaf.log", help="NWDAF log in 5GC (new stack: ~/mve-bin/nwdaf.log)")
    ap.add_argument("--upf-log", default="~/upf-run.out", help="UPF stdout log (new stack: ~/mve-upf-run.out)")
    ap.add_argument("--tol", type=float, default=0.25, help="interval counts as on-period if |iv - period| <= tol*period")
    ap.add_argument("--out", default=f"{R}/p0/collection_check.csv")
    a = ap.parse_args()
    since, start, end = ts(a.since), ts(a.start), ts(a.end)

    # --- #3 NWDAF subscriptions (nwdaf.log is appended across runs: keep lines after --since)
    subs = {}
    for ln in vssh("5GC", "grep -a 'SMF subscription created: supi=' " + a.nwdaf_log).splitlines():
        m = re.search(r'time="([^"]+)".*supi=([^,]+), subId=([^,]+), corrId=(\S+) \(from group=([^)]+)\)', ln)
        if m and ts(m.group(1)[:26] + "Z") >= since:
            subs[m.group(2)] = dict(corr=m.group(4), smf_sub=m.group(3), group=m.group(5))
    corr2supi = {v["corr"]: k for k, v in subs.items()}

    upf_subs = {}
    for vm in ("UPF-EES", "UPF-EES2"):
        out = vssh(vm, r'''sed "s/\x1b\[[0-9;]*m//g" ''' + a.upf_log + r''' | grep -aE "ees notification sent successfully|ees subscription created: id=" | grep -aoE "^[0-9TZ:.-]+|(subscriptionId:|id=)sub-[0-9-]+" | paste - - ''')
        ids = set()
        for ln in out.splitlines():
            p = ln.split()
            if len(p) == 2 and ts(p[0][:26] + "Z") >= since:
                ids.add(p[1].split("sub-")[1])
        upf_subs[vm] = len(ids)

    # --- MongoDB records in [start, end)
    js = f'''const r=db["nwdaf.upfTrafficData"].find({{timestamp:{{$gte:new Date("{a.start}"),$lt:new Date("{a.end}")}}}},
      {{_id:0,timestamp:1,metadata:1,ulVolume:1,dlVolume:1,ulNbOfPackets:1,dlNbOfPackets:1}}).toArray();
      print(JSON.stringify(r.map(d=>[d.timestamp.toISOString(),d.metadata.correlationId,d.metadata.ipAddr,
      Number(d.ulVolume||0),Number(d.dlVolume||0),Number(d.ulNbOfPackets||0),Number(d.dlNbOfPackets||0)])))'''
    recs = json.loads(subprocess.run(["mongosh", "--quiet", "mongodb://127.0.0.1/free5gc", "--eval", js],
                                     capture_output=True, text=True).stdout)
    by = defaultdict(list)
    for t, c, ip, ulv, dlv, ulp, dlp in recs:
        by[c].append((ts(t), ip, ulv, dlv, ulp, dlp))

    ue_ip = {r["supi"]: (r["ue_ip"], r["tun"], r["gnb"]) for r in csv.DictReader(open(f"{R}/p0/ue_check.csv"))}

    # --- ping ground truth: echo requests sent per tun inside [start, end)
    sent = {}
    for vm in ("gNB", "gNB2"):
        out = vssh(vm, "cd ~/p0ping && for f in *.txt; do awk -v t=${f%.txt} '/^\\[/{gsub(/[\\[\\]]/,\"\",$1); print t, $1}' $f; done")
        cnt = Counter()
        s0, e0 = start.timestamp(), end.timestamp()
        for ln in out.splitlines():
            t, x = ln.split()
            if s0 <= float(x) < e0:
                cnt[t] += 1
        for t, n in cnt.items():
            sent[(vm, t)] = n

    span = int((end - start).total_seconds())
    rows = []
    for supi, s in sorted(subs.items()):
        L = sorted(by.get(s["corr"], []))
        tss = [x[0] for x in L]
        iv = [(b - a).total_seconds() for a, b in zip(tss, tss[1:])]
        dup = len(tss) - len(set(tss))
        nz = [x[0] for x in L if x[4] or x[5]]
        nziv = [(b - a).total_seconds() for a, b in zip(nz, nz[1:])]
        ip_rec = sorted({x[1] for x in L})
        ip, tun, vm = ue_ip.get(supi, ("", "", ""))
        ul_pk = sum(x[4] for x in L)
        dl_pk = sum(x[5] for x in L)
        ping_req = sent.get((vm, tun), 0)
        rows.append(dict(
            supi=supi, corr=s["corr"], group=s["group"], new=int(supi[-3:]) >= 100,
            records=len(L), expected=span // a.period, dup_ts=dup,
            iv_min=min(iv) if iv else "", iv_med=st.median(iv) if iv else "", iv_max=max(iv) if iv else "",
            iv_eq_period_frac=round(sum(abs(x - a.period) <= a.tol * a.period for x in iv) / len(iv), 4) if iv else "",
            nonzero_records=len(nz), nz_iv_med=st.median(nziv) if nziv else "",
            nz_iv_max=max(nziv) if nziv else "",
            rec_ip=";".join(ip_rec), ue_ip=ip, ip_match=ip_rec == [ip],
            ul_pkts=ul_pk, dl_pkts=dl_pk, ping_replies=ping_req,
            ul_pkts_per_ping_reply=round(ul_pk / ping_req, 4) if ping_req else "",
        ))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    new = [r for r in rows if r["new"]]
    print(f"window {a.start} .. {a.end} ({span} s)")
    print(f"#3 NWDAF per-SUPI SMF subscriptions since {a.since}: {len(subs)} (new SUPIs {len(new)}/40)")
    print(f"#3 UPF EES subscriptions notifying: {upf_subs}")
    print(f"#3 SUPIs with records: {sum(r['records'] > 0 for r in rows)}/{len(rows)}; record ip == UE ip: {sum(r['ip_match'] for r in rows)}/{len(rows)}")
    allv = [x for r in rows for x in [r]]
    print(f"#4 records per UE: min {min(r['records'] for r in rows)} max {max(r['records'] for r in rows)} (expected {span // a.period}); dup timestamps total {sum(r['dup_ts'] for r in rows)}")
    print(f"#4 interval: min {min(r['iv_min'] for r in rows)} max {max(r['iv_max'] for r in rows)}; share of intervals == {a.period} s: worst UE {min(r['iv_eq_period_frac'] for r in rows)}")
    print(f"#4 nonzero-volume records per UE: min {min(r['nonzero_records'] for r in rows)} max {max(r['nonzero_records'] for r in rows)}; median spacing between nonzero records (s): {sorted(Counter(r['nz_iv_med'] for r in rows if r['nz_iv_med'] != '').items())}; UEs with <2 nonzero records: {sum(r['nz_iv_med'] == '' for r in rows)}; max spacing {max(r['nz_iv_max'] for r in rows if r['nz_iv_max'] != '')}")
    rat = [r["ul_pkts_per_ping_reply"] for r in rows if r["ul_pkts_per_ping_reply"] != ""]
    print(f"#4 UL packets reported / ping replies (each reply = request that crossed the UPF UL path): min {min(rat)} median {st.median(rat)} max {max(rat)}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
