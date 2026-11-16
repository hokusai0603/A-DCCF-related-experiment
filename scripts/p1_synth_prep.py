#!/usr/bin/env python3
"""Extract the inputs for p1_synth.py from a real P1 capture (cost/raw/<tag>.pcap.gz):
  cost/synth/hdr.hex    exact request header block of one real UPF->NWDAF EES notification
  cost/synth/resp.hex   exact NWDAF response bytes (HTTP/1.1 204)
  cost/synth/items.txt  real notificationItem JSON strings, one per line (distinct UEs first)
usage: p1_synth_prep.py <tag>
"""
import os
import subprocess
import sys

R = os.path.expanduser("~/Research-data-collection")
tag = sys.argv[1]
pcap = f"{R}/cost/raw/{tag}.pcap.gz"
out = f"{R}/cost/synth"
os.makedirs(out, exist_ok=True)


def tshark(flt, fields):
    cmd = ["tshark", "-r", pcap, "-n", "-Y", flt, "-T", "fields", "-E", "separator=\t"]
    for f in fields:
        cmd += ["-e", f]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()


req = tshark("http.request and tcp.dstport==8080 and ip.src==192.168.107.10 and not tcp.reassembled.length", ["tcp.payload"])
raw = bytes.fromhex(req[len(req) // 2].replace(":", ""))
hdr = raw[: raw.index(b"\r\n\r\n") + 4]
open(f"{out}/hdr.hex", "w").write(hdr.hex())
resp = tshark("http.response.code==204 and tcp.srcport==8080 and ip.dst==192.168.107.10", ["tcp.payload"])
open(f"{out}/resp.hex", "w").write(resp[len(resp) // 2].replace(":", ""))

bodies = tshark("http.request and tcp.dstport==8080 and (ip.src==192.168.107.10 or ip.src==192.168.107.111)", ["http.file_data"])
seen, items, rest = set(), [], []
pre = '{"notificationItems":['
for b in bodies:
    if not b.startswith(pre):
        continue
    it = b[len(pre): b.rindex('],"correlationId":"')]
    ip = it.split('"ueIpv4Addr":"')[1].split('"')[0]
    (rest if ip in seen else items).append(it)
    seen.add(ip)
items += rest[: 500]
open(f"{out}/items.txt", "w").write("\n".join(items) + "\n")
print(f"hdr {len(hdr)} B, resp {len(bytes.fromhex(open(out + '/resp.hex').read()))} B, items {len(items)} ({len(seen)} distinct UEs)")
print(hdr.decode().replace("\r\n", " | "))
print(bytes.fromhex(open(out + "/resp.hex").read()).decode(errors="replace").replace("\r\n", " | "))
