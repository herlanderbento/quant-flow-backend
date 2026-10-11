# Keeps Windows from idle-sleeping while a paper soak runs (no power settings are changed).
# Closing the lid / manual sleep still sleeps. Ends by itself after -Hours, or stop the process.
#   powershell -ExecutionPolicy Bypass -File scripts\keep_awake.ps1 -Hours 25
param([double]$Hours = 25)

Add-Type -Namespace Native -Name Power -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
'@
$ES_CONTINUOUS = [uint32]"0x80000000"
$ES_SYSTEM_REQUIRED = [uint32]"0x00000001"

$until = (Get-Date).AddHours($Hours)
try {
    while ((Get-Date) -lt $until) {
        [Native.Power]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED) | Out-Null
        Start-Sleep -Seconds 60
    }
} finally {
    [Native.Power]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
}
