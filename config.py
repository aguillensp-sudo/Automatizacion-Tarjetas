"""Configuración de la aplicación "Automatización Tarjetas Banco".

Aquí viven las rutas, los destinos de Ninox y la tabla de tarjetas. **No hay
secretos**: la única credencial es ``NINOX_API_KEY`` y se resuelve en
``env_loader.py``.

Decisión de diseño (regla 7 del know-how de Ninox): **la base de datos destino
nunca la elige una variable de entorno**. Los identificadores de team y base
están escritos aquí, verificados contra la API el 15/10/2026, y las variables
``NINOX_DB_ID`` / ``NINOX_DBFAWALT_ID`` sólo se usan para avisar si la máquina
apunta a otra base de la esperada.
"""
from __future__ import annotations

from pathlib import Path

APP_NOMBRE = "Automatización Tarjetas Banco"
APP_VERSION = "1.0.0"

# ──────────────────────────────────────────────────────────────────────────────
# Rutas
# ──────────────────────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent
PDFS_DIR: Path = BASE_DIR / "PDFS"
LOGS_DIR: Path = BASE_DIR / "logs"
ICONO_ICO: Path = BASE_DIR / "recursos" / "tarjetas.ico"
ICONO_PNG: Path = BASE_DIR / "recursos" / "tarjetas.png"

# ──────────────────────────────────────────────────────────────────────────────
# API de Ninox (interfaz clásica: teams → databases → tables)
# ──────────────────────────────────────────────────────────────────────────────
NINOX_BASE_URL: str = "https://api.ninox.com/v1"
NINOX_TEAM_ID: str = "qCq3JS7q7ptoap8Yg"     # «Equipo JI» (compartido por las dos bases)
NINOX_TABLA_TARJETAS: str = "YB"             # Tarjetas Banco / Credit Cards
NINOX_TABLA_CATALOGO: str = "XB"             # Tarjetas Bancarias (catálogo de tarjetas)

REQUEST_TIMEOUT_SEC: int = 60
PAGE_SIZE: int = 100                          # máximo aceptado por Ninox
MAX_RETRIES: int = 3
RETRY_BACKOFF_SEC: float = 1.5

ENV_API_KEY = "NINOX_API_KEY"

# ──────────────────────────────────────────────────────────────────────────────
# Bases de datos destino, verificadas contra la API el 15/10/2026.
# ──────────────────────────────────────────────────────────────────────────────
DB_JULSA = "JULSA"
DB_FAWALT = "FAWALT"

