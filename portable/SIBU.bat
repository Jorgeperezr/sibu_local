@echo off
REM ---------------------------------------------------------------------------
REM  SIBU portable — Windows
REM
REM  Esto es lo que hay detras del icono. Crea un acceso directo a este archivo
REM  en el escritorio y cambiele el icono por portable\sibu.ico.
REM
REM  Usa el Python que viaja en la carpeta (python\python.exe) si esta, y si no
REM  el del sistema. Asi la carpeta funciona en un computador sin Python
REM  instalado, que es de lo que trata ser portable.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

if exist "python\python.exe" (
    set "PY=python\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  No se encontro Python, y la carpeta no trae el suyo.
        echo  Ejecute portable\preparar_windows.ps1 para armarla completa,
        echo  o instale Python 3.11 o superior.
        echo.
        pause
        exit /b 1
    )
    set "PY=python"
)

title SIBU - Unidad de Bienestar Universitario
echo Arrancando SIBU... no cierre esta ventana mientras lo use.
"%PY%" portable\arrancar.py %*

REM Si algo revienta, que la ventana no se cierre antes de poder leerlo.
if errorlevel 1 pause
endlocal
