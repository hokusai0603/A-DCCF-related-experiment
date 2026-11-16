#!/usr/bin/env python3
"""P1 cost-model fit from cost/cells.csv (12 real cells) and cost/synth/synth_requests.csv (GRO off).

Wire bytes = IP bytes (L2 excluded) of the UPF -> NWDAF EES hop, both directions.
Model per producer (UPF) and reporting period, k notifications fired together, N items each:
  bytes = k * (a0 + b * N) + max(0, k - 2) * c_conn + [P >= 30 s] * min(k, 2) * c_ka
  a0     fixed bytes of one notification on a kept-alive connection (headers, envelope, response, ACKs)
  b      bytes per item
  c_conn extra bytes of a new TCP connection (Go client keeps <= 2 idle connections per host)
  c_ka   TCP keep-alive probe + ACK per idle connection per 30 s (Go dialer/server KeepAlive 30 s)
usage: p1_fit.py -> cost/fit.json, prints the summary
"""
import csv
import json
import os
import statistics as st
from collections import defaultdict

R = os.path.expanduser("~/Research-data-collection")
rows = list(csv.DictReader(open(f"{R}/cost/cells.csv")))
for r in rows:
    for k, v in r.items():
        try:
            r[k] = float(v)
        except (TypeError, ValueError):
            pass
rows.sort(key=lambda r: (r["period"], r["nue"]))
PER_UPF = {6: (3, 3), 26: (23, 3), 46: (23, 23)}  # group-test-001 (1-3) + mve-s1 on UPF-EES; 004-006 + mve-s2 on UPF-EES2


