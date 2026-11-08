param(
    [ValidateSet('Ai','Ledger','All')][string]$Mode = 'Ai',
    [switch]$SkipLocalInference,
    [switch]$AllowLowMemory,
    [switch]$Logs = $true,
    [switch]$NoLogs
)
# Keep the previous entry point while using one Docker service-mode launcher.
$PSBoundParameters.Remove('NoLogs') | Out-Null
$PSBoundParameters['Logs'] = $Logs -and -not $NoLogs
& (Join-Path $PSScriptRoot 'start-services.ps1') @PSBoundParameters
