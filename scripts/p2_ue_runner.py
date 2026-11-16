#!/usr/bin/env python3
"""P2 UE traffic runner, executed INSIDE a gNB VM (python3 stdlib only).

Plays every UE's on-segments (scripts/p2_schedule.py) with iperf3 UDP clients bound to the UE IP
(-B <ue_ip>; UERANSIM installs `ip rule from <ue_ip> lookup rt_uesimtunX`), one server port per
UE on MEC/MEC2. One thread per UE; segment times are relative to the absolute epoch --t0.
The byte count (-n) is computed at the actual launch time from the remaining segment length,
so a late start (previous burst still finishing, "server busy" retry) keeps the planned end time.

Per UE: <out>/<supi>/<k>-<attempt>.json = iperf3 -J output; <out>/attempts.jsonl = every launch
(t_launch, t_exit, rc, bytes requested). Stops launching at t0 + duration.

usage: p2_ue_runner.py --plan plan.json --t0 <epoch> --out <dir>
plan.json: {"duration_s": 1800, "pkt_len": 1200,
            "ues": [{"supi", "ue_ip", "server", "port", "segments": [[s, e, rate_bps], ...]}]}
"""
import argparse
import json
import os
import subprocess
import threading
import time

LOCK = threading.Lock()


def log(fh, rec):
    with LOCK:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()


def sleep_until(t):
    while True:
        d = t - time.time()
        if d <= 0:
            return
        time.sleep(min(d, 0.5) if d > 0.02 else d)


def run_ue(ue, t0, dur, pkt, out, fh):
    d = os.path.join(out, ue["supi"])
    os.makedirs(d, exist_ok=True)
    for k, (s, e, rate) in enumerate(ue["segments"]):
        s_abs, e_abs = t0 + s, t0 + min(e, dur)
        sleep_until(s_abs)
        att = 0
        while True:
            now = time.time()
            remain = e_abs - now
            if remain < 0.02:
                log(fh, dict(supi=ue["supi"], seg=k, attempt=att, skipped=True, t=now, remain=remain))
                break
            nbytes = max(pkt, int(rate * remain / 8 / pkt) * pkt)
            cmd = ["iperf3", "-c", ue["server"], "-p", str(ue["port"]), "-B", ue["ue_ip"], "-u",
                   "-b", str(int(rate)), "-l", str(pkt), "-n", str(nbytes), "-i", "1", "-J"]
            f = os.path.join(d, f"{k}-{att}.json")
            t_launch = time.time()
            with open(f, "w") as o:
                rc = subprocess.call(cmd, stdout=o, stderr=subprocess.STDOUT)
            t_exit = time.time()
            busy = False
            if rc != 0:
                try:
                    busy = "busy" in json.load(open(f)).get("error", "")
                except Exception:
                    busy = False
            log(fh, dict(supi=ue["supi"], seg=k, attempt=att, file=os.path.basename(f), t_launch=t_launch,
                         t_exit=t_exit, rc=rc, busy=busy, bytes_req=nbytes, rate=rate, seg_start=s_abs, seg_end=e_abs))
            if rc == 0 or att >= 50 or time.time() >= e_abs - 0.02:
                break
            att += 1
            time.sleep(0.1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--t0", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    plan = json.load(open(a.plan))
    os.makedirs(a.out, exist_ok=True)
    fh = open(os.path.join(a.out, "attempts.jsonl"), "a")
    log(fh, dict(event="runner-start", t=time.time(), t0=a.t0, ues=len(plan["ues"])))
    th = [threading.Thread(target=run_ue, args=(u, a.t0, plan["duration_s"], plan["pkt_len"], a.out, fh), daemon=True)
          for u in plan["ues"]]
    for t in th:
        t.start()
    for t in th:
        t.join()
    log(fh, dict(event="runner-done", t=time.time()))


if __name__ == "__main__":
    main()
