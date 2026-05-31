<#
.SYNOPSIS
    Test Super Stress - Simula un servidor SharePoint OnPrem escribiendo ULS a saco
    en ráfagas grandes y sostenidas, durante varios minutos.

.DESCRIPTION
    Combina tres patrones de carga simultáneos para emular un farm SharePoint
    bajo presión:

      1. RÁFAGAS: bloques grandes de líneas escritas de golpe (Flush al final).
         Tamaño por defecto: 2.000 a 8.000 líneas por ráfaga, aleatorio.
      2. GAP entre ráfagas: pausa corta aleatoria (default 0.3 a 1.5s).
      3. JOBS PARALELOS: -ParallelJobs Background Jobs de PowerShell escribiendo
         a la vez sobre el MISMO fichero (FileShare.ReadWrite | Delete).
         Esto reproduce lo que hace SharePoint con OWSTIMER + varios w3wp.

    Por defecto:
      - Duración: 180 s.
      - Jobs paralelos: 3.
      - Ráfagas: 2.000 a 8.000 líneas (mezcla de Levels: Unexpected, High,
        Medium, Monitorable, Information, Verbose).
      - Gap: 0.3 a 1.5 s.

    Esperado en Trolli:
      - buffer_count se clava en 100.000 (cap LIFO) -> descarte sano.
      - total_ingested sube sin parar (ver UI / trolli.log si se expone).
      - lines/s pico alto sostenido durante varios segundos.
      - UI sigue respondiendo (scroll, clic, filtros).
      - Sin [WATCHER] Error ni [TAILER] Error en src/trolli.log.

.EXAMPLE
    .\test-watcher-superstress.ps1
    .\test-watcher-superstress.ps1 -DurationSeconds 300 -ParallelJobs 5
    .\test-watcher-superstress.ps1 -MinBurst 5000 -MaxBurst 15000 -ParallelJobs 4 -DurationSeconds 600
    .\test-watcher-superstress.ps1 -LogFile 'C:\Temp\LOGS\SAPCOL03-20260531-0243.log'
#>

