<#
.SYNOPSIS
    Test 3/4 helper - Trickle continuo de líneas para ejercitar auto-pausa,
    chip "N nuevas" y ciclos Stop/Start del watcher.

.DESCRIPTION
    Escribe 1 línea cada N segundos durante DurationSeconds (default 5 min).
    Pensado para correr en paralelo mientras se interactúa con la UI:

    Test 3 - Auto-pausa con filtros:
      1. Arrancar este script.
      2. Con watcher ON, escribir algo en "Buscar" o cambiar "Nivel".
      3. Verificar que pending_new_count sube y aparece chip "N nuevas - clic para ver".
      4. Las nuevas filas NO se inyectan en la tabla mientras hay filtro.
      5. Clic en el chip -> resetea filtros/página, vuelca buffer, chip desaparece.

    Test 4 - Stop/Start cycle (mientras el trickle sigue corriendo):
      1. Botón rojo Stop: watch_status_text vacío, is_watching=False.
      2. Cambiar carpeta o patrón.
      3. Botón verde Play: arranca limpio, abre fichero más reciente desde EOF.
         (Las líneas del trickle escritas mientras estuvo OFF NO deben aparecer:
         se arranca con start_from_end=True.)
      4. Cerrar app, reabrir -> watch_folder y watch_pattern recordados.

.EXAMPLE
    .\test-watcher-trickle.ps1
    .\test-watcher-trickle.ps1 -IntervalSeconds 2 -DurationSeconds 600
    .\test-watcher-trickle.ps1 -LogFile 'C:\Temp\LOGS\SAPCOL03-20260530-1200.log'
#>

[CmdletBinding()]
param(
    [string] $Folder = 'C:\Temp\LOGS',
    [string] $Pattern = '*.log',
    [string] $LogFile,
    [double] $IntervalSeconds = 1.0,
    [int]    $DurationSeconds = 300
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\test-watcher-common.ps1"

if (-not $LogFile) {
    $LogFile = Resolve-WatcherLogFile -Folder $Folder -Pattern $Pattern
}

$end = (Get-Date).AddSeconds($DurationSeconds)
Write-Host "[trickle] Append cada ${IntervalSeconds}s durante ${DurationSeconds}s en:" -ForegroundColor Cyan
Write-Host "          $LogFile" -ForegroundColor Cyan
Write-Host "          Ctrl+C para abortar." -ForegroundColor DarkGray

$appender = Open-WatcherAppender -Path $LogFile
$i = 0
try {
    while ((Get-Date) -lt $end) {
        $i++
        $line = New-UlsLine -Index $i
        $appender.Writer.WriteLine($line)
        $appender.Writer.Flush()
        Start-Sleep -Seconds $IntervalSeconds
    }
}
finally {
    & $appender.Dispose $appender
}

Write-Host "[trickle] Listo: $i líneas escritas." -ForegroundColor Green
