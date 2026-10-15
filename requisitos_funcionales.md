# OBJETIVO
Este proyecto de automatización persigue realizar una lectura de documentos pdf bancarios en los que se recogen movimientos asociados a una tarjeta de crédito comprendidsos en un período mensual. Se trata de leer los registros de movimientos y verificar si existen en Ninox. El programa devolverá tras la lectura una conclusión que indique si los registros ya existían o si hay que incluirlos.

## 1. Know-how previo adquirido y base de partida para el proyecto.
- Lee la carpeta: C:\Users\admin\proyectos\ninox-agent-skill. Este trabajo proporciona información sobre como trabajar leyendo/insertando registros en nuestro ERP. Asimismo lee la carpeta: C:\Proyectos\ninox-ai-agent.
- Los proyectos que se han realizado sobre nuestro ERP hasta ahora están en la carpeta C:\Users\admin\proyectos\Utilidades
- Se ha creado un proyecto en GitHub contra el que deberán realizarse los commits: https://github.com/aguillensp-sudo/Automatizacion-Tarjetas
- Se ha creado una carpeta en local contra la que deberá trabajarse toda la documentación: "C:\Users\admin\proyectos\Utilidades\Tarjetas-banco".

## 2. Accesos/Bases de datos y tablas implicadas
- usa Get-ChildItem Env: en el terminal para acceder a Ninox con la NINOX_API_KEY.
- Los accesos a GitHub los conoces también por Terminal.
- Se van a realizar lecturas/modificaciones y alta de registros en dos tablas:
    a) En la BBDD de JULSA INDUSTRIAL, la tabla es la `YB` (TARJETAS BANCO)
    b) En la BBDD de FAWALT INVESTMENT, la tabla es la `YB` (CREDIT CARDS)

## 3. Procedimiento
    3.1. El usuario deja en la carpeta "C:\Users\admin\proyectos\Utilidades\Tarjetas-banco\PDFS" los pdfs que hay que leer. Te dejo los dos primeros para realizar pruebas. La carpeta "C:\Users\admin\proyectos\Utilidades\Tarjetas-banco\PDFS" nunca debe publicarse en GitHub
    3.2. El usuario arranca la aplicación desde su escritorio de windows 11.
    3.3. La aplicación le muestra la carpeta de trabajo y le indica la lista de ficheros disponibles. Si no hay ficheros se lo muestra con un mensaje de error. Si hay ficheros, le pregunta si quiere procesarlos o no. Si dice que no, se cierra la aplicación. Si dice que si, se procede a la lectura de los ficheros. Este campo/s es/son informativo, nunca editables.
    3.4. La aplicación procede a la lectura de los pdfs. La ventana no se cierra y contiene una barra de estado del proceso con una ventana informativa del log de lo que está haciendo. Si hay algún error, se muestra en la barra de estado y se detiene el proceso. Si todo va bien, se muestra el log de lo que se ha hecho.
    3.5. Resultados de la lectura. Consultar apartado ##5.

## 4. Rutina de trabajo del agente:
    4.1. Lectura de pdf. Instrucciones:
        - No leer nunca la primera página.
        - Leer la segunda y posteriores hasta que aparezca una línea en la tabla que indique "TOTAL OPERACIONES". Esa es la última línea que debe  leerse.
        - Aplica los conocimientos que ya tienes para analizar los datos y preservarlo en memoria para las siguientes fases de la rutina del agente.
    4.2. Campos a analizar de cada pdf:
        - Número de tarjeta (Primer campo arriba la izquierda):
            -Valores posibles y selección de empresa: 
                GIVEN "4106 **** **** 4011" THEN BASE DE DATOS: JULSA INDUSTRIAL
                GIVEN "5566 **** **** 5013" THEN BASE DE DATOS: FAWALT INVESTMENT
                GIVEN "5566 **** **** 1012" THEN BASE DE DATOS: JULSA INDUSTRIAL
        - Tabla de datos con operaciones (Los movimientos se muestran en cada línea en el marco de una tabla).
