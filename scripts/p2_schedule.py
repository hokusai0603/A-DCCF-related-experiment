#!/usr/bin/env python3
"""P2 traffic schedule generator (PREREGISTRATION 2.1/2.2, fixed before any P2 run).

One JSON per (scenario, seed): for every one of the 46 UEs a list of on-segments
[start_s, end_s, rate_bps] relative to the run start T0 (0 <= start < end <= 1800).
Outside the segments the UE sends nothing.

  S1 steady : one segment [0, 1800) at rate ~ U[0.2, 1.0] Mbps per UE
  S2 bursty : on ~ Exp(mean 10 s), off ~ Exp(mean 30 s), on at 1 Mbps; the initial state is
              "on" with probability 10/40 (stationary on/off process; durations are memoryless)
  S3 mixed  : fixed by UE number (same for every seed): 23 UEs S1, 14 S2, 9 idle
              (50/30/20 % of 46, largest remainder), interleaved along the SUPI order with a
              largest-deficit rule so both slices get a mix
  S4 change : S1 for [0, 900), S2 for [900, 1800) (the S2 process starts fresh at 900 s)

Randomness: numpy default_rng(SeedSequence([seed, ue_index])) per UE, ue_index = position in
the SUPI order below, so a UE's S1 rate is the same in S1, S3 and S4 for a given seed and its
S2 on/off draws are the same in S2 and S3 (S4 uses a separate stream, see `s2_stream`).

usage: p2_schedule.py --out traces/schedules            (writes S1..S4 x seeds 1,2,3)
"""
import argparse
import json
import pathlib

import numpy as np

DUR = 1800
HALF = 900
SUPIS = [f"imsi-2089300000{i:05d}" for i in [1, 2, 3, 4, 5, 6] + list(range(101, 121)) + list(range(201, 221))]
S1_LO, S1_HI = 0.2e6, 1.0e6
ON_MEAN, OFF_MEAN, ON_RATE = 10.0, 30.0, 1.0e6


def slice_of(supi):
    n = int(supi[-3:])
    return 1 if n in (1, 2, 3) or 101 <= n <= 120 else 2


def s3_classes():
    quota = {"S1": 23, "S2": 14, "idle": 9}          # 0.5/0.3/0.2 x 46, largest remainder
    share = {k: v / len(SUPIS) for k, v in quota.items()}
    got = {k: 0 for k in quota}
    out = []
    for i in range(len(SUPIS)):
        c = max((k for k in quota if got[k] < quota[k]), key=lambda k: (share[k] * (i + 1) - got[k], -list(quota).index(k)))
        got[c] += 1
        out.append(c)
    assert got == quota
    return out


def rng_for(seed, idx, stream):
    return np.random.default_rng(np.random.SeedSequence([seed, idx, stream]))


def s1_rate(seed, idx):
    return float(rng_for(seed, idx, 1).uniform(S1_LO, S1_HI))


def s2_segments(seed, idx, t0, t1, stream):
    g = rng_for(seed, idx, stream)
    on = g.random() < ON_MEAN / (ON_MEAN + OFF_MEAN)
    t, segs = t0, []
    while t < t1:
        d = float(g.exponential(ON_MEAN if on else OFF_MEAN))
        if on:
            segs.append([round(t, 3), round(min(t + d, t1), 3), ON_RATE])
        t += d
        on = not on
    return [s for s in segs if s[1] > s[0]]


def build(scn, seed):
    cls = s3_classes()
    ues = []
    for idx, supi in enumerate(SUPIS):
        if scn == "S1":
            kind, segs = "S1", [[0.0, float(DUR), s1_rate(seed, idx)]]
        elif scn == "S2":
            kind, segs = "S2", s2_segments(seed, idx, 0.0, DUR, 2)
        elif scn == "S3":
            kind = cls[idx]
            segs = {"S1": [[0.0, float(DUR), s1_rate(seed, idx)]],
                    "S2": s2_segments(seed, idx, 0.0, DUR, 2), "idle": []}[kind]
        elif scn == "S4":
            kind = "S1->S2"
            segs = [[0.0, float(HALF), s1_rate(seed, idx)]] + s2_segments(seed, idx, float(HALF), DUR, 4)
        ues.append(dict(supi=supi, slice=slice_of(supi), kind=kind, segments=segs,
                        scheduled_bytes=round(sum((e - s) * r / 8 for s, e, r in segs))))
    per_slice_peak = {}
    for sl in (1, 2):
        # worst-case instantaneous slice load: max over segment starts of the sum of active rates
        evs = sorted({s for u in ues if u["slice"] == sl for s, _, _ in u["segments"]})
        per_slice_peak[sl] = max([sum(r for u in ues if u["slice"] == sl for s, e, r in u["segments"] if s <= t < e) for t in evs] or [0])
    return dict(scenario=scn, seed=seed, duration_s=DUR, generator="scripts/p2_schedule.py",
                rng="numpy default_rng(SeedSequence([seed, ue_index, stream])); stream 1 = S1 rate, 2 = S2 on/off, 4 = S4 second half",
                per_slice_peak_bps=per_slice_peak, ues=ues)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="traces/schedules")
    ap.add_argument("--seeds", default="1,2,3")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for seed in map(int, a.seeds.split(",")):
        for scn in ("S1", "S2", "S3", "S4"):
            s = build(scn, seed)
            assert all(max(v, 0) <= 50e6 for v in s["per_slice_peak_bps"].values()), "rule 9: slice > 50 Mbps"
            p = out / f"{scn}-seed{seed}.json"
            p.write_text(json.dumps(s, indent=1))
            on = [sum(e - st for st, e, _ in u["segments"]) for u in s["ues"]]
            nseg = sum(len(u["segments"]) for u in s["ues"])
            print(f"{p.name}: segments {nseg}, on-time mean {np.mean(on):.0f} s, scheduled {sum(u['scheduled_bytes'] for u in s['ues'])/1e6:.1f} MB, "
                  f"peak slice load {s['per_slice_peak_bps'][1]/1e6:.1f}/{s['per_slice_peak_bps'][2]/1e6:.1f} Mbps")


if __name__ == "__main__":
    main()
