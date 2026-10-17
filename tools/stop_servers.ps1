# Stop every emulator server (python login_stub.py) and its obstacle-worker child processes.
#   powershell -File tools/stop_servers.ps1
# Matches python.exe processes only, so the shell running this script is never caught by its own
# command line.
$name = 'login_stub' + '.py'
$servers = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*$name*" }
foreach ($s in $servers) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $($s.ProcessId)" |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $s.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output "stopped $($s.ProcessId): $($s.CommandLine)"
}
