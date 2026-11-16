#!/usr/bin/env python3
"""P2 export + trace quality check for one run directory (written by scripts/p2_run.sh).

Inputs in --dir: meta.json (since, t0, end, duration_s), ue_check.csv (SUPI -> UE IP of this run),
nwdaf_subs.log (NWDAF "SMF subscription created: supi=..., corrId=..."), iperf3-gNB*.tgz.
MongoDB free5gc.nwdaf.upfTrafficData records with timestamp in [since, end + 30 s).

Outputs (traces/README.md documents the format):
  upf_records.parquet  every MongoDB record of the run (incl. duplicates, flagged)
  upf_1s.parquet       ground truth: SUPI x second k in [0, duration) after dedup
  iperf3_1s.parquet    iperf3 client per-second sent bytes/packets on the same wall-clock seconds
  iperf3_tests.parquet one row per iperf3 launch (schedule realisation)
  quality.json         PREREGISTRATION 2.3 checks + auxiliaries; "valid": true/false

Definitions (fixed before the first P2 run; see traces/README.md):
  * record time ts = MongoDB `timestamp` = START of the ~1 s measurement interval [ts, ts+1)
    (pilot traces/pilot-S3-seed1-d180: the per-second correlation with iperf3 is 0.9999 for
    [ts, ts+1) and 0.959 for [ts-1, ts); bytes*8/throughput gives a 1.0001 s mean interval).
    Dedup key (SUPI, timestamp), keep the first.
  * second index for UE u: k = round(ts - T0 - phi_u), phi_u = circular mean of frac(ts - T0)
    over u's records, so the record measuring [T0+phi_u+k, T0+phi_u+k+1) lands in bin k and jitter
    (+-0.1 s) never crosses a bin edge. Two records in one bin are summed (counted as collisions).
    Traffic in [T0, T0+phi_u) falls into bin -1 (outside the grid; the schedule starts at T0).
  * missing seconds = SUPI x k (k in [0, duration)) bins with no record; rule: <= 2 %.
  * volume check: UPF UL bytes of ALL deduplicated records of the run (also bin -1, which holds
    the traffic of [T0, T0+phi_u)) vs iperf3 client sent bytes; rule: |UPF / iperf3 - 1| <= 5 %.
    No header correction: the pilot (traces/pilot-S3-seed1-d180) showed that the UPF UL volume of a
    UDP datagram equals the iperf3 payload (per UE: + 8 iperf3 control TCP packets, ~450 B).
    The ratio with +8 B/packet is reported as an auxiliary (volume_ratio_hdr8).
  * iperf3_1s uses the same per-UE bins as upf_1s: bin k = floor(t - T0 - phi_u).
exit 0 valid, 10 invalid, 1 error. With --delete (default on) the run's MongoDB records are deleted
after upf_records.parquet was read back with the same row count and byte sums.
"""
import argparse
import csv
import io
import json
import math
import pathlib
import re
import subprocess
import sys
import tarfile
from collections import defaultdict

import numpy as np
import pandas as pd

MONGO = "mongodb://127.0.0.1/free5gc"
COLL = "nwdaf.upfTrafficData"


