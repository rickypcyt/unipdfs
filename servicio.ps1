param([ValidateSet('start','stop','status','toggle')][string]$accion = 'toggle')

$dir  = $PSScriptRoot
$port = 8000
$log  = Join-Path $dir 'servidor.log'

function Get-Listener {
    # El socket que escucha no siempre sale con State=Listen en Windows 11: se filtra por conexion sin remoto y PID real
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        Where-Object { $_.RemotePort -eq 0 -and $_.OwningProcess -ne 0 } | Select-Object -First 1
}

function Start-Servidor {
    if (Get-Listener) { Write-Host "Ya esta corriendo en http://localhost:$port"; return }
    $py = if (Get-Command py -ErrorAction SilentlyContinue) { 'py' } else { 'python' }
    $args = if ($py -eq 'py') { @('-3','-u','servidor.py') } else { @('-u','servidor.py') }
    Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $dir -WindowStyle Hidden `
        -RedirectStandardOutput $log -RedirectStandardError "$log.err"
    for ($i = 0; $i -lt 20 -and -not (Get-Listener); $i++) { Start-Sleep -Milliseconds 500 }
    if (Get-Listener) { Write-Host "Corriendo en segundo plano: http://localhost:$port" }
    else { Write-Host "No arranco. Revisa $log y $log.err" }
}

function Stop-Servidor {
    $l = Get-Listener
    if (-not $l) { Write-Host 'No estaba corriendo.'; return }
    Stop-Process -Id $l.OwningProcess -Force
    Write-Host 'Detenido.'
}

switch ($accion) {
    'start'  { Start-Servidor }
    'stop'   { Stop-Servidor }
    'status' { if (Get-Listener) { Write-Host "CORRIENDO en http://localhost:$port" } else { Write-Host 'DETENIDO' } }
    'toggle' { if (Get-Listener) { Stop-Servidor } else { Start-Servidor; Start-Process "http://localhost:$port" } }
}
