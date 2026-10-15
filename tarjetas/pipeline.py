"""El proceso completo: leer los PDFs y conciliarlos contra Ninox.

Es la pieza que comparten la interfaz gráfica y el modo consola, para que lo que
se prueba por consola sea exactamente lo que hace la ventana.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import config
import env_loader
from ninox_client import NinoxClient
from tarjetas import cards, pdf_reader
from tarjetas.reconciler import Conciliacion, conciliar


@dataclass
class ProcesoResultado:
    """Lo que ha salido de leer y comparar todos los extractos."""

    conciliaciones: list[Conciliacion] = field(default_factory=list)
    ficheros: list[Path] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def total_nuevos(self) -> int:
        return sum(len(c.nuevas) for c in self.conciliaciones)

    @property
    def total_decisiones(self) -> int:
        return sum(len(c.decisiones) for c in self.conciliaciones)

    @property
    def total_inserciones_previstas(self) -> int:
        """Nuevos + totales mensuales + lo que el usuario decida insertar."""
        return self.total_nuevos + len(self.conciliaciones) + self.total_decisiones


class FabricaClientes:
    """Crea (y reutiliza) un cliente de Ninox por base de datos."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or env_loader.api_key()
        self._clientes: dict[str, NinoxClient] = {}

    def __call__(self, base_clave: str) -> NinoxClient:
        if base_clave not in self._clientes:
            base = config.BASES[base_clave]
            self._clientes[base_clave] = NinoxClient(
                team_id=config.NINOX_TEAM_ID,
                db_id=base["id"],
                api_key=self._api_key,
                etiqueta=base["nombre"],
            )
        return self._clientes[base_clave]

    def todos(self) -> dict[str, NinoxClient]:
        return dict(self._clientes)


def procesar(rutas: Iterable[str | Path],
             api_key: str | None = None,
             log: Callable[[str], None] | None = None,
             progreso: Callable[[int, int], None] | None = None) -> ProcesoResultado:
    """Lee los extractos indicados y los concilia contra su tabla de Ninox.

    Cualquier problema (PDF ilegible, tarjeta no contemplada, credencial
    rechazada, suma que no cuadra) se propaga como excepción con un mensaje
    explícito: la interfaz lo muestra en la barra de estado y detiene el proceso.
    """
    def _log(mensaje: str) -> None:
        if log:
            log(mensaje)

    rutas = [Path(r) for r in rutas]
    fabrica = FabricaClientes(api_key)
    resultado = ProcesoResultado(ficheros=rutas)

    for aviso in env_loader.avisos_entorno():
        resultado.avisos.append(aviso)
        _log("⚠ " + aviso)

    total = len(rutas)
    for indice, ruta in enumerate(rutas, start=1):
        if progreso:
            progreso(indice - 1, total)
        _log("• [%d/%d] Leyendo %s" % (indice, total, ruta.name))
        extracto = pdf_reader.leer_extracto(ruta, log=_log)
        destino = cards.resolver_destino(extracto, fabrica, log=_log)
        cliente = fabrica(destino.base_clave)
        conciliacion = conciliar(extracto, destino, cliente, log=_log)
        resultado.conciliaciones.append(conciliacion)

    if resultado.conciliaciones:
        agrupadas: dict[str, list[str]] = {}
        for conciliacion in resultado.conciliaciones:
            clave = "%s · %s (`%s` «%s»)" % (
                conciliacion.destino.base_nombre,
                conciliacion.destino.numero_tarjeta_pdf,
                conciliacion.destino.tabla,
                conciliacion.destino.tabla_nombre)
            agrupadas.setdefault(clave, []).append(conciliacion.extracto.nombre)
        _log("Resumen de destinos:")
        for clave, ficheros in agrupadas.items():
            _log("  · %s ← %s" % (clave, ", ".join(ficheros)))

    if progreso:
        progreso(total, total)
    return resultado
