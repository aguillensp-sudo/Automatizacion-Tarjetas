"""Cliente REST de Ninox, de destino explícito.

Reglas que implementa (todas pagadas ya una vez en los proyectos hermanos
`Automatizacion JI` y `Automatizacion_FAWALT`):

1. **El destino se pasa explícitamente** al construir el cliente. Ninguna
   variable de entorno decide la base de datos.
2. **Los nombres de campo se validan contra los metadatos** antes de enviar: un
   nombre mal escrito no devuelve 400, devuelve **HTTP 500** sin explicación.
3. **Un POST no se reintenta nunca a ciegas.** Si se pierde la respuesta, el
   registro puede haber entrado: se pasa a estado *incierto* y se reconcilia
   leyendo (`EscrituraIncierta`), jamás reenviando.
4. **Tras crear, se relee** el registro: hay campos con valor por defecto que
   descartan lo enviado.
5. El cuerpo va anidado bajo ``fields`` y claveado por **nombre** de campo.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable

import config

_log = logging.getLogger(__name__)


class NinoxError(Exception):
    """Error base del cliente Ninox."""


class NinoxAuthError(NinoxError):
    """Credenciales rechazadas (401/403). No se reintenta: hay que pedir token."""


class NinoxNotFoundError(NinoxError):
    """Tabla o registro inexistente (404). No se reintenta."""


class NinoxServerError(NinoxError):
    """5xx o error de red tras agotar los reintentos de una lectura."""


class NinoxMappingError(NinoxError):
    """El 500 persistente es casi siempre un nombre de campo inválido."""


class EscrituraIncierta(NinoxError):
    """Se envió un POST y se perdió la respuesta: el registro puede existir.

    Nunca se reintenta. Hay que reconciliar leyendo la tabla.
    """

    def __init__(self, mensaje: str, campos: dict[str, Any] | None = None) -> None:
        super().__init__(mensaje)
        self.campos = campos or {}


def _decode(body: str) -> Any:
    texto = body.strip()
    if not texto:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return body


class NinoxClient:
    """Cliente ligero sobre la API clásica de Ninox, atado a una base concreta."""

    def __init__(self, team_id: str, db_id: str, api_key: str, etiqueta: str = "") -> None:
        self.team_id = team_id
        self.db_id = db_id
        self.etiqueta = etiqueta or db_id
        self._api_key = api_key
        self._esquema: dict[str, dict[str, dict[str, Any]]] = {}   # tabla → {nombre: campo}
        self._cache_registros: dict[str, list[dict[str, Any]]] = {}

    def __repr__(self) -> str:  # pragma: no cover - sólo depuración
        return "<NinoxClient %s db=%s>" % (self.etiqueta, self.db_id)

    # ──────────────────────────────────────────────────────────────────────────
    # Núcleo HTTP
    # ──────────────────────────────────────────────────────────────────────────
    def _url(self, path: str) -> str:
        return "%s/teams/%s/databases/%s%s" % (
            config.NINOX_BASE_URL, self.team_id, self.db_id, path)

    def _cabeceras(self, con_cuerpo: bool = False) -> dict[str, str]:
        cabeceras = {
            "Authorization": "Bearer %s" % self._api_key,
            "Accept": "application/json",
        }
        if con_cuerpo:
            cabeceras["Content-Type"] = "application/json"
        return cabeceras

    def _peticion(self, path: str, *, intentos: int | None = None) -> Any:
        """GET con backoff. Devuelve el JSON decodificado."""
        intentos = intentos or config.MAX_RETRIES
        url = self._url(path)
        ultimo: Exception | None = None
        for intento in range(1, intentos + 1):
            try:
                req = urllib.request.Request(url, headers=self._cabeceras(), method="GET")
                with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_SEC) as resp:
                    return _decode(resp.read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as exc:
                cuerpo = exc.read().decode("utf-8", "replace")[:300]
                if exc.code in (401, 403):
                    raise NinoxAuthError(
                        "Ninox rechazó la credencial (%d) en %s. Revisa %s."
                        % (exc.code, self.etiqueta, config.ENV_API_KEY)) from exc
                if exc.code == 404:
                    raise NinoxNotFoundError(
                        "No existe el recurso %s en %s (404)." % (path, self.etiqueta)) from exc
                if 400 <= exc.code < 500 and exc.code != 429:
                    raise NinoxError("HTTP %d en %s: %s" % (exc.code, path, cuerpo)) from exc
                ultimo = exc
                _log.warning("[%s] HTTP %d en %s (reintentable): %s",
                             self.etiqueta, exc.code, path, cuerpo)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                ultimo = exc
                _log.warning("[%s] Error de red en %s: %r", self.etiqueta, path, exc)
            if intento < intentos:
                time.sleep(config.RETRY_BACKOFF_SEC * (2 ** (intento - 1)))
        raise NinoxServerError(
            "Fallo tras %d intentos en %s (%s): %r"
            % (intentos, path, self.etiqueta, ultimo))

    def _peticion_escritura(self, metodo: str, path: str,
                            payload: Any = None) -> tuple[int, Any]:
        """POST/PUT/DELETE **sin reintentos** en POST.

        Devuelve ``(status, cuerpo)``. Un POST perdido lanza
        ``EscrituraIncierta``: reintentarlo podría duplicar un apunte contable.
        """
        url = self._url(path)
        datos = None
        if payload is not None:
            datos = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url, data=datos, headers=self._cabeceras(con_cuerpo=payload is not None),
            method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT_SEC) as resp:
                cuerpo = resp.read().decode("utf-8", "replace")
                return resp.status, _decode(cuerpo)
        except urllib.error.HTTPError as exc:
            cuerpo = exc.read().decode("utf-8", "replace")
            return exc.code, _decode(cuerpo)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if metodo == "POST":
                raise EscrituraIncierta(
                    "Se envió el alta a %s pero se perdió la respuesta (%r). "
                    "No se reintenta: hay que comprobar la tabla." % (path, exc),
                    payload if isinstance(payload, dict) else None) from exc
            raise NinoxServerError(
                "Error de red en %s %s (%s): %r" % (metodo, path, self.etiqueta, exc)) from exc

    # ──────────────────────────────────────────────────────────────────────────
    # Esquema
    # ──────────────────────────────────────────────────────────────────────────
    def metadatos_tabla(self, tabla: str, *, refrescar: bool = False) -> dict[str, Any]:
        """Metadatos (id, nombre y campos) de una tabla."""
        if refrescar or tabla not in self._esquema:
            meta = self._peticion("/tables/%s" % tabla)
            campos: dict[str, dict[str, Any]] = {}
            for f in (meta or {}).get("fields", []):
                campos[f["name"]] = {
                    "id": f.get("id"),
                    "nombre": f.get("name"),
                    "tipo": f.get("type"),
                    "choices": f.get("choices"),
                    "tabla_destino": f.get("referenceToTable"),
                }
            self._esquema[tabla] = campos
        return {"campos": self._esquema[tabla], "id": tabla}

    def campos_tabla(self, tabla: str) -> dict[str, dict[str, Any]]:
        """{nombre de campo: metadatos} de una tabla."""
        return self.metadatos_tabla(tabla)["campos"]

    def campo_por_id(self, tabla: str, id_campo: str) -> dict[str, Any] | None:
        for f in self.campos_tabla(tabla).values():
            if f["id"] == id_campo:
                return f
        return None

    def validar_campos(self, tabla: str, nombres: Iterable[str]) -> None:
        """Comprueba los nombres contra el esquema. Evita el 500 opaco de Ninox."""
        disponibles = set(self.campos_tabla(tabla))
        desconocidos = [n for n in nombres if n not in disponibles]
        if desconocidos:
            raise NinoxMappingError(
                "Campos inexistentes en [%s].%s: %s. Campos válidos: %s"
                % (self.etiqueta, tabla, ", ".join(desconocidos),
                   ", ".join(sorted(disponibles))))

    def _coercionar(self, tabla: str, campos: dict[str, Any]) -> dict[str, Any]:
        """Ajusta cada valor al tipo declarado del campo."""
        esquema = self.campos_tabla(tabla)
        salida: dict[str, Any] = {}
        for nombre, valor in campos.items():
            meta = esquema.get(nombre)
            if meta is None:
                raise NinoxMappingError(
                    "Campo '%s' inexistente en [%s].%s" % (nombre, self.etiqueta, tabla))
            tipo = meta.get("tipo")
            if valor is None:
                continue
            if tipo == "date" and hasattr(valor, "isoformat"):
                valor = valor.isoformat()
            elif tipo == "number":
                valor = float(valor)
            elif tipo in ("ref", "reference"):
                valor = int(valor)
            salida[nombre] = valor
        return salida

    # ──────────────────────────────────────────────────────────────────────────
    # Lecturas
    # ──────────────────────────────────────────────────────────────────────────
    def fetch_all_records(self, tabla: str, *, refrescar: bool = False) -> list[dict[str, Any]]:
        """Todos los registros de una tabla, paginando hasta agotar.

        La API no filtra en servidor en el endpoint de registros: hay que
        descargar y filtrar en cliente. El resultado se cachea por tabla.
        """
        if not refrescar and tabla in self._cache_registros:
            return self._cache_registros[tabla]
        registros: list[dict[str, Any]] = []
        pagina = 0
        while True:
            trozo = self._peticion(
                "/tables/%s/records?perPage=%d&page=%d" % (tabla, config.PAGE_SIZE, pagina))
            if not isinstance(trozo, list):
                break
            registros.extend(trozo)
            if len(trozo) < config.PAGE_SIZE:
                break
            pagina += 1
        _log.info("[%s] %s: %d registros descargados", self.etiqueta, tabla, len(registros))
        self._cache_registros[tabla] = registros
        return registros

    def get_record(self, tabla: str, record_id: int) -> dict[str, Any] | None:
        """Lectura directa de un registro por id (evita paginar)."""
        try:
            return self._peticion("/tables/%s/records/%s" % (tabla, record_id))
        except NinoxNotFoundError:
            return None

    def fetch_records_by_ids(self, tabla: str, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
        """{id: registro} en una sola pasada sobre la caché de la tabla."""
        indice = {r["id"]: r for r in self.fetch_all_records(tabla)
                  if isinstance(r.get("id"), int)}
        return {i: indice[i] for i in set(ids) if i in indice}

    def invalidar_cache(self, tabla: str | None = None) -> None:
        if tabla is None:
            self._cache_registros.clear()
        else:
            self._cache_registros.pop(tabla, None)

    # ──────────────────────────────────────────────────────────────────────────
    # Escrituras
    # ──────────────────────────────────────────────────────────────────────────
    def crear_registro(self, tabla: str, campos: dict[str, Any]) -> dict[str, Any]:
        """Alta verificada: valida nombres, envía y **relee** el registro.

        Devuelve el registro tal y como quedó guardado (no el eco del POST).
        """
        self.validar_campos(tabla, campos)
        payload = {"fields": self._coercionar(tabla, campos)}
        status, cuerpo = self._peticion_escritura("POST", "/tables/%s/records" % tabla, payload)

        if status == 500:
            # Casi siempre es un nombre de campo: refrescar el esquema y un único
            # reintento, como manda el know-how.
            _log.warning("[%s] HTTP 500 al crear en %s. Se refresca el esquema y se "
                         "reintenta una vez.", self.etiqueta, tabla)
            self.metadatos_tabla(tabla, refrescar=True)
            self.validar_campos(tabla, campos)
            status, cuerpo = self._peticion_escritura("POST", "/tables/%s/records" % tabla, payload)
            if status == 500:
                raise NinoxMappingError(
                    "Ninox devuelve 500 al crear en [%s].%s (parece un problema de mapeo "
                    "de campos, no una caída). Campos enviados: %s. Respuesta: %r"
                    % (self.etiqueta, tabla, sorted(campos), cuerpo))

        if status in (401, 403):
            raise NinoxAuthError("Credencial rechazada (%d) al crear en %s." % (status, self.etiqueta))
        if status >= 400:
            raise NinoxError("HTTP %d al crear en [%s].%s: %r"
                             % (status, self.etiqueta, tabla, cuerpo))

        nuevo_id = cuerpo.get("id") if isinstance(cuerpo, dict) else None
        if nuevo_id is None:
            raise NinoxError("El alta en [%s].%s no devolvió id: %r"
                             % (self.etiqueta, tabla, cuerpo))
        self.invalidar_cache(tabla)
        guardado = self.get_record(tabla, int(nuevo_id))
        if guardado is None:
            raise NinoxError("El registro %s creado en [%s].%s no se puede releer."
                             % (nuevo_id, self.etiqueta, tabla))
        return guardado

    def borrar_registro(self, tabla: str, record_id: int) -> int:
        """Borra un registro. Devuelve el código HTTP (200 si fue bien)."""
        status, _ = self._peticion_escritura(
            "DELETE", "/tables/%s/records/%s" % (tabla, record_id))
        self.invalidar_cache(tabla)
        return status


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades de lectura
# ──────────────────────────────────────────────────────────────────────────────
def primer_id_ref(valor: Any) -> int | None:
    """Extrae el id de un campo ``ref`` de Ninox.

    Los ref llegan como ``196``, ``[321]``, ``[196, 197]`` o ``{'id': 3}``.
    """
    if valor is None:
        return None
    if isinstance(valor, list):
        if not valor:
            return None
        valor = valor[0]
    if isinstance(valor, dict) and "id" in valor:
        return int(valor["id"])
    if isinstance(valor, (int, float)):
        return int(valor)
    return None