**TABLA DE MAPEO**        
| Número de tarjeta | Campo Extracto | Campo Ninox | BBDD Ninox | Valor a informar si no existe campo mapeado |
| --- | --- | --- | --- | --- |
| 5566 \*\*\*\* \*\*\*\* 1012 | Fecha | `C` | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | Concepto | No Existe | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | Población/país | No Existe | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | Importe de la moneda de origen | No Existe | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | Tipo de cambio aplicado | No Existe | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | Importe de la operación | `D` | JULSA INDUSTRIAL | NaN |
| 5566 \*\*\*\* \*\*\*\* 1012 | No Existe | `B` | JULSA INDUSTRIAL | Tabla: `XB. Registro a seleccionar 'Nr'=17; Titular:"ALVARO M. GUILLEN" |
| 5566 \*\*\*\* \*\*\*\* 1012 | No Existe | `G` | JULSA INDUSTRIAL | Seleccionar: `1`(cargo puntual) |
| 5566 \*\*\*\* \*\*\*\* 1012 | Total Operaciones | \*\*Desestimar/Este campo tiene otra funcionalidad que se explica más adelante\*\* | NaN | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Fecha | `C` | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Concepto | No Existe | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Población/país | No Existe | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Importe de la moneda de origen | No Existe | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Tipo de cambio aplicado | No Existe | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | Importe de la operación | `D` | JULSA INDUSTRIAL | NaN |
| 4106 \*\*\*\* \*\*\*\* 4011 | No Existe | `B` | JULSA INDUSTRIAL | Tabla: `XB. Registro a seleccionar 'Nr'=13; Titular:"FIDEL RODRIGUEZ MORALES" |
| 4106 \*\*\*\* \*\*\*\* 4011 | No Existe | `G` | JULSA INDUSTRIAL | Seleccionar: `1`(cargo puntual) |
| 4106 \*\*\*\* \*\*\*\* 4011 | Total Operaciones | \*\*Desestimar/Este campo tiene otra funcionalidad que se explica más adelante\*\* | NaN | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Fecha | `C` | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Concepto | No Existe | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Población/país | No Existe | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Importe de la moneda de origen | No Existe | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Tipo de cambio aplicado | No Existe | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | Importe de la operación | `D` | FAWALT INVESTMENT | NaN |
| 5566 \*\*\*\* \*\*\*\* 5013 | No Existe | `B` | FAWALT INVESTMENT | Tabla: `XB. Registro a seleccionar 'Nr'=17; Titular:"ALVARO M. GUILLEN" |
| 5566 \*\*\*\* \*\*\*\* 5013 | No Existe | `G` | FAWALT INVESTMENT | Seleccionar: `1`(cargo puntual) |
| 5566 \*\*\*\* \*\*\*\* 5013 | Total Operaciones | \*\*Desestimar/Este campo tiene otra funcionalidad que se explica más adelante\*\* | NaN | NaN |

## 5. Resultados de la lectura.
- Para cada registro de las tablas pdf extraidas que tengan una Fecha informada en sus tablas hay que compararlas contra la lectura de la tabla correspondiente en Ninox. Los campos que se compararán en Ninox son: Fecha e Importe (Ojo este campo es calculado por Ninox y no aparece en la tabla. Es siempre la suma de dos campos que aparecen en tabla `D`+`J`). Si ambos coinciden el registro se cuenta como Repetido y si alguno no coincide se le indicará al usuario la incidencia para que decida si deben ser registrados.
Se pueden dar las siguientes casuísticas:
    a) GIVEN El registro no existe THEN crear registro en Ninox
    b) GIVEN la comparacion de fecha e Importe es idéntica a la existente en Ninox THEN se informa al usuario de la coincidencia
    c) GIVEN al leer Ninox se observan campos en los que la fecha es coincidente THEN se informa al usuario de la incidencia

## 6. Presentación de resultados
El usuario debe decidir sobre los resultdos del apartado anterior. Las casuísticas son:
    WHEN a) THEN sumar número de registros a insertar al no existir coincidencias.
    WHEN b) o c) THEN indicar los datos del registro separando el que es coincidencia del que es incidencia y poner a cada lado un radio buttom que indique Insertar o Desestimar.
Cada una de las tablas tendrá su espacio para que al usuario le quede claro contra que pdf/tabla Ninox se van a ejecutar las decisiones/tareas.

## 7. Funcionalidad de la columna Total Operaciones
Por cada registro "TOTAL OPERACIONES" DETECTADO, se crea una nueva línea en Ninox informando los siguientes campos:
    a) Fecha: día 5 del mes que se registra y año que se registra. 
    b) Tarjeta Bancaria: La misma que corresponde a los registros de la tabla/pdf que se ha leído.
    c) Importe: Corresponde al valor del campo "TOTAL OPERACIONES"
    d) `G`: `2`(cargo total mes)
    El resto de campos se dejan en blanco

## 8. Ejecución de la tarea
Una vez el usuario ha decidido sobre todos los radio buttom (obligado informar uno u otro pues sino es así no se puede continuar ejecutando) la aplicación realiza las acciones en Ninox en cada tabla. Mostrará barra de estado y log como ya se indicó y finalizará mostrando error al usuario si el proceso no pudo completarse indicando la razón o si por el contrario se ejecutó conforme a lo previsto, mostrando en un mensaje el total de inserciones.

## 9. Tu plan de ejecución
Después de haber leído y analizado todo este documento:
1. Pregunta al PO las dudas relativas al desarrollo. Antes de preguntar asegurate de haber leído todo el contexto bien.
2. Decide sobre la arquitectura de la aplicación y sus componentes. Muestra al PO como consideras que debería realizarse y Comprueba si todo el entorno que se te proporciona tiene las herramientas y claves para realizarlo.
3. una vez tengas el OK del PO, trabaja autonomamente para completar la tarea sin interrupción.
4. Puedas usar las bases de datos en producción de Ninox para insertar registros y hacer las comprobaciones que necesites para tus tests. Al final procede al borrado de los registros creados.
5. Crea un acceso directo en el escritorio para la aplicación y elige un icono que te guste.


            