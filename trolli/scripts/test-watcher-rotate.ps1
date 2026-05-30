<#
.SYNOPSIS
    Test bonus - Simula rotación creando un nuevo .log más reciente.

.DESCRIPTION
    Copia el .log actual a un nombre nuevo con timestamp posterior, de modo
    que el watcher (poll cada 500 ms, ranking por mtime) haga handoff al
    nuevo fichero y lo abra desde offset=0.

    Esperado:
      - file_label cambia al nuevo fichero.
      - En src/trolli.log: "Abre <nuevo>.log (offset inicial=0)".
      - Sin perder líneas previas del buffer LIFO.

.EXAMPLE
    .\test-watcher-rotate.ps1
    .\test-watcher-rotate.ps1 -BaseName 'SAPCOL03'
#>

[CmdletBinding()]
param(
    [string] $Folder = 'C:\Temp\LOGS',
    [string] $Pattern = '*.log',
    [string] $BaseName = 'SAPCOL03',
    [string] $SourceFile
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\test-watcher-common.ps1"

if (-not $SourceFile) {
    $SourceFile = Resolve-WatcherLogFile -Folder $Folder -Pattern $Pattern
}

$stamp = (Get-Date).ToString('yyyyMMdd-HHmm')
$target = Join-Path $Folder "$BaseName-$stamp.log"

if (Test-Path -LiteralPath $target) {
    Write-Host "[rotate] El fichero destino ya existe; se sobreescribe: $target" -ForegroundColor Yellow
}

Copy-Item -LiteralPath $SourceFile -Destination $target -Force
# Forzar mtime "ahora" para que el watcher lo elija como más reciente.
(Get-Item -LiteralPath $target).LastWriteTime = Get-Date

Write-Host "[rotate] Copiado:" -ForegroundColor Cyan
Write-Host "         desde: $SourceFile" -ForegroundColor Cyan
Write-Host "         hacia: $target"     -ForegroundColor Cyan
Write-Host "[rotate] Esperando ~1s para que el watcher (poll 500ms) lo detecte..." -ForegroundColor DarkGray
Start-Sleep -Milliseconds 1200
Write-Host "[rotate] Listo. Verifica file_label en la UI y src/trolli.log." -ForegroundColor Green
