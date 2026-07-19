# RiskDL Services Launcher for Windows
$ErrorActionPreference = "Stop"

# Clear screen
Clear-Host

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "         RiskDL - Smart Contract & AI Management System          " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " This script starts the multi-service application locally on Windows." -ForegroundColor Gray
Write-Host " Each service will open in a separate, dedicated terminal window." -ForegroundColor Gray
Write-Host ""

# Check environment file
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env file not found in root directory!" -ForegroundColor Red
    Exit 1
}

# Check virtual environment
if (-not (Test-Path "venv\Scripts\activate")) {
    Write-Host "[ERROR] Python virtual environment (venv) not found!" -ForegroundColor Red
    Exit 1
}

Write-Host "Choose an option to run the project:" -ForegroundColor Yellow
Write-Host "  [1] Start ALL Services (Web, Blockchain, Workflow, AI Inference, AI Summary)" -ForegroundColor White
Write-Host "  [2] Start Core Services only (Web, Blockchain, Workflow)" -ForegroundColor White
Write-Host "  [3] Run End-to-End Blockchain Verification Tests (test_e2e_blockchain.py)" -ForegroundColor White
Write-Host "  [4] Exit" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter your choice (1-4)"

if ($choice -eq "4" -or -not $choice) {
    Write-Host "Exiting." -ForegroundColor Yellow
    Exit 0
}

# Define services
$runWeb = {
    Write-Host "Launching Main Web Application on http://localhost:8000..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - Main Web (Port 8000)'; Get-Content .env | Where-Object { `$_ -match '=' -and `$_ -notmatch '^#' } | ForEach-Object { `$name, `$value = `$_ -split '=', 2; [System.Environment]::SetEnvironmentVariable(`$name.Trim(), `$value.Trim()) }; .\venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000"
}

$runBlockchain = {
    Write-Host "Launching Blockchain Service on http://localhost:8002..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - Blockchain Service (Port 8002)'; Get-Content .env | Where-Object { `$_ -match '=' -and `$_ -notmatch '^#' } | ForEach-Object { `$name, `$value = `$_ -split '=', 2; [System.Environment]::SetEnvironmentVariable(`$name.Trim(), `$value.Trim()) }; `$env:DB_NAME='blockchain_db'; .\venv\Scripts\python.exe blockchain_service/manage.py runserver 0.0.0.0:8002"
}

$runWorkflow = {
    Write-Host "Launching Workflow Service on http://localhost:8003..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - Workflow Service (Port 8003)'; Get-Content .env | Where-Object { `$_ -match '=' -and `$_ -notmatch '^#' } | ForEach-Object { `$name, `$value = `$_ -split '=', 2; [System.Environment]::SetEnvironmentVariable(`$name.Trim(), `$value.Trim()) }; `$env:DB_NAME='workflow_db'; .\venv\Scripts\python.exe workflow_service/manage.py runserver 0.0.0.0:8003"
}

$runAiService = {
    Write-Host "Launching AI Inference Service on http://localhost:8001..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - AI Service (Port 8001)'; Get-Content .env | Where-Object { `$_ -match '=' -and `$_ -notmatch '^#' } | ForEach-Object { `$name, `$value = `$_ -split '=', 2; [System.Environment]::SetEnvironmentVariable(`$name.Trim(), `$value.Trim()) }; cd ai_service; ..\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8001"
}

$runAiSummary = {
    Write-Host "Launching AI Summary Proxy on http://localhost:8004..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - AI Summary Proxy (Port 8004)'; Get-Content .env | Where-Object { `$_ -match '=' -and `$_ -notmatch '^#' } | ForEach-Object { `$name, `$value = `$_ -split '=', 2; [System.Environment]::SetEnvironmentVariable(`$name.Trim(), `$value.Trim()) }; cd ai_summary; ..\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8004"
}

if ($choice -eq "1") {
    & $runWeb
    & $runBlockchain
    & $runWorkflow
    & $runAiService
    & $runAiSummary
    Write-Host ""
    Write-Host "All 5 services have been started in separate terminal windows." -ForegroundColor Green
    Write-Host "Enjoy testing RiskDL!" -ForegroundColor Cyan
}
elseif ($choice -eq "2") {
    & $runWeb
    & $runBlockchain
    & $runWorkflow
    Write-Host ""
    Write-Host "Core services have been started in separate terminal windows." -ForegroundColor Green
}
elseif ($choice -eq "3") {
    Write-Host "Running End-to-End Blockchain Verification Tests..." -ForegroundColor Yellow
    Write-Host "Make sure the core services (or at least Blockchain Service) are running first!" -ForegroundColor DarkYellow
    Write-Host ""
    
    # Load .env variables locally for the test run
    Get-Content .env | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
    }
    
    # Set blockchain service url for test client calls
    $env:BLOCKCHAIN_SERVICE_URL = "http://localhost:8002"
    
    # Run test
    .\venv\Scripts\python.exe test_e2e_blockchain.py
}
else {
    Write-Host "Invalid choice!" -ForegroundColor Red
}
