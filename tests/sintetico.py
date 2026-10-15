"""Generador de un extracto sintético con la geometría real de Banco Sabadell.

Las pruebas no pueden depender de los PDFs reales: la carpeta `PDFS/` está fuera
del repositorio porque contiene extractos bancarios auténticos. Este módulo
fabrica un extracto con **las mismas coordenadas** que el banco usa (medidas
sobre los tres extractos de prueba), de modo que el parser se prueba siempre.

Uso:  from tests.sintetico import crear_pdf
      ruta = crear_pdf(tmp_path / "extracto.pdf")
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

# Coordenadas reales medidas en los extractos de Banco Sabadell (página 595x281)
X_SELLO = 484.6
Y_SELLO = 22.0
X_CABECERA = 45.4
Y_NUMERO_TARJETA = 38.0
Y_ENCABEZADO = 48.0
Y_SEGUNDA_LINEA_ENCABEZADO = 56.0
Y_FOOTER = 260.0

COL = {
    "fecha": 45.4,
    "concepto": 68.0,
    "poblacion": 289.1,
    "importe_origen": 371.6,
    "moneda": 399.7,
    "tipo_cambio": 449.6,
    "importe": 492.2,
}

#: Operaciones de ejemplo, en el orden de las columnas del banco.
OPERACIONES: list[dict[str, str]] = [
    {"fecha": "0109", "concepto": "Lodging H LE PALAIS AV", "poblacion": "Marrakech",
     "pais": "/MA", "importe_origen": "880,00", "moneda": "MAD",
     "tipo_cambio": "0,0929", "importe": "81,78"},
    {"fecha": "0109", "concepto": "Comisión por conversión de divisas (*)",
     "importe": "2,86"},
    {"fecha": "1709", "concepto": "MERCADONA AVDA MANOLETE", "poblacion": "CORDOBA",
     "importe_origen": "174,85", "importe": "174,85"},
    {"fecha": "2209", "concepto": "DEVOLUCION HOTEL BOOKING", "poblacion": "MADRID",
     "importe_origen": "23,99-", "importe": "23,99-"},
]

TOTAL = "235,50"          # 81,78 + 2,86 + 174,85 − 23,99

NUMERO_TARJETA = "5566 **** **** 5013"
SELLO = "MADRID,VERGARA,05.10.26"


def _texto(pagina: fitz.Page, x: float, y: float, texto: str, tamano: float = 7.0) -> None:
    pagina.insert_text((x, y), texto, fontsize=tamano)


def _cabecera_detalle(pagina: fitz.Page, numero: str = NUMERO_TARJETA) -> None:
    _texto(pagina, 344.9, 12.0, "Detalle nuevas operaciones del periodo de liquidación")
    _texto(pagina, X_SELLO, 28.0, SELLO)
    _texto(pagina, 392.5, 37.0, "Tel. 913217227")
    _texto(pagina, 45.4, Y_NUMERO_TARJETA + 6, "Número de tarjeta %s" % numero)
    _texto(pagina, 218.2, Y_NUMERO_TARJETA + 6, "BUSINESS MASTERCARD")
    _texto(pagina, 45.4, Y_ENCABEZADO + 6, "Fecha")
    _texto(pagina, 67.9, Y_ENCABEZADO + 6, "Concepto")
    _texto(pagina, 289.2, Y_ENCABEZADO + 6, "Población/país")
    _texto(pagina, 364.3, Y_ENCABEZADO + 6, "Importe de la moneda")
    _texto(pagina, 433.2, Y_ENCABEZADO + 6, "Tipo de cambio")
    _texto(pagina, 482.6, Y_ENCABEZADO + 6, "Importe de")
    _texto(pagina, 519.3, Y_ENCABEZADO + 6, "Dias")
    _texto(pagina, 535.9, Y_ENCABEZADO + 6, "Números")
    _texto(pagina, 364.3, Y_SEGUNDA_LINEA_ENCABEZADO + 6, "de origen")
    _texto(pagina, 433.2, Y_SEGUNDA_LINEA_ENCABEZADO + 6, "aplicado")
    _texto(pagina, 483.1, Y_SEGUNDA_LINEA_ENCABEZADO + 6, "la operación")


def _pie(pagina: fitz.Page) -> None:
    _texto(pagina, 504.8, Y_FOOTER + 6, "www.bancosabadell.com")
    _texto(pagina, 42.5, Y_FOOTER + 8,
           "Banco de Sabadell, S.A. - NIF A08000143")


def crear_pdf(destino: str | Path, operaciones: list[dict[str, str]] | None = None,
              total: str = TOTAL, numero: str = NUMERO_TARJETA,
              secciones_extra: int = 1) -> Path:
    """Crea un extracto de 2 (+1) páginas con la geometría del banco.

    La primera página se rellena con el texto de condiciones: si el parser la
    leyera, aparecerían datos basura y las pruebas fallarían.
    """
    destino = Path(destino)
    operaciones = operaciones if operaciones is not None else OPERACIONES
    documento = fitz.open()

    # Página 1: condiciones. Nunca debe leerse.
    portada = documento.new_page(width=595.3, height=280.65)
    _texto(portada, 45.4, 40.0, "Liquidación del contrato de tarjeta de crédito")
    _texto(portada, 45.4, 60.0, "Total importe a pagar")
    _texto(portada, 45.4, 70.0, "9.999,99  Euros")
    _texto(portada, 45.4, 80.0, "Número de tarjeta 9999 **** **** 9999")

    # Página 2: detalle de operaciones
    pagina = documento.new_page(width=595.3, height=280.65)
    _cabecera_detalle(pagina, numero)
    y = 71.0
    for operacion in operaciones:
        _texto(pagina, COL["fecha"], y, operacion["fecha"])
        _texto(pagina, COL["concepto"], y, operacion["concepto"])
        if operacion.get("poblacion"):
            _texto(pagina, COL["poblacion"], y, operacion["poblacion"])
        if operacion.get("pais"):
            _texto(pagina, 343.6, y, operacion["pais"])
        if operacion.get("importe_origen"):
            _texto(pagina, COL["importe_origen"], y, operacion["importe_origen"])
        if operacion.get("moneda"):
            _texto(pagina, COL["moneda"], y, operacion["moneda"])
        if operacion.get("tipo_cambio"):
            _texto(pagina, COL["tipo_cambio"], y, operacion["tipo_cambio"])
        _texto(pagina, COL["importe"], y, operacion["importe"])
        y += 9.0
    y += 10.0
    _texto(pagina, COL["concepto"], y, "Total")
    _texto(pagina, 93.2, y, "operaciones")
    _texto(pagina, 479.4, y, total)
    _pie(pagina)

    # Página 3: resumen por concepto (debe ignorarse: el proceso para en el total)
    for _ in range(secciones_extra):
        resumen = documento.new_page(width=595.3, height=280.65)
        _texto(resumen, 45.4, 40.0, "Resumen por concepto")
        _texto(resumen, 45.4, 50.0, "TOTAL GASTOS")
        _texto(resumen, 45.4, 60.0, "12")
        _texto(resumen, 45.4, 70.0, "1.394")

    documento.save(destino)
    documento.close()
    return destino
