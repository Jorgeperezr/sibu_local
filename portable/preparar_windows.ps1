# ---------------------------------------------------------------------------
#  Arma la carpeta portable de SIBU para Windows.
#
#  Qué hace: baja el Python "embeddable" de python.org, lo deja DENTRO de la
#  carpeta y le instala las dependencias ahí mismo. A partir de eso, la carpeta
#  entera se copia a cualquier Windows —o a una memoria— y funciona sin
#  instalar nada.
#
#  Se ejecuta UNA vez, en el computador donde se arma la carpeta:
#
#      powershell -ExecutionPolicy Bypass -File portable\preparar_windows.ps1
#
#  AVISO HONESTO: este script no se ha podido ejecutar donde se escribió —el
#  desarrollo corre en Linux—. La lógica es la documentada por python.org para
#  la distribución embebida, pero la primera ejecución real en Windows hay que
#  hacerla con calma y leyendo lo que imprime.
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"

$VersionPython = "3.11.9"
$Raiz    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Destino = Join-Path $Raiz "python"
$Temp    = Join-Path $env:TEMP "sibu-portable"

Write-Host ""
Write-Host "SIBU portable - armando la carpeta para Windows" -ForegroundColor Green
Write-Host "Carpeta: $Raiz"
Write-Host ""

if (Test-Path $Destino) {
    Write-Host "Ya existe '$Destino'. Borrelo si quiere rehacerlo desde cero." -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $Temp | Out-Null

# 1) Python embebido -------------------------------------------------------
$Zip = Join-Path $Temp "python-embed.zip"
$Url = "https://www.python.org/ftp/python/$VersionPython/python-$VersionPython-embed-amd64.zip"
Write-Host "[1/4] Bajando Python $VersionPython embebido..."
Invoke-WebRequest -Uri $Url -OutFile $Zip
Expand-Archive -Path $Zip -DestinationPath $Destino -Force

# La distribucion embebida trae un archivo ._pth que deja fuera el directorio
# de trabajo y site-packages. Sin tocarlo, `import django` falla aunque Django
# este instalado al lado: es la causa numero uno de que esto "no funcione".
$Pth = Get-ChildItem -Path $Destino -Filter "python*._pth" | Select-Object -First 1
if ($Pth) {
    Write-Host "      habilitando site-packages en $($Pth.Name)"
    $contenido = Get-Content $Pth.FullName
    $contenido = $contenido -replace '^#\s*import site', 'import site'
    if ($contenido -notcontains "import site") { $contenido += "import site" }
    if ($contenido -notcontains "..")          { $contenido += ".." }
    Set-Content -Path $Pth.FullName -Value $contenido
}

# 2) pip -------------------------------------------------------------------
Write-Host "[2/4] Instalando pip..."
$GetPip = Join-Path $Temp "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
& "$Destino\python.exe" $GetPip --no-warn-script-location

# 3) Dependencias ----------------------------------------------------------
Write-Host "[3/4] Instalando las dependencias de SIBU..."
& "$Destino\python.exe" -m pip install --no-warn-script-location `
    -r (Join-Path $Raiz "requirements\portable.txt")

# 4) Primera preparacion ---------------------------------------------------
Write-Host "[4/4] Preparando la base y los estaticos..."
Push-Location $Raiz
& "$Destino\python.exe" -c @"
import os, sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.portable')
import django; django.setup()
from django.core.management import call_command
call_command('migrate', interactive=False, verbosity=1)
call_command('preparar', '--si-cambio', '--sin-demo', verbosity=1)
call_command('collectstatic', interactive=False, verbosity=0)
"@
Pop-Location

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host ""
Write-Host "  1. Cree la primera cuenta:"
Write-Host "       python\python.exe portable\crear_cuenta.py"
Write-Host "  2. Arranque el sistema con portable\SIBU.bat"
Write-Host "  3. Para el icono: cree un acceso directo a SIBU.bat en el"
Write-Host "     escritorio y en Propiedades > Cambiar icono elija"
Write-Host "     portable\sibu.ico"
Write-Host ""
Write-Host "  La carpeta completa ya es portable: copiela a otro Windows"
Write-Host "  o a una memoria y funcionara igual." -ForegroundColor Green
Write-Host ""
