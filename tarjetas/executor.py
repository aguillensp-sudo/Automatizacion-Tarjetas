"""Ejecución de las inserciones en Ninox, con verificación y sin sorpresas.

Protocolo de escritura (know-how de Ninox, verificado en los proyectos hermanos):

1. **Validar** los nombres de campo contra el esquema antes de enviar: un nombre
   mal escrito devuelve HTTP 500, no un 400.
2. **Crear** y **releer**: el eco del POST no es prueba de nada, hay campos con
   valor por defecto que descartan lo enviado. Se compara lo guardado con lo
   pretendido y, si no cuadra, se detiene el proceso y se dice por qué.
3. **Un POST no se reintenta jamás a ciegas.** Si se pierde la respuesta, el
   registro puede haber entrado: se reconcilia leyendo y, si está, se informa;
   si no está, se avisa del error. Nunca se duplica un apunte contable.

El proceso se detiene en el primer error (§3.4 del requisito) y el informe dice
cuántos registros se habían creado y con qué ids, para poder revisarlos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

import config
from ninox_client import (EscrituraIncierta, NinoxClient, NinoxError,
                          NinoxMappingError, primer_id_ref)
from tarjetas.cards import Destino
from tarjetas.mapping import campos_cargo_puntual, describir
from tarjetas.pdf_reader import Operacion, formato_es
from tarjetas.reconciler import Conciliacion, Estado, FilaConciliacion

DECISION_INSERTAR = "I"
DECISION_DESESTIMAR = "D"


class PlanError(Exception):
    """El plan de ejecución no es válido (falta alguna decisión, por ejemplo)."""


@dataclass
class TareaInsercion:
    """Un alta pendiente, con su trazabilidad."""

    origen: str                    # «FW-AGS.pdf · 5566 **** **** 5013»
    base_clave: str
    tabla: str
    campos: dict[str, Any]
    etiqueta: str                  # «movimiento 2026-09-01 · 81,78 €»
    operacion: Operacion | None = None

    @property
    def resumen(self) -> str:
        return "%s · %s · %s" % (self.origen, self.etiqueta, describir(self.campos))


@dataclass
class GrupoPlan:
    """Las inserciones que corresponden a un extracto y una tarjeta."""

    conciliacion: Conciliacion
    tareas: list[TareaInsercion] = field(default_factory=list)
    desestimadas: list[FilaConciliacion] = field(default_factory=list)

    @property
    def etiqueta(self) -> str:
        return "%s · %s · %s" % (self.conciliacion.extracto.nombre,
                                 self.conciliacion.destino.numero_tarjeta_pdf,
                                 self.conciliacion.destino.base_nombre)


@dataclass
class PlanEjecucion:
    grupos: list[GrupoPlan]

    @property
    def tareas(self) -> list[TareaInsercion]:
        return [t for grupo in self.grupos for t in grupo.tareas]

    @property
    def total_inserciones(self) -> int:
        return len(self.tareas)

    @property
    def total_desestimadas(self) -> int:
        return sum(len(g.desestimadas) for g in self.grupos)


@dataclass
class ResultadoEjecucion:
    creados: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    abortado: bool = False

    @property
    def ok(self) -> bool:
        return not self.errores

    @property
    def total_creados(self) -> int:
        return len(self.creados)

    def resumen(self) -> str:
        if self.errores:
            return ("Proceso detenido con error tras %d inserción(es). %s"
                    % (self.total_creados, self.errores[0]))
        return "Proceso completado: %d inserción(es) en Ninox." % self.total_creados


# ──────────────────────────────────────────────────────────────────────────────
# Construcción del plan
# ──────────────────────────────────────────────────────────────────────────────
def clave_decision(conciliacion: Conciliacion, fila: FilaConciliacion) -> tuple[str, int]:
    """Clave estable de una fila con decisión: (fichero, orden en el extracto)."""
    return (conciliacion.extracto.nombre, fila.operacion.orden)


def decisiones_pendientes(conciliaciones: list[Conciliacion],
                          decisiones: dict[tuple[str, int], str]) -> list[FilaConciliacion]:
    """Filas b) y c) que aún no tienen «Insertar» ni «Desestimar»."""
    pendientes: list[FilaConciliacion] = []
    for conciliacion in conciliaciones:
        for fila in conciliacion.decisiones:
            if decisiones.get(clave_decision(conciliacion, fila)) not in (
                    DECISION_INSERTAR, DECISION_DESESTIMAR):
                pendientes.append(fila)
    return pendientes


def construir_plan(conciliaciones: list[Conciliacion],
                   decisiones: dict[tuple[str, int], str]) -> PlanEjecucion:
    """Traduce las decisiones del usuario en la lista de altas a ejecutar."""
    pendientes = decisiones_pendientes(conciliaciones, decisiones)
    if pendientes:
        raise PlanError(
            "Faltan %d registro(s) por decidir: hay que marcar «Insertar» o "
            "«Desestimar» en todos antes de ejecutar." % len(pendientes))

    grupos: list[GrupoPlan] = []
    for conciliacion in conciliaciones:
        destino = conciliacion.destino
        grupo = GrupoPlan(conciliacion=conciliacion)
        origen = "%s · %s" % (conciliacion.extracto.nombre, destino.numero_tarjeta_pdf)

        for fila in conciliacion.nuevas:                      # caso a)
            op = fila.operacion
            grupo.tareas.append(TareaInsercion(
                origen=origen,
                base_clave=destino.base_clave,
                tabla=destino.tabla,
                campos=campos_cargo_puntual(destino, op),
                etiqueta="nuevo · %s · %s € · %s" % (
                    op.fecha.isoformat(), formato_es(op.importe),
                    (op.concepto or "")[:40]),
                operacion=op,
            ))

        for fila in conciliacion.decisiones:                  # casos b) y c)
            decision = decisiones[clave_decision(conciliacion, fila)]
            if decision == DECISION_INSERTAR:
                op = fila.operacion
                grupo.tareas.append(TareaInsercion(
                    origen=origen,
                    base_clave=destino.base_clave,
                    tabla=destino.tabla,
                    campos=campos_cargo_puntual(destino, op),
                    etiqueta="%s (decidido insertar) · %s · %s €" % (
                        fila.estado.value, op.fecha.isoformat(),
                        formato_es(op.importe)),
                    operacion=op,
                ))
            else:
                grupo.desestimadas.append(fila)

        total = conciliacion.extracto.total_operaciones
        grupo.tareas.append(TareaInsercion(                    # §7
            origen=origen,
            base_clave=destino.base_clave,
            tabla=destino.tabla,
            campos=conciliacion.total_mes_campos,
            etiqueta="Total operaciones · %s · %s €" % (
                conciliacion.total_mes_fecha.isoformat(), formato_es(total)),
        ))
        grupos.append(grupo)
    return PlanEjecucion(grupos=grupos)


# ──────────────────────────────────────────────────────────────────────────────
# Ejecución
# ──────────────────────────────────────────────────────────────────────────────
def _verificar(guardado: dict[str, Any], tarea: TareaInsercion) -> list[str]:
    """Compara lo guardado con lo pretendido. Devuelve las discrepancias."""
    campos = guardado.get("fields") or {}
    problemas: list[str] = []

    esperado_tarjeta = int(tarea.campos[config.CAMPO_YB_TARJETA])
    if primer_id_ref(campos.get(config.CAMPO_YB_TARJETA)) != esperado_tarjeta:
        problemas.append("Tarjeta Bancaria=%s (se esperaba %s)"
                         % (campos.get(config.CAMPO_YB_TARJETA), esperado_tarjeta))

    esperado_fecha = tarea.campos[config.CAMPO_YB_FECHA]
    texto_fecha = esperado_fecha.isoformat() if hasattr(esperado_fecha, "isoformat") else esperado_fecha
    if str(campos.get(config.CAMPO_YB_FECHA) or "")[:10] != str(texto_fecha)[:10]:
        problemas.append("Fecha=%s (se esperaba %s)"
                         % (campos.get(config.CAMPO_YB_FECHA), texto_fecha))

    esperado_importe = Decimal(str(tarea.campos[config.CAMPO_YB_IMPORTE])).quantize(Decimal("0.01"))
    leido = Decimal(str(campos.get(config.CAMPO_YB_IMPORTE, 0))).quantize(Decimal("0.01"))
    if abs(leido - esperado_importe) > Decimal("0.005"):
        problemas.append("Importe=%s (se esperaba %s)"
                         % (formato_es(leido), formato_es(esperado_importe)))

    esperado_tipo = (config.TIPO_CARGO_PUNTUAL_TEXTO
                     if str(tarea.campos[config.CAMPO_YB_TIPO]) == config.TIPO_CARGO_PUNTUAL
                     else config.TIPO_CARGO_TOTAL_MES_TEXTO)
    leido_tipo = str(campos.get(config.CAMPO_YB_TIPO) or "")
    if leido_tipo and leido_tipo != esperado_tipo:
        problemas.append("Tipo=%s (se esperaba %s)" % (leido_tipo, esperado_tipo))
    return problemas


def _buscar_tras_perdida(cliente: NinoxClient, tarea: TareaInsercion) -> dict[str, Any] | None:
    """Reconciliación de un alta incierta: ¿llegó el registro a la tabla?"""
    try:
        registros = cliente.fetch_all_records(tarea.tabla, refrescar=True)
    except NinoxError:
        return None
    deseada_fecha = tarea.campos[config.CAMPO_YB_FECHA]
    texto_fecha = deseada_fecha.isoformat() if hasattr(deseada_fecha, "isoformat") else deseada_fecha
    deseado_importe = Decimal(str(tarea.campos[config.CAMPO_YB_IMPORTE])).quantize(Decimal("0.01"))
    deseada_tarjeta = int(tarea.campos[config.CAMPO_YB_TARJETA])
    for registro in registros:
        campos = registro.get("fields") or {}
        if primer_id_ref(campos.get(config.CAMPO_YB_TARJETA)) != deseada_tarjeta:
            continue
        if str(campos.get(config.CAMPO_YB_FECHA) or "")[:10] != str(texto_fecha)[:10]:
            continue
        leido = Decimal(str(campos.get(config.CAMPO_YB_IMPORTE, 0))).quantize(Decimal("0.01"))
        if abs(leido - deseado_importe) <= Decimal("0.005"):
            return registro
    return None


def ejecutar_plan(plan: PlanEjecucion,
                  cliente_de: Callable[[str], NinoxClient],
                  log: Callable[[str], None] | None = None,
                  progreso: Callable[[int, int], None] | None = None) -> ResultadoEjecucion:
    """Ejecuta las altas del plan, deteniéndose en el primer error."""
    def _log(mensaje: str) -> None:
        if log:
            log(mensaje)

    resultado = ResultadoEjecucion()
    tareas = plan.tareas
    for indice, tarea in enumerate(tareas, start=1):
        if progreso:
            progreso(indice - 1, len(tareas))
        cliente = cliente_de(tarea.base_clave)
        _log("→ [%d/%d] %s" % (indice, len(tareas), tarea.resumen))
        try:
            guardado = cliente.crear_registro(tarea.tabla, tarea.campos)
        except EscrituraIncierta as exc:
            _log("   ⚠ Se perdió la respuesta del alta: se comprueba si el registro llegó…")
            encontrado = _buscar_tras_perdida(cliente, tarea)
            if encontrado is not None:
                resultado.creados.append({"tarea": tarea, "id": encontrado.get("id"),
                                          "guardado": encontrado.get("fields") or {}})
                resultado.avisos.append(
                    "%s: el alta llegó pese a perderse la respuesta (registro id %s). "
                    "No se reintenta." % (tarea.etiqueta, encontrado.get("id")))
                _log("   ✔ el registro está en la tabla (id %s): no se reintenta"
                     % encontrado.get("id"))
                continue
            resultado.errores.append("%s: %s" % (tarea.etiqueta, exc))
            resultado.abortado = True
            _log("   ✘ %s" % exc)
            break
        except (NinoxMappingError, NinoxError) as exc:
            resultado.errores.append("%s: %s" % (tarea.etiqueta, exc))
            resultado.abortado = True
            _log("   ✘ %s" % exc)
            break

        problemas = _verificar(guardado, tarea)
        nuevo_id = guardado.get("id")
        resultado.creados.append({"tarea": tarea, "id": nuevo_id,
                                  "guardado": guardado.get("fields") or {}})
        if problemas:
            resultado.errores.append(
                "%s: el registro id %s se guardó con valores distintos de los "
                "enviados (%s). Revisa la configuración de la tabla en Ninox."
                % (tarea.etiqueta, nuevo_id, "; ".join(problemas)))
            resultado.abortado = True
            _log("   ✘ id %s guardado con discrepancias: %s" % (nuevo_id, "; ".join(problemas)))
            break
        _log("   ✔ creado id %s · %s" % (nuevo_id, describir(guardado.get("fields") or {})))

    if progreso:
        progreso(len(tareas) if not resultado.abortado else len(resultado.creados), len(tareas))
    if resultado.creados and resultado.ok:
        _log("✔ Total de inserciones realizadas: %d" % resultado.total_creados)
    return resultado
