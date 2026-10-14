param(
    [ValidateSet('Start', 'Status', 'Stop')]
    [string]$Action = 'Status'
)

$taskRoot = $PSScriptRoot
$taskState = Join-Path $taskRoot '.cache/collector'
$taskLock = Join-Path $taskState 'run.lock'
$taskStop = Join-Path $taskState 'stop.request'
$taskStatus = Join-Path $taskRoot 'reviewed/COLLECTION_STATUS.json'
$taskOutput = Join-Path $taskState 'background.stdout.log'
$taskError = Join-Path $taskState 'background.stderr.log'

New-Item -ItemType Directory -Path $taskState -Force | Out-Null
$taskProcess = $null
if (Test-Path -LiteralPath $taskLock) {
    $taskPid = [int](Get-Content -LiteralPath $taskLock -Raw)
    $taskProcess = Get-Process -Id $taskPid -ErrorAction SilentlyContinue
}

if ($Action -eq 'Stop') {
    Set-Content -LiteralPath $taskStop -Value 'Graceful stop requested' -Encoding utf8
    Write-Output 'Stop requested. The collector will publish its current batch and exit at the next request boundary.'
    return
}

if ($Action -eq 'Start') {
    if ($taskProcess) {
        Write-Output "Collector already running with PID $($taskProcess.Id)."
        return
    }
    if (Test-Path -LiteralPath $taskLock) {
        Remove-Item -LiteralPath $taskLock
    }
    if (Test-Path -LiteralPath $taskStop) {
        Remove-Item -LiteralPath $taskStop
    }
    if (-not (Test-Path -LiteralPath (Join-Path $taskState 'inventory.json'))) {
        throw 'Run python -B crowdsourced/collect_archive.py inventory first.'
    }
    $taskPython = (& python -B -c 'import sys; print(sys.executable)').Trim()
    $taskScript = Join-Path $taskRoot 'collect_archive.py'
    $taskArguments = @('-u', '-B', ('"' + $taskScript + '"'), 'run', '--limit', '100', '--topic', 'archive-bulk')
    $taskQueue = Join-Path $taskState 'active_queue.json'
    if (Test-Path -LiteralPath $taskQueue) {
        $taskArguments += @('--queue', ('"' + $taskQueue + '"'))
    }
    $taskStarted = Start-Process -FilePath $taskPython -ArgumentList $taskArguments `
        -WorkingDirectory (Split-Path -Parent $taskRoot) -WindowStyle Hidden `
        -RedirectStandardOutput $taskOutput -RedirectStandardError $taskError -PassThru
    Write-Output "Background collector started with PID $($taskStarted.Id)."
    return
}

if ($taskProcess) {
    Write-Output "Collector running with PID $($taskProcess.Id)."
} else {
    Write-Output 'Collector is not running.'
}
if (Test-Path -LiteralPath $taskStatus) {
    Get-Content -LiteralPath $taskStatus
}
$taskCurrentQueue = Join-Path $taskState 'active_queue.json'
if (Test-Path -LiteralPath $taskCurrentQueue) {
    $taskQueueContents = Get-Content -LiteralPath $taskCurrentQueue -Raw | ConvertFrom-Json
    Write-Output "Active queue at batch start: $(@($taskQueueContents).Count) pages (current batch progress is shown below)."
}
if (Test-Path -LiteralPath $taskOutput) {
    Get-Content -LiteralPath $taskOutput -Tail 5
}
if (Test-Path -LiteralPath $taskError) {
    Get-Content -LiteralPath $taskError -Tail 5
}
