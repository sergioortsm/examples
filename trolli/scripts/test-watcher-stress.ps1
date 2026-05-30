<#
.SYNOPSIS
    Test 2 - Stress: vuelca N líneas de golpe (default 50.000).

.DESCRIPTION
    Escribe todas las líneas seguidas (un único Flush al final) sobre el
    fichero .log más reciente. Sirve para validar:
      - buffer_count sube cerca del cap (100.000) sin romper.
      - lines/s pico alto y baja.
      - UI sigue respondiendo (scroll, clic).
      - Sin [WATCHER] Error en consola de la app.

.EXAMPLE
    .\test-watcher-stress.ps1
    .\test-watcher-stress.ps1 -Lines 100000
    .\test-watcher-stress.ps1 -LogFile 'C:\Temp\LOGS\SAPCOL03-20260530-1200.log' -Lines 10000
#>

[CmdletBinding()]
param(
    [string] $Folder = 'C:\Temp\LOGS',
    [string] $Pattern = '*.log',
    [string] $LogFile,
    [int]    $Lines = 50000
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\test-watcher-common.ps1"

if (-not $LogFile) {
    $LogFile = Resolve-WatcherLogFile -Folder $Folder -Pattern $Pattern
}

Write-Host "[stress] Volcando $Lines líneas en:" -ForegroundColor Cyan
Write-Host "         $LogFile" -ForegroundColor Cyan

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$appender = Open-WatcherAppender -Path $LogFile
try {
    for ($i = 1; $i -le $Lines; $i++) {
        $line = New-UlsLine -Index $i
        $appender.Writer.WriteLine($line)
    }
    $appender.Writer.Flush()
}
finally {
    & $appender.Dispose $appender
}
$sw.Stop()

$rate = if ($sw.Elapsed.TotalSeconds -gt 0) { [int]($Lines / $sw.Elapsed.TotalSeconds) } else { 0 }
Write-Host ("[stress] Listo: {0} líneas en {1:N2}s ({2} líneas/s en escritura)" -f `
    $Lines, $sw.Elapsed.TotalSeconds, $rate) -ForegroundColor Green
