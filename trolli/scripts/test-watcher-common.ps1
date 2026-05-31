<#
.SYNOPSIS
    Helpers compartidos por los scripts de test del watcher en vivo.

.DESCRIPTION
    - Resuelve el fichero .log "en vivo" (más reciente por LastWriteTime) en una carpeta y patrón.
    - Abre un FileStream en modo Append con FileShare.ReadWrite|Delete para
      emular cómo SharePoint OnPrem escribe sobre sus .log (compartiendo lectura).
    - Devuelve un objeto con .Writer (StreamWriter) y .Dispose() para cierre limpio.

    NO ejecutar como script suelto: usar Dot-source desde los otros tests.
#>

function Resolve-WatcherLogFile {
    [CmdletBinding()]
    param(
        [string] $Folder = 'C:\Temp\LOGS',
        [string] $Pattern = '*.log'
    )

    if (-not (Test-Path -LiteralPath $Folder)) {
        throw "La carpeta '$Folder' no existe."
    }

    $candidate = Get-ChildItem -LiteralPath $Folder -Filter $Pattern -File -ErrorAction Stop |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $candidate) {
        throw "No se encontró ningún fichero que coincida con '$Pattern' en '$Folder'."
    }

    return $candidate.FullName
}

function Open-WatcherAppender {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string] $Path
    )

    $share = [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete
    $fs = [System.IO.FileStream]::new(
        $Path,
        [System.IO.FileMode]::Append,
        [System.IO.FileAccess]::Write,
        $share
    )
    $sw = [System.IO.StreamWriter]::new($fs, [System.Text.UTF8Encoding]::new($false))

    return [pscustomobject]@{
        Path   = $Path
        Stream = $fs
        Writer = $sw
        Dispose = {
            param($self)
            if ($self.Writer) { $self.Writer.Dispose() }
            if ($self.Stream) { $self.Stream.Dispose() }
        }
    }
}

# --- Datos realistas extraídos del log real SAPCOL03-20260529-1249.log ---

$script:UlsProcesses = @(
    'w3wp.exe (0x12F0)',
    'w3wp.exe (0x1F44)',
    'OWSTIMER.EXE (0x0ECC)',
    'mssearch.exe (0x1A20)',
    'noderunner.exe (0x2B14)',
    'wsstracing.exe (0x0F88)'
)

$script:UlsTids = @(
    '0x0D14','0x21CC','0x2708','0x15A4','0x1F78','0x08DC','0x113C','0x15BC','0x15C0','0x1B30','0x2C18'
)

