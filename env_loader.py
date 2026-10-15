"""Resolución de la credencial de Ninox.

La aplicación se lanza desde un acceso directo del escritorio con ``pythonw``,
así que **no puede confiar en que el proceso tenga las variables de entorno**.
Se prueba primero ``os.environ`` (rápido y cubre el desarrollo desde consola) y,
si falta, se consulta el registro de usuario de Windows, que es donde el usuario
las definió con ``setx`` o desde el panel de Sistema.

Sólo se lee la API key. Los identificadores de team y base **no** se leen del
entorno: están fijados en ``config.py`` (regla 7 del know-how de Ninox).
"""
from __future__ import annotations

import os
import subprocess

import config


class CredencialError(RuntimeError):
    """No se ha podido obtener la credencial de Ninox."""


def _leer_registro_usuario(nombre: str) -> str | None:
    """``[Environment]::GetEnvironmentVariable(nombre, 'User')`` de Windows."""
    try:
        salida = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "[Environment]::GetEnvironmentVariable('%s','User')" % nombre],
            capture_output=True, text=True, timeout=20,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    valor = salida.stdout.strip()
    return valor or None


def get_credencial(nombre: str) -> str | None:
    """Valor de una variable: primero el proceso, después el registro de Windows."""
    valor = os.environ.get(nombre)
    if valor:
        return valor
    return _leer_registro_usuario(nombre)


def api_key() -> str:
    """Devuelve ``NINOX_API_KEY`` o lanza ``CredencialError``.

    Nunca se registra ni se imprime el valor: sólo su longitud.
    """
    valor = get_credencial(config.ENV_API_KEY)
    if not valor:
        raise CredencialError(
            "No se encuentra la variable %s. Defínela con:\n"
            '    setx %s "tu_token_de_ninox"\n'
            "y vuelve a abrir la aplicación." % (config.ENV_API_KEY, config.ENV_API_KEY)
        )
    return valor


def avisos_entorno() -> list[str]:
    """Avisa si las variables de la máquina apuntan a otra base de la esperada.

    No cambia nunca el destino: sólo evita el error silencioso de trabajar sobre
    la base equivocada.
    """
    avisos: list[str] = []
    for clave, base in config.BASES.items():
        valor = get_credencial(base["env_id"])
        if valor and valor != base["id"]:
            avisos.append(
                "%s apunta a '%s' pero esta aplicación escribe en %s (%s). "
                "Se usará la base fijada en config.py." %
                (base["env_id"], valor, base["nombre"], base["id"])
            )
    return avisos
