@echo off
rem Version de desarrollo: consola visible (ves logs y errores), puerto 8000. No lo uses a la vez que el servicio en segundo plano (Servidor.bat), usan el mismo puerto.
cd /d "%~dp0"
set APUNTES_PORT=8000
set PY=py -3
%PY% --version >nul 2>&1 || set PY=python
%PY% -u servidor.py
pause
