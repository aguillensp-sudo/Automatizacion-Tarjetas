"""Sondeo de SOLO LECTURA de Ninox (YB / XB) en JULSA y FAWALT.

No escribe nada. Sirve para verificar el esquema real de las tablas implicadas
antes de diseñar la aplicación.

Uso:  python tools/probe_readonly.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BASE = "https://api.ninox.com/v1"
TEAM = "qCq3JS7q7ptoap8Yg"
DBS = {"JULSA INDUSTRIAL": "ssy88c9uryyl", "FAWALT INVESTMENT": "we43bpehexq6"}


def cred(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         f"[Environment]::GetEnvironmentVariable('{name}','User')"],
        capture_output=True, text=True, timeout=20,
    )
    return out.stdout.strip()


def get(path: str):
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {KEY}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body.strip() else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


KEY = cred("NINOX_API_KEY")
print("API key presente:", bool(KEY), "len:", len(KEY))

for dbname, dbid in DBS.items():
    print("\n" + "=" * 78)
    print(f"BASE: {dbname}  ({dbid})")
    print("=" * 78)

    for table in ("YB", "XB"):
        st, meta = get(f"/teams/{TEAM}/databases/{dbid}/tables/{table}")
        print(f"\n--- [{table}] metadatos (HTTP {st}) ---")
        if st != 200:
            print(meta)
            continue
        print("nombre:", meta.get("name"))
        for f in meta.get("fields", []):
            extra = ""
            t = f.get("type")
            if t == "reference":
                extra = f" -> {f.get('tableId')}"
            if f.get("choices"):
                extra = " " + json.dumps(
                    [(c.get("id"), c.get("caption")) for c in f["choices"]],
                    ensure_ascii=False)
            print(f"   {f.get('id'):<4} {f.get('name'):<32} {t:<12} "
                  f"must={f.get('required')} ro={f.get('readOnly')} {extra}")

    for table in ("XB", "YB"):
        st, recs = get(f"/teams/{TEAM}/databases/{dbid}/tables/{table}/records?perPage=100&page=0")
        print(f"\n--- [{table}] registros (HTTP {st}) ---")
        if st != 200:
            print(recs)
            continue
        print("total página 0:", len(recs) if isinstance(recs, list) else recs)
        if isinstance(recs, list):
            for r in recs[:40]:
                print(f"   id={r.get('id'):<6} seq={r.get('sequence')!s:<8} "
                      f"{json.dumps(r.get('fields'), ensure_ascii=False)[:400]}")
