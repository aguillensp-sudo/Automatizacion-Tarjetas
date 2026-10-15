"""Punto de entrada de la Automatización Tarjetas Banco.

Sin argumentos abre la ventana. Con ``--consola`` hace el mismo trabajo sin
interfaz: sirve para comprobar contra Ninox qué saldría de cada extracto sin
tocar nada, que es lo que se usa en las pruebas.

    python main.py                 abre la aplicación (o pythonw, sin consola)
    python main.py --consola       lee los PDFs de la carpeta y muestra el informe
    python main.py --consola --fichero PDFS\\FW-AGS.pdf
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

import config
from tarjetas import pdf_reader, pipeline
from tarjetas.pdf_reader import formato_es
from tarjetas.reconciler import Estado


def _preparar_consola() -> None:
    """La consola de Windows usa cp1252: sin esto, los acentos rompen el informe."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):       # pragma: no cover
            pass


def _imprimir_informe(resultado: pipeline.ProcesoResultado) -> None:
    print()
    print("=" * 100)
    print("INFORME DE CONCILIACIÓN (sólo lectura: no se ha escrito nada en Ninox)")
    print("=" * 100)
    for indice, conciliacion in enumerate(resultado.conciliaciones, start=1):
        destino = conciliacion.destino
        print()
        print("%d. %s   (liquidación %s · período %s)"
              % (indice, conciliacion.extracto.nombre,
                 conciliacion.extracto.fecha_liquidacion.isoformat(),
                 conciliacion.extracto.periodo_texto))
        print("   Destino: %s · tarjeta %s · tabla `%s` «%s» · registro XB %s (%s)"
              % (destino.base_nombre, destino.numero_tarjeta_pdf, destino.tabla,
                 destino.tabla_nombre, destino.xb_id, destino.titular))
        print("   Operaciones leídas: %d · total del banco %s €"
              % (len(conciliacion.filas),
                 formato_es(conciliacion.extracto.total_operaciones)))
        print("   a) Nuevos a insertar ....... %d" % len(conciliacion.nuevas))
        print("   b) Coincidencias ........... %d" % len(conciliacion.coincidencias))
        print("   c) Incidencias ............. %d" % len(conciliacion.incidencias))
        for fila in conciliacion.filas:
            marca = {Estado.NUEVO: "[nuevo]     ",
                     Estado.COINCIDENCIA: "[coincide]  ",
                     Estado.INCIDENCIA: "[INCIDENCIA]"}[fila.estado]
            ninox = fila.ninox.descripcion() if fila.ninox else "-"
            print("      %s %s  %10s €  %-38s  | Ninox: %s"
                  % (marca, fila.operacion.fecha.isoformat(),
                     formato_es(fila.operacion.importe),
                     (fila.operacion.concepto or "")[:38], ninox))
        print("   Total operaciones (§7) → se crearía 1 registro: Fecha %s · "
              "Importe %s € · Tipo «Cargo Total Mes»"
              % (conciliacion.total_mes_fecha.isoformat(),
                 formato_es(conciliacion.total_mes_importe)))
        if conciliacion.total_mes_previo is not None:
            print("      ⚠ Ya existe un registro idéntico (%s): se duplicaría."
                  % conciliacion.total_mes_previo.descripcion())
    print()
    print("Resumen: %d extracto(s) · %d nuevos · %d por decidir (coincidencias+incidencias) "
          "· %d totales mensuales"
          % (len(resultado.conciliaciones), resultado.total_nuevos,
             resultado.total_decisiones, len(resultado.conciliaciones)))
    for aviso in resultado.avisos:
        print("⚠ " + aviso)


def main(argv: list[str] | None = None) -> int:
    _preparar_consola()
    analizador = argparse.ArgumentParser(description=config.APP_NOMBRE)
    analizador.add_argument("--consola", action="store_true",
                            help="informe por consola, sin abrir la ventana (sólo lectura)")
    analizador.add_argument("--fichero", action="append", default=None,
                            help="extracto concreto a procesar (se puede repetir)")
    argumentos = analizador.parse_args(argv)

    if not argumentos.consola:
        from ui.app import arrancar
        arrancar()
        return 0

    if argumentos.fichero:
        rutas = [Path(f) if Path(f).is_absolute() else config.PDFS_DIR / Path(f).name
                 for f in argumentos.fichero]
    else:
        rutas = pdf_reader.listar_pdfs(config.PDFS_DIR)
    if not rutas:
        print("No hay ficheros PDF en %s" % config.PDFS_DIR)
        return 1

    resultado = pipeline.procesar(rutas, log=lambda m: print(m))
    _imprimir_informe(resultado)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