[CmdletBinding()]
param(
    [string] $Folder = 'C:\Temp\LOGS',
    [string] $Pattern = '*.log',
    [string] $LogFile,
    [int]    $DurationSeconds = 180,
    [int]    $ParallelJobs = 3,
    [int]    $MinBurst = 2000,
    [int]    $MaxBurst = 8000,
    [double] $MinGapSeconds = 0.3,
    [double] $MaxGapSeconds = 1.5
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\test-watcher-common.ps1"

if (-not $LogFile) {
    $LogFile = Resolve-WatcherLogFile -Folder $Folder -Pattern $Pattern
}

if ($MaxBurst -lt $MinBurst) { throw "MaxBurst ($MaxBurst) < MinBurst ($MinBurst)." }
if ($MaxGapSeconds -lt $MinGapSeconds) { throw "MaxGapSeconds < MinGapSeconds." }
if ($ParallelJobs -lt 1) { throw "ParallelJobs debe ser >= 1." }

Write-Host ""
Write-Host "[superstress] Configuración:" -ForegroundColor Cyan
Write-Host "  Fichero       : $LogFile"
Write-Host "  Duración      : ${DurationSeconds}s"
Write-Host "  Jobs paralelos: $ParallelJobs"
Write-Host "  Ráfaga        : ${MinBurst}..${MaxBurst} líneas"
Write-Host "  Gap           : ${MinGapSeconds}..${MaxGapSeconds}s"
Write-Host "  Ctrl+C para abortar (intentará limpiar jobs)." -ForegroundColor DarkGray
Write-Host ""

# Scriptblock que correrá cada Background Job. Es autocontenido (sin dot-source
# de los helpers): replicamos aquí la apertura compartida + plantillas ULS.
$jobBlock = {
    param(
        [string] $Path,
        [int]    $DurationSeconds,
        [int]    $MinBurst,
        [int]    $MaxBurst,
        [double] $MinGapSeconds,
        [double] $MaxGapSeconds,
        [int]    $JobIndex
    )

    $UlsProcesses = @(
        'w3wp.exe (0x12F0)','w3wp.exe (0x1F44)','OWSTIMER.EXE (0x0ECC)',
        'mssearch.exe (0x1A20)','noderunner.exe (0x2B14)','wsstracing.exe (0x0F88)'
    )
    $UlsTids = @('0x0D14','0x21CC','0x2708','0x15A4','0x1F78','0x08DC','0x113C','0x15BC','0x15C0','0x1B30','0x2C18')

    $UlsTemplates = @(
        @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='a4kcq'; Level='Unexpected';  Msg='SPDistributedCachePointerWrapper::InitializeDataCacheFactory - No cache hosts are present or running in the farm.' },
        @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='ah24w'; Level='Unexpected';  Msg="Unexpected Exception in SPDistributedCachePointerWrapper::InitializeDataCacheFactory for usage 'DistributedLogonTokenCache'." },
        @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='9w6du'; Level='Monitorable'; Msg='Token Cache: Failed to initialize SPDistributedSecurityTokenCacheV2.' },
        @{ Area='SharePoint Foundation'; Category='Database';                 EventId='bggfq'; Level='Medium';      Msg='UsageLoggedSqlSession: Before executing command against SharePoint_Config. Command is proc_ScheduleTimerJob' },
        @{ Area='SharePoint Foundation'; Category='Database';                 EventId='a08yc'; Level='High';        Msg='Database with Id 036cc9bc-c57b-4f41-8084-43a1dd3ee951 was not found in database collection. Returning null.' },
        @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='apm5x'; Level='Medium';      Msg='Successfully started timer job {36B3A71F-52EC-44B4-AA01-23F705EE45BF} in store for service {64CB95F2-8D12-407F-8C04-220A3AFD3599}.' },
        @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='aoovq'; Level='Medium';      Msg='Starting content database timer job [webhook-processing] on target 0 of 1.' },
        @{ Area='SharePoint Foundation'; Category='Monitoring';               EventId='nasq';  Level='Medium';      Msg='Entering Monitored Scope (Timer Job MySite-Instantiation-Interactive-Request-Queue). Parent=None' },
        @{ Area='SharePoint Foundation'; Category='Monitoring';               EventId='b4ly';  Level='Medium';      Msg='Leaving Monitored Scope: Tiempo de ejecución=7.0718; CPU Milliseconds=1; Recuento de consultas SQL=6; Parent=None' },
        @{ Area='SharePoint Server';     Category='Site Provisioning';        EventId='aj58q'; Level='Medium';      Msg='<LogTimerJobInstance> Starting timer for web application: Colabora Validación 03. Function: SiteInstantiationJob:Execute' },
        @{ Area='SharePoint Foundation'; Category='General';                  EventId='8e2s';  Level='Information'; Msg='Request handled OK.' },
        @{ Area='SharePoint Foundation'; Category='General';                  EventId='8sl1';  Level='Verbose';     Msg='Detailed trace event for diagnostics.' }
    )

    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $mutexName = "Global\TrolliWatcherSuperstress-$([Math]::Abs($Path.ToLowerInvariant().GetHashCode()))"
    $mutex = [System.Threading.Mutex]::new($false, $mutexName)
    $fs = [System.IO.FileStream]::new(
        $Path,
        [System.IO.FileMode]::Append,
        [System.IO.FileAccess]::Write,
        $share
    )
    $sw = [System.IO.StreamWriter]::new($fs, [System.Text.UTF8Encoding]::new($false))

    $end = (Get-Date).AddSeconds($DurationSeconds)
    $bursts = 0
    $lines  = 0
    try {
        while ((Get-Date) -lt $end) {
            $burstSize = Get-Random -Minimum $MinBurst -Maximum ($MaxBurst + 1)
            $lockTaken = $false
            try {
                $lockTaken = $mutex.WaitOne([TimeSpan]::FromSeconds(30))
                if (-not $lockTaken) {
                    throw "Timeout adquiriendo mutex de escritura para $Path"
                }

                for ($i = 1; $i -le $burstSize; $i++) {
                    $tpl  = Get-Random -InputObject $UlsTemplates
                    $proc = Get-Random -InputObject $UlsProcesses
                    $tid  = Get-Random -InputObject $UlsTids
                    $corr = [Guid]::NewGuid().ToString().ToLowerInvariant()
                    $ts   = (Get-Date).ToString('MM/dd/yyyy HH:mm:ss.ff')
                    $msg  = "$($tpl.Msg) [job=$JobIndex burst=$bursts seq=$i]"
                    $line = "$ts`t$proc`t$tid`t$($tpl.Area)`t$($tpl.Category)`t$($tpl.EventId)`t$($tpl.Level)`t$msg`t$corr"
                    $sw.WriteLine($line)
                }
                $sw.Flush()
            }
            finally {
                if ($lockTaken) {
                    $null = $mutex.ReleaseMutex()
                }
            }
            $bursts++
            $lines += $burstSize

            $gap = Get-Random -Minimum $MinGapSeconds -Maximum $MaxGapSeconds
            Start-Sleep -Milliseconds ([int]($gap * 1000))
        }
    }
    finally {
        if ($mutex) { $mutex.Dispose() }
        if ($sw) { $sw.Dispose() }
        if ($fs) { $fs.Dispose() }
    }

    [pscustomobject]@{ JobIndex = $JobIndex; Bursts = $bursts; Lines = $lines }
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$jobs = @()
for ($j = 1; $j -le $ParallelJobs; $j++) {
    $jobs += Start-Job -Name "ss-$j" -ScriptBlock $jobBlock -ArgumentList `
        $LogFile, $DurationSeconds, $MinBurst, $MaxBurst, $MinGapSeconds, $MaxGapSeconds, $j
    Write-Host "[superstress] Job $j arrancado (id=$($jobs[-1].Id))." -ForegroundColor DarkCyan
}

Write-Host ""
Write-Host "[superstress] Esperando a que terminen los $ParallelJobs jobs..." -ForegroundColor Cyan
try {
    $null = $jobs | Wait-Job
    $results = $jobs | Receive-Job
}
finally {
    $jobs | Remove-Job -Force -ErrorAction SilentlyContinue | Out-Null
}
$sw.Stop()

$totalLines  = ($results | Measure-Object -Property Lines  -Sum).Sum
$totalBursts = ($results | Measure-Object -Property Bursts -Sum).Sum
$avgRate     = if ($sw.Elapsed.TotalSeconds -gt 0) { [int]($totalLines / $sw.Elapsed.TotalSeconds) } else { 0 }

Write-Host ""
Write-Host "[superstress] Resultados por job:" -ForegroundColor Green
$results | Sort-Object JobIndex | Format-Table -AutoSize | Out-String | Write-Host

Write-Host ("[superstress] TOTAL: {0} líneas en {1} ráfagas, {2:N1}s reales ({3} líneas/s medio)." -f `
    $totalLines, $totalBursts, $sw.Elapsed.TotalSeconds, $avgRate) -ForegroundColor Green
