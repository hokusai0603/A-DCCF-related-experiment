#!/usr/bin/env python3
"""Batch-create MVE subscribers through the free5GC webconsole REST API.

Per plan 4.2 / 4.3 item 1: new IMSIs copy an existing subscriber of the same slice
(same K / OP / opType=OP / AMF=8000 / DNN internet), only SUPI and GPSI change.

  slice 1 (sd 010203): template imsi-208930000000001, range 101..
  slice 2 (sd 112233): template imsi-208930000000006, range 201..
    (not 004: its slice-level charging is Online/quota 100000 and the core runs
     without CHF, so the UPF FAR becomes DROP and the UE has no data plane)

API (webconsole v1.4.x):
  POST /api/login {"username","password"} -> {"access_token"}; header "Token: <jwt>"
  GET  /api/subscriber/{ueId}/{plmn}
  POST /api/subscriber/{ueId}/{plmn}/{userNumber}
The server-side userNumber auto-increment does not advance the GPSI string
(api_webui.go PostSubscriberByID), so >1 per call fails with "duplicate gpsi";
this script posts one UE per call instead.

usage: provision_subscribers.py [--url http://127.0.0.1:5001] [--count 20] [--first 1]
                                [--dry-run]
"""
import argparse
import copy
import json
import sys
import urllib.error
import urllib.request

PLMN = "20893"
SLICES = [
    # (template SUPI, first new MSIN suffix, sd)
    ("imsi-208930000000001", 101, "010203"),
    ("imsi-208930000000006", 201, "112233"),
]


def req(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Token", token)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw.decode(errors="replace")


def replace_supi(obj, old, new):
    if isinstance(obj, dict):
        return {k: replace_supi(v, old, new) for k, v in obj.items()}
    if isinstance(obj, list):
        return [replace_supi(v, old, new) for v in obj]
    if obj == old:
        return new
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5001")
    ap.add_argument("--count", type=int, default=20, help="UEs per slice")
    ap.add_argument("--first", type=int, default=0, help="offset inside each range (0-based)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    st, body = req("POST", a.url + "/api/login", body={"username": "admin", "password": "free5gc"})
    if st != 200:
        sys.exit(f"login failed: {st} {body}")
    tok = body["access_token"]

    created, skipped, failed = [], [], []
    for tmpl_supi, base, sd in SLICES:
        st, tmpl = req("GET", f"{a.url}/api/subscriber/{tmpl_supi}/{PLMN}", tok)
        if st != 200 or not tmpl or tmpl.get("ueId") != tmpl_supi:
            sys.exit(f"template {tmpl_supi} not readable: {st}")
        got_sd = tmpl["AccessAndMobilitySubscriptionData"]["nssai"]["defaultSingleNssais"][0]["sd"]
        if got_sd != sd:
            sys.exit(f"template {tmpl_supi} has sd {got_sd}, expected {sd}")
        for i in range(a.first, a.first + a.count):
            n = base + i
            supi = f"imsi-2089300000{n:05d}"
            st, cur = req("GET", f"{a.url}/api/subscriber/{supi}/{PLMN}", tok)
            # GET echoes ueId even when absent; existence = has a permanent key
            if st == 200 and cur and (cur.get("AuthenticationSubscription") or {}).get("permanentKey"):
                skipped.append(supi)
                continue
            sub = replace_supi(copy.deepcopy(tmpl), tmpl_supi, supi)
            sub["AccessAndMobilitySubscriptionData"]["gpsis"] = [f"msisdn-{n}"]
            # The template's chargingData also holds copies created at runtime (with a
            # ratingGroup, which GET does not return). The webconsole's slice-level upsert
            # filter (qosRef: 0) never matches the stored doc, so every slice-level entry is
            # inserted again. Keep one entry per (snssai, dnn, filter, qosRef), giving the
            # same 2 documents a freshly created UE has.
            seen, charging = set(), []
            for c in sub.get("ChargingDatas", []):
                key = (c.get("snssai"), c.get("dnn"), c.get("filter"), c.get("qosRef"))
                if key not in seen:
                    seen.add(key)
                    charging.append(c)
            sub["ChargingDatas"] = charging
            for k in ("plmnID",):
                sub[k] = PLMN
            if a.dry_run:
                print("DRY", supi, sd, sub["AccessAndMobilitySubscriptionData"]["gpsis"])
                continue
            st, resp = req("POST", f"{a.url}/api/subscriber/{supi}/{PLMN}/1", tok, sub)
            (created if st == 201 else failed).append((supi, st, resp))
            print(supi, st, resp if st != 201 else "")
    print(f"created={len(created)} skipped(existing)={len(skipped)} failed={len(failed)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
