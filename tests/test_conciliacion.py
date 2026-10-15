"""Pruebas de tarjetas, mapeo y conciliación, con un cliente de Ninox falso.

No se toca la red: el cliente falso reproduce la forma de los registros de la
API (``{"id": …, "fields": {nombre: valor}}``), que es lo que consume la lógica.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

import config
from ninox_client import EscrituraIncierta, NinoxError
from tarjetas import cards, executor, mapping
from tarjetas.cards import Destino, TarjetaError, mascara_desde_entero
from tarjetas.pdf_reader import leer_extracto
from tarjetas.reconciler import (Estado, conciliar, movimientos_de_tarjeta)
from tests.sintetico import crear_pdf


# ──────────────────────────────────────────────────────────────────────────────
# Cliente falso
# ──────────────────────────────────────────────────────────────────────────────
class ClienteFalso:
    """Imita lo mínimo de ``NinoxClient`` que usa la lógica de negocio."""

    def __init__(self, etiqueta: str, registros: list[dict] | None = None,
                 catalogo: dict[int, dict] | None = None,
                 excepciones: list[Exception] | None = None,
                 guardado_alterado: dict | None = None) -> None:
        self.etiqueta = etiqueta
        self._registros = list(registros or [])
        self._catalogo = dict(catalogo or {})
        self._excepciones = list(excepciones or [])
        self._guardado_alterado = guardado_alterado
        self.creados: list[dict] = []
        self._siguiente_id = 9000

    def fetch_all_records(self, tabla, refrescar=False):        # noqa: ARG002
        return [dict(r) for r in self._registros]

    def get_record(self, tabla, record_id):                     # noqa: ARG002
        return self._catalogo.get(record_id)

    def invalidar_cache(self, tabla=None):                      # noqa: ARG002
        return None

    def crear_registro(self, tabla, campos):                    # noqa: ARG002
        if self._excepciones:
            raise self._excepciones.pop(0)
        self._siguiente_id += 1
        guardado = dict(campos)
        if self._guardado_alterado:
            guardado.update(self._guardado_alterado)
        campos_api = {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                      for k, v in guardado.items()}
        campos_api[config.CAMPO_YB_TIPO] = (
            config.TIPO_CARGO_PUNTUAL_TEXTO
            if str(guardado.get(config.CAMPO_YB_TIPO)) == config.TIPO_CARGO_PUNTUAL
            else config.TIPO_CARGO_TOTAL_MES_TEXTO)
        registro = {"id": self._siguiente_id, "fields": campos_api}
        self.creados.append(registro)
        self._registros.append(registro)
        return registro


class FabricaFalsa:
    """Sustituto de ``pipeline.FabricaClientes``: devuelve siempre el mismo cliente."""

    def __init__(self, cliente: ClienteFalso) -> None:
        self._cliente = cliente

    def __call__(self, base_clave: str) -> ClienteFalso:        # noqa: ARG002
        return self._cliente

    def todos(self) -> dict[str, ClienteFalso]:
        return {self._cliente.etiqueta: self._cliente}


def _registro(rid: int, fecha: str, importe: float | None, tipo: str = "Cargo puntual",
              iva: float | None = None, tarjeta: int = 13) -> dict:
    campos = {config.CAMPO_YB_TARJETA: tarjeta, config.CAMPO_YB_FECHA: fecha,
              config.CAMPO_YB_TIPO: tipo}
    if importe is not None:
        campos[config.CAMPO_YB_IMPORTE] = importe
    if iva is not None:
        campos[config.CAMPO_YB_IMPORTE_IVA] = iva
    return {"id": rid, "fields": campos}


def _extracto(tmp_path):
    return leer_extracto(crear_pdf(tmp_path / "extracto.pdf"))


def _destino() -> Destino:
    definicion = config.TARJETAS["5566 **** **** 5013"]
    base = config.BASES[str(definicion["base"])]
    return Destino(
        base_clave=str(definicion["base"]), base_id=base["id"],
        base_nombre=base["nombre"], tabla=base["tabla_yb"],
        tabla_nombre=base["tabla_yb_nombre"], xb_id=int(definicion["xb_id"]),
        titular=str(definicion["titular"]),
        numero_tarjeta_pdf="5566 **** **** 5013",
        etiqueta_tarjeta=str(definicion["etiqueta"]))


# ──────────────────────────────────────────────────────────────────────────────
# Tarjetas
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("numero, esperado", [
    ("5566710954255013", "5566 **** **** 5013"),
    ("4106410061924011", "4106 **** **** 4011"),
    ("5566 7109 5425 1012", "5566 **** **** 1012"),
    ("9192 2900 0232 0089  ", "9192 **** **** 0089"),
    ("1234", None),
    ("", None),
])
def test_mascara_desde_entero(numero, esperado):
    assert mascara_desde_entero(numero) == esperado


def test_resolver_destino_verifica_el_numero_en_ninox(tmp_path):
    extracto = _extracto(tmp_path)
    catalogo = {13: {"id": 13, "fields": {
        "Número": "5566710954255013", "Titular": "ALVARO M. GUILLEN"}}}
    fabrica = lambda clave: ClienteFalso(config.BASES[clave]["nombre"], catalogo=catalogo)
    destino = cards.resolver_destino(extracto, fabrica, log=lambda _m: None)
    assert destino.base_clave == config.DB_FAWALT
    assert destino.xb_id == 13
    assert destino.titular == "ALVARO M. GUILLEN"
    assert destino.tabla == "YB"


def test_resolver_destino_aborta_si_el_id_no_corresponde(tmp_path):
    """Si el id fijo apunta a otra tarjeta, se detiene en vez de imputar mal."""
    extracto = _extracto(tmp_path)
    catalogo = {13: {"id": 13, "fields": {"Número": "5566710954251012"}}}
    fabrica = lambda clave: ClienteFalso(config.BASES[clave]["nombre"], catalogo=catalogo)
    with pytest.raises(TarjetaError) as info:
        cards.resolver_destino(extracto, fabrica)
    assert "no corresponde" in str(info.value)


def test_resolver_destino_aborta_si_falta_el_registro(tmp_path):
    extracto = _extracto(tmp_path)
    fabrica = lambda clave: ClienteFalso(config.BASES[clave]["nombre"], catalogo={})
    with pytest.raises(TarjetaError) as info:
        cards.resolver_destino(extracto, fabrica)
    assert "no existe el registro" in str(info.value)


def test_tarjeta_no_contemplada(tmp_path):
    extracto = leer_extracto(crear_pdf(tmp_path / "otra.pdf",
                                       numero="9999 **** **** 0001"))
    fabrica = lambda clave: ClienteFalso(config.BASES[clave]["nombre"])
    with pytest.raises(TarjetaError) as info:
        cards.resolver_destino(extracto, fabrica)
    assert "no está contemplada" in str(info.value)


# ──────────────────────────────────────────────────────────────────────────────
# Mapeo
# ──────────────────────────────────────────────────────────────────────────────
def test_campos_cargo_puntual(tmp_path):
    extracto = _extracto(tmp_path)
    operacion = extracto.operaciones[0]
    campos = mapping.campos_cargo_puntual(_destino(), operacion)
    assert campos == {
        "Tarjeta Bancaria": 13,
        "Fecha": date(2026, 9, 1),
        "Importe": 81.78,
        "Tipo": "1",
    }


def test_campos_cargo_total_mes(tmp_path):
    extracto = _extracto(tmp_path)
    campos = mapping.campos_cargo_total_mes(_destino(), extracto.fecha_cargo_total_mes,
                                           extracto.total_operaciones)
    assert campos == {
        "Tarjeta Bancaria": 13,
        "Fecha": date(2026, 10, 5),
        "Importe": 235.50,
        "Tipo": "2",
    }
    assert "Tipo=Cargo Total Mes" in mapping.describir(campos)


# ──────────────────────────────────────────────────────────────────────────────
# Conciliación
# ──────────────────────────────────────────────────────────────────────────────
def test_conciliacion_casuisticas_a_b_c(tmp_path):
    extracto = _extracto(tmp_path)
    registros = [
        _registro(1, "2026-09-01", 81.78),
        _registro(2, "2026-09-01", 2.86),
        _registro(3, "2026-09-17", 170.00),          # misma fecha, otro importe → c)
    ]
    cliente = ClienteFalso("FAWALT INVESTMENT", registros)
    resultado = conciliar(extracto, _destino(), cliente)

    assert [f.estado for f in resultado.filas] == [
        Estado.COINCIDENCIA, Estado.COINCIDENCIA, Estado.INCIDENCIA, Estado.NUEVO]
    assert [f.ninox.id for f in resultado.filas[:3]] == [1, 2, 3]
    assert resultado.filas[3].ninox is None
    assert len(resultado.nuevas) == 1
    assert len(resultado.coincidencias) == 2
    assert len(resultado.incidencias) == 1
    assert len(resultado.decisiones) == 3


def test_el_importe_comparado_es_d_mas_j(tmp_path):
    """Decisión del PO: se compara contra `D + J`, no contra `D` a secas."""
    extracto = _extracto(tmp_path)
    registros = [_registro(1, "2026-09-01", 80.00, iva=1.78)]
    resultado = conciliar(extracto, _destino(),
                          ClienteFalso("FAWALT INVESTMENT", registros))
    assert resultado.filas[0].estado is Estado.COINCIDENCIA
    assert resultado.filas[0].ninox.importe_total == Decimal("81.78")


def test_un_cargo_total_mes_no_hace_coincidir_una_operacion(tmp_path):
    extracto = _extracto(tmp_path)
    registros = [
        _registro(1, "2026-09-01", 81.78),
        _registro(2, "2026-09-01", 2.86),
        _registro(3, "2026-09-17", 170.00),
        # Un apunte de liquidación con fecha e importe idénticos a la devolución
        _registro(4, "2026-09-22", -23.99, tipo="Cargo Total Mes"),
    ]
    resultado = conciliar(extracto, _destino(),
                          ClienteFalso("FAWALT INVESTMENT", registros))
    assert resultado.filas[3].estado is Estado.NUEVO


def test_dos_operaciones_iguales_consumen_dos_registros(tmp_path):
    """El emparejamiento es 1 a 1: no se marca como nuevo lo que ya está dos veces."""
    extracto = _extracto(tmp_path)
    registros = [
        _registro(1, "2026-09-01", 81.78), _registro(2, "2026-09-01", 81.78),
        _registro(3, "2026-09-01", 2.86),
    ]
    resultado = conciliar(extracto, _destino(),
                          ClienteFalso("FAWALT INVESTMENT", registros))
    assert resultado.filas[0].estado is Estado.COINCIDENCIA
    assert resultado.filas[1].estado is Estado.COINCIDENCIA


def test_un_solo_registro_no_cubre_dos_operaciones(tmp_path):
    extracto = leer_extracto(crear_pdf(tmp_path / "doble.pdf", operaciones=[
        {"fecha": "0109", "concepto": "CAFE", "poblacion": "MADRID",
         "importe_origen": "2,50", "importe": "2,50"},
        {"fecha": "0109", "concepto": "CAFE", "poblacion": "MADRID",
         "importe_origen": "2,50", "importe": "2,50"},
    ], total="5,00"))
    registros = [_registro(1, "2026-09-01", 2.50)]
    resultado = conciliar(extracto, _destino(),
                          ClienteFalso("FAWALT INVESTMENT", registros))
    assert [f.estado for f in resultado.filas] == [Estado.COINCIDENCIA, Estado.NUEVO]


def test_avisa_si_el_total_mes_ya_existe(tmp_path):
    extracto = _extracto(tmp_path)
    registros = [_registro(437, "2026-10-05", 235.50, tipo="Cargo Total Mes")]
    resultado = conciliar(extracto, _destino(),
                          ClienteFalso("FAWALT INVESTMENT", registros))
    assert resultado.total_mes_previo is not None
    assert resultado.total_mes_previo.id == 437


def test_solo_se_leen_los_registros_de_la_tarjeta(tmp_path):
    registros = [
        _registro(1, "2026-09-01", 81.78, tarjeta=13),
        _registro(2, "2026-09-01", 81.78, tarjeta=99),
    ]
    movimientos = movimientos_de_tarjeta(ClienteFalso("FAWALT INVESTMENT", registros),
                                         "YB", 13)
    assert [m.id for m in movimientos] == [1]


# ──────────────────────────────────────────────────────────────────────────────
# Plan de ejecución y ejecución
# ──────────────────────────────────────────────────────────────────────────────
def _plan(tmp_path, decisiones_todas: str | None = None):
    extracto = _extracto(tmp_path)
    registros = [
        _registro(1, "2026-09-01", 81.78),
        _registro(2, "2026-09-01", 2.86),
        _registro(3, "2026-09-17", 170.00),
    ]
    cliente = ClienteFalso("FAWALT INVESTMENT", registros)
    conciliacion = conciliar(extracto, _destino(), cliente)
    decisiones: dict[tuple[str, int], str] = {}
    if decisiones_todas:
        for fila in conciliacion.decisiones:
            decisiones[(extracto.nombre, fila.operacion.orden)] = decisiones_todas
    return conciliacion, decisiones, cliente


def test_plan_exige_todas_las_decisiones(tmp_path):
    conciliacion, decisiones, _ = _plan(tmp_path)
    with pytest.raises(executor.PlanError) as info:
        executor.construir_plan([conciliacion], decisiones)
    assert "Faltan 3" in str(info.value)


def test_plan_marca_desestimadas_y_conserva_el_total(tmp_path):
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_DESESTIMAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    # Quedan por insertar el registro nuevo (la devolución no está en Ninox) y el
    # «Total operaciones», que siempre se crea (§7).
    assert plan.total_inserciones == 2
    assert plan.total_desestimadas == 3
    ultima = plan.tareas[-1]
    assert ultima.campos[config.CAMPO_YB_TIPO] == config.TIPO_CARGO_TOTAL_MES
    assert ultima.campos[config.CAMPO_YB_FECHA] == date(2026, 10, 5)
    assert ultima.campos[config.CAMPO_YB_IMPORTE] == 235.50
    assert plan.tareas[0].campos[config.CAMPO_YB_IMPORTE] == -23.99


def test_plan_inserta_lo_decidido_y_lo_nuevo(tmp_path):
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_INSERTAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    # 3 coincidencias/incidencias + 1 nuevo + 1 total mensual
    assert plan.total_inserciones == 5
    assert plan.total_desestimadas == 0
    tipos = [t.campos[config.CAMPO_YB_TIPO] for t in plan.tareas]
    assert tipos.count(config.TIPO_CARGO_PUNTUAL) == 4
    assert tipos.count(config.TIPO_CARGO_TOTAL_MES) == 1


def test_ejecucion_feliz(tmp_path):
    conciliacion, decisiones, cliente = _plan(tmp_path, executor.DECISION_DESESTIMAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    resultado = executor.ejecutar_plan(plan, lambda _clave: cliente)
    assert resultado.ok
    # El registro nuevo (la devolución) más el «Total operaciones»
    assert resultado.total_creados == 2
    assert resultado.errores == []
    assert cliente.creados[-1]["fields"][config.CAMPO_YB_TIPO] == "Cargo Total Mes"
    assert cliente.creados[0]["fields"][config.CAMPO_YB_IMPORTE] == -23.99


def test_ejecucion_detecta_valores_que_no_se_guardaron(tmp_path):
    """Si Ninox guarda otra cosa de la enviada, se avisa y se detiene."""
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_DESESTIMAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    cliente = ClienteFalso("FAWALT INVESTMENT",
                           guardado_alterado={config.CAMPO_YB_IMPORTE: 1.0})
    resultado = executor.ejecutar_plan(plan, lambda _clave: cliente)
    assert not resultado.ok
    assert resultado.abortado
    assert "Importe" in resultado.errores[0]


def test_ejecucion_se_para_en_el_primer_error(tmp_path):
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_INSERTAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    cliente = ClienteFalso("FAWALT INVESTMENT",
                           excepciones=[NinoxError("HTTP 500 de prueba")])
    resultado = executor.ejecutar_plan(plan, lambda _clave: cliente)
    assert not resultado.ok
    assert resultado.total_creados == 0
    assert len(resultado.errores) == 1


def test_alta_incierta_que_si_llego_no_se_reintenta(tmp_path):
    """POST sin respuesta: se reconcilia leyendo. Nunca se reenvía."""
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_DESESTIMAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    tarea = plan.tareas[0]
    cliente = ClienteFalso("FAWALT INVESTMENT", registros=[{
        "id": 555, "fields": {
            config.CAMPO_YB_TARJETA: tarea.campos[config.CAMPO_YB_TARJETA],
            config.CAMPO_YB_FECHA: tarea.campos[config.CAMPO_YB_FECHA].isoformat(),
            config.CAMPO_YB_IMPORTE: tarea.campos[config.CAMPO_YB_IMPORTE],
        }}], excepciones=[EscrituraIncierta("respuesta perdida")])
    resultado = executor.ejecutar_plan(plan, lambda _clave: cliente)
    assert resultado.ok
    assert resultado.total_creados == 2       # el recuperado + el total mensual
    assert resultado.avisos and "no se reintenta" in resultado.avisos[0].lower()
    # El registro incierto no se ha reenviado: sólo se creó el segundo
    assert len(cliente.creados) == 1


def test_alta_incierta_que_no_llego_es_un_error(tmp_path):
    conciliacion, decisiones, _ = _plan(tmp_path, executor.DECISION_DESESTIMAR)
    plan = executor.construir_plan([conciliacion], decisiones)
    cliente = ClienteFalso("FAWALT INVESTMENT", registros=[],
                           excepciones=[EscrituraIncierta("respuesta perdida")])
    resultado = executor.ejecutar_plan(plan, lambda _clave: cliente)
    assert not resultado.ok
    assert "respuesta perdida" in resultado.errores[0]