def mongo(js):
    r = subprocess.run(["mongosh", "--quiet", MONGO, "--eval", js], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return r.stdout


def iso(epoch):
    return pd.Timestamp(epoch, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-4] + "Z"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--no-delete", action="store_true")
    ap.add_argument("--reanalyze", action="store_true", help="read upf_records.parquet instead of MongoDB (no delete)")
    a = ap.parse_args()
    d = pathlib.Path(a.dir)
    meta = json.load(open(d / "meta.json"))
    t0, dur = float(meta["t0"]), int(meta["duration_s"])
    since = pd.Timestamp(meta["since"]).timestamp()
    q_end = t0 + dur + 30

    # --- SUPI <-> corrId (NWDAF log, lines after `since`) and UE IPs of this run
    corr2supi = {}
    for ln in open(d / "nwdaf_subs.log", errors="replace"):
        m = re.search(r'time="([^"]+)".*supi=([^,]+), subId=([^,]+), corrId=(\S+) \(from group=([^)]+)\)', ln)
        if m and pd.Timestamp(m.group(1)[:26] + "Z").timestamp() >= since - 1:
            corr2supi[m.group(4)] = m.group(2)
    ue = {r["supi"]: r for r in csv.DictReader(open(d / "ue_check.csv"))}
    supis = sorted(ue)

    # --- MongoDB export
    js = f'''const r=db["{COLL}"].find({{timestamp:{{$gte:new Date("{iso(since)}"),$lt:new Date("{iso(q_end)}")}}}},
      {{_id:0}}).toArray();
      print(JSON.stringify(r.map(x=>[x.timestamp.getTime(),x.metadata.correlationId,x.metadata.groupId,x.metadata.ipAddr,
      Number(x.ulVolume||0),Number(x.dlVolume||0),Number(x.ulNbOfPackets||0),Number(x.dlNbOfPackets||0),
      Number(x.ulThroughput||0),Number(x.dlThroughput||0)])))'''
    if a.reanalyze:
        rec = pd.read_parquet(d / "upf_records.parquet").drop(columns=["supi", "k", "dup", "ip_ok"])
        rec["ts_ms"] = rec.pop("ts").astype("int64") // 10**6
        a.no_delete = True
    else:
        rec = pd.DataFrame(json.loads(mongo(js)), columns=["ts_ms", "corr_id", "group_id", "ip", "ul_bytes", "dl_bytes",
                                                           "ul_pkts", "dl_pkts", "ul_thr_bps", "dl_thr_bps"])
    rec["supi"] = rec["corr_id"].map(corr2supi)
    rec["ts"] = pd.to_datetime(rec["ts_ms"], unit="ms", utc=True)
    n_mongo = len(rec)
    rec = rec.sort_values(["supi", "ts_ms"], kind="stable").reset_index(drop=True)
    rec["dup"] = rec.duplicated(["supi", "ts_ms"], keep="first")
    rec["ip_ok"] = [ue.get(s, {}).get("ue_ip") == ip for s, ip in zip(rec["supi"], rec["ip"])]
    rel = rec["ts_ms"] / 1000.0 - t0
    rec["k"] = -1
    phis = {}
    for s, g in rec[~rec["dup"]].groupby("supi"):
        r = rel[g.index]
        inwin = r[(r > -1) & (r < dur + 1)]
        fr = (inwin - np.floor(inwin)).to_numpy()
        phi = (math.atan2(np.sin(2 * np.pi * fr).mean(), np.cos(2 * np.pi * fr).mean()) / (2 * np.pi)) % 1.0 if len(fr) else 0.0
        phis[s] = phi
        rec.loc[g.index, "k"] = np.round(r - phi).astype(int)
    out_cols = ["supi", "corr_id", "group_id", "ip", "ts", "k", "ul_bytes", "dl_bytes", "ul_pkts", "dl_pkts",
                "ul_thr_bps", "dl_thr_bps", "dup", "ip_ok"]
    rec[out_cols].to_parquet(d / "upf_records.parquet", index=False)

    # --- ground-truth grid
    ok = rec[(~rec["dup"]) & rec["supi"].notna() & (rec["k"] >= 0) & (rec["k"] < dur)]
    agg = ok.groupby(["supi", "k"]).agg(ul_bytes=("ul_bytes", "sum"), dl_bytes=("dl_bytes", "sum"),
                                        ul_pkts=("ul_pkts", "sum"), dl_pkts=("dl_pkts", "sum"),
                                        n_rec=("ul_bytes", "size"))
    full = pd.MultiIndex.from_product([supis, range(dur)], names=["supi", "k"])
    grid = agg.reindex(full).reset_index()
    grid["missing"] = grid["n_rec"].isna()
    grid = grid.fillna({"ul_bytes": 0, "dl_bytes": 0, "ul_pkts": 0, "dl_pkts": 0, "n_rec": 0})
    for c in ("ul_bytes", "dl_bytes", "ul_pkts", "dl_pkts", "n_rec"):
        grid[c] = grid[c].astype("int64")
    grid["phi_s"] = grid["supi"].map(phis).fillna(0.0)
    grid.to_parquet(d / "upf_1s.parquet", index=False)

    # --- iperf3 (client side)
    tests, sec = [], defaultdict(lambda: [0.0, 0.0])
    for tg in sorted(d.glob("iperf3-gNB*.tgz")):
        with tarfile.open(tg) as tf:
            att = [json.loads(x) for x in tf.extractfile("out/attempts.jsonl").read().decode().splitlines() if x.strip()]
            for x in att:
                if "file" not in x:
                    continue
                m = tf.getmember(f"out/{x['supi']}/{x['file']}")
                txt = tf.extractfile(m).read().decode(errors="replace")
                try:
                    j = json.loads(txt)
                except Exception:
                    j = {"error": "unparsable: " + txt[:200]}
                end = j.get("end", {})
                ssum = end.get("sum_sent") or end.get("sum") or {}
                rsum = end.get("sum_received") or end.get("sum") or {}
                tstart = j.get("start", {}).get("timestamp", {}).get("timesecs")
                iv = j.get("intervals", [])
                # absolute time of the test start: launch time (the control connection adds a few ms)
                for it in iv:
                    sm = it.get("sum", {})
                    b, p = float(sm.get("bytes", 0)), float(sm.get("packets", 0))
                    s_abs, e_abs = x["t_launch"] + sm.get("start", 0), x["t_launch"] + sm.get("end", 0)
                    if e_abs <= s_abs:
                        continue
                    # split proportionally over the UE's bins k = floor(t - T0 - phi_u)
                    ph = phis.get(x["supi"], 0.0)
                    base = t0 + ph
                    k0, k1 = math.floor(s_abs - base), math.floor(e_abs - base)
                    for k in range(k0, k1 + 1):
                        lo, hi = max(s_abs, base + k), min(e_abs, base + k + 1)
                        if hi <= lo:
                            continue
                        f = (hi - lo) / (e_abs - s_abs)
                        sec[(x["supi"], k)][0] += b * f
                        sec[(x["supi"], k)][1] += p * f
                tests.append(dict(supi=x["supi"], seg=x["seg"], attempt=x["attempt"], rc=x["rc"], busy=x.get("busy", False),
                                  t_launch=x["t_launch"], t_exit=x["t_exit"], seg_start=x["seg_start"], seg_end=x["seg_end"],
                                  rate_bps=x["rate"], bytes_req=x["bytes_req"],
                                  sent_bytes=int(ssum.get("bytes", 0) if x["rc"] == 0 else sum(i.get("sum", {}).get("bytes", 0) for i in iv)),
                                  sent_pkts=int(ssum.get("packets", 0) if x["rc"] == 0 else sum(i.get("sum", {}).get("packets", 0) for i in iv)),
                                  lost_pkts=int(rsum.get("lost_packets", 0) or 0), n_intervals=len(iv),
                                  error=j.get("error", ""), iperf_timesecs=tstart))
            skipped = [x for x in att if x.get("skipped")]
    tdf = pd.DataFrame(tests)
    tdf.to_parquet(d / "iperf3_tests.parquet", index=False)
    isec = pd.DataFrame([(s, k, v[0], v[1]) for (s, k), v in sec.items()], columns=["supi", "k", "bytes", "pkts"])
    isec = isec[(isec["k"] >= 0) & (isec["k"] < dur + 5)]
    ifull = pd.MultiIndex.from_product([supis, range(dur)], names=["supi", "k"])
    isec = isec.groupby(["supi", "k"]).sum().reindex(ifull, fill_value=0.0).reset_index()
    isec.to_parquet(d / "iperf3_1s.parquet", index=False)

    # --- quality (PREREGISTRATION 2.3)
    n_cells = len(supis) * dur
    miss = int(grid["missing"].sum())
    upf_ul_grid = int(grid["ul_bytes"].sum())
    allrec = rec[(~rec["dup"]) & rec["supi"].notna()]
    upf_ul = int(allrec["ul_bytes"].sum())
    ip_bytes, ip_pkts = int(tdf["sent_bytes"].sum()) if len(tdf) else 0, int(tdf["sent_pkts"].sum()) if len(tdf) else 0
    ip_corr = ip_bytes + 8 * ip_pkts
    ratio = upf_ul / ip_bytes if ip_bytes else float("nan")
    per_ue = []
    ug = allrec.groupby("supi")[["ul_bytes", "ul_pkts"]].sum().reindex(supis, fill_value=0)
    tg = tdf.groupby("supi")[["sent_bytes", "sent_pkts"]].sum() if len(tdf) else pd.DataFrame(columns=["sent_bytes", "sent_pkts"])
    for s in supis:
        ib = float(tg.loc[s, "sent_bytes"]) if s in tg.index else 0.0
        per_ue.append(dict(supi=s, upf_ul=int(ug.loc[s, "ul_bytes"]), upf_ul_pkts=int(ug.loc[s, "ul_pkts"]), iperf_bytes=ib,
                           iperf_pkts=float(tg.loc[s, "sent_pkts"]) if s in tg.index else 0.0,
                           ratio=(ug.loc[s, "ul_bytes"] / ib) if ib else None,
                           missing=int(grid[grid["supi"] == s]["missing"].sum())))
    nondup = rec[~rec["dup"]]
    coll = int((agg["n_rec"] > 1).sum())
    m_upf = grid.set_index(["supi", "k"])["ul_bytes"]
    m_ip = isec.set_index(["supi", "k"])
    m_ipc = m_ip["bytes"].reindex(m_upf.index, fill_value=0)
    corr = float(np.corrcoef(m_upf.to_numpy(float), m_ipc.to_numpy(float))[0, 1]) if m_upf.std() > 0 and m_ipc.std() > 0 else None
    late = (tdf["t_launch"] - tdf["seg_start"]) if len(tdf) else pd.Series(dtype=float)
    first = tdf[tdf["attempt"] == 0] if len(tdf) else tdf
    q = dict(
        run=meta["run"], attempt=meta["attempt"], t0=t0, duration_s=dur,
        records_total=len(rec), records_unmapped_corr=int(rec["supi"].isna().sum()),
        duplicates=int(rec["dup"].sum()), ip_mismatch=int((~rec["ip_ok"]).sum()),
        corr_ids=len(corr2supi), supis_with_records=int(nondup["supi"].nunique()),
        missing_seconds=miss, cells=n_cells, missing_frac=miss / n_cells, bin_collisions=coll,
        phi_s=dict(min=min(phis.values()) if phis else None, max=max(phis.values()) if phis else None),
        upf_ul_bytes=upf_ul, upf_ul_bytes_in_grid=upf_ul_grid, upf_dl_bytes=int(allrec["dl_bytes"].sum()),
        upf_ul_pkts=int(allrec["ul_pkts"].sum()),
        iperf3_sent_bytes=ip_bytes, iperf3_sent_pkts=ip_pkts,
        volume_ratio=ratio, volume_ratio_hdr8=(upf_ul / ip_corr) if ip_corr else None,
        per_ue_ratio=dict(min=min((u["ratio"] for u in per_ue if u["ratio"]), default=None),
                          max=max((u["ratio"] for u in per_ue if u["ratio"]), default=None)),
        per_second_corr_upf_vs_iperf3=corr,
        iperf3=dict(launches=len(tdf), failed=int((tdf["rc"] != 0).sum()) if len(tdf) else 0,
                    busy_retries=int(tdf["busy"].sum()) if len(tdf) else 0, skipped_segments=len(skipped),
                    lost_pkts=int(tdf["lost_pkts"].sum()) if len(tdf) else 0,
                    launch_late_s=dict(p50=float(late.quantile(.5)) if len(late) else None,
                                       p99=float(late.quantile(.99)) if len(late) else None,
                                       max=float(late.max()) if len(late) else None),
                    first_attempt_launches=len(first)),
        rules=dict(volume_within_5pct=bool(abs(ratio - 1) <= 0.05) if ip_bytes else (upf_ul == 0),
                   missing_le_2pct=miss / n_cells <= 0.02),
        per_ue=per_ue,
    )
    q["valid"] = all(q["rules"].values()) and q["records_unmapped_corr"] == 0 and q["supis_with_records"] == len(supis)
    json.dump(q, open(d / "quality.json", "w"), indent=1, default=float)
    print(f"[{meta['run']} a{meta['attempt']}] records {len(rec)} dup {q['duplicates']} unmapped {q['records_unmapped_corr']} "
          f"ip_mismatch {q['ip_mismatch']} supis {q['supis_with_records']}/{len(supis)} | missing {miss}/{n_cells} "
          f"({100*miss/n_cells:.3f}%) collisions {coll} | UPF/iperf3 {ratio:.5f} (hdr8 {q['volume_ratio_hdr8']:.5f}) "
          f"per-UE {q['per_ue_ratio']} corr1s {corr} | iperf3 launches {len(tdf)} failed {q['iperf3']['failed']} "
          f"busy {q['iperf3']['busy_retries']} skipped {len(skipped)} late p99 {q['iperf3']['launch_late_s']['p99']} -> "
          f"{'VALID' if q['valid'] else 'INVALID'}")

    # --- round-trip check, then delete this run's records
    back = pd.read_parquet(d / "upf_records.parquet")
    same = len(back) == n_mongo and int(back["ul_bytes"].sum()) == int(rec["ul_bytes"].sum()) \
        and int(back["dl_bytes"].sum()) == int(rec["dl_bytes"].sum())
    if not same:
        print("export round-trip mismatch: MongoDB records kept")
        return 1
    if not a.no_delete:
        n = mongo(f'''print(db["{COLL}"].deleteMany({{timestamp:{{$gte:new Date("{iso(since)}"),$lt:new Date("{iso(q_end)}")}}}}).deletedCount)''').strip()
        print(f"deleted {n} MongoDB records of this run (exported {len(rec)})")
        json.dump(dict(deleted=int(n), exported=len(rec), since=iso(since), until=iso(q_end)), open(d / "mongo_deleted.json", "w"))
    return 0 if q["valid"] else 10


if __name__ == "__main__":
    sys.exit(main())