BASES: dict[str, dict[str, str]] = {
    DB_JULSA: {
        "id": "ssy88c9uryyl",
        "nombre": "JULSA INDUSTRIAL",
        "env_id": "NINOX_DB_ID",
        "tabla_yb": "YB",          # «Tarjetas Banco»
        "tabla_yb_nombre": "Tarjetas Banco",
    },
    DB_FAWALT: {
        "id": "we43bpehexq6",
        "nombre": "FAWALT INVESTMENT",
        "env_id": "NINOX_DBFAWALT_ID",
        "tabla_yb": "YB",          # «Credit Cards»
        "tabla_yb_nombre": "Credit Cards",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Campos de la tabla YB (id ↔ nombre). Los nombres son los que viajan en el
# payload; los ids son los que aparecen en requisitos_funcionales.md.
#
# ⚠ Los campos se validan contra los metadatos reales de cada base al arrancar
# (`NinoxClient.validar_campos_yb`): si alguien renombra una columna en Ninox,
# el fallo se ve al empezar y no a mitad de una inserción.
# ──────────────────────────────────────────────────────────────────────────────
CAMPO_YB_BANCOS = "Bancos"                          # A, ref → T (no se informa)
CAMPO_YB_TARJETA = "Tarjeta Bancaria"               # B, ref → XB
CAMPO_YB_FECHA = "Fecha"                            # C, date
CAMPO_YB_IMPORTE = "Importe"                        # D, number
CAMPO_YB_CODIGO_PRESUPUESTARIO = "Código Presupuestario"   # E, ref → B (no se informa)
CAMPO_YB_EXPEDIENTE = "Expediente"                  # F, ref → CB (no se informa)
CAMPO_YB_TIPO = "Tipo"                              # G, choice
CAMPO_YB_TESORERIA = "Tesorería"                    # H, ref → A (no se informa)
CAMPO_YB_IMPORTE_IVA = "Importe IVA deducible"      # J, number

#: Campos que informa esta aplicación al dar de alta un movimiento.
CAMPOS_YB_INFORMADOS: tuple[str, ...] = (
    CAMPO_YB_TARJETA,
    CAMPO_YB_FECHA,
    CAMPO_YB_IMPORTE,
    CAMPO_YB_TIPO,
)

#: Campo calculado por la aplicación al comparar: Importe + Importe IVA deducible.
#: Decisión del PO (15/10/2026): la comparación se hace contra D + J.
CAMPOS_YB_IMPORTE_COMPARADO: tuple[str, ...] = (CAMPO_YB_IMPORTE, CAMPO_YB_IMPORTE_IVA)

# Valores del choice `G. Tipo` (metadatos reales, ambas bases)
TIPO_CARGO_PUNTUAL = "1"      # «Cargo puntual»
TIPO_CARGO_PUNTUAL_TEXTO = "Cargo puntual"
TIPO_CARGO_TOTAL_MES = "2"    # «Cargo Total Mes»
TIPO_CARGO_TOTAL_MES_TEXTO = "Cargo Total Mes"

# ──────────────────────────────────────────────────────────────────────────────
# Tarjetas contempladas (requisitos_funcionales.md §4.2)
#
# `xb_id` es el identificador del registro en la tabla `XB` «Tarjetas
# Bancarias», que es el valor que se informa en `YB.Tarjeta Bancaria` (campo B).
# Los ids son los que fija el requisito y se **verifican contra Ninox** al
# procesar: si el número de la tarjeta guardado en `XB` no corresponde a la
# máscara del PDF, el proceso se detiene con un error explícito.
# ──────────────────────────────────────────────────────────────────────────────
TARJETAS: dict[str, dict[str, object]] = {
    "4106 **** **** 4011": {
        "base": DB_JULSA,
        "xb_id": 13,
        "titular": "FIDEL RODRIGUEZ MORALES",
        "etiqueta": "JULSA · VISA BUSINESS (FIDEL RODRIGUEZ MORALES)",
    },
    "5566 **** **** 1012": {
        "base": DB_JULSA,
        "xb_id": 17,
        "titular": "ALVARO M. GUILLEN",
        "etiqueta": "JULSA · MASTERCARD ORO (ALVARO M. GUILLEN)",
    },
    "5566 **** **** 5013": {
        "base": DB_FAWALT,
        "xb_id": 13,
        "titular": "ALVARO M. GUILLEN",
        "etiqueta": "FAWALT · MASTERCARD ORO (ALVARO M. GUILLEN)",
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# Geometría del extracto de Banco Sabadell.
#
# Las columnas se identifican por la coordenada X del inicio de cada palabra,
# NO por el orden en que el texto plano aparece en la extracción (que devuelve
# «Importe de la operación» antes que «Tipo de cambio aplicado»). Verificado
# sobre los tres extractos de prueba; la suma de los importes leídos debe
# cuadrar con la línea «Total operaciones» o el proceso se detiene.
# ──────────────────────────────────────────────────────────────────────────────
COL_FECHA_MAX = 62.0            # «0109»
COL_CONCEPTO_MIN = 62.0
COL_CONCEPTO_MAX = 285.0
COL_POBLACION_MIN = 285.0
COL_POBLACION_MAX = 362.0
COL_IMPORTE_ORIGEN_MIN = 362.0
COL_IMPORTE_ORIGEN_MAX = 428.0
COL_TIPO_CAMBIO_MIN = 428.0
COL_TIPO_CAMBIO_MAX = 479.0
COL_IMPORTE_OP_MIN = 479.0
COL_IMPORTE_OP_MAX = 516.0

TEXTO_TOTAL_OPERACIONES = "total operaciones"
TEXTO_NUMERO_TARJETA = "número de tarjeta"
TEXTO_SELLO_LIQUIDACION = "MADRID"

# Tolerancia al comprobar que la suma de importes cuadra con el total del banco
TOLERANCIA_TOTAL = 0.01
