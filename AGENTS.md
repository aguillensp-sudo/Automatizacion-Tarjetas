# Instrucciones para agentes IA que trabajen en este repositorio

Este proyecto lee **extractos de tarjeta de Banco Sabadell** y los concilia contra
el ERP **Ninox** (tablas `YB` de JULSA INDUSTRIAL y FAWALT INVESTMENT). El requisito
funcional completo está en `requisitos_funcionales.md`; la guía de uso, en
`README.md`. Este fichero es el punto de entrada para un agente.

## Reglas no negociables

1. **`PDFS\` no se publica nunca.** Contiene extractos bancarios reales. Está en
   `.gitignore`; no lo añadas con `git add -f` ni lo copies a otro sitio del repo.
2. **No inventes nombres de campo ni ids de registro.** Los nombres de la tabla `YB`
   están en `config.py` y se **validan contra los metadatos reales** antes de enviar.
   Un nombre mal escrito devuelve **HTTP 500**, no un 400: parece una caída del
   servidor y no dice qué falló.
3. **Tras crear, vuelve a leer.** Hay campos con valor por defecto que descartan lo
   enviado. Nunca te fíes del eco del `POST`.
4. **Un `POST` no se reintenta a ciegas.** Si se pierde la respuesta, el registro
   puede haber entrado: reconcilia leyendo (`EscrituraIncierta` en `ninox_client.py`).
5. **No borres registros en tablas de negocio.** La única excepción es la limpieza de
   los registros de prueba con **importe marcador** (`987654.32` / `98765.43`),
   creados por `tools/prueba_escritura_ninox.py` y anotados en
   `logs/prueba_escritura_<fecha>.json`.
6. **El destino no lo elige el entorno.** Team y base están fijados en `config.py`;
   las variables `NINOX_DB_ID` / `NINOX_DBFAWALT_ID` sólo sirven para avisar de una
   discrepancia.
7. **Nunca imprimas ni registres `NINOX_API_KEY`.** Compruébala por longitud o por
   efecto, jamás por valor.
8. **Ninox puede tener automatizaciones que la API no muestra**: crear un registro
   puede tocar otras tablas.

## Cómo está organizado

| Si vas a… | Mira |
|---|---|
| Cambiar cómo se lee el PDF | `tarjetas/pdf_reader.py` + la geometría en `config.py` |
| Cambiar a qué base/tarjeta se escribe | `config.py` (bloque `TARJETAS` y `BASES`) |
| Cambiar la conciliación (casuísticas a/b/c) | `tarjetas/reconciler.py` |
| Cambiar qué campos se informan | `tarjetas/mapping.py` |
| Cambiar el alta o su verificación | `tarjetas/executor.py` y `ninox_client.py` |
| Tocar la ventana | `ui/app.py` (flujo) y `ui/results_view.py` (decisiones) |
| Entender el orden de todo el proceso | `tarjetas/pipeline.py` → `procesar()` |

## Antes de dar algo por bueno

```bat
python -m pytest tests/ -q                       :: deben pasar todas
python main.py --consola                         :: informe real, sólo lectura
python tools\prueba_arranque_gui.py              :: la ventana arranca y procesa
python tools\prueba_escritura_ninox.py           :: simulación de la escritura
```

Si tocas la escritura, ejecuta la prueba real **con limpieza** y comprueba que no
queda residuo:

```bat
python tools\prueba_escritura_ninox.py --execute --confirm ESCRIBIR-Y-BORRAR
python tools\prueba_escritura_ninox.py --limpiar
```

## Trampas ya encontradas (no las repitas)

* **El orden del texto plano del PDF no es el de las columnas.** La extracción
  devuelve «Importe de la operación» antes que «Tipo de cambio aplicado»; hay que
  ordenar por coordenada X. Está resuelto y cubierto por pruebas.
* **Dentro de una línea, el orden por Y exacta descoloca las palabras**
  (la línea del número de tarjeta salía empezando por «BUSINESS MASTERCARD»).
  Se ordena por X.
* **Los importes negativos llevan el signo al final**: `23,99-`.
* **Comparar por texto con acentos falla**: `config.TEXTO_NUMERO_TARJETA` lleva
  tilde, así que se compara siempre con `_sin_acentos()`.
* **Al leer un `choice`, Ninox devuelve el TEXTO**; al escribir se acepta el id o el
  texto. Un log que compare contra `"1"` mentirá sobre lo que se guardó.
* **La caché de la tabla `YB`** hay que invalidarla después de escribir
  (`cliente.invalidar_cache`), o una relectura devolverá la foto antigua.
