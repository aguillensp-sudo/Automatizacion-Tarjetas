@echo off
rem ─────────────────────────────────────────────────────────────────────────────
rem  Automatización Tarjetas Banco · lanzador para el acceso directo del escritorio
rem  Arranca la ventana SIN consola (pythonw). Si algo falla al arrancar, usa
rem  «iniciar_con_consola.bat», que muestra el error.
rem ─────────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"
start "" pythonw.exe "%~dp0main.py"
endlocal
