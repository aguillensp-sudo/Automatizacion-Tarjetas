# Automatización Tarjetas Banco

Aplicación de escritorio (Windows 11) que lee los **extractos mensuales de tarjeta
de crédito de Banco Sabadell** que el usuario deja en `PDFS\`, comprueba si cada
movimiento **ya existe** en el ERP **Ninox** y permite darlos de alta con decisión
del usuario, registro a registro.

Trabaja sobre dos bases de datos distintas según la tarjeta:

| Tarjeta (máscara del extracto) | Base de datos | Tabla | Registro `XB` |
|---|---|---|---|
| `5566 **** **** 1012` | JULSA INDUSTRIAL | `YB` «Tarjetas Banco» | 17 |
| `4106 **** **** 4011` | JULSA INDUSTRIAL | `YB` «Tarjetas Banco» | 13 |
| `5566 **** **** 5013` | FAWALT INVESTMENT | `YB` «Credit Cards» | 13 |

> Los ids de `XB` son los del requisito y **se verifican contra Ninox** en cada
> ejecución: si el número de tarjeta guardado no corresponde a la máscara del PDF,
> el proceso se detiene en lugar de imputar los movimientos a otra tarjeta.

---

## 1. Cómo se usa

1. El usuario deja los extractos en `C:\Users\admin\proyectos\Utilidades\Tarjetas-banco\PDFS`.
2. Abre la aplicación desde el **acceso directo del escritorio**
   («Automatización Tarjetas Banco», con su icono).
3. La ventana muestra la **carpeta de trabajo** y la **lista de ficheros**
   (campos informativos, no editables) y pregunta si se quieren procesar.
   * Si no hay ficheros, avisa con un mensaje de error.
   * Si se responde «No», la aplicación se cierra.
4. La ventana **no se cierra**: muestra una **barra de estado** y un **historial**
   de todo lo que va haciendo. Cualquier error se muestra en la barra de estado y
   **detiene el proceso**.
5. Los resultados aparecen agrupados **por extracto y tarjeta**, con los registros
   que no existen (que se contarán para insertar) y los que requieren decisión.
6. El usuario marca **Insertar** o **Desestimar** en **todos** los registros que lo
   requieren (la aplicación no deja ejecutar si falta alguno) y pulsa
   **«Ejecutar las inserciones»**.
7. Al terminar, muestra el **total de inserciones** o el motivo del error.

### Otras formas de arrancar

```bat
python main.py                  :: abre la ventana (con consola, útil para depurar)
pythonw main.py                 :: abre la ventana sin consola (lo que hace el acceso directo)
python main.py --consola        :: INFORME por consola, sólo lectura, sin escribir en Ninox
python main.py --consola --fichero FW-AGS.pdf
iniciar_con_consola.bat         :: lanzador con consola, para ver errores de arranque
```

---

## 2. Reglas de negocio que aplica

### Lectura del extracto (§4.1)

* **Nunca se lee la primera página** (resumen de condiciones).
* Se leen la segunda y siguientes **hasta la línea «Total operaciones»**.
* Las operaciones se localizan por las **coordenadas** de cada palabra: la
  extracción de texto devuelve «Importe de la operación» antes que «Tipo de cambio
  aplicado», y agrupar por líneas de texto mezclaría importes con tipos de cambio.
* El año (el detalle sólo trae `DDMM`) se deduce del **sello de liquidación** de la
  propia página de la tabla (`MADRID,VERGARA,05.10.26`): el período liquidado es el
  **mes anterior**. Así no hace falta leer la página 1.
* **Comprobación de integridad**: la suma de los importes leídos tiene que cuadrar
  con el «Total operaciones» del banco. Si no cuadra, el proceso se detiene.

### Campos que se informan (§4.2)

| Extracto | Campo Ninox | ¿Se informa? |
|---|---|---|
| Fecha | `C` Fecha | **Sí** (`AAAA-MM-DD`) |
| Importe de la operación | `D` Importe | **Sí** |
| — (catálogo) | `B` Tarjeta Bancaria | **Sí** (registro de `XB`) |
| — (regla fija) | `G` Tipo | **Sí** = `1` «Cargo puntual» |
| Concepto, Población/país, Importe de la moneda de origen, Tipo de cambio | no existen en Ninox | No |
| Total Operaciones | ver más abajo | — |

Los campos `A` Bancos, `E` Código Presupuestario, `F` Expediente, `H` Tesorería y
`J` Importe IVA deducible **se dejan en blanco**.

### Conciliación (§5)

Para cada movimiento del extracto se compara **Fecha** e **Importe** con los
registros de esa tarjeta en `YB`. El importe comparado es el cálculo
`D + J` (Importe + Importe IVA deducible), según la decisión del PO.

| Caso | Condición | Qué hace la aplicación |
|---|---|---|
| **a** | No existe ningún movimiento de esa tarjeta con esa fecha | Se cuenta como **nuevo** y se inserta sin preguntar |
| **b** | Existe uno con la **misma fecha y el mismo importe** | **Coincidencia**: se muestra con los datos de Ninox y el usuario decide |
| **c** | Existe uno con la **misma fecha y distinto importe** | **Incidencia**: se muestra la diferencia y el usuario decide |

Detalles que evitan falsos avisos:

* El emparejamiento es **1 a 1**: dos consumos idénticos el mismo día consumen dos
  registros distintos.
* Los apuntes `G = 2` «Cargo Total Mes» **no cuentan** como coincidencia de una
  operación: son la liquidación, no el consumo.
* Si el registro «Cargo Total Mes» de ese período **ya existe**, se avisa antes de
  crear un duplicado.

### Total Operaciones (§7)

Por cada línea «Total operaciones» detectada se crea **un** registro más:

| Campo | Valor |
|---|---|
| `C` Fecha | **día 5 del mes de la liquidación** y año del extracto (`2026-10-05`) |
| `B` Tarjeta Bancaria | la misma tarjeta del extracto |
| `D` Importe | el valor de «Total operaciones» |
| `G` Tipo | `2` «Cargo Total Mes» |
| resto | en blanco |

---

## 3. Seguridad al escribir en Ninox

El ERP es contabilidad real: las reglas del know-how de Ninox están implementadas
en `ninox_client.py` y `tarjetas\executor.py`.

1. **Los nombres de campo se validan contra los metadatos antes de enviar.** Un
   nombre mal escrito no devuelve `400`, devuelve **`500` sin explicación**. La
   validación previa convierte ese fallo opaco en un mensaje claro.
2. **Después de crear, se relee el registro** y se compara con lo enviado: hay
   campos con valor por defecto que descartan lo enviado. Si no coincide, se avisa
   y **se detiene el proceso**.
3. **Un `POST` no se reintenta jamás a ciegas.** Si se pierde la respuesta, el
   registro puede haber entrado: se pasa a estado *incierto* y se reconcilia
   **leyendo**. Nunca se duplica un apunte contable.
4. **El proceso se detiene en el primer error** y el informe dice cuántos registros
   se habían creado y con qué ids, para poder revisarlos.
5. **Antes de escribir se pide confirmación**, con el número de altas y su reparto
   por base de datos.
6. **La base destino nunca la elige una variable de entorno**: los identificadores
   están fijados en `config.py`. Las variables `NINOX_DB_ID` / `NINOX_DBFAWALT_ID`
   sólo se usan para **avisar** si la máquina apunta a otra base.

---

## 4. Instalación y entorno

* **Python 3.14** (probado con 3.14.4). Dependencias:

```bat
pip install -r requirements.txt
```

`PyMuPDF` (lectura del PDF), `Pillow` (icono), `pytest` (pruebas). La comunicación
con Ninox usa `urllib` de la biblioteca estándar.

* **Credencial**: `NINOX_API_KEY` como variable de entorno del usuario:
  ```bat
  setx NINOX_API_KEY "tu_token"
  ```
  La aplicación la busca primero en el proceso y, si no está, en el registro de
  usuario de Windows (necesario porque el acceso directo arranca con `pythonw`).
  **El token nunca se registra en el log ni se imprime.**

* **Acceso directo del escritorio** (con icono):

```bat
python tools/crear_icono.py             :: genera recursos\tarjetas.ico
python tools\crear_acceso_directo.py    :: crea el acceso directo con ese icono
```

---

## 5. Estructura del proyecto

```
Tarjetas-banco\
├─ main.py                     punto de entrada (ventana o informe por consola)
├─ config.py                   rutas, bases de Ninox, tabla de tarjetas, geometría del PDF
├─ env_loader.py               resolución de NINOX_API_KEY
├─ ninox_client.py             cliente REST: paginación, backoff, validación, alta verificada
├─ tarjetas\
│  ├─ pdf_reader.py            lectura del extracto (páginas, columnas, total, cuadre)
│  ├─ cards.py                 máscara del PDF → base de datos y registro `XB`
│  ├─ mapping.py               extracto → campos de `YB`
│  ├─ reconciler.py            casuísticas a) / b) / c)
│  ├─ executor.py              plan de inserciones y ejecución verificada
│  └─ pipeline.py              proceso completo (lo comparten la ventana y la consola)
├─ ui\
│  ├─ app.py                   ventana: carpeta, ficheros, pregunta, log, estado, ejecutar
│  └─ results_view.py          resultados por extracto y decisiones Insertar/Desestimar
├─ recursos\tarjetas.ico|png   icono de la aplicación
├─ tools\                      sondas, icono, acceso directo y pruebas de escritura
├─ tests\                      pruebas (incluye un extracto sintético con la geometría real)
├─ PDFS\                       extractos a procesar — NUNCA se publica (está en .gitignore)
└─ logs\                       historial de cada sesión y trazas de las pruebas
```

---

## 6. Pruebas

```bat
python -m pytest tests/ -q                     :: toda la batería
python tools\prueba_arranque_gui.py            :: arranque simulado de la ventana (sólo lectura)
python tools\prueba_escritura_ninox.py         :: prueba de escritura, SIMULACIÓN (por defecto)
```

El extracto real **no se publica**, así que las pruebas construyen un extracto
sintético con las **mismas coordenadas** que usa el banco (`tests/sintetico.py`) y,
si la carpeta `PDFS\` existe, verifican además los tres extractos reales.

### Prueba de escritura en producción

Autorizada por el PO para comprobar y limpiar. Los registros de prueba se
reconocen por un **importe marcador imposible** (`987654.32` y `98765.43`) y se
borran inmediatamente después de verificarlos:

```bat
python tools\prueba_escritura_ninox.py                              :: simulación, no escribe
python tools\prueba_escritura_ninox.py --execute --confirm ESCRIBIR-Y-BORRAR
python tools\prueba_escritura_ninox.py --limpiar                    :: busca residuos (sólo lectura)
python tools\prueba_escritura_ninox.py --limpiar --execute --confirm ESCRIBIR-Y-BORRAR
```

Deja traza en `logs\prueba_escritura_<fecha>.json` con los ids creados y borrados.

---

## 7. Límites conocidos

* Sólo se contemplan las **tres tarjetas** del requisito. Cualquier otra máscara
  detiene el proceso con un mensaje claro.
* El formato leído es el de **Banco Sabadell** (`Liquidación del contrato de
  tarjeta de crédito`). Otro banco exigiría revisar `config.py` (geometría de
  columnas) y `tarjetas\pdf_reader.py`.
* Las fechas del detalle no traen año: se deduce del sello de liquidación (mes
  anterior). Si un extracto se emitiera con otra periodicidad, habría que revisarlo.
* La API de Ninox **no filtra en servidor**: para conciliar se descarga la tabla
  `YB` completa de la base y se filtra en cliente (una vez por base y ejecución).
* El esquema de Ninox **no dice qué campos son obligatorios**: la aplicación informa
  los cuatro campos del requisito y deja el resto en blanco, tal y como se pidió.
