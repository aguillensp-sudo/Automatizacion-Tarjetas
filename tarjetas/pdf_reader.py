"""Lectura de los extractos de tarjeta de Banco Sabadell.

Rutina (§4.1 del requisito):

* **Nunca se lee la primera página**: es el resumen de condiciones.
* Se leen la segunda y siguientes hasta la línea **«Total operaciones»**, que es
  la última que se interpreta.
* Las operaciones se localizan por las **coordenadas** de cada palabra, no por el
  orden del texto plano: la extracción de texto devuelve «Importe de la
  operación» antes que «Tipo de cambio aplicado», y agrupar por líneas de texto
  mezclaría importes con tipos de cambio.
* El año de las operaciones (el detalle sólo trae ``DDMM``) se deduce del sello
  de liquidación de la propia página de la tabla, ``MADRID,VERGARA,05.10.26``:
  el período liquidado es el **mes anterior** al del sello. Decisión del PO,
  que evita tener que leer la página 1.
* Comprobación de integridad: la suma de los importes leídos **tiene que
  cuadrar** con el «Total operaciones» del banco; si no, el proceso se detiene.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Iterable

import fitz  # PyMuPDF

import config


class ExtractoError(Exception):
    """El extracto no se ha podido interpretar con seguridad."""


# ──────────────────────────────────────────────────────────────────────────────
# Expresiones regulares
# ──────────────────────────────────────────────────────────────────────────────
RE_MASCARA_TARJETA = re.compile(r"(\d{4})\s+\*{4}\s+\*{4}\s+(\d{4})")
RE_SELLO = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})")
RE_FECHA_DDMM = re.compile(r"^(\d{2})(\d{2})$")
RE_IMPORTE = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}-?$")

#: Textos que marcan el pie de página (fuera de la tabla de operaciones)
MARCAS_PIE = ("www.bancosabadell", "banco de sabadell", "sabadell, s.a.", "nif a08000143")


def _sin_acentos(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in plano if not unicodedata.combining(c)).lower()


def parsear_importe(texto: str) -> Decimal:
    """«1.394,39» → 1394.39 · «23,99-» → -23.99 (el banco marca el negativo al final)."""
    limpio = texto.strip().replace(" ", "")
    negativo = limpio.endswith("-")
    limpio = limpio.rstrip("-")
    limpio = limpio.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(limpio)
    except InvalidOperation as exc:  # pragma: no cover - defensivo
        raise ExtractoError("Importe ilegible: %r" % texto) from exc
    return -valor if negativo else valor


def es_importe(texto: str) -> bool:
    """Un importe de operación: siempre con dos decimales tras coma."""
    return bool(RE_IMPORTE.match(texto.strip()))


def formato_es(valor: Decimal | float) -> str:
    """1234.5 → «1.234,50» (formato español, para logs y pantalla)."""
    texto = "{:,.2f}".format(Decimal(str(valor)))
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


# ──────────────────────────────────────────────────────────────────────────────
# Modelo
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class Operacion:
    """Un movimiento del extracto."""

    fecha: date
    fecha_pdf: str                 # «0109», tal cual viene
    concepto: str
    poblacion: str
    importe_origen: str            # «880,00 MAD» (informativo)
    tipo_cambio: str               # «0,0929» (informativo)
    importe: Decimal               # «Importe de la operación»
    pagina: int
    orden: int

    @property
    def descripcion(self) -> str:
        return "%s · %s" % (self.fecha.isoformat(), self.concepto or "(sin concepto)")


@dataclass
class ExtractoPDF:
    """Resultado de leer un extracto completo."""

    ruta: Path
    numero_tarjeta: str            # «5566 **** **** 5013»
    tipo_tarjeta: str              # «BUSINESS MASTERCARD»
    fecha_liquidacion: date        # del sello MADRID,VERGARA,DD.MM.AA
    operaciones: list[Operacion] = field(default_factory=list)
    total_operaciones: Decimal = Decimal("0")
    suma_importes: Decimal = Decimal("0")
    paginas: int = 0

    @property
    def nombre(self) -> str:
        return self.ruta.name

    @property
    def mes_operaciones(self) -> int:
        """Mes del período liquidado: el anterior al del sello."""
        mes = self.fecha_liquidacion.month - 1
        return mes or 12

    @property
    def anio_operaciones(self) -> int:
        if self.fecha_liquidacion.month == 1:
            return self.fecha_liquidacion.year - 1
        return self.fecha_liquidacion.year

    @property
    def periodo_texto(self) -> str:
        return "%02d/%d" % (self.mes_operaciones, self.anio_operaciones)

    @property
    def fecha_cargo_total_mes(self) -> date:
        """Día 5 del mes de la liquidación (decisión del PO, §7 del requisito)."""
        return date(self.fecha_liquidacion.year, self.fecha_liquidacion.month, 5)


# ──────────────────────────────────────────────────────────────────────────────
# Núcleo del parser
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class _Linea:
    y: float
    palabras: list[tuple[float, float, float, float, str]]

    @property
    def texto(self) -> str:
        # Orden por X: dentro de una misma línea visual el orden de las palabras
        # es el de izquierda a derecha, no el de la coordenada Y exacta.
        return " ".join(p[4] for p in sorted(self.palabras, key=lambda p: p[0]))


def _lineas_de_pagina(pagina: fitz.Page) -> list[_Linea]:
    """Agrupa las palabras de una página en líneas visuales."""
    palabras = pagina.get_text("words")
    lineas: list[_Linea] = []
    actual: _Linea | None = None
    for x0, y0, x1, y1, texto, *_ in sorted(palabras, key=lambda p: (round(p[1], 1), p[0])):
        if actual is None or abs(y0 - actual.y) > 2.0:
            actual = _Linea(y=y0, palabras=[])
            lineas.append(actual)
        actual.palabras.append((x0, y0, x1, y1, texto))
    return lineas


def _columna(x0: float) -> str | None:
    """Columna a la que pertenece una palabra según su coordenada X."""
    if x0 < config.COL_FECHA_MAX:
        return "fecha"
    if x0 < config.COL_CONCEPTO_MAX:
        return "concepto"
    if x0 < config.COL_POBLACION_MAX:
        return "poblacion"
    if x0 < config.COL_IMPORTE_ORIGEN_MAX:
        return "importe_origen"
    if x0 < config.COL_TIPO_CAMBIO_MAX:
        return "tipo_cambio"
    if x0 < config.COL_IMPORTE_OP_MAX:
        return "importe_operacion"
    return None                      # «Días» y «Números»: no se usan


def _repartir_por_columna(linea: _Linea) -> dict[str, list[str]]:
    columnas: dict[str, list[str]] = {}
    for x0, _y0, _x1, _y1, texto in sorted(linea.palabras, key=lambda p: p[0]):
        col = _columna(x0)
        if col is None:
            continue
        columnas.setdefault(col, []).append(texto)
    return columnas


def _importe_de_columna(linea: _Linea) -> Decimal | None:
    """Importe de la operación de una línea, si lo lleva."""
    for x0, _y0, _x1, _y1, texto in sorted(linea.palabras, key=lambda p: p[0]):
        if config.COL_IMPORTE_OP_MIN <= x0 < config.COL_IMPORTE_OP_MAX and es_importe(texto):
            return parsear_importe(texto)
    return None


def _fecha_de_linea(linea: _Linea) -> tuple[str, int, int] | None:
    """Devuelve (texto, día, mes) si la línea arranca una operación."""
    for x0, _y0, _x1, _y1, texto in sorted(linea.palabras, key=lambda p: p[0]):
        if x0 < config.COL_FECHA_MAX:
            m = RE_FECHA_DDMM.match(texto.strip())
            if m:
                dia, mes = int(m.group(1)), int(m.group(2))
                if 1 <= dia <= 31 and 1 <= mes <= 12:
                    return texto.strip(), dia, mes
            return None              # la primera palabra de la columna no es una fecha
    return None


def leer_extracto(ruta: str | Path, log: Callable[[str], None] | None = None) -> ExtractoPDF:
    """Lee un extracto y devuelve sus operaciones y su total.

    Lanza ``ExtractoError`` si el fichero no cumple el formato esperado o si la
    suma de importes no cuadra con el total del banco.
    """
    def _log(mensaje: str) -> None:
        if log:
            log(mensaje)

    ruta = Path(ruta)
    if not ruta.exists():
        raise ExtractoError("No existe el fichero %s" % ruta)

    try:
        documento = fitz.open(ruta)
    except Exception as exc:  # pragma: no cover - PDF corrupto
        raise ExtractoError("No se puede abrir %s: %s" % (ruta.name, exc)) from exc

    numero_tarjeta = ""
    tipo_tarjeta = ""
    fecha_liquidacion: date | None = None
    operaciones: list[Operacion] = []
    total: Decimal | None = None
    total_encontrado = False
    orden = 0
    paginas = 0

    try:
        paginas = documento.page_count
        if paginas < 2:
            raise ExtractoError(
                "%s tiene %d página(s): no hay detalle de operaciones (la primera "
                "página no se lee nunca)." % (ruta.name, paginas))

        for indice in range(1, paginas):
            if total_encontrado:
                break
            pagina = documento[indice]
            lineas = _lineas_de_pagina(pagina)

            # Cabecera de la página: número y tipo de tarjeta, sello de liquidación
            for linea in lineas:
                bajo = _sin_acentos(linea.texto)
                if not numero_tarjeta and _sin_acentos(config.TEXTO_NUMERO_TARJETA) in bajo:
                    m = RE_MASCARA_TARJETA.search(linea.texto)
                    if m:
                        numero_tarjeta = "%s **** **** %s" % (m.group(1), m.group(2))
                        resto = linea.texto[m.end():].strip()
                        if resto:
                            tipo_tarjeta = resto
                if fecha_liquidacion is None and config.TEXTO_SELLO_LIQUIDACION in linea.texto.upper():
                    m = RE_SELLO.search(linea.texto)
                    if m:
                        dia, mes, anio = (int(g) for g in m.groups())
                        try:
                            fecha_liquidacion = date(2000 + anio, mes, dia)
                        except ValueError:      # pragma: no cover - fecha imposible
                            pass

            # Límites verticales de la tabla
            y_cabecera: float | None = None
            y_pie = float("inf")
            for linea in lineas:
                bajo = _sin_acentos(linea.texto)
                if y_cabecera is None and "fecha" in bajo and "concepto" in bajo:
                    y_cabecera = linea.y
                if any(marca in bajo for marca in MARCAS_PIE):
                    y_pie = min(y_pie, linea.y)
            if y_cabecera is None:
                continue

            for linea in lineas:
                if linea.y <= y_cabecera or linea.y >= y_pie:
                    continue
                columnas = _repartir_por_columna(linea)
                texto_concepto = " ".join(columnas.get("concepto", []))
                if _sin_acentos(texto_concepto).startswith(config.TEXTO_TOTAL_OPERACIONES):
                    importe_total = _importe_de_columna(linea)
                    if importe_total is None:
                        raise ExtractoError(
                            "%s: la línea «Total operaciones» no lleva importe legible."
                            % ruta.name)
                    total = importe_total
                    total_encontrado = True
                    break

                fecha_linea = _fecha_de_linea(linea)
                if fecha_linea is not None:
                    texto_fecha, dia, mes = fecha_linea
                    orden += 1
                    operaciones.append(Operacion(
                        fecha=date(1900, mes, dia),      # el año se fija al final
                        fecha_pdf=texto_fecha,
                        concepto=texto_concepto,
                        poblacion=" ".join(columnas.get("poblacion", [])),
                        importe_origen=" ".join(columnas.get("importe_origen", [])),
                        tipo_cambio=" ".join(columnas.get("tipo_cambio", [])),
                        importe=_importe_de_columna(linea) or Decimal("0"),
                        pagina=indice + 1,
                        orden=orden,
                    ))
                    continue

                # Línea de continuación: conceptos largos que ocupan dos renglones
                if operaciones and (texto_concepto or columnas.get("poblacion")):
                    op = operaciones[-1]
                    if texto_concepto:
                        op.concepto = ("%s %s" % (op.concepto, texto_concepto)).strip()
                    if columnas.get("poblacion"):
                        op.poblacion = ("%s %s" % (op.poblacion,
                                                   " ".join(columnas["poblacion"]))).strip()
                    if not op.importe_origen and columnas.get("importe_origen"):
                        op.importe_origen = " ".join(columnas["importe_origen"])
                    if not op.tipo_cambio and columnas.get("tipo_cambio"):
                        op.tipo_cambio = " ".join(columnas["tipo_cambio"])
                    importe_continuacion = _importe_de_columna(linea)
                    if op.importe == 0 and importe_continuacion is not None:
                        op.importe = importe_continuacion
    finally:
        documento.close()

    # ── Validaciones ─────────────────────────────────────────────────────────
    if not numero_tarjeta:
        raise ExtractoError(
            "%s: no se encuentra el «Número de tarjeta» en el detalle de "
            "operaciones." % ruta.name)
    if fecha_liquidacion is None:
        raise ExtractoError(
            "%s: no se encuentra el sello de liquidación (MADRID,VERGARA,DD.MM.AA) "
            "en el detalle de operaciones." % ruta.name)
    if not operaciones:
        raise ExtractoError("%s: no se ha leído ninguna operación." % ruta.name)
    if not total_encontrado or total is None:
        raise ExtractoError(
            "%s: no se ha encontrado la línea «Total operaciones», que marca el final "
            "de la tabla." % ruta.name)

    extracto = ExtractoPDF(
        ruta=ruta,
        numero_tarjeta=numero_tarjeta,
        tipo_tarjeta=tipo_tarjeta,
        fecha_liquidacion=fecha_liquidacion,
        operaciones=[],
        total_operaciones=total,
        paginas=paginas,
    )
    for op in operaciones:
        op.fecha = date(extracto.anio_operaciones, op.fecha.month, op.fecha.day)
        if op.importe == 0:
            raise ExtractoError(
                "%s: la operación del %s (%s) no tiene importe legible."
                % (ruta.name, op.fecha_pdf, op.concepto or "sin concepto"))
        extracto.operaciones.append(op)
    extracto.suma_importes = sum((op.importe for op in extracto.operaciones), Decimal("0"))

    if abs(extracto.suma_importes - extracto.total_operaciones) > Decimal(str(config.TOLERANCIA_TOTAL)):
        raise ExtractoError(
            "%s: la suma de los %d importes leídos (%s) no cuadra con el «Total "
            "operaciones» del banco (%s). Se detiene el proceso para no registrar "
            "datos incompletos." % (ruta.name, len(extracto.operaciones),
                                    formato_es(extracto.suma_importes),
                                    formato_es(extracto.total_operaciones)))

    _log("  · %s: tarjeta %s · liquidación %s · período %s · %d operaciones · total %s"
         % (ruta.name, numero_tarjeta, fecha_liquidacion.isoformat(),
            extracto.periodo_texto, len(extracto.operaciones),
            formato_es(extracto.total_operaciones)))
    return extracto


def listar_pdfs(carpeta: str | Path) -> list[Path]:
    """Ficheros PDF de la carpeta de trabajo, ordenados por nombre."""
    carpeta = Path(carpeta)
    if not carpeta.exists():
        raise ExtractoError("No existe la carpeta de trabajo %s" % carpeta)
    return sorted((p for p in carpeta.iterdir()
                   if p.is_file() and p.suffix.lower() == ".pdf"),
                  key=lambda p: p.name.lower())


def leer_extractos(rutas: Iterable[str | Path],
                   log: Callable[[str], None] | None = None) -> list[ExtractoPDF]:
    """Lee varios extractos en orden."""
    return [leer_extracto(r, log=log) for r in rutas]