# Mezcla de (Area, Category, EventID, Level, plantilla mensaje).
# Niveles repartidos para que filtrar por Level dé resultados variados.
$script:UlsTemplates = @(
    @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='a4kcq'; Level='Unexpected';  Msg='SPDistributedCachePointerWrapper::InitializeDataCacheFactory - No cache hosts are present or running in the farm.' },
    @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='ah24w'; Level='Unexpected';  Msg="Unexpected Exception in SPDistributedCachePointerWrapper::InitializeDataCacheFactory for usage 'DistributedLogonTokenCache'." },
    @{ Area='SharePoint Foundation'; Category='DistributedCache';         EventId='9w6du'; Level='Monitorable'; Msg='Token Cache: Failed to initialize SPDistributedSecurityTokenCacheV2.' },
    @{ Area='SharePoint Foundation'; Category='Database';                 EventId='bggfq'; Level='Medium';      Msg='UsageLoggedSqlSession: Before executing command against SharePoint_Config. Command is proc_ScheduleTimerJob' },
    @{ Area='SharePoint Foundation'; Category='Database';                 EventId='a08yc'; Level='High';        Msg='Database with Id 036cc9bc-c57b-4f41-8084-43a1dd3ee951 was not found in database collection. Returning null.' },
    @{ Area='SharePoint Foundation'; Category='Database';                 EventId='az4y7'; Level='Medium';      Msg='Checking database SPConfigurationDatabase Name=SharePoint_Config for all site subscriptions in content database 984d2155-2a61-4b89-971f-13fd8705154e.' },
    @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='apm5x'; Level='Medium';      Msg='Successfully started timer job {36B3A71F-52EC-44B4-AA01-23F705EE45BF} in store for service {64CB95F2-8D12-407F-8C04-220A3AFD3599}.' },
    @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='aoovq'; Level='Medium';      Msg='Starting content database timer job [webhook-processing] on target 0 of 1.' },
    @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='an9i8'; Level='Medium';      Msg='Completed processing of timer job [webhook-processing] with lock type [None]. Status result: [Succeeded].' },
    @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='apm55'; Level='Medium';      Msg='Successfully completed with result 2 timer running job {7F68A2EA-E365-40B0-A34A-B1586822B9C9}.' },
    @{ Area='SharePoint Foundation'; Category='Timer';                    EventId='cb5oc'; Level='Medium';      Msg='[NoLockTypeDBPartitioning]: NoLockTypeDBPartitioningFlight is DISABLED! Reverting to old behavior.' },
    @{ Area='SharePoint Foundation'; Category='Monitoring';               EventId='nasq';  Level='Medium';      Msg='Entering Monitored Scope (Timer Job MySite-Instantiation-Interactive-Request-Queue). Parent=None' },
    @{ Area='SharePoint Foundation'; Category='Monitoring';               EventId='b4ly';  Level='Medium';      Msg='Leaving Monitored Scope: Tiempo de ejecución=7.0718; CPU Milliseconds=1; Recuento de consultas SQL=6; Parent=None' },
    @{ Area='SharePoint Foundation'; Category='Logging Correlation Data'; EventId='xmnv';  Level='Medium';      Msg='Name=Timer Job MySite-Instantiation-Interactive-Request-Queue' },
    @{ Area='SharePoint Foundation'; Category='Topology';                 EventId='a0ebr'; Level='Medium';      Msg="Initializing a site subscription collection for content DB 984d2155-2a61-4b89-971f-13fd8705154e. That's going to be a lot of work." },
    @{ Area='SharePoint Server';     Category='Site Provisioning';        EventId='aj58q'; Level='Medium';      Msg='<LogTimerJobInstance> Starting timer for web application: Colabora Validación 03. Function: SiteInstantiationJob:Execute' },
    @{ Area='SharePoint Server';     Category='Site Provisioning';        EventId='aj58r'; Level='Medium';      Msg='<LogTimerJobInstance> Finishing on timer for web application: Colabora Validación 03. Function: SiteInstantiationJob:Execute' },
    @{ Area='SharePoint Foundation'; Category='General';                  EventId='8e2s';  Level='Information'; Msg='Request handled OK.' },
    @{ Area='SharePoint Foundation'; Category='General';                  EventId='8sl1';  Level='Verbose';     Msg='Detailed trace event for diagnostics.' }
)

function _New-CorrelationGuid {
    return [Guid]::NewGuid().ToString().ToLowerInvariant()
}

function New-UlsLine {
    [CmdletBinding()]
    param(
        [string] $Message,
        [string] $Area,
        [string] $Category,
        [string] $Level,
        [string] $Process,
        [string] $Tid,
        [string] $EventId,
        [string] $Correlation,
        [int]    $Index = 0
    )

    $tpl = Get-Random -InputObject $script:UlsTemplates

    if (-not $Process)     { $Process     = Get-Random -InputObject $script:UlsProcesses }
    if (-not $Tid)         { $Tid         = Get-Random -InputObject $script:UlsTids }
    if (-not $Area)        { $Area        = $tpl.Area }
    if (-not $Category)    { $Category    = $tpl.Category }
    if (-not $EventId)     { $EventId     = $tpl.EventId }
    if (-not $Level)       { $Level       = $tpl.Level }
    if (-not $Correlation) { $Correlation = _New-CorrelationGuid }

    if (-not $Message) {
        $suffix = if ($Index -gt 0) { " [seq #$Index]" } else { '' }
        $Message = "$($tpl.Msg)$suffix"
    }

    $ts = (Get-Date).ToString('MM/dd/yyyy HH:mm:ss.ff')
    # Formato ULS tabulado:
    # Timestamp \t Process \t TID \t Area \t Category \t EventID \t Level \t Message \t Correlation
    return "$ts`t$Process`t$Tid`t$Area`t$Category`t$EventId`t$Level`t$Message`t$Correlation"
}
