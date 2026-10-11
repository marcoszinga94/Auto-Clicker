# Compila AutoClicker.exe para Windows.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts/build-exe.ps1
param(
    [string]$Name = "AutoClicker"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Instalando dependencias..."
python -m pip install --upgrade pip
python -m pip install pyinstaller keyboard

Write-Host "Compilando $Name.exe..."
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
pyinstaller --onefile --windowed --name $Name windows/autoclicker.py

$exe = Join-Path (Get-Location) "dist\$Name.exe"
if (Test-Path $exe) {
    Write-Host "Listo: $exe"
} else {
    Write-Host "ERROR: no se genero el .exe" -ForegroundColor Red
    exit 1
}