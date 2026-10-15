"""Crea el acceso directo del escritorio con el icono de la aplicación.

El acceso directo lanza ``pythonw.exe`` sobre ``main.py``: la ventana aparece sin
consola negra detrás. El icono es el que genera ``tools/crear_icono.py``.

    python tools/crear_acceso_directo.py            crea el acceso directo
    python tools/crear_acceso_directo.py --consola  crea además uno con consola,
                                                    útil para ver errores de arranque
"""
from __future__ import annotations

import argparse
import base64
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
NOMBRE = "Automatización Tarjetas Banco"


def _pythonw() -> Path:
    """El intérprete sin consola del mismo Python que ejecuta esto."""
    candidato = Path(sys.executable).with_name("pythonw.exe")
    if candidato.exists():
        return candidato
    return Path(sys.executable)


def _crear_lnk(destino: Path, interprete: Path, argumentos: str, icono: Path) -> None:
    """Crea el .lnk con WScript.Shell (COM de Windows)."""
    guion = """
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut('%s')
$lnk.TargetPath = '%s'
$lnk.Arguments = '%s'
$lnk.WorkingDirectory = '%s'
$lnk.IconLocation = '%s,0'
$lnk.Description = '%s'
$lnk.WindowStyle = 1
$lnk.Save()
Write-Output ('CREADO ' + $lnk.FullName)
""" % (destino, interprete, argumentos, RAIZ, icono, NOMBRE)
    codificado = base64.b64encode(guion.encode("utf-16-le")).decode("ascii")
    salida = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-EncodedCommand", codificado],
        capture_output=True, text=True, timeout=60)
    if salida.returncode != 0:
        raise SystemExit("No se ha podido crear el acceso directo:\n%s\n%s"
                         % (salida.stdout, salida.stderr))
    print(salida.stdout.strip())


def _escritorio() -> Path:
    salida = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, timeout=30)
    ruta = Path(salida.stdout.strip())
    if not ruta.exists():
        raise SystemExit("No se ha podido localizar el escritorio del usuario.")
    return ruta


def main(argv: list[str] | None = None) -> int:
    analizador = argparse.ArgumentParser(description="Acceso directo de la aplicación")
    analizador.add_argument("--consola", action="store_true",
                            help="crea un segundo acceso directo con consola visible")
    argumentos = analizador.parse_args(argv)

    interprete = _pythonw()
    if not interprete.exists():
        raise SystemExit("No se encuentra el intérprete de Python: %s" % interprete)
    icono = RAIZ / "recursos" / "tarjetas.ico"
    if not icono.exists():
        raise SystemExit("Falta el icono %s: ejecuta antes tools/crear_icono.py" % icono)

    escritorio = _escritorio()
    _crear_lnk(escritorio / ("%s.lnk" % NOMBRE), interprete,
               '"%s"' % (RAIZ / "main.py"), icono)
    if argumentos.consola:
        _crear_lnk(escritorio / ("%s (con consola).lnk" % NOMBRE),
                   Path(sys.executable), '"%s"' % (RAIZ / "main.py"), icono)
    print("Intérprete: %s" % interprete)
    print("Escritorio: %s" % escritorio)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
