# ==============================================================================
# DENSO FACTORY INTELLIGENCE - ONE-CLICK START SCRIPT (POWERSHELL)
# ==============================================================================
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = "Continue"

Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "  🏭 DENSO FACTORY INTELLIGENCE SYSTEM - KHỞI ĐỘNG HỆ THỐNG" -ForegroundColor Green
Write-Host "  Hybrid RAG: Qdrant Vector DB + Neo4j Graph + Multilingual BGE" -ForegroundColor Yellow
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ------------------------------------------------------------------------------
# 1. KIỂM TRA & CÀI ĐẶT THƯ VIỆN PYTHON (LẦN CHẠY ĐẦU TIÊN)
# ------------------------------------------------------------------------------
Write-Host "[1/5] Kiểm tra các thư viện Python cần thiết..." -ForegroundColor Cyan
$Missing = $false
try {
    python -c "import django, qdrant_client, neo4j, sentence_transformers, torch, numpy" 2>$null
    if ($LASTEXITCODE -ne 0) { $Missing = $true }
} catch {
    $Missing = $true
}

if ($Missing) {
    Write-Host "  -> Phát hiện thiếu thư viện. Đang tự động cài đặt từ requirements.txt..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [!] Cảnh báo: Một số thư viện cài đặt chưa hoàn tất. Tiếp tục kiểm tra dịch vụ..." -ForegroundColor Yellow
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
Write-Host "[2/5] Kiểm tra dịch vụ Docker (Neo4j & Qdrant)..." -ForegroundColor Cyan

# Kiểm tra Docker daemon
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
        Write-Host "  -> Đang chờ Docker Engine sẵn sàng (tối đa 25s)..." -ForegroundColor Yellow
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
    Write-Host "  [!] Docker chưa bật. Hệ thống sẽ tự động chuyển sang chế độ Safe Fallback (SQLite + Embedded Qdrant Storage)!" -ForegroundColor Yellow
}
Write-Host ""

# ------------------------------------------------------------------------------
# 3. DATABASE MIGRATIONS (DJANGO SQLITE)
# ------------------------------------------------------------------------------
Write-Host "[3/5] Áp dụng Database Migrations..." -ForegroundColor Cyan
python manage.py migrate --noinput
Write-Host ""

# ------------------------------------------------------------------------------
# 4. TỰ ĐỘNG ĐỒNG BỘ TRI THỨC VÀO NEO4J VÀ QDRANT (NẾU CẦN)
# ------------------------------------------------------------------------------
Write-Host "[4/5] Đồng bộ tri thức vào Qdrant & Neo4j Graph..." -ForegroundColor Cyan
python -c "
import os, sys, django
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.models import Case
from core.services import Neo4jGraphService, QdrantVectorService

# Kiểm tra dữ liệu demo
if Case.objects.count() == 0:
    from django.core.management import call_command
    print('  -> Cơ sở dữ liệu trống. Đang nạp dữ liệu demo ban đầu...')
    call_command('seed_demo_data')

# Đồng bộ Neo4j
neo_svc = Neo4jGraphService()
if neo_svc.is_connected():
    neo_svc.seed_factory_knowledge_graph()
    print('  -> Đã đồng bộ Đồ thị Tri thức Neo4j thành công!')

# Đồng bộ Qdrant
try:
    q_svc = QdrantVectorService()
    info = q_svc.client.get_collection(q_svc.COLLECTION_CASES)
    if info.points_count == 0:
        import subprocess
        subprocess.run([sys.executable, 'scratch/index_qdrant.py'], check=True)
    else:
        print(f'  -> Qdrant Vector DB đã có sẵn {info.points_count} Cases (Sẵn sàng HNSW Search)!')
except Exception as e:
    print('  [Qdrant Sync Notice]', e)
"
Write-Host ""

# ------------------------------------------------------------------------------
# 5. KHỞI CHẠY DJANGO SERVER & IN BANNER TRUY CẬP
# ------------------------------------------------------------------------------
Write-Host "====================================================================" -ForegroundColor Green
Write-Host "  🚀 HỆ THỐNG ĐÃ SẴN SÀNG! CÁC ĐỊA CHỈ TRUY CẬP:" -ForegroundColor Green
Write-Host "====================================================================" -ForegroundColor Green
Write-Host "  🌐 Ứng dụng Web DENSO:       http://127.0.0.1:8000/" -ForegroundColor White
Write-Host "  💬 AI Chat & Knowledge Gap:  http://127.0.0.1:8000/chat/" -ForegroundColor White
Write-Host "  🎙️ Phỏng vấn Socratic:       http://127.0.0.1:8000/interview/" -ForegroundColor White
Write-Host "  📊 Bảng điều khiển Giám sát: http://127.0.0.1:8000/dashboard/" -ForegroundColor White
Write-Host "  ⚡ Qdrant Vector Dashboard:   http://localhost:6333/dashboard" -ForegroundColor Magenta
Write-Host "  🕸️ Neo4j Knowledge Browser:  http://localhost:7474/ (neo4j/denso2026)" -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Đang chạy máy chủ Django tại http://127.0.0.1:8000 ... (Nhấn Ctrl+C để dừng)" -ForegroundColor Yellow
python manage.py runserver 127.0.0.1:8000
