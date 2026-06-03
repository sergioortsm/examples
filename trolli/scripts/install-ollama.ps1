# install-ollama.ps1
# Instala Ollama y descarga el modelo llama3 en Windows.
# Ejecutar como Administrador para añadir Ollama al PATH del sistema.
#
# Uso:
#   .\install-ollama.ps1
#   .\install-ollama.ps1 -Model mistral
#   .\install-ollama.ps1 -Model llama3 -SkipModelPull

param(
    [string]$Model = "llama3",
    [switch]$SkipModelPull
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$OllamaInstallDir = "$env:LOCALAPPDATA\Programs\Ollama"
$OllamaExe        = "$OllamaInstallDir\ollama.exe"
$InstallerUrl     = "https://ollama.com/download/OllamaSetup.exe"
$InstallerPath    = "$env:TEMP\OllamaSetup.exe"

function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Add-ToPath([string]$dir) {
    $currentPath = [Environment]::GetEnvironmentVariable("PATH", "Machine")
    if ($currentPath -notlike "*$dir*") {
        [Environment]::SetEnvironmentVariable("PATH", "$currentPath;$dir", "Machine")
        Write-Host "    Añadido al PATH del sistema: $dir" -ForegroundColor Green
    } else {
        Write-Host "    Ya estaba en el PATH del sistema." -ForegroundColor Yellow
    }
    # También para la sesión actual
    $env:PATH = "$env:PATH;$dir"
}

# ?? 1. Comprobar si ya está instalado ??????????????????????????????????????
Write-Step "Comprobando instalación de Ollama"
if (Test-Path $OllamaExe) {
    $version = & $OllamaExe --version 2>&1
    Write-Host "    Ollama ya instalado: $version" -ForegroundColor Green
} else {
    # ?? 2. Descargar instalador ????????????????????????????????????????????
    Write-Step "Descargando instalador de Ollama desde $InstallerUrl"
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerPath -UseBasicParsing
    Write-Host "    Descargado en $InstallerPath" -ForegroundColor Green

    # ?? 3. Instalar en silencio ????????????????????????????????????????????
    Write-Step "Instalando Ollama (modo silencioso)"
    Start-Process -FilePath $InstallerPath -ArgumentList "/SILENT" -Wait
    Write-Host "    Instalación completada." -ForegroundColor Green

    if (-not (Test-Path $OllamaExe)) {
        Write-Error "No se encontró ollama.exe tras la instalación en $OllamaInstallDir"
        exit 1
    }
}

# ?? 4. Añadir al PATH del sistema ??????????????????????????????????????????
Write-Step "Configurando PATH"
Add-ToPath $OllamaInstallDir

# ?? 5. Verificar que responde ??????????????????????????????????????????????
Write-Step "Verificando servidor Ollama (http://localhost:11434)"
$retries = 6
$ready   = $false
# Arrancar el servidor en segundo plano si no está corriendo
$serverJob = Start-Job -ScriptBlock {
    param($exe)
    & $exe serve 2>&1
} -ArgumentList $OllamaExe

for ($i = 1; $i -le $retries; $i++) {
    Start-Sleep -Seconds 3
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
        $ready = $true
        Write-Host "    Servidor listo." -ForegroundColor Green
        break
    } catch {
        Write-Host "    Esperando servidor... ($i/$retries)"
    }
}

if (-not $ready) {
    Write-Warning "El servidor Ollama no respondió a tiempo. Prueba a ejecutar 'ollama serve' manualmente."
}

# ?? 6. Descargar modelo ????????????????????????????????????????????????????
if (-not $SkipModelPull) {
    Write-Step "Descargando modelo '$Model' (puede tardar varios minutos)"
    & $OllamaExe pull $Model
    Write-Host "    Modelo '$Model' listo." -ForegroundColor Green
} else {
    Write-Host "`n    Omitiendo descarga de modelo (-SkipModelPull)." -ForegroundColor Yellow
}

# ?? 7. Resumen ?????????????????????????????????????????????????????????????
Write-Step "Modelos disponibles"
& $OllamaExe list

Write-Host "`n? Ollama instalado y listo. La app Trolli detectará el servidor en http://localhost:11434`n" -ForegroundColor Green
