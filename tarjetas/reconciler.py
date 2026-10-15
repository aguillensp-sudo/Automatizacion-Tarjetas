"""Comparación de las operaciones del extracto contra la tabla `YB` de Ninox.

Casuísticas del requisito (§5):

| Caso | Condición | Estado |
|---|---|---|
| **a** | No hay ningún movimiento de esa tarjeta con esa fecha | `NUEVO` → se cuenta para insertar |
| **b** | Existe uno con la **misma fecha y el mismo importe** | `COINCIDENCIA` → se avisa y el usuario decide |
| **c** | Existe uno con la **misma fecha y distinto importe** | `INCIDENCIA` → se avisa y el usuario decide |

El importe que se compara es el **calculado por Ninox**, `D` + `J` (Importe +
Importe IVA deducible), según la decisión del PO del 15/10/2026.

Detalles que evitan falsos avisos:

* El emparejamiento es **1 a 1**: dos consumos idénticos el mismo día (dos cafés)
  consumen dos registros distintos, y el segundo no se marca como nuevo si hay
  dos coincidencias disponibles.
* Los registros con `G = 2` «Cargo Total Mes» **no cuentan** como coincidencia de
  una operación: son el apunte de la liquidación, no el consumo. La suma del mes
  puede coincidir con una operación suelta y no por eso está registrada.
* Si el registro de «Cargo Total Mes» de este período **ya existe** (con el mismo
  importe), se avisa: volver a procesar el mismo extracto lo duplicaría.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

import config
from ninox_client import NinoxClient, primer_id_ref
from tarjetas.cards import Destino
from tarjetas.mapping import campos_cargo_total_mes
from tarjetas.pdf_reader import ExtractoPDF, Operacion, formato_es

TOLERANCIA_IMPORTE = Decimal("0.005")


class Estado(str, Enum):
    """Clasificación de una línea del extracto."""

    NUEVO = "nuevo"
    COINCIDENCIA = "coincidencia"
    INCIDENCIA = "incidencia"

    @property
    def etiqueta(self) -> str:
        return {
            Estado.NUEVO: "No existe en Ninox",
            Estado.COINCIDENCIA: "Coincidencia exacta (fecha e importe)",
            Estado.INCIDENCIA: "Incidencia (misma fecha, importe distinto)",
        }[self]


def _a_decimal(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return Decimal("0")
    try:
        return Decimal(str(valor))
    except Exception:  # pragma: no cover - dato corrupto en Ninox
        return Decimal("0")


def _a_fecha(valor: Any) -> date | None:
    if isinstance(valor, str) and len(valor) >= 10:
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None
    return None


@dataclass
class MovimientoNinox:
    """Un registro de `YB` ya existente, con el importe que se compara."""

    id: int
    fecha: date | None
    importe_d: Decimal
    importe_j: Decimal
    tipo: str
    campos: dict[str, Any] = field(default_factory=dict)

    @property
    def importe_total(self) -> Decimal:
        """Importe calculado por la aplicación: `D` + `J`."""
        return (self.importe_d + self.importe_j).quantize(Decimal("0.01"))

    @property
    def es_cargo_total_mes(self) -> bool:
        return self.tipo == config.TIPO_CARGO_TOTAL_MES_TEXTO

    @property
    def fecha_texto(self) -> str:
        return self.fecha.isoformat() if self.fecha else "(sin fecha)"

    @property
    def importe_texto(self) -> str:
        return formato_es(self.importe_total)

    def coincide_con(self, operacion: Operacion) -> bool:
        if self.fecha != operacion.fecha:
            return False
        return abs(self.importe_total - operacion.importe.quantize(Decimal("0.01"))) <= TOLERANCIA_IMPORTE

    def descripcion(self) -> str:
        return "%s · %s € · %s · registro id %d" % (
            self.fecha_texto, self.importe_texto, self.tipo or "(sin tipo)", self.id)


@dataclass
class FilaConciliacion:
    """Una operación del extracto y su veredicto."""

    operacion: Operacion
    estado: Estado
    ninox: MovimientoNinox | None = None

    @property
    def decision_requerida(self) -> bool:
        """Los casos b) y c) necesitan que el usuario decida insertar o desestimar."""
        return self.estado is not Estado.NUEVO


@dataclass
class Conciliacion:
    """Resultado completo de comparar un extracto contra su tabla de Ninox."""

    extracto: ExtractoPDF
    destino: Destino
    filas: list[FilaConciliacion]
    movimientos_tarjeta: list[MovimientoNinox]
    total_mes_campos: dict[str, Any]
    total_mes_previo: MovimientoNinox | None = None

    @property
    def nuevas(self) -> list[FilaConciliacion]:
        return [f for f in self.filas if f.estado is Estado.NUEVO]

    @property
    def coincidencias(self) -> list[FilaConciliacion]:
        return [f for f in self.filas if f.estado is Estado.COINCIDENCIA]

    @property
    def incidencias(self) -> list[FilaConciliacion]:
        return [f for f in self.filas if f.estado is Estado.INCIDENCIA]

    @property
    def decisiones(self) -> list[FilaConciliacion]:
        return [f for f in self.filas if f.decision_requerida]

    @property
    def total_mes_fecha(self) -> date:
        return self.extracto.fecha_cargo_total_mes

    @property
    def total_mes_importe(self) -> Decimal:
        return self.extracto.total_operaciones

    def resumen(self) -> str:
        return ("%s · %s: %d movimientos → %d nuevos, %d coincidencias, %d incidencias"
                % (self.extracto.nombre, self.destino.numero_tarjeta_pdf,
                   len(self.filas), len(self.nuevas), len(self.coincidencias),
                   len(self.incidencias)))


def movimientos_de_tarjeta(cliente: NinoxClient, tabla: str, xb_id: int,
                           log: Callable[[str], None] | None = None) -> list[MovimientoNinox]:
    """Todos los movimientos de `YB` de una tarjeta, con D y J ya leídos.

    La tabla se descarga **una sola vez por base y proceso** (la caché del
    cliente): dos extractos de la misma empresa no vuelven a barrer las mismas
    páginas. No se fuerza el refresco porque la conciliación siempre ocurre antes
    de cualquier escritura del proceso; tras insertar, la caché se invalida.
    """
    registros = cliente.fetch_all_records(tabla)
    movimientos: list[MovimientoNinox] = []
    for registro in registros:
        campos = registro.get("fields") or {}
        if primer_id_ref(campos.get(config.CAMPO_YB_TARJETA)) != xb_id:
            continue
        movimientos.append(MovimientoNinox(
            id=int(registro.get("id")),
            fecha=_a_fecha(campos.get(config.CAMPO_YB_FECHA)),
            importe_d=_a_decimal(campos.get(config.CAMPO_YB_IMPORTE)),
            importe_j=_a_decimal(campos.get(config.CAMPO_YB_IMPORTE_IVA)),
            tipo=str(campos.get(config.CAMPO_YB_TIPO) or ""),
            campos=campos,
        ))
    movimientos.sort(key=lambda m: (m.fecha or date.min, m.id))
    if log:
        log("  · %s: %d registros leídos en `%s` para la tarjeta XB %s"
            % (cliente.etiqueta, len(movimientos), tabla, xb_id))
    return movimientos


def conciliar(extracto: ExtractoPDF,
              destino: Destino,
              cliente: NinoxClient,
              log: Callable[[str], None] | None = None) -> Conciliacion:
    """Compara el extracto con Ninox y clasifica cada operación."""
    movimientos = movimientos_de_tarjeta(cliente, destino.tabla, destino.xb_id, log=log)
    # Los apuntes de liquidación («Cargo Total Mes») no son consumos: no pueden
    # hacer que una operación se dé por registrada.
    candidatos = [m for m in movimientos if not m.es_cargo_total_mes]
    usados: set[int] = set()
    filas: list[FilaConciliacion] = []

    for operacion in extracto.operaciones:
        exacto = next((m for m in candidatos
                       if m.id not in usados and m.coincide_con(operacion)), None)
        if exacto is not None:
            usados.add(exacto.id)
            filas.append(FilaConciliacion(operacion, Estado.COINCIDENCIA, exacto))
            continue
        misma_fecha = next((m for m in candidatos
                            if m.id not in usados and m.fecha == operacion.fecha), None)
        if misma_fecha is not None:
            usados.add(misma_fecha.id)
            filas.append(FilaConciliacion(operacion, Estado.INCIDENCIA, misma_fecha))
            continue
        filas.append(FilaConciliacion(operacion, Estado.NUEVO, None))

    campos_total = campos_cargo_total_mes(destino, extracto.fecha_cargo_total_mes,
                                          extracto.total_operaciones)
    previo = next((m for m in movimientos
                   if m.es_cargo_total_mes
                   and m.fecha == extracto.fecha_cargo_total_mes
                   and abs(m.importe_total - extracto.total_operaciones.quantize(Decimal("0.01")))
                   <= TOLERANCIA_IMPORTE), None)

    conciliacion = Conciliacion(
        extracto=extracto,
        destino=destino,
        filas=filas,
        movimientos_tarjeta=movimientos,
        total_mes_campos=campos_total,
        total_mes_previo=previo,
    )
    if log:
        log("  · " + conciliacion.resumen())
        for fila in filas:
            if fila.estado is Estado.INCIDENCIA and fila.ninox is not None:
                log("      ⚠ incidencia %s: el PDF dice %s € y Ninox tiene %s"
                    % (fila.operacion.fecha.isoformat(),
                       formato_es(fila.operacion.importe), fila.ninox.importe_texto))
        if previo is not None:
            log("      ⚠ ya existe un «Cargo Total Mes» de este período (%s) con importe %s "
                "(registro id %d): la inserción del total crearía un duplicado."
                % (previo.fecha_texto, previo.importe_texto, previo.id))
    return conciliacion
