#!/usr/bin/env python3
"""Freeze the P3 simulator cost-model parameters (user decisions 2026-11-11, PREREGISTRATION 5.1).

Two-level model, wire IP bytes (L2 excluded) of producer -> A-DCCF, both directions:
  bytes(notification) = a + sum over reports in it of (r + n_stat * s)
  raw 1-s measurement report: n_stat = 10 (6 volume + 4 throughput fields) -> r + 10 s = b_wire
  a = a0 (main); sensitivity a = a0 + c_conn * (k - 2) / k with k = 23 notifications per UPF at once
  c_ka (30 s keep-alive) is ignored.
r and s come from splitting the real items (cost/synth/items.txt, JSON) into the 10 numeric
"key":value fields and the rest, scaled to wire bytes by b_wire / b_json of the synthetic run,
with r chosen so that r + 10 s = b_wire exactly.
usage: p1_params.py -> cost/sim_params.json
"""
import json
import os
import re
import statistics as st

R = os.path.expanduser("~/Research-data-collection")
fit = json.load(open(f"{R}/cost/fit.json"))
F = ["totalVolume", "ulVolume", "dlVolume", "totalNbOfPackets", "ulNbOfPackets", "dlNbOfPackets",
     "ulThroughput", "dlThroughput", "ulPacketThroughput", "dlPacketThroughput"]
items = [ln.strip() for ln in open(f"{R}/cost/synth/items.txt") if ln.strip()]
field, rest, total = [], [], []
for s in items:
    fb = sum(len(re.search(r'"%s":("[^"]*"|[^,}]*),?' % f, s).group(0).encode()) for f in F)
    total.append(len(s.encode())); field.append(fb / len(F)); rest.append(len(s.encode()) - fb)
b_wire = fit["b_wire"]
wire_factor = b_wire / fit["synth"]["body_b"]
s_wire = st.mean(field) * wire_factor
r_wire = b_wire - len(F) * s_wire
a0, c_conn, k = fit["a0_wire"], fit["c_conn"], 23
out = dict(
    unit="wire IP bytes (L2 excluded), both directions, producer -> A-DCCF",
    model="bytes(notification) = a + sum_reports (r + n_stat * s); raw report n_stat = 10",
    a=a0,
    a_sensitivity=round(a0 + c_conn * (k - 2) / k, 1),
    a_sensitivity_note=f"a0 + c_conn*(k-2)/k, k = {k} notifications per UPF fired together (46 UEs on 2 UPFs, aligned periods)",
    r=round(r_wire, 1),
    s=round(s_wire, 2),
    n_stat_raw=len(F),
    b_raw=b_wire,
    c_ka="ignored (about 0.65 % of EES bytes at p = 30 s, 46 UEs)",
    derivation=dict(items=len(items), item_json_mean=round(st.mean(total), 1),
                    field_json_mean=round(st.mean(field), 2), rest_json_mean=round(st.mean(rest), 1),
                    rest_json_range=[min(rest), max(rest)], wire_factor=round(wire_factor, 4),
                    source="cost/fit.json (a0_wire, c_conn, b_wire, synth.body_b), cost/synth/items.txt"),
)
json.dump(out, open(f"{R}/cost/sim_params.json", "w"), indent=1)
print(json.dumps(out, indent=1))
