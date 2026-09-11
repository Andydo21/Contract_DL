# ==============================================================================
# DENSO FACTORY INTELLIGENCE - ROOT STARTER (POWERSHELL)
# ==============================================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DemoDir = Join-Path $ScriptDir "denso_demo"
Set-Location $DemoDir
& "$DemoDir\start_project.ps1"
