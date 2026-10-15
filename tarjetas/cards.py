"""Qué tarjeta es y contra qué base de datos de Ninox se trabaja.

La tabla de tarjetas de ``config.py`` es la del requisito (§4.2): la máscara que
imprime el banco determina la base de datos y el registro del catálogo `XB`.

Aunque los ids de `XB` están fijados por el requisito (JULSA 17 y 13, FAWALT 13),
**siempre se verifican contra Ninox antes de escribir**: se lee el registro y se
comprueba que su número de tarjeta corresponde a la máscara del PDF. Si alguien
recrea el registro y el id cambia, el proceso se detiene en vez de imputar los
movimientos a la tarjeta equivocada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import config
from ninox_client import NinoxClient
from tarjetas.pdf_reader import ExtractoPDF

RE_SOLO_DIGITOS = re.compile(r"\D+")


class TarjetaError(Exception):
    """La tarjeta del extracto no se puede resolver contra Ninox."""


@dataclass
class Destino:
    """Destino de la escritura: base de datos, tabla y tarjeta del catálogo."""

    base_clave: str
    base_id: str
    base_nombre: str
    tabla: str
    tabla_nombre: str
    xb_id: int
    titular: str
    numero_tarjeta_pdf: str
    etiqueta_tarjeta: str

    @property
    def etiqueta(self) -> str:
        return "%s · %s (`%s` «%s»)" % (
            self.base_nombre, self.numero_tarjeta_pdf, self.tabla, self.tabla_nombre)


def _normalizar_numero(numero: str) -> str:
    return RE_SOLO_DIGITOS.sub("", numero or "")


def mascara_desde_entero(numero: str) -> str | None:
    """«5566710954255013» → «5566 **** **** 5013»."""
    digitos = _normalizar_numero(numero)
    if len(digitos) < 8:
        return None
    return "%s **** **** %s" % (digitos[:4], digitos[-4:])


def resolver_destino(extracto: ExtractoPDF,
                     cliente_de: Callable[[str], NinoxClient],
                     log: Callable[[str], None] | None = None) -> Destino:
    """Máscara del PDF → base de datos y registro de `XB`, verificado en Ninox."""
    def _log(mensaje: str) -> None:
        if log:
            log(mensaje)

    definicion = config.TARJETAS.get(extracto.numero_tarjeta)
    if definicion is None:
        contempladas = ", ".join(sorted(config.TARJETAS))
        raise TarjetaError(
            "La tarjeta %s de %s no está contemplada en el requisito. Tarjetas "
            "válidas: %s" % (extracto.numero_tarjeta, extracto.nombre, contempladas))

    base_clave = str(definicion["base"])
    base = config.BASES[base_clave]
    xb_id = int(definicion["xb_id"])
    cliente = cliente_de(base_clave)

    registro = cliente.get_record(config.NINOX_TABLA_CATALOGO, xb_id)
    if registro is None:
        raise TarjetaError(
            "En %s no existe el registro %s de la tabla `%s` que el requisito asigna a "
            "la tarjeta %s. ¿Se ha recreado el registro en Ninox con otro id?"
            % (base["nombre"], xb_id, config.NINOX_TABLA_CATALOGO, extracto.numero_tarjeta))

    campos = registro.get("fields") or {}
    numero_ninox = str(campos.get("Número") or "")
    mascara_ninox = mascara_desde_entero(numero_ninox)
    if mascara_ninox != extracto.numero_tarjeta:
        raise TarjetaError(
            "El registro %s de `%s` en %s tiene el número %s (%s) y no corresponde a la "
            "tarjeta %s del extracto %s. Se detiene el proceso para no imputar "
            "movimientos a otra tarjeta."
            % (xb_id, config.NINOX_TABLA_CATALOGO, base["nombre"], numero_ninox,
               mascara_ninox or "ilegible", extracto.numero_tarjeta, extracto.nombre))

    titular = str(campos.get("Titular") or definicion["titular"])
    destino = Destino(
        base_clave=base_clave,
        base_id=base["id"],
        base_nombre=base["nombre"],
        tabla=base["tabla_yb"],
        tabla_nombre=base["tabla_yb_nombre"],
        xb_id=xb_id,
        titular=titular,
        numero_tarjeta_pdf=extracto.numero_tarjeta,
        etiqueta_tarjeta=str(definicion["etiqueta"]),
    )
    _log("  · %s → %s · registro XB %s · titular %s"
         % (extracto.nombre, destino.etiqueta, xb_id, titular))
    return destino
