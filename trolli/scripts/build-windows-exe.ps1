# scripts/build-windows-exe.ps1
# Genera el ejecutable Windows de Trolli.
# Modos:
#   flet build windows  (requiere Flutter SDK)
#   PyInstaller         (no requiere Flutter, util para pruebas rapidas)
#
# Uso:
#   .\scripts\build-windows-exe.ps1                                     # flet build windows
#   .\scripts\build-windows-exe.ps1 -UsePyInstaller                      # PyInstaller, carpeta (onedir)
#   .\scripts\build-windows-exe.ps1 -UsePyInstaller -OneFile             # PyInstaller, un solo .exe
#   .\scripts\build-windows-exe.ps1 -SkipFlutterCheck                   # omite check de Flutter
#   .\scripts\build-windows-exe.ps1 -OpenOutputDir                      # abre carpeta al finalizar
#
# Opciones para entornos corporativos con SSL/proxy (ej. servidor SharePoint):
#   .\scripts\build-windows-exe.ps1 -UsePyInstaller -CACertBundle C:\ruta\ca-bundle.pem
#                                                    # incluye CA corporativa en el launcher
#   .\scripts\build-windows-exe.ps1 -UsePyInstaller -AllowUntrustedSSL
#                                                    # deshabilita verificacion SSL (solo primer arranque)
#
# Nota: -CACertBundle/-AllowUntrustedSSL solo afectan a la descarga del cliente Flet
# en el primer arranque en el servidor. Despues queda cacheado y no se vuelve a descargar.

param(
    [switch]$UsePyInstaller,
    [switch]$OneFile,              # solo con -UsePyInstaller: genera un unico .exe (mas lento al arrancar)
    [switch]$SkipFlutterCheck,
    [switch]$OpenOutputDir,
    [string]$CACertBundle  = "",  # ruta a un .pem con la CA corporativa para entornos con proxy SSL
    [switch]$AllowUntrustedSSL,    # deshabilita verificacion SSL (alternativa si no tienes el .pem)
    [string]$ProjectRoot   = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No se encontro Python del entorno virtual en: $venvPython. Ejecuta primero: python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt"
}

