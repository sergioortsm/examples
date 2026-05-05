@echo off
setlocal EnableExtensions

set "FECHA_INICIO=%~1"
set "FECHA_FIN=%~2"

if "%FECHA_INICIO%"=="" (
  echo Uso: imputar_rango_fechas.bat YYYY-MM-DD YYYY-MM-DD
  exit /b 1
)

if "%FECHA_FIN%"=="" (
  echo Uso: imputar_rango_fechas.bat YYYY-MM-DD YYYY-MM-DD
  exit /b 1
)

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$ini=[datetime]::ParseExact('%FECHA_INICIO%','yyyy-MM-dd',$null);" ^
  "$fin=[datetime]::ParseExact('%FECHA_FIN%','yyyy-MM-dd',$null);" ^
  "if($ini -gt $fin){ throw 'FECHA_INICIO mayor que FECHA_FIN' };" ^
  "$oks=0; $fallos=0;" ^
  "for($d=$ini; $d -le $fin; $d=$d.AddDays(1)){" ^
  "  if($d.DayOfWeek -eq 'Saturday' -or $d.DayOfWeek -eq 'Sunday'){ continue };" ^
  "  $env:SOLO_FECHA=$d.ToString('yyyy-MM-dd');" ^
  "  Write-Host '';" ^
  "  Write-Host ('=== Procesando ' + $env:SOLO_FECHA + ' ===');" ^
  "  & python -m src.servicio;" ^
  "  if($LASTEXITCODE -ne 0){ Write-Host ('[ERROR] ' + $env:SOLO_FECHA); $fallos++ } else { Write-Host ('[OK] ' + $env:SOLO_FECHA); $oks++ }" ^
  "};" ^
  "Write-Host '';" ^
  "Write-Host ('Resumen: OK=' + $oks + ' FALLIDOS=' + $fallos);" ^
  "exit $fallos"

exit /b %ERRORLEVEL%