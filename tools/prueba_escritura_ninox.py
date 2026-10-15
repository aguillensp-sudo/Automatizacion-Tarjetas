"""Prueba de escritura real contra las bases de Ninox, con limpieza garantizada.

Autorizado por el PO (requisito §9.4): se puede usar producción para insertar y
comprobar, borrando después los registros creados.

Qué comprueba
-------------
**A. Camino de escritura del cliente** (una base de cada empresa):

    crear → releer → comparar lo guardado con lo enviado → borrar → comprobar
    que ya no está. Y que un nombre de campo inválido se detecta **antes** de
    enviar (Ninox devolvería un HTTP 500 opaco).

**B. El proceso completo de la aplicación** (lectura → conciliación → inserción →
    verificación → limpieza): se fabrica un extracto con una operación imposible
    (importe marcador) y se ejecuta el plan real contra Ninox.

Cómo se reconoce lo que hay que borrar
--------------------------------------
Los registros de prueba llevan un **importe marcador** que no puede aparecer en
datos reales:

* ``987654.32`` → prueba A (fecha 1999-12-31)
* ``98765.43``  → prueba B (fecha del período del extracto fabricado)

Los ids creados se anotan en ``logs/prueba_escritura_<fecha>.json`` y se borran en
un bloque ``finally``: si algo falla a mitad, quedan anotados y ``--limpiar``
barre cualquier residuo.

Uso
---
    python tools/prueba_escritura_ninox.py                     # simulación
    python tools/prueba_escritura_ninox.py --execute --confirm ESCRIBIR-Y-BORRAR
    python tools/prueba_escritura_ninox.py --limpiar --execute --confirm ESCRIBIR-Y-BORRAR
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import config                                                    # noqa: E402
import env_loader                                                # noqa: E402
from ninox_client import NinoxClient, NinoxMappingError          # noqa: E402
from tarjetas import executor, pipeline                          # noqa: E402
from tarjetas.cards import Destino                               # noqa: E402
from tarjetas.pdf_reader import formato_es, leer_extracto        # noqa: E402
from tarjetas.reconciler import Estado, conciliar        # noqa: E402

FRASE = "ESCRIBIR-Y-BORRAR"
MARCADOR_A = 987654.32           # prueba A
MARCADOR_B = 98765.43            # prueba B
FECHA_A = date(1999, 12, 31)

#: (clave de base, id del registro XB de la tarjeta, etiqueta)
TARJETAS_PRUEBA = [
    (config.DB_JULSA, 17, "5566 **** **** 1012 · JULSA INDUSTRIAL"),
    (config.DB_FAWALT, 13, "5566 **** **** 5013 · FAWALT INVESTMENT"),
]

creados: list[dict] = []          # [{"base":…, "tabla":…, "id":…, "motivo":…}]
avisos: list[str] = []


def log(mensaje: str) -> None:
    print(mensaje, flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────
def cliente_de(base_clave: str) -> NinoxClient:
    base = config.BASES[base_clave]
    return NinoxClient(config.NINOX_TEAM_ID, base["id"], env_loader.api_key(),
                       etiqueta=base["nombre"])


def _anotar_creado(base: str, id_registro: int, motivo: str, campos: dict) -> None:
    creados.append({"base": base, "tabla": config.NINOX_TABLA_TARJETAS,
                    "id": id_registro, "motivo": motivo, "campos": campos})
    _volcar_incidencias()


def _ruta_incidencias() -> Path:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return config.LOGS_DIR / ("prueba_escritura_%s.json" % datetime.now().strftime("%Y%m%d"))


def _volcar_incidencias() -> None:
    ruta = _ruta_incidencias()
    ruta.write_text(json.dumps({"creados": creados, "avisos": avisos},
                               ensure_ascii=False, indent=2), encoding="utf-8")


def borrar_creados() -> None:
    """Borra todo lo creado por esta prueba y lo verifica."""
    if not creados:
        log("No hay registros que borrar.")
        return
    log("\n── Limpieza: borrando los registros de prueba ──")
    for anotado in list(creados):
        cliente = cliente_de(anotado["base"])
        try:
            estado = cliente.borrar_registro(anotado["tabla"], anotado["id"])
        except Exception as exc:                    # noqa: BLE001
            log("   ✘ no se ha podido borrar el id %s (%s): %r"
                % (anotado["id"], anotado["base"], exc))
            continue
        queda = cliente.get_record(anotado["tabla"], anotado["id"])
        if estado == 200 and queda is None:
            log("   ✔ borrado y verificado: %s id %s (%s)"
                % (anotado["tabla"], anotado["id"], anotado["motivo"]))
            creados.remove(anotado)
            _volcar_incidencias()
        else:
            log("   ✘ el id %s sigue en la tabla tras borrarlo (HTTP %s)"
                % (anotado["id"], estado))
    if creados:
        log("   ⚠ Quedan %d registro(s) sin borrar. Ids: %s"
            % (len(creados), ", ".join(str(c["id"]) for c in creados)))
    else:
        log("   ✔ No queda ningún residuo: la base está como estaba.")


def barrer_residuos(execute: bool) -> None:
    """Busca y borra registros con importe marcador (residuos de ejecuciones previas)."""
    log("\n── Barrido de residuos (importe marcador %s o %s) ──"
        % (formato_es(MARCADOR_A), formato_es(MARCADOR_B)))
    for base_clave in (config.DB_JULSA, config.DB_FAWALT):
        cliente = cliente_de(base_clave)
        encontrados = []
        for registro in cliente.fetch_all_records(config.NINOX_TABLA_TARJETAS,
                                                  refrescar=True):
            campos = registro.get("fields") or {}
            valor = campos.get(config.CAMPO_YB_IMPORTE)
            if valor is None:
                continue
            if abs(float(valor) - MARCADOR_A) < 0.005 or abs(float(valor) - MARCADOR_B) < 0.005:
                encontrados.append(registro)
        log("   %s: %d coincidencia(s)" % (cliente.etiqueta, len(encontrados)))
        for registro in encontrados:
            log("      id %s · %s" % (registro.get("id"),
                                      json.dumps(registro.get("fields"),
                                                 ensure_ascii=False)))
            if execute:
                estado = cliente.borrar_registro(config.NINOX_TABLA_TARJETAS,
                                                 int(registro["id"]))
                log("      → borrado HTTP %s · sigue: %s"
                    % (estado, cliente.get_record(config.NINOX_TABLA_TARJETAS,
                                                  int(registro["id"])) is not None))
        if not execute and encontrados:
            log("      (simulación: no se ha borrado nada)")


# ──────────────────────────────────────────────────────────────────────────────
# Prueba A: camino de escritura del cliente
# ──────────────────────────────────────────────────────────────────────────────
def prueba_a(execute: bool) -> None:
    log("\n" + "=" * 90)
    log("PRUEBA A · alta, relectura y borrado de un registro marcador")
    log("=" * 90)
    for base_clave, xb_id, etiqueta in TARJETAS_PRUEBA:
        cliente = cliente_de(base_clave)
        campos = {
            config.CAMPO_YB_TARJETA: xb_id,
            config.CAMPO_YB_FECHA: FECHA_A,
            config.CAMPO_YB_IMPORTE: MARCADOR_A,
            config.CAMPO_YB_TIPO: config.TIPO_CARGO_PUNTUAL,
        }
        log("\n· %s" % etiqueta)
        log("  payload: %s" % {"fields": {k: str(v) for k, v in campos.items()}})

        # 1) Un nombre de campo inválido debe detectarse ANTES de enviar
        try:
            cliente.validar_campos(config.NINOX_TABLA_TARJETAS,
                                   list(campos) + ["Campo Que No Existe"])
        except NinoxMappingError as exc:
            log("  ✔ validación de campos: se detecta el nombre inválido sin llamar a la API")
            log("      (%s)" % str(exc)[:110])
        else:
            raise SystemExit("La validación de campos no ha detectado el campo inválido.")

        if not execute:
            log("  · simulación: no se crea nada")
            continue

        guardado = cliente.crear_registro(config.NINOX_TABLA_TARJETAS, campos)
        _anotar_creado(base_clave, int(guardado["id"]), "prueba A", guardado["fields"])
        log("  ✔ creado id %s" % guardado["id"])
        log("    releído: %s" % json.dumps(guardado.get("fields"), ensure_ascii=False))
        problemas = []
        if int(guardado["fields"].get(config.CAMPO_YB_TARJETA)) != xb_id:
            problemas.append("Tarjeta Bancaria")
        if str(guardado["fields"].get(config.CAMPO_YB_FECHA))[:10] != FECHA_A.isoformat():
            problemas.append("Fecha")
        if abs(float(guardado["fields"].get(config.CAMPO_YB_IMPORTE, 0)) - MARCADOR_A) > 0.005:
            problemas.append("Importe")
        if guardado["fields"].get(config.CAMPO_YB_TIPO) != config.TIPO_CARGO_PUNTUAL_TEXTO:
            problemas.append("Tipo")
        if problemas:
            avisos.append("%s: el registro id %s se guardó distinto en %s"
                          % (base_clave, guardado["id"], ", ".join(problemas)))
            log("  ✘ discrepancias: %s" % ", ".join(problemas))
        else:
            log("  ✔ lo guardado coincide con lo enviado (tarjeta, fecha, importe, tipo)")
        # Se borra de inmediato: cuanto menos tiempo esté el registro en producción, mejor
        borrar_creados()


# ──────────────────────────────────────────────────────────────────────────────
# Prueba B: el proceso completo de la aplicación
# ──────────────────────────────────────────────────────────────────────────────
def prueba_b(execute: bool, tmp_dir: Path) -> None:
    log("\n" + "=" * 90)
    log("PRUEBA B · extracto fabricado → conciliación → inserción → verificación")
    log("=" * 90)

    from tests.sintetico import crear_pdf

    # Una operación imposible (importe marcador) y su total
    ruta = crear_pdf(tmp_dir / "prueba_ninox.pdf", operaciones=[
        {"fecha": "0109", "concepto": "PRUEBA AUTOMATICA TARJETAS",
         "poblacion": "MADRID", "importe_origen": "98.765,43", "importe": "98.765,43"},
    ], total="98.765,43")

    extracto = leer_extracto(ruta, log=lambda m: log("  " + m))
    definicion = config.TARJETAS[extracto.numero_tarjeta]
    base_clave = str(definicion["base"])
    base = config.BASES[base_clave]
    destino = Destino(
        base_clave=base_clave, base_id=base["id"], base_nombre=base["nombre"],
        tabla=base["tabla_yb"], tabla_nombre=base["tabla_yb_nombre"],
        xb_id=int(definicion["xb_id"]), titular=str(definicion["titular"]),
        numero_tarjeta_pdf=extracto.numero_tarjeta,
        etiqueta_tarjeta=str(definicion["etiqueta"]))
    log("  destino: %s · %s · XB %s" % (destino.base_nombre, destino.tabla, destino.xb_id))

    fabrica = pipeline.FabricaClientes()
    cliente = fabrica(base_clave)
    conciliacion = conciliar(extracto, destino, cliente, log=lambda m: log("  " + m))
    log("  resultado: %d nuevas · %d coincidencias · %d incidencias"
        % (len(conciliacion.nuevas), len(conciliacion.coincidencias),
           len(conciliacion.incidencias)))
    if len(conciliacion.filas) != 1:
        raise SystemExit("El extracto fabricado debería tener exactamente 1 operación.")
    fila = conciliacion.filas[0]
    if fila.estado is Estado.COINCIDENCIA:
        raise SystemExit(
            "El importe marcador ya existe en Ninox: hay residuos de una ejecución "
            "anterior. Ejecuta antes: --limpiar --execute --confirm %s" % FRASE)

    # Como haría el usuario en la ventana: el registro de prueba se inserta.
    # Si la fecha ya tiene otros movimientos, la aplicación lo clasifica como
    # incidencia (misma fecha, importe distinto) y hay que decidir «Insertar».
    decisiones = {(extracto.nombre, fila.operacion.orden): executor.DECISION_INSERTAR}
    plan = executor.construir_plan([conciliacion], decisiones)
    log("  estado de la operación: %s → decisión del usuario: insertar"
        % fila.estado.etiqueta)
    log("  plan: %d inserción(es)" % plan.total_inserciones)
    for tarea in plan.tareas:
        log("    · %s" % tarea.resumen)

    if not execute:
        log("  · simulación: no se inserta nada")
        return

    resultado = executor.ejecutar_plan(plan, fabrica, log=lambda m: log("  " + m))
    for creado in resultado.creados:
        _anotar_creado(base_clave, int(creado["id"]), "prueba B", creado["guardado"])
    if not resultado.ok:
        raise SystemExit("La prueba B ha fallado: %s" % "; ".join(resultado.errores))
    log("  ✔ insertados %d registro(s): %s"
        % (resultado.total_creados, ", ".join(str(c["id"]) for c in resultado.creados)))

    # Verificación por lectura independiente: los registros están y dicen lo que deben
    ids = [int(c["id"]) for c in resultado.creados]
    cliente.invalidar_cache(config.NINOX_TABLA_TARJETAS)
    leidos = cliente.fetch_records_by_ids(config.NINOX_TABLA_TARJETAS, ids)
    if len(leidos) != len(ids):
        raise SystemExit("No se releen todos los registros creados: %s" % ids)
    for identificador, registro in leidos.items():
        log("    id %s → %s" % (identificador,
                                json.dumps(registro.get("fields"), ensure_ascii=False)))
    log("  ✔ verificación por lectura correcta")

    # Y se borran en cuanto están comprobados
    borrar_creados()


# ──────────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description="Prueba de escritura en Ninox")
    analizador.add_argument("--execute", action="store_true",
                            help="escribe de verdad (por defecto: simulación)")
    analizador.add_argument("--confirm", default="", help="frase de confirmación: %s" % FRASE)
    analizador.add_argument("--limpiar", action="store_true",
                            help="sólo barre residuos con importe marcador")
    analizador.add_argument("--solo-b", action="store_true", help="ejecuta sólo la prueba B")
    argumentos = analizador.parse_args(argv)

    if argumentos.execute and argumentos.confirm != FRASE:
        raise SystemExit(
            "Para escribir de verdad hay que confirmarlo:\n"
            "    --execute --confirm %s" % FRASE)

    tmp_dir = config.BASE_DIR / ".tmp_pruebas"
    tmp_dir.mkdir(exist_ok=True)

    log("Ninox · equipo %s · API key presente: %s"
        % (config.NINOX_TEAM_ID, bool(env_loader.api_key())))
    log("Modo: %s" % ("ESCRITURA REAL + LIMPIEZA" if argumentos.execute else "SIMULACIÓN"))

    try:
        if argumentos.limpiar:
            barrer_residuos(argumentos.execute)
            return 0
        if not argumentos.solo_b:
            prueba_a(argumentos.execute)
        prueba_b(argumentos.execute, tmp_dir)
    except Exception as exc:                           # noqa: BLE001
        log("\n✘ La prueba ha lanzado una excepción: %r" % exc)
    finally:
        if argumentos.execute:
            borrar_creados()
        else:
            log("\n(simulación: no se ha escrito ni borrado nada)")

    if avisos:
        log("\nAvisos:")
        for aviso in avisos:
            log("  ⚠ " + aviso)
    log("\nFichero de trazabilidad: %s" % _ruta_incidencias())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
