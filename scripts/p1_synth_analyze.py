#!/usr/bin/env python3
"""Per-request wire bytes of the synthetic run vs number of items N, and the linear fit.
Each frame on the persistent connection (after the handshake, before FIN) is assigned to the most
recent request; wire bytes = sum of ip.len (both directions: request segments, ACKs, response).
usage: p1_synth_analyze.py  -> cost/synth/synth_requests.csv, cost/synth/synth_fit.txt
"""
import csv
import json
import os
import statistics as st
import subprocess
from collections import defaultdict

O = os.path.expanduser("~/Research-data-collection/cost/synth")
send = [json.loads(ln) for ln in open(f"{O}/synth_send.jsonl")]
cmd = ["tshark", "-r", f"{O}/synth.pcap.gz", "-n", "-T", "fields", "-E", "separator=\t", "-E", "occurrence=f",
       "-e", "ip.len", "-e", "tcp.len", "-e", "tcp.flags.syn", "-e", "tcp.flags.fin", "-e", "tcp.dstport",
       "-e", "tcp.seq", "-e", "tcp.ack"]
rows = [ln.split("\t") for ln in subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()]
# Assign every frame to a request by TCP sequence space (relative seq starts at 1 after the SYN):
# client data by seq in the request ranges, server ACKs by ack in the request ranges,
# server data (responses, RESP bytes each) by seq, client ACKs of responses by ack.
RESP = len(bytes.fromhex(open(f"{O}/resp.hex").read().strip()))
creq, sresp, c, sv = [], [], 1, 1
for x in send:
    creq.append((c, c + x["head"] + x["body"])); c += x["head"] + x["body"]
    sresp.append((sv, sv + RESP)); sv += RESP
import bisect
cst = [a for a, _ in creq]; sst = [a for a, _ in sresp]
per = defaultdict(lambda: dict(bytes=0, frames=0, c2s_segs=0, body=0))
unassigned = 0
for ipl, tl, syn, fin, dport, seq, ack in rows:
    if syn == "1" or fin == "1":
        continue
    tl, seq, ack = int(tl or 0), int(seq or 0), int(ack or 0)
    c2s = dport == "18080"
    if c2s and tl > 0:
        i = bisect.bisect_right(cst, seq) - 1
    elif c2s:
        i = bisect.bisect_left([b for _, b in sresp], ack)  # ACK of response j covers (start_j, end_j]
    elif tl > 0:
        i = bisect.bisect_right(sst, seq) - 1
    else:
        i = bisect.bisect_left([b for _, b in creq], ack)
    if not (0 <= i < len(send)):
        unassigned += 1
        continue
    p = per[i]
    p["bytes"] += int(ipl)
    p["frames"] += 1
    if c2s and tl > 0:
        p["c2s_segs"] += 1
for i, x in enumerate(send):
    per[i]["body"] = x["body"]
print("unassigned frames:", unassigned)
out = []
for i, s in enumerate(send):
    out.append(dict(n=s["n"], rep=s["rep"], head=s["head"], body=s["body"], wire=per[i]["bytes"],
                    frames=per[i]["frames"], c2s_segments=per[i]["c2s_segs"]))
with open(f"{O}/synth_requests.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0]))
    w.writeheader()
    w.writerows(out)


def fit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    ss = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss / sum((y - my) ** 2 for y in ys)
    res = [y - a - b * x for x, y in zip(xs, ys)]
    return a, b, r2, max(abs(r) for r in res)


lines = []
by = defaultdict(list)
for r in out:
    by[r["n"]].append(r)
lines.append("N  body_mean  wire_mean  wire_sd  frames_mean  c2s_segments")
for n in sorted(by):
    L = by[n]
    lines.append(f"{n:<3} {st.mean(r['body'] for r in L):9.1f} {st.mean(r['wire'] for r in L):10.1f} "
                 f"{st.pstdev([r['wire'] for r in L]):8.1f} {st.mean(r['frames'] for r in L):11.2f} {st.mean(r['c2s_segments'] for r in L):6.2f}")
xs = [r["n"] for r in out]
for name, key in (("body (JSON)", "body"), ("wire (IP bytes, req+ACK+resp)", "wire")):
    a, b, r2, mr = fit(xs, [r[key] for r in out])
    lines.append(f"fit {name}: a = {a:.1f} B, b = {b:.2f} B/item, R^2 = {r2:.6f}, max |residual| = {mr:.1f} B")
open(f"{O}/synth_fit.txt", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
