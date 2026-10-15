"""Vuelca los metadatos CRUDOS de la tabla YB en ambas bases (solo lectura).

Uso: python tools/probe_yb_meta.py
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.request

TEAM = "qCq3JS7q7ptoap8Yg"


def cred(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "[Environment]::GetEnvironmentVariable('%s','User')" % name],
        capture_output=True, text=True, timeout=20).stdout.strip()


key = cred("NINOX_API_KEY")
for db in ("ssy88c9uryyl", "we43bpehexq6"):
    req = urllib.request.Request(
        "https://api.ninox.com/v1/teams/%s/databases/%s/tables/YB" % (TEAM, db),
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"})
    meta = json.load(urllib.request.urlopen(req, timeout=60))
    print("=" * 70)
    print(db, "->", meta.get("name"), "| claves:", list(meta.keys()))
    for f in meta.get("fields", []):
        print("  ", json.dumps(f, ensure_ascii=False))
