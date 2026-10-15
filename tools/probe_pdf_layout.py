"""Vuelca las palabras de la página de operaciones con sus coordenadas.

Sirve para deducir las columnas reales de la tabla antes de escribir el parser.
Solo lectura de PDF. Uso: python tools/probe_pdf_layout.py
"""
from __future__ import annotations

import sys

import fitz  # PyMuPDF

for name in ("FW-AGS", "JI-AGS", "JI-FRM"):
    doc = fitz.open(f"PDFS/{name}.pdf")
    page = doc[1]  # la tabla está en la 2ª página
    print("=" * 100)
    print(f"{name} · página 2 · tamaño {page.rect}")
    words = page.get_text("words")  # x0, y0, x1, y1, word, block, line, word_no
    rows: dict[float, list] = {}
    for w in words:
        key = round(w[1], 0)
        rows.setdefault(key, []).append(w)
    for y in sorted(rows):
        line = sorted(rows[y], key=lambda w: w[0])
        txt = "  ".join(f"[{w[0]:6.1f}]{w[4]}" for w in line)
        print(f"y={y:7.1f} | {txt}")
    doc.close()