def ols(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    sst = sum((y - my) ** 2 for y in ys)
    r2 = 1 - sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / sst if sst else 1.0
    return a, b, r2


out = {}
# 1. b: item JSON bytes from real bodies, per period
b_by_p = defaultdict(list)
for r in rows:
    b_by_p[int(r["period"])].append(r["ees_item_mean"])
out["b_item_json_by_period"] = {p: round(st.mean(v), 2) for p, v in sorted(b_by_p.items())}
out["b_item_json_range"] = [min(r["ees_item_min"] for r in rows), max(r["ees_item_max"] for r in rows)]

# 2. a0 and c_conn from real cells with P < 30 (no keep-alive probes): a_cell = wire/notif - b*items
pts = [(r["ees_conn_open_per_notif"], r["ees_wire_per_notif"] - r["ees_item_mean"] * r["ees_items_per_notif"]) for r in rows if r["period"] < 30]
a0, c_conn, r2 = ols([x for x, _ in pts], [y for _, y in pts])
out["a0_wire"], out["c_conn"], out["a_fit_r2"] = round(a0, 1), round(c_conn, 1), round(r2, 6)
# conn/notif predicted by max(0, k-2) per UPF
out["conn_per_notif_check"] = {r["tag"]: [r["ees_conn_open_per_notif"], round(sum(max(0, k - 2) for k in PER_UPF[int(r["nue"])]) / r["nue"], 4)] for r in rows}

# 3. keep-alive at P = 30 s: extra bytes per 30 s period, total over both UPFs
ka = {}
for r in rows:
    if r["period"] >= 30:
        a_cell = r["ees_wire_per_notif"] - r["ees_item_mean"]
        extra = (a_cell - (a0 + c_conn * r["ees_conn_open_per_notif"])) * r["nue"]
        idle = sum(min(k, 2) for k in PER_UPF[int(r["nue"])])
        ka[r["tag"]] = dict(extra_per_period=round(extra, 1), idle_conns=idle, per_idle_conn=round(extra / idle, 1))
out["keepalive_30s"] = ka
c_ka = st.mean(v["per_idle_conn"] for v in ka.values())
out["c_ka"] = round(c_ka, 1)

# 4. synthetic (GRO off): wire and body fits vs N
syn = list(csv.DictReader(open(f"{R}/cost/synth/synth_requests.csv")))
xs = [int(s["n"]) for s in syn]
sa, sb, sr2 = ols(xs, [int(s["wire"]) for s in syn])
ba, bb, br2 = ols(xs, [int(s["body"]) for s in syn])
out["synth"] = dict(wire_a=round(sa, 1), wire_b=round(sb, 2), wire_r2=round(sr2, 6), body_a=round(ba, 1), body_b=round(bb, 2), body_r2=round(br2, 7), requests=len(syn))
out["b_wire"] = round(sb, 2)


# 5. model check: predicted vs measured EES wire bytes/s for every cell (b = cell's own item mean at N = 1)
def predict(r):
    P, b = r["period"], r["ees_item_mean"]
    tot = 0
    for k in PER_UPF[int(r["nue"])]:
        tot += k * (a0 + b) + max(0, k - 2) * c_conn + (min(k, 2) * c_ka if P >= 30 else 0)
    return tot / P


chk = {}
for r in rows:
    p = predict(r)
    chk[r["tag"]] = dict(measured=r["ees_wire_bytes_per_s"], predicted=round(p, 1), err_pct=round(100 * (p - r["ees_wire_bytes_per_s"]) / r["ees_wire_bytes_per_s"], 2))
out["model_check_bytes_per_s"] = chk

# 6. H3: notifications/s and bytes/s vs subscribed UEs, per period
h3 = {}
for P in sorted({int(r["period"]) for r in rows}):
    rr = [r for r in rows if int(r["period"]) == P]
    n = [r["nue"] for r in rr]
    a1, b1, r21 = ols(n, [r["ees_notif_per_s"] for r in rr])
    a2, b2, r22 = ols(n, [r["ees_wire_bytes_per_s"] for r in rr])
    h3[P] = dict(notif_per_s=dict(intercept=round(a1, 4), slope=round(b1, 5), r2=round(r21, 6)),
                 bytes_per_s=dict(intercept=round(a2, 1), slope=round(b2, 2), r2=round(r22, 6)))
out["H3_linearity"] = h3

# 7. auxiliary per cell
aux = {}
for r in rows:
    aux[r["tag"]] = {k: r[k] for k in ("pfcp_msgs_per_s", "pfcp_bytes_per_s", "adrf_req_per_s", "adrf_wire_per_req", "adrf_bytes_per_s",
                                        "consumer_notif_per_s", "consumer_wire_per_notif", "cpu_5GC_smf", "cpu_5GC_nwdaf", "cpu_5GC_adrf",
                                        "cpu_upfees_upf", "cpu_upfees2_upf", "adrf_records_per_h", "mongo_adrf_dataSize_per_h")}
    aux[r["tag"]]["upfTrafficData_records_per_h"] = round(r["records_total"] / r["window_s"] * 3600)
out["auxiliary"] = aux
out["adrf_bytes_per_record"] = round(st.mean(r["mongo_adrf_dataSize_per_h"] / r["adrf_records_per_h"] for r in rows), 1)
json.dump(out, open(f"{R}/cost/fit.json", "w"), indent=1)

print(f"b (item JSON, real bodies) by period: {out['b_item_json_by_period']}  range {out['b_item_json_range']}")
print(f"a0 = {a0:.1f} B, c_conn = {c_conn:.1f} B/new connection (R^2 {r2:.6f}, 9 cells P<30 s)")
print(f"c_ka = {c_ka:.1f} B per idle connection per 30 s: {ka}")
print(f"synthetic: wire a {sa:.1f} b {sb:.2f} R^2 {sr2:.6f}; body a {ba:.1f} b {bb:.2f} R^2 {br2:.7f}")
print("model check (bytes/s):", {k: v['err_pct'] for k, v in chk.items()})
print("conn/notif measured vs max(0,k-2):", out["conn_per_notif_check"])
print("H3:", json.dumps(h3))
print("ADRF bytes/record:", out["adrf_bytes_per_record"])
