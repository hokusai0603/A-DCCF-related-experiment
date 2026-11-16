#!/usr/bin/env python3
"""P1 analysis: per-cell cost metrics from cost/raw/<tag>.{pcap.gz,meta.json,snap-*.txt}.

Hops (5GC capture, -i any; "wire bytes" = IP bytes, i.e. ip.len, L2 excluded):
  ees      UPF (192.168.107.10 / .111) <-> NWDAF 192.168.107.5:8080   (main cost, HTTP/1.1)
  pfcp     N4 UDP 8805 (UPF <-> SMF)                                   (auxiliary)
  adrf     NWDAF <-> ADRF :9888                                        (auxiliary)
  consumer NWDAF -> consumer 127.0.0.11:9095                           (auxiliary)
Per EES notification (all counted inside [start, end)):
  body / item bytes (item = body minus the {"notificationItems":[ ... ],"correlationId":"..."} envelope),
  HTTP request header bytes, HTTP response bytes, wire bytes per notification split into request
  segments / response segments / pure TCP control (ACK, SYN, FIN), TCP connections opened per notification.
Model (decision 2026-11-10): b = item JSON bytes; a = wire bytes per notification - b.
usage: p1_analyze.py [tags...]   -> cost/cells.csv, cost/ees_items.csv (per-notification sample)
"""
import csv
import glob
import json
import os
import re
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict

R = os.path.expanduser("~/Research-data-collection")
RAW = f"{R}/cost/raw"
NWDAF = "192.168.107.5"
UPFS = {"192.168.107.10", "192.168.107.111"}
F = ["frame.time_epoch", "ip.src", "ip.dst", "ip.len", "tcp.srcport", "tcp.dstport", "udp.srcport", "udp.dstport",
     "tcp.stream", "tcp.len", "tcp.flags.syn", "tcp.flags.ack", "tcp.flags.fin", "tcp.flags.reset",
     "http.request.method", "http.request.uri", "http.response.code", "http.content_length_header",
     "tcp.reassembled.length", "pfcp.msg_type"]


def tshark(pcap, fields, flt=None):
    cmd = ["tshark", "-r", pcap, "-n", "-T", "fields", "-E", "separator=\t", "-E", "occurrence=a", "-E", "aggregator=|"]
    if flt:
        cmd += ["-Y", flt]
    for f in fields:
        cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout
    for ln in out.splitlines():
        p = ln.split("\t")
        yield dict(zip(fields, p + [""] * (len(fields) - len(p))))


def iso(s):
    import datetime as dt
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def first_int(s):
    return int(s.split("|")[0]) if s else 0


def hop_of(r):
    if r["udp.srcport"] == "8805" or r["udp.dstport"] == "8805":
        return "pfcp"
    sp, dp = r["tcp.srcport"], r["tcp.dstport"]
    if "9888" in (sp, dp):
        return "adrf"
    if "9095" in (sp, dp):
        return "consumer"
    if "8080" in (sp, dp) and (r["ip.src"] in UPFS or r["ip.dst"] in UPFS):
        return "ees"
    return "other"


def snaps(tag):
    out = {}
    for lab in ("start", "end"):
        d = {}
        for ln in open(f"{RAW}/{tag}.snap-{lab}.txt"):
            p = ln.split()
            if p[0] == "mongo":
                for kv in p[1:]:
                    k, v = kv.split("=")
                    d["mongo." + k] = float(v)
            elif p[1].startswith("t="):
                for kv in p[1:]:
                    k, v = kv.split("=")
                    d[f"{p[0]}.{k}"] = float(v)
            else:
                d[f"{p[0]}.{p[1]}"] = float(p[2]) if len(p) > 2 and p[2] else float("nan")
        out[lab] = d
    return out


