"""Comprobación de arranque de la ventana, sin intervención manual.

Simula lo que ocurre al abrir la aplicación desde el escritorio: se muestra la
carpeta de trabajo, se listan los ficheros, se responde «Sí» a la pregunta de
procesarlos y se deja que se dibujen los resultados. Sólo lee: no inserta nada
en Ninox.

    python tools/prueba_arranque_gui.py            # abre la ventana 15 s
    python tools/prueba_arranque_gui.py --segundos 5
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import config                                       # noqa: E402
import ui.app as app                                # noqa: E402


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description="Arranque simulado de la ventana")
    analizador.add_argument("--segundos", type=float, default=3.0,
                            help="tiempo mínimo que la ventana permanece abierta")
    argumentos = analizador.parse_args(argv)

    eventos: list[str] = []
    app.messagebox.askyesno = lambda *a, **k: eventos.append("pregunta-procesar") or True
    app.messagebox.showinfo = lambda *a, **k: eventos.append("informe: %s" % (a[-1],))
    app.messagebox.showwarning = lambda *a, **k: eventos.append("aviso: %s" % (a[-1],))
    app.messagebox.showerror = lambda *a, **k: eventos.append("error: %s" % (a[-1],))

    ventana = app.VentanaPrincipal()               # con la pregunta de arranque
    inicio = time.time()
    limite = inicio + argumentos.segundos
    # Se atiende la ventana al menos `--segundos`, y todo lo que tarde el proceso
    while time.time() < limite or ventana._ocupado:
        if time.time() > inicio + 300:             # red de seguridad
            print("⚠ Se agota el tiempo de espera con el proceso en marcha.")
            break
        ventana.update()
        time.sleep(0.05)

    print("Carpeta de trabajo:", ventana._var_carpeta.get())
    print("Ficheros listados:", len(ventana._lista.get_children()))
    print("Eventos:", eventos)
    print("Estado final:", ventana._var_estado.get())
    if ventana._resultado is not None:
        for conciliacion in ventana._resultado.conciliaciones:
            print("  · %s" % conciliacion.resumen())
    print("Decisiones pendientes:", len(ventana._resultados.pendientes()))
    print("\n── Historial de la ventana ──")
    print(ventana._log_texto.get("1.0", "end"))
    ventana.destroy()
    ok = bool(ventana._resultado) and "pregunta-procesar" in eventos
    print("RESULTADO:", "arranque correcto" if ok else "REVISAR: algo ha fallado")
    print("Log en fichero:", config.LOGS_DIR)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
