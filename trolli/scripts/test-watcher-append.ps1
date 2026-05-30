<#
.SYNOPSIS
    Test 1 - Append en vivo emulando SharePoint OnPrem (FileShare.ReadWrite).

.DESCRIPTION
    Escribe N líneas, una por intervalo, sobre el fichero .log más reciente
    de la carpeta. Mantiene el handle abierto (no rota).

    Esperado en la UI de Trolli (watcher ON):
      - 1 fila nueva por intervalo aparece arriba (LIFO, page 1).
      - buffer_count sube 1 a 1.
      - lines/s ? 1/IntervalSeconds.
      - file_label NO cambia.

.EXAMPLE
    .\test-watcher-append.ps1
    .\test-watcher-append.ps1 -Lines 60 -IntervalSeconds 0.5
    .\test-watcher-append.ps1 -LogFile 'C:\Temp\LOGS\SAPCOL03-20260530-1200.log'
#>

[CmdletBinding()]
param(
    [string] $Folder = 'C:\Temp\LOGS',
    [string] $Pattern = '*.log',
    [string] $LogFile,
    [int]    $Lines = 30,
    [double] $IntervalSeconds = 1.0
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\test-watcher-common.ps1"

if (-not $LogFile) {
    $LogFile = Resolve-WatcherLogFile -Folder $Folder -Pattern $Pattern
}

Write-Host "[append] Escribiendo $Lines líneas (cada ${IntervalSeconds}s) en:" -ForegroundColor Cyan
Write-Host "         $LogFile" -ForegroundColor Cyan

$appender = Open-WatcherAppender -Path $LogFile
try {
    for ($i = 1; $i -le $Lines; $i++) {
        $line = New-UlsLine -Index $i
        $appender.Writer.WriteLine($line)
        $appender.Writer.Flush()
        Write-Host "  [$i/$Lines] $((Get-Date).ToString('HH:mm:ss.fff'))" -ForegroundColor DarkGray
        if ($i -lt $Lines) { Start-Sleep -Seconds $IntervalSeconds }
    }
}
finally {
    & $appender.Dispose $appender
}

Write-Host "[append] Listo." -ForegroundColor Green