def cpu_and_mongo(tag):
    s = snaps(tag)
    a, b = s["start"], s["end"]
    res = {}
    for host, procs in (("5GC", ("smf", "nwdaf", "adrf", "amf")), ("upf-ees", ("upf",)), ("upf-ees2", ("upf",))):
        dt_ = b[f"{host}.t"] - a[f"{host}.t"]
        tck = a[f"{host}.tck"]
        for p in procs:
            res[f"cpu_{host.replace('-', '')}_{p}"] = round((b[f"{host}.{p}"] - a[f"{host}.{p}"]) / tck / dt_, 4)
    dtm = b["mongo.t"] - a["mongo.t"]
    for k in ("free5gc.dataSize", "free5gc.storageSize", "adrf.dataSize", "adrf.storageSize", "adrf.records.size"):
        res["mongo_" + k.replace(".", "_") + "_per_h"] = round((b["mongo." + k] - a["mongo." + k]) / dtm * 3600)
    res["adrf_records_per_h"] = round((b["mongo.adrf.records"] - a["mongo.adrf.records"]) / dtm * 3600)
    return res


def analyze(tag):
    m = json.load(open(f"{RAW}/{tag}.meta.json"))
    pcap = f"{RAW}/{tag}.pcap.gz"
    t0, t1 = iso(m["start"]), iso(m["end"])
    dur = t1 - t0
    by = defaultdict(lambda: Counter())
    ees_streams_open = set()
    reqs = []
    resp_msgs = []
    for r in tshark(pcap, F):
        if not r["frame.time_epoch"]:
            continue
        t = float(r["frame.time_epoch"])
        if not (t0 <= t < t1):
            continue
        h = hop_of(r)
        c = by[h]
        ipl = first_int(r["ip.len"])
        c["frames"] += 1
        c["ip_bytes"] += ipl
        if h == "pfcp":
            for mt in r["pfcp.msg_type"].split("|"):
                if mt:
                    c[f"pfcp_type_{mt}"] += 1
            continue
        tl = first_int(r["tcp.len"])
        if r["tcp.flags.syn"] == "1" and r["tcp.flags.ack"] == "0":
            c["conn_open"] += 1
        if r["http.request.method"]:
            n = len(r["http.request.method"].split("|"))
            c["requests"] += n
            msg = first_int(r["tcp.reassembled.length"]) or tl
            cl = first_int(r["http.content_length_header"])
            c["req_msg_bytes"] += msg
            c["req_body_bytes"] += cl
            if h == "ees":
                reqs.append((t, msg, cl))
        if r["http.response.code"]:
            c["responses"] += len(r["http.response.code"].split("|"))
            msg = first_int(r["tcp.reassembled.length"]) or tl
            c["resp_msg_bytes"] += msg
            if h == "ees":
                resp_msgs.append(msg)
        if tl == 0:
            c["ctrl_bytes"] += ipl
        else:
            client_to_server = r["tcp.dstport"] in ("8080", "9888", "9095")
            c["c2s_data_bytes" if client_to_server else "s2c_data_bytes"] += ipl

    # EES bodies (item bytes)
    items = []
    flt = "http.request and tcp.dstport==8080 and (ip.src==192.168.107.10 or ip.src==192.168.107.111)"
    for r in tshark(pcap, ["frame.time_epoch", "http.file_data", "ip.src"], flt):
        t = float(r["frame.time_epoch"] or 0)
        if not (t0 <= t < t1):
            continue
        body = r["http.file_data"]
        if not body.startswith('{"notificationItems":['):
            continue
        j = json.loads(body)
        k = body.rindex('],"correlationId":"')
        inner = body[len('{"notificationItems":['):k]
        n = len(j["notificationItems"])
        items.append(dict(t=t, src=r["ip.src"], n_items=n, body=len(body.encode()),
                          item=(len(inner.encode()) - (n - 1)) / n if n else 0,
                          envelope=len(body.encode()) - len(inner.encode())))
    e = by["ees"]
    n = e["requests"] or 1
    row = dict(tag=tag, period=m["period"], nue=m["nue"], window_s=round(dur),
               records_total=m["records"]["total"], records_min_per_ue=m["records"]["min"],
               expected_per_ue=m["records"]["expected_per_ue"],
               ees_notif=e["requests"], ees_notif_per_s=round(e["requests"] / dur, 4),
               ees_items_per_notif=round(st.mean(x["n_items"] for x in items), 4) if items else "",
               ees_body_mean=round(e["req_body_bytes"] / n, 2),
               ees_item_mean=round(st.mean(x["item"] for x in items), 2) if items else "",
               ees_item_min=min((x["item"] for x in items), default=""), ees_item_max=max((x["item"] for x in items), default=""),
               ees_envelope_mean=round(st.mean(x["envelope"] for x in items), 2) if items else "",
               ees_req_hdr_mean=round((e["req_msg_bytes"] - e["req_body_bytes"]) / n, 2),
               ees_resp_msg_mean=round(e["resp_msg_bytes"] / (e["responses"] or 1), 2),
               ees_wire_per_notif=round(e["ip_bytes"] / n, 2),
               ees_wire_c2s_data_per_notif=round(e["c2s_data_bytes"] / n, 2),
               ees_wire_s2c_data_per_notif=round(e["s2c_data_bytes"] / n, 2),
               ees_wire_ctrl_per_notif=round(e["ctrl_bytes"] / n, 2),
               ees_frames_per_notif=round(e["frames"] / n, 3),
               ees_conn_open_per_notif=round(e["conn_open"] / n, 4),
               ees_wire_bytes_per_s=round(e["ip_bytes"] / dur, 1),
               pfcp_msgs_per_s=round(by["pfcp"]["frames"] / dur, 3),
               pfcp_bytes_per_s=round(by["pfcp"]["ip_bytes"] / dur, 1),
               pfcp_types=";".join(f"{k[10:]}:{v}" for k, v in sorted(by["pfcp"].items()) if k.startswith("pfcp_type_")),
               adrf_req_per_s=round(by["adrf"]["requests"] / dur, 4),
               adrf_wire_per_req=round(by["adrf"]["ip_bytes"] / (by["adrf"]["requests"] or 1), 1),
               adrf_bytes_per_s=round(by["adrf"]["ip_bytes"] / dur, 1),
               consumer_notif_per_s=round(by["consumer"]["requests"] / dur, 4),
               consumer_wire_per_notif=round(by["consumer"]["ip_bytes"] / (by["consumer"]["requests"] or 1), 1),
               other_bytes_per_s=round(by["other"]["ip_bytes"] / dur, 1),
               adrf_records_in_window=m.get("adrf_records_in_window", ""))
    if items:
        row["a_wire"] = round(row["ees_wire_per_notif"] - row["ees_item_mean"] * row["ees_items_per_notif"], 2)
        row["b_item"] = row["ees_item_mean"]
    row.update(cpu_and_mongo(tag))
    with open(f"{RAW}/{tag}.ees_items.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["t", "src", "n_items", "body", "item", "envelope"])
        w.writeheader()
        w.writerows(items)
    return row


def main():
    tags = sys.argv[1:] or sorted(os.path.basename(p)[:-10] for p in glob.glob(f"{RAW}/*.meta.json"))
    rows = []
    for t in tags:
        rows.append(analyze(t))
        r = rows[-1]
        print(f"{t}: notif/s {r['ees_notif_per_s']} items/notif {r['ees_items_per_notif']} body {r['ees_body_mean']} "
              f"item {r['ees_item_mean']} req_hdr {r['ees_req_hdr_mean']} resp {r['ees_resp_msg_mean']} "
              f"wire/notif {r['ees_wire_per_notif']} (c2s {r['ees_wire_c2s_data_per_notif']} s2c {r['ees_wire_s2c_data_per_notif']} "
              f"ctrl {r['ees_wire_ctrl_per_notif']}) conn/notif {r['ees_conn_open_per_notif']} a {r.get('a_wire')} b {r.get('b_item')}")
    out = f"{R}/cost/cells.csv" if not sys.argv[1:] else f"{R}/cost/cells_partial.csv"
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out)


if __name__ == "__main__":
    main()