# ---------------------------------------------------------------------------
# 1. Validar Flutter SDK (solo en modo flet build)
# ---------------------------------------------------------------------------
if ($UsePyInstaller) {
    Write-Host "[1/4] Modo PyInstaller: se omite verificacion de Flutter." -ForegroundColor Yellow
    $outputDir = Join-Path $ProjectRoot "build\pyinstaller"
} else {
    $outputDir = Join-Path $ProjectRoot "build\windows"
    if (-not $SkipFlutterCheck) {
        Write-Host "[1/4] Verificando Flutter SDK..." -ForegroundColor Cyan
        $flutter = Get-Command flutter -ErrorAction SilentlyContinue
        if (-not $flutter) {
            throw "Flutter no encontrado en PATH. Instala Flutter SDK antes de continuar:`nhttps://docs.flet.dev/publish/windows/`n`nPara compilar sin Flutter usa: .\build-windows-exe.ps1 -UsePyInstaller"
        }
        Write-Host "      Flutter: $($flutter.Source)" -ForegroundColor Gray
    } else {
        Write-Host "[1/4] Verificacion de Flutter omitida (-SkipFlutterCheck)." -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# 2. Validar dependencias del modo seleccionado
# ---------------------------------------------------------------------------
$fletVersion = & $venvPython -m pip show flet 2>$null | Where-Object { $_ -like "Version: *" } | ForEach-Object { $_.Substring(9).Trim() }

if ($UsePyInstaller) {
    Write-Host "[2/4] Verificando PyInstaller en el entorno virtual..." -ForegroundColor Cyan
    $pyiCheck = & $venvPython -m pip show pyinstaller 2>$null
    if (-not $pyiCheck) {
        Write-Host "      PyInstaller no encontrado. Instalando..." -ForegroundColor Yellow
        & $venvPython -m pip install pyinstaller
        if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de PyInstaller." }
    }
    $pyiVersion = & $venvPython -m pip show pyinstaller 2>$null | Where-Object { $_ -like "Version: *" } | ForEach-Object { $_.Substring(9).Trim() }
    Write-Host "      flet version      : $fletVersion" -ForegroundColor Gray
    Write-Host "      pyinstaller version: $pyiVersion" -ForegroundColor Gray
} else {
    Write-Host "[2/4] Verificando flet-cli en el entorno virtual..." -ForegroundColor Cyan
    $venvFlet = Join-Path $ProjectRoot ".venv\Scripts\flet.exe"
    if (-not (Test-Path $venvFlet)) {
        throw "flet.exe no encontrado en .venv\Scripts. Ejecuta: pip install flet-cli"
    }
    Write-Host "      flet version: $fletVersion" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# 3. Build
# ---------------------------------------------------------------------------
if ($UsePyInstaller) {
    Write-Host "[3/4] Ejecutando PyInstaller..." -ForegroundColor Cyan
    $mainScript  = Join-Path $ProjectRoot "src\main.py"
    $srcDir      = Join-Path $ProjectRoot "src"
    $rthookPath  = Join-Path $PSScriptRoot "rthook_flet_view.py"

    # --- Verificar que el cliente Flet esta cacheado en esta maquina -----------
    # El hook hook-flet.py de flet_cli lo incluye en el bundle solo si existe en
    # ~/.flet/client/flet-desktop-full-{version}/. Si no esta, flet_desktop lo
    # descargara de GitHub durante el build; en entornos sin internet el bundle
    # quedara sin el cliente y el exe necesitara conexion en el primer arranque.
    $fletClientDir = Join-Path $env:USERPROFILE ".flet\client\flet-desktop-full-$fletVersion"
    if (Test-Path (Join-Path $fletClientDir "flet\flet.exe")) {
        Write-Host "      Cliente Flet bundleado desde: $fletClientDir" -ForegroundColor Gray
    } else {
        Write-Host "" 
        Write-Host "      AVISO: No se encontro el cliente Flet en:" -ForegroundColor Yellow
        Write-Host "             $fletClientDir" -ForegroundColor Yellow
        Write-Host "             flet_desktop lo descargara de GitHub durante el build." -ForegroundColor Yellow
        Write-Host "             En entornos sin internet el exe resultante necesitara" -ForegroundColor Yellow
        Write-Host "             conexion en el primer arranque del servidor." -ForegroundColor Yellow
        Write-Host "      Para pre-cachear ejecuta una vez: python -c ""import flet; import flet_desktop; flet_desktop.ensure_client_cached()""" -ForegroundColor Yellow
        Write-Host ""
    }
    # ---------------------------------------------------------------------------

    Push-Location $ProjectRoot
    try {
        $pyiMode = if ($OneFile) { "--onefile" } else { "--onedir" }
        & $venvPython -m PyInstaller `
            $pyiMode `
            --windowed `
            --name trolli `
            --distpath $outputDir `
            --paths $srcDir `
            --runtime-hook $rthookPath `
            $mainScript
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo con codigo $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[3/4] Ejecutando 'flet build windows' (esto puede tardar varios minutos)..." -ForegroundColor Cyan
    Push-Location $ProjectRoot
    try {
        & $venvFlet build windows
        if ($LASTEXITCODE -ne 0) { throw "'flet build windows' fallo con codigo $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# 4. Resultado
# ---------------------------------------------------------------------------
if (Test-Path $outputDir) {
    $exe = Get-ChildItem -Path $outputDir -Filter "*.exe" -Recurse | Select-Object -First 1
    Write-Host ""
    $modeLabel = if ($UsePyInstaller) { "PyInstaller" } else { "flet build windows" }
    Write-Host "[4/4] Build completado ($modeLabel)." -ForegroundColor Green
    Write-Host "      Directorio : $outputDir" -ForegroundColor Green
    if ($exe) {
        Write-Host "      Ejecutable  : $($exe.FullName)" -ForegroundColor Green
    }

    # --- Launcher .bat para entornos corporativos con SSL/proxy ---
    if ($CACertBundle -or $AllowUntrustedSSL) {
        $exeDir  = if ($UsePyInstaller -and -not $OneFile) { Join-Path $outputDir "trolli" } else { $outputDir }
        $batPath = Join-Path $exeDir "trolli-launcher.bat"

        if ($CACertBundle) {
            if (-not (Test-Path $CACertBundle)) { throw "CACertBundle no encontrado: $CACertBundle" }
            $destCert = Join-Path $exeDir "ca-bundle.pem"
            Copy-Item -Path $CACertBundle -Destination $destCert -Force
            Write-Host "      CA bundle   : $destCert" -ForegroundColor Gray
            $sslLine = "set SSL_CERT_FILE=%~dp0ca-bundle.pem"
        } else {
            $sslLine = "set TROLLI_SKIP_SSL_VERIFY=1"
        }

        $batContent = "@echo off`r`nrem Launcher de Trolli para entornos con proxy/CA corporativa.`r`nrem Solo es necesario en el primer arranque; despues el cliente Flet queda cacheado.`r`n$sslLine`r`nstart `"`" `"%~dp0trolli.exe`"`r`n"
        [System.IO.File]::WriteAllText($batPath, $batContent, [System.Text.Encoding]::ASCII)
        Write-Host "      Launcher    : $batPath" -ForegroundColor Green
        Write-Host ""
        Write-Host "ENTORNO CORPORATIVO: usa 'trolli-launcher.bat' en lugar de 'trolli.exe'" -ForegroundColor Magenta
        Write-Host "Solo es necesario en el primer arranque; despues el cliente Flet queda cacheado." -ForegroundColor Magenta
    }

    Write-Host ""
    Write-Host "Para usarlo en el servidor SharePoint:" -ForegroundColor Yellow
    if ($UsePyInstaller -and $OneFile) {
        Write-Host "  1. Copia SOLO el archivo '$($exe.Name)' al servidor." -ForegroundColor Yellow
    } else {
        Write-Host "  1. Copia la CARPETA COMPLETA '$outputDir' al servidor (no solo el .exe)." -ForegroundColor Yellow
    }
    if ($CACertBundle -or $AllowUntrustedSSL) {
        Write-Host "  2. Ejecuta 'trolli-launcher.bat' (no trolli.exe directamente)." -ForegroundColor Yellow
    } else {
        Write-Host "  2. Ejecuta el .exe." -ForegroundColor Yellow
    }
    Write-Host "  3. Apunta 'watch_folder' a la carpeta de logs ULS, por ejemplo:" -ForegroundColor Yellow
    Write-Host "     C:\Program Files\Common Files\Microsoft Shared\Web Server Extensions\16\LOGS" -ForegroundColor Yellow

    if ($OpenOutputDir) {
        explorer.exe $outputDir
    }
} else {
    throw "No se encontro el directorio de salida: $outputDir"
}