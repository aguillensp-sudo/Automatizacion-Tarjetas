"""Pruebas del lector de extractos.

Dos bloques:

1. **Extracto sintético** (siempre): geometría real, casos límite incluidos
   (importe negativo, concepto con comisión, operación sin población/país).
2. **Extractos reales** de `PDFS/`: se ejecutan sólo si la carpeta existe, porque
   no se publica en el repositorio. Verifican los números del requisito.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import config
from tarjetas import pdf_reader
from tarjetas.pdf_reader import ExtractoError, leer_extracto, parsear_importe
from tests.sintetico import COL, crear_pdf


# ──────────────────────────────────────────────────────────────────────────────
# Casos límite de importes
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto, esperado", [
    ("1.394,39", Decimal("1394.39")),
    ("23,99-", Decimal("-23.99")),
    ("0,00", Decimal("0.00")),
    ("81,78", Decimal("81.78")),
    ("12.345.678,90", Decimal("12345678.90")),
])
def test_parsear_importe(texto, esperado):
    assert parsear_importe(texto) == esperado


@pytest.mark.parametrize("texto", ["0,0929", "texto", "1.394", "23,9", ""])
def test_es_importe_descarta_lo_que_no_es_importe(texto):
    assert pdf_reader.es_importe(texto) is False


# ──────────────────────────────────────────────────────────────────────────────
# Extracto sintético
# ──────────────────────────────────────────────────────────────────────────────
def test_extracto_sintetico(tmp_path):
    ruta = crear_pdf(tmp_path / "sintetico.pdf")
    extracto = leer_extracto(ruta)

    assert extracto.numero_tarjeta == "5566 **** **** 5013"
    assert extracto.tipo_tarjeta == "BUSINESS MASTERCARD"
    assert extracto.fecha_liquidacion == date(2026, 10, 5)
    # El período liquidado es el mes anterior al sello
    assert (extracto.mes_operaciones, extracto.anio_operaciones) == (9, 2026)
    assert extracto.periodo_texto == "09/2026"
    # Día 5 del mes de la liquidación (§7)
    assert extracto.fecha_cargo_total_mes == date(2026, 10, 5)

    assert len(extracto.operaciones) == 4
    importes = [op.importe for op in extracto.operaciones]
    assert importes == [Decimal("81.78"), Decimal("2.86"), Decimal("174.85"),
                        Decimal("-23.99")]
    assert extracto.total_operaciones == Decimal("235.50")
    assert extracto.suma_importes == extracto.total_operaciones

    primera = extracto.operaciones[0]
    assert primera.fecha == date(2026, 9, 1)
    assert primera.concepto == "Lodging H LE PALAIS AV"
    assert primera.poblacion == "Marrakech /MA"
    assert primera.importe_origen == "880,00 MAD"
    assert primera.tipo_cambio == "0,0929"

    # La primera página (condiciones) no se lee: su tarjeta 9999 no aparece
    assert "9999" not in extracto.numero_tarjeta
    # La página de resumen posterior al total tampoco se interpreta
    assert all(op.pagina == 2 for op in extracto.operaciones)


def test_el_anio_sale_del_mes_anterior_al_sello(tmp_path):
    """Un extracto liquidado en enero pertenece a diciembre del año anterior."""
    ruta = crear_pdf(tmp_path / "enero.pdf")
    # Se reescribe el sello a 03.01.27 manteniendo las operaciones de septiembre:
    # basta comprobar el cálculo del período y del día 5.
    extracto = leer_extracto(ruta)
    extracto.fecha_liquidacion = date(2027, 1, 3)
    assert (extracto.mes_operaciones, extracto.anio_operaciones) == (12, 2026)
    assert extracto.fecha_cargo_total_mes == date(2027, 1, 5)


def test_suma_que_no_cuadra_detiene_el_proceso(tmp_path):
    """Si la suma de importes no cuadra con el banco, se aborta (§3.4)."""
    ruta = crear_pdf(tmp_path / "descuadrado.pdf", total="999,99")
    with pytest.raises(ExtractoError) as info:
        leer_extracto(ruta)
    assert "no cuadra" in str(info.value)


def test_sin_linea_total_detiene_el_proceso(tmp_path):
    origen = crear_pdf(tmp_path / "con_total.pdf")
    destino = tmp_path / "sin_total.pdf"
    documento = pdf_reader.fitz.open(origen)
    pagina = documento[1]
    for palabra in pagina.get_text("words"):
        if palabra[4] in ("Total", "operaciones"):
            pagina.add_redact_annot(palabra[:4])
    pagina.apply_redactions()
    documento.save(destino)
    documento.close()
    with pytest.raises(ExtractoError) as info:
        leer_extracto(destino)
    assert "Total operaciones" in str(info.value)


def test_pdf_de_una_sola_pagina_no_tiene_detalle(tmp_path):
    import fitz
    ruta = tmp_path / "una_pagina.pdf"
    documento = fitz.open()
    documento.new_page(width=595.3, height=280.65)
    documento.save(ruta)
    documento.close()
    with pytest.raises(ExtractoError) as info:
        leer_extracto(ruta)
    assert "no hay detalle" in str(info.value)


def test_listar_pdfs_ordena_y_filtra(tmp_path):
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "a.PDF").write_bytes(b"%PDF-1.4")
    (tmp_path / "notas.txt").write_text("no es un pdf", encoding="utf-8")
    nombres = [p.name for p in pdf_reader.listar_pdfs(tmp_path)]
    assert nombres == ["a.PDF", "b.pdf"]


# ──────────────────────────────────────────────────────────────────────────────
# Extractos reales (sólo si el usuario los ha dejado en PDFS/)
# ──────────────────────────────────────────────────────────────────────────────
EXTRACTOS_REALES = {
    # nombre del fichero: (tarjeta, operaciones, total, período)
    "FW-AGS.pdf": ("5566 **** **** 5013", 13, Decimal("1394.39"), (9, 2026)),
    "JI-AGS.pdf": ("5566 **** **** 1012", 12, Decimal("943.45"), (8, 2026)),
    "JI-FRM.pdf": ("4106 **** **** 4011", 16, Decimal("722.90"), (9, 2026)),
}


@pytest.mark.parametrize("nombre", sorted(EXTRACTOS_REALES))
def test_extractos_reales(nombre):
    ruta = config.PDFS_DIR / nombre
    if not ruta.exists():
        pytest.skip("No está %s (la carpeta PDFS/ no se publica)" % nombre)
    tarjeta, cuantas, total, periodo = EXTRACTOS_REALES[nombre]
    extracto = leer_extracto(ruta)
    assert extracto.numero_tarjeta == tarjeta
    assert len(extracto.operaciones) == cuantas
    assert extracto.total_operaciones == total
    assert extracto.suma_importes == extracto.total_operaciones
    assert (extracto.mes_operaciones, extracto.anio_operaciones) == periodo
    fechas = [op.fecha for op in extracto.operaciones]
    assert fechas == sorted(fechas), "las operaciones deben conservar el orden del extracto"
    assert all(fecha.month == periodo[0] and fecha.year == periodo[1] for fecha in fechas)
