#!/usr/bin/env python3
"""P1 synthetic linearity check for `bytes = a + b * items` (user decision 2026-11-10, option 1).

recv (5GC): raw TCP HTTP/1.1 keep-alive sink on a NON-NWDAF port; answers every request with the
            exact response bytes captured from the real NWDAF (--resp-hex). Nothing is stored.
send (UPF-EES): replays the exact request header block captured from the real UPF notifier
            (--hdr-hex, Content-Length rewritten) with bodies built from real notificationItems
            (--items, one JSON item string per line) repeated to N items, over one persistent
            connection, writing header+body the same way the real client did (--split: header and
            body in separate send() calls if the real capture shows two segments).
usage:
  p1_synth.py recv --bind 192.168.107.5 --port 18080 --resp-hex HEX
  p1_synth.py send --host 192.168.107.5 --port 18080 --hdr-hex HEX --items FILE --corr corr-1
                   --ns 1,2,4,8,16,23,32,46 --reps 30 --gap 0.1 [--split] --log FILE
"""
import argparse
import json
import socket
import socketserver
import time


def recv(a):
    resp = bytes.fromhex(a.resp_hex)

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            buf = b""
            s = self.request
            while True:
                while b"\r\n\r\n" not in buf:
                    d = s.recv(65536)
                    if not d:
                        return
                    buf += d
                head, buf = buf.split(b"\r\n\r\n", 1)
                cl = 0
                for ln in head.split(b"\r\n")[1:]:
                    k, _, v = ln.partition(b":")
                    if k.strip().lower() == b"content-length":
                        cl = int(v)
                while len(buf) < cl:
                    d = s.recv(65536)
                    if not d:
                        return
                    buf += d
                buf = buf[cl:]
                s.sendall(resp)

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    S((a.bind, a.port), H).serve_forever()


def send(a):
    hdr = bytes.fromhex(a.hdr_hex).decode()
    items = [ln.strip() for ln in open(a.items) if ln.strip()]
    s = socket.create_connection((a.host, a.port))
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Go sets TCP_NODELAY by default
    log = open(a.log, "w")
    for n in [int(x) for x in a.ns.split(",")]:
        for r in range(a.reps):
            its = [items[(r * n + i) % len(items)] for i in range(n)]
            body = ('{"notificationItems":[' + ",".join(its) + '],"correlationId":"' + a.corr + '"}').encode()
            lines = []
            for ln in hdr.split("\r\n"):
                if ln.lower().startswith("content-length:"):
                    ln = f"Content-Length: {len(body)}"
                lines.append(ln)
            head = "\r\n".join(lines).encode()
            assert head.endswith(b"\r\n\r\n")
            t0 = time.time()
            if a.split:
                s.sendall(head)
                s.sendall(body)
            else:
                s.sendall(head + body)
            got = b""
            while b"\r\n\r\n" not in got:  # NWDAF response: headers only or tiny body
                got += s.recv(65536)
            hl, _, rest = got.partition(b"\r\n\r\n")
            cl = 0
            for ln in hl.split(b"\r\n")[1:]:
                k, _, v = ln.partition(b":")
                if k.strip().lower() == b"content-length":
                    cl = int(v)
            while len(rest) < cl:
                rest += s.recv(65536)
            log.write(json.dumps(dict(n=n, rep=r, t0=t0, t1=time.time(), head=len(head), body=len(body))) + "\n")
            time.sleep(a.gap)
    s.close()
    log.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("recv")
    r.add_argument("--bind", required=True)
    r.add_argument("--port", type=int, default=18080)
    r.add_argument("--resp-hex", required=True)
    s = sp.add_parser("send")
    s.add_argument("--host", required=True)
    s.add_argument("--port", type=int, default=18080)
    s.add_argument("--hdr-hex", required=True)
    s.add_argument("--items", required=True)
    s.add_argument("--corr", default="corr-1")
    s.add_argument("--ns", default="1,2,3,4,6,8,12,16,23,32,46")
    s.add_argument("--reps", type=int, default=30)
    s.add_argument("--gap", type=float, default=0.1)
    s.add_argument("--split", action="store_true")
    s.add_argument("--log", default="synth_send.jsonl")
    a = ap.parse_args()
    recv(a) if a.cmd == "recv" else send(a)
