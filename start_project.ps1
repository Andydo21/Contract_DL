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
Write-Host "  [1] Start ALL Services (Web, Blockchain, Workflow, AI Inference, AI Summary, Legal MCP) [Default]" -ForegroundColor White
Write-Host "  [2] Start Core Services only (Web, Blockchain, Workflow)" -ForegroundColor White
Write-Host "  [3] Run End-to-End Blockchain Verification Tests (test_e2e_blockchain.py)" -ForegroundColor White
Write-Host "  [4] Exit" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter your choice (1-4) [Press ENTER for Option 1]"

if (-not $choice) {
    $choice = "1"
}
if ($choice -eq "4") {
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

$runLegalMcp = {
    Write-Host "Launching Legal MCP Server on http://127.0.0.1:8005..." -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle='RiskDL - Legal MCP Server (Port 8005)'; cd ai_service; ..\venv\Scripts\python.exe legal_mcp_server.py"
}

$startFabricDocker = {
    Write-Host "Checking Docker status..." -ForegroundColor Yellow
    $dockerRunning = $false
    try {
        $oldPref = $ErrorActionPreference
        $ErrorActionPreference = "SilentlyContinue"
        & docker ps > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerRunning = $true
        }
        $ErrorActionPreference = $oldPref
    } catch {
        $dockerRunning = $false
    }

    if (-not $dockerRunning) {
        Write-Host "[WARNING] Docker Desktop is not running! Hyperledger Fabric services cannot start." -ForegroundColor Red
        Write-Host "Please start Docker Desktop and press Enter to continue, or Ctrl+C to abort." -ForegroundColor Yellow
        $null = Read-Host
        try {
            $oldPref = $ErrorActionPreference
            $ErrorActionPreference = "SilentlyContinue"
            & docker ps > $null 2>&1
            if ($LASTEXITCODE -eq 0) {
                $dockerRunning = $true
            }
            $ErrorActionPreference = $oldPref
        } catch {
            $dockerRunning = $false
        }
        if (-not $dockerRunning) {
            Write-Host "[ERROR] Docker is still not running. Starting local services without Fabric." -ForegroundColor Red
            return
        }
    }
    Write-Host "Starting Fabric network and Explorer services in Docker..." -ForegroundColor Yellow
    docker compose up -d orderer.example.com peer0.org1.example.com fabric-chaincode fabric-gateway explorer-db explorer
}

if ($choice -eq "1") {
    & $startFabricDocker
    & $runWeb
    & $runBlockchain
    & $runWorkflow
    & $runAiService
    & $runAiSummary
    & $runLegalMcp
    Write-Host ""
    Write-Host "All local microservices and Legal MCP Server have been started!" -ForegroundColor Green
    Write-Host "Fabric blockchain network and Explorer are running in Docker." -ForegroundColor Green
    Write-Host "Enjoy testing RiskDL!" -ForegroundColor Cyan
}
elseif ($choice -eq "2") {
    & $startFabricDocker
    & $runWeb
    & $runBlockchain
    & $runWorkflow
    Write-Host ""
    Write-Host "Core local services have been started in separate terminal windows." -ForegroundColor Green
    Write-Host "Fabric blockchain network is running in Docker." -ForegroundColor Green
}
elseif ($choice -eq "3") {
    Write-Host "Running End-to-End Blockchain Verification Tests..." -ForegroundColor Yellow
    Write-Host "Make sure the core services (or at least Blockchain Service) are running first!" -ForegroundColor DarkYellow
    Write-Host ""
    
    Get-Content .env | Where-Object { $_ -match '=' -and $_ -notmatch '^#' } | ForEach-Object {
        $name, $value = $_ -split '=', 2
        [System.Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim())
    }
    
    $env:BLOCKCHAIN_SERVICE_URL = "http://localhost:8002"
    
    .\venv\Scripts\python.exe test_e2e_blockchain.py
}
else {
    Write-Host "Invalid choice!" -ForegroundColor Red
}
