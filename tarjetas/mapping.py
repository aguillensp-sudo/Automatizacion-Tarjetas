"""Mapeo del extracto a los campos de la tabla `YB`.

Tabla de mapeo del requisito (§4.2), para las tres tarjetas:

| Campo del extracto | Campo Ninox | ¿Se informa? |
|---|---|---|
| Fecha | `C` Fecha | **Sí** |
| Importe de la operación | `D` Importe | **Sí** |
| — (dato del catálogo) | `B` Tarjeta Bancaria | **Sí** (registro de `XB`) |
| — (regla del requisito) | `G` Tipo | **Sí** (`1` Cargo puntual) |
| Concepto | no existe en Ninox | No |
| Población/país | no existe en Ninox | No |
| Importe de la moneda de origen | no existe en Ninox | No |
| Tipo de cambio aplicado | no existe en Ninox | No |
| Total Operaciones | ver §7: genera un registro `2` Cargo Total Mes | — |

Los campos `A` Bancos, `E` Código Presupuestario, `F` Expediente, `H` Tesorería y
`J` Importe IVA deducible **no se informan**: se dejan en blanco.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import config
from tarjetas.cards import Destino
from tarjetas.pdf_reader import Operacion, formato_es


def campos_cargo_puntual(destino: Destino, operacion: Operacion) -> dict[str, Any]:
    """Campos de un movimiento del extracto (§4.2): `B`, `C`, `D`, `G`=1."""
    return {
        config.CAMPO_YB_TARJETA: destino.xb_id,
        config.CAMPO_YB_FECHA: operacion.fecha,
        config.CAMPO_YB_IMPORTE: float(operacion.importe),
        config.CAMPO_YB_TIPO: config.TIPO_CARGO_PUNTUAL,
    }


def campos_cargo_total_mes(destino: Destino, fecha: date, importe: Decimal) -> dict[str, Any]:
    """Campos del registro «Total operaciones» (§7): `B`, `C`, `D`, `G`=2.

    La fecha es el día 5 del **mes de la liquidación** (decisión del PO): en el
    extracto de septiembre liquidado el 05/10 es el 2026-10-05, que es además la
    «Fecha del apunte» que imprime el propio banco.
    """
    return {
        config.CAMPO_YB_TARJETA: destino.xb_id,
        config.CAMPO_YB_FECHA: fecha,
        config.CAMPO_YB_IMPORTE: float(importe),
        config.CAMPO_YB_TIPO: config.TIPO_CARGO_TOTAL_MES,
    }


def describir(campos: dict[str, Any]) -> str:
    """Texto legible de un payload, para el log y la pantalla.

    Ojo: al **enviar** el tipo viaja como id (``"1"``/``"2"``), pero al **leer**
    Ninox devuelve el texto (``"Cargo puntual"``/``"Cargo Total Mes"``). Hay que
    aceptar las dos formas o el log miente.
    """
    partes = []
    for nombre, valor in campos.items():
        if nombre == config.CAMPO_YB_TIPO:
            es_puntual = str(valor) in (config.TIPO_CARGO_PUNTUAL,
                                        config.TIPO_CARGO_PUNTUAL_TEXTO)
            partes.append("%s=%s" % (nombre, config.TIPO_CARGO_PUNTUAL_TEXTO if es_puntual
                                     else config.TIPO_CARGO_TOTAL_MES_TEXTO))
        elif nombre == config.CAMPO_YB_FECHA:
            partes.append("%s=%s" % (nombre, valor.isoformat() if hasattr(valor, "isoformat") else valor))
        elif nombre == config.CAMPO_YB_IMPORTE:
            partes.append("%s=%s" % (nombre, formato_es(valor)))
        else:
            partes.append("%s=%s" % (nombre, valor))
    return " · ".join(partes)
