@echo off
rem ─────────────────────────────────────────────────────────────────────────────
rem  Automatización Tarjetas Banco · lanzador CON consola
rem  Útil para ver los errores de arranque (credencial ausente, PDF ilegible…).
rem  Para el uso normal, usa el acceso directo del escritorio o iniciar.bat.
rem ─────────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"
python.exe "%~dp0main.py" %*
if errorlevel 1 (
    echo.
    echo ─────────────────────────────────────────────────────────────
    echo  La aplicacion termino con error. Revisa el mensaje de arriba.
    echo ─────────────────────────────────────────────────────────────
    pause
)
endlocal
