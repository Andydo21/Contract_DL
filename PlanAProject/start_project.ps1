# ==============================================================================
# DENSO PLAN A PROJECT - ONE-CLICK START SCRIPT (POWERSHELL)
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  📑 DENSO PLAN A - DOCUMENT INTELLIGENCE (VISION & VECTOR)" -ForegroundColor Green
Write-Host "  ColPali Visual Late Interaction + Qdrant Vector Engine + Neo4j" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ------------------------------------------------------------------------------
# 1. KIỂM TRA & CÀI ĐẶT THƯ VIỆN PYTHON (LẦN CHẠY ĐẦU TIÊN)
# ------------------------------------------------------------------------------
Write-Host "[1/4] Kiểm tra các thư viện Python (PDF to Image, Qdrant, AI)..." -ForegroundColor Cyan
$Missing = $false
try {
    python -c "import django, rest_framework, qdrant_client, neo4j, sentence_transformers, PIL" 2>$null
    if ($LASTEXITCODE -ne 0) { $Missing = $true }
} catch {
    $Missing = $true
}

if ($Missing) {
    Write-Host "  -> Phát hiện thiếu thư viện. Đang tự động cài đặt từ requirements.txt..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [!] Cảnh báo: Một số thư viện cài đặt chưa hoàn tất." -ForegroundColor Yellow
    } else {
        Write-Host "  -> Đã cài đặt đầy đủ thư viện Python!" -ForegroundColor Green
    }
} else {
    Write-Host "  -> Các thư viện Python cốt lõi đã sẵn sàng!" -ForegroundColor Green
}
Write-Host ""

# ------------------------------------------------------------------------------
# 2. KIỂM TRA & KHỞI ĐỘNG DOCKER CONTAINERS (NEO4J & QDRANT)
# ------------------------------------------------------------------------------
Write-Host "[2/4] Kiểm tra dịch vụ Docker (Neo4j & Qdrant)..." -ForegroundColor Cyan

$DockerRunning = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { $DockerRunning = $true }
} catch {
    $DockerRunning = $false
}

if (-not $DockerRunning) {
    Write-Host "  -> Docker Engine chưa bật. Đang thử khởi động Docker Desktop..." -ForegroundColor Yellow
    if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") {
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        Write-Host "  -> Đang chờ Docker Engine sẵn sàng..." -ForegroundColor Yellow
        for ($i = 0; $i -lt 8; $i++) {
            Start-Sleep -Seconds 3
            docker info 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $DockerRunning = $true
                break
            }
        }
    }
}

if ($DockerRunning) {
    Write-Host "  -> Docker Engine đang hoạt động!" -ForegroundColor Green

    # Kiểm tra container Neo4j
    $NeoExists = docker ps -a --filter "name=denso-neo4j" --format "{{.Names}}"
    if (-not $NeoExists) {
        Write-Host "  -> Tạo mới container denso-neo4j (Port 7474, 7687)..." -ForegroundColor Yellow
        docker run -d --name denso-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/denso2026 neo4j:5-community | Out-Null
    } else {
        $NeoRunning = docker ps --filter "name=denso-neo4j" --format "{{.Names}}"
        if (-not $NeoRunning) {
            Write-Host "  -> Khởi động lại container denso-neo4j..." -ForegroundColor Yellow
            docker start denso-neo4j | Out-Null
        }
    }
    Write-Host "  -> Container Neo4j (denso-neo4j): ĐANG CHẠY" -ForegroundColor Green

    # Kiểm tra container Qdrant
    $QdrantExists = docker ps -a --filter "name=denso-qdrant" --format "{{.Names}}"
    if (-not $QdrantExists) {
        Write-Host "  -> Tạo mới container denso-qdrant (Port 6333, 6334)..." -ForegroundColor Yellow
        docker run -d --name denso-qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest | Out-Null
    } else {
        $QdrantRunning = docker ps --filter "name=denso-qdrant" --format "{{.Names}}"
        if (-not $QdrantRunning) {
            Write-Host "  -> Khởi động lại container denso-qdrant..." -ForegroundColor Yellow
            docker start denso-qdrant | Out-Null
        }
    }
    Write-Host "  -> Container Qdrant (denso-qdrant): ĐANG CHẠY" -ForegroundColor Green
} else {
    Write-Host "  [!] Docker chưa bật. Sẽ sử dụng chế độ lưu trữ Qdrant cục bộ (Local Storage)!" -ForegroundColor Yellow
}
Write-Host ""

# ------------------------------------------------------------------------------
# 3. DATABASE MIGRATIONS (DJANGO SQLITE)
# ------------------------------------------------------------------------------
Write-Host "[3/4] Áp dụng Database Migrations cho Plan A..." -ForegroundColor Cyan
python manage.py migrate --noinput
Write-Host ""

# ------------------------------------------------------------------------------
# 4. KHỞI CHẠY DJANGO SERVER & IN BANNER TRUY CẬP
# ------------------------------------------------------------------------------
# Kiểm tra cổng 8000 có bị trùng với denso_demo không
$Port = 8000
$PortCheck = Test-NetConnection -ComputerName 127.0.0.1 -Port 8000 -WarningAction SilentlyContinue
if ($PortCheck.TcpTestSucceeded) {
    Write-Host "  [Chú ý] Cổng 8000 đang được sử dụng (có thể bởi denso_demo). Tự động chuyển sang cổng 8001..." -ForegroundColor Yellow
    $Port = 8001
}

Write-Host "====================================================================" -ForegroundColor Green
Write-Host "  🚀 PLAN A PROJECT ĐÃ SẴN SÀNG! CÁC ĐỊA CHỈ TRUY CẬP:" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
Write-Host "  🌐 Ứng dụng Document Intelligence: http://127.0.0.1:$Port/" -ForegroundColor White
Write-Host "  ⚡ Qdrant Vector Dashboard:       http://localhost:6333/dashboard" -ForegroundColor Magenta
Write-Host "  🕸️ Neo4j Knowledge Browser:      http://localhost:7474/ (neo4j/denso2026)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Đang chạy máy chủ Django tại http://127.0.0.1:$Port ... (Nhấn Ctrl+C để dừng)" -ForegroundColor Yellow
python manage.py runserver 127.0.0.1:$Port
