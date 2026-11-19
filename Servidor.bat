@echo off
rem Doble click: si esta detenido lo arranca en segundo plano y abre el navegador; si esta corriendo lo detiene.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0servicio.ps1" toggle
timeout /t 2 >nul
