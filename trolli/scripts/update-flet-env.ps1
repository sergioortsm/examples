param(
    [switch]$SyncDependencyFiles,
    [switch]$InstallFromRequirements,
    [string]$ProjectRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "No se encontro Python del entorno virtual en: $venvPython"
}

$requirementsPath = Join-Path $ProjectRoot "requirements.txt"
$pyprojectPath = Join-Path $ProjectRoot "pyproject.toml"

function Run-Python {
    param([string[]]$PyArgs)
    & $venvPython @PyArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo comando: python $($PyArgs -join ' ')"
    }
}

function Get-PackageVersion {
    param([string]$PackageName)

    $output = & $venvPython -m pip show $PackageName 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $output) {
        throw "No se pudo obtener version de '$PackageName'."
    }

    foreach ($line in $output) {
        if ($line -like "Version: *") {
            return $line.Substring(9).Trim()
        }
    }

    throw "No se encontro linea Version para '$PackageName'."
}

Write-Host "[1/5] Actualizando herramientas base de pip..." -ForegroundColor Cyan
Run-Python -PyArgs @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

if ($InstallFromRequirements) {
    if (-not (Test-Path $requirementsPath)) {
        throw "No existe requirements.txt en: $requirementsPath"
    }
    Write-Host "[2/5] Instalando desde requirements.txt..." -ForegroundColor Cyan
    Run-Python -PyArgs @("-m", "pip", "install", "-r", $requirementsPath)
}
else {
    Write-Host "[2/5] Actualizando stack Flet y python-dotenv..." -ForegroundColor Cyan
    Run-Python -PyArgs @("-m", "pip", "install", "--upgrade", "flet", "flet-cli", "flet-web", "flet-desktop", "python-dotenv")
}

Write-Host "[3/5] Validando dependencias (pip check)..." -ForegroundColor Cyan
Run-Python -PyArgs @("-m", "pip", "check")

$fletVersion = Get-PackageVersion -PackageName "flet"
$fletCliVersion = Get-PackageVersion -PackageName "flet-cli"
$fletWebVersion = Get-PackageVersion -PackageName "flet-web"
$fletDesktopVersion = Get-PackageVersion -PackageName "flet-desktop"
$dotenvVersion = Get-PackageVersion -PackageName "python-dotenv"

if (($fletVersion -ne $fletCliVersion) -or ($fletVersion -ne $fletWebVersion) -or ($fletVersion -ne $fletDesktopVersion)) {
    throw "Versiones de stack Flet desalineadas: flet=$fletVersion, cli=$fletCliVersion, web=$fletWebVersion, desktop=$fletDesktopVersion"
}

if ($SyncDependencyFiles) {
    Write-Host "[4/5] Sincronizando requirements.txt y pyproject.toml..." -ForegroundColor Cyan

    $requirementsContent = @(
        "flet==$fletVersion"
        "python-dotenv==$dotenvVersion"
    )
    Set-Content -Path $requirementsPath -Value $requirementsContent -Encoding UTF8

    if (Test-Path $pyprojectPath) {
        $pyproject = Get-Content -Path $pyprojectPath -Raw

        $newDependenciesBlock = @"
dependencies = [
  "flet==$fletVersion",
  "python-dotenv==$dotenvVersion"
]
"@

        $updatedPyproject = [regex]::Replace(
            $pyproject,
            "dependencies\s*=\s*\[(.|\r|\n)*?\]",
            $newDependenciesBlock,
            [System.Text.RegularExpressions.RegexOptions]::Singleline
        )

        Set-Content -Path $pyprojectPath -Value $updatedPyproject -Encoding UTF8
    }
}

Write-Host "[5/5] Resumen final" -ForegroundColor Cyan
Write-Host "flet=$fletVersion" -ForegroundColor Green
Write-Host "flet-cli=$fletCliVersion" -ForegroundColor Green
Write-Host "flet-web=$fletWebVersion" -ForegroundColor Green
Write-Host "flet-desktop=$fletDesktopVersion" -ForegroundColor Green
Write-Host "python-dotenv=$dotenvVersion" -ForegroundColor Green
Write-Host "Listo. Entorno consistente y validado." -ForegroundColor Green
