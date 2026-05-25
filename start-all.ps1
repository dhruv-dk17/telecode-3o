# Telecode — Ultimate All-in-One Orchestration Script for Windows PowerShell
# Author: Antigravity AI
# Version: 1.0.0

$ErrorActionPreference = "Stop"

# ─── Beautiful Ascii Art & Theme ─────────────────────────────────────────────
Clear-Host
Write-Host @"
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ████████╗███████╗██╗     ███████╗ ██████╗  ██████╗ ██████╗ ███████╗
  ╚══██╔══╝██╔════╝██║     ██╔════╝██╔════╝ ██╔═══██╗██╔══██╗██╔════╝
     ██║   █████╗  ██║     █████╗  ██║      ██║   ██║██║  ██║█████╗  
     ██║   ██╔══╝  ██║     ██╔══╝  ██║      ██║   ██║██║  ██║██╔══╝  
     ██║   ███████╗███████╗███████╗╚██████╗ ╚██████╔╝██████╔╝███████╗
     ╚═╝   ╚══════╝╚══════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝
                     Ambient AI Coding Continuity Platform
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"@ -ForegroundColor Cyan

# ─── Helper Functions ─────────────────────────────────────────────────────────
function Show-Status($message, $type="info") {
    $time = Get-Date -Format "HH:mm:ss"
    switch ($type) {
        "success" { Write-Host "[$time] [✅ SUCCESS] $message" -ForegroundColor Green }
        "info"    { Write-Host "[$time] [⚡ INFO]    $message" -ForegroundColor Cyan }
        "warning" { Write-Host "[$time] [⚠️ WARNING] $message" -ForegroundColor Yellow }
        "error"   { Write-Host "[$time] [❌ ERROR]   $message" -ForegroundColor Red }
    }
}

function Check-Port($port) {
    $connection = Test-NetConnection -ComputerName 127.0.0.1 -Port $port -WarningAction SilentlyContinue
    return $connection.TcpTestSucceeded
}

# ─── Port Conflicts Check ─────────────────────────────────────────────────────
Show-Status "Verifying port availability..." "info"

if (Check-Port 3005) {
    Show-Status "Port 3005 is already in use. NestJS Server might already be running." "warning"
}
if (Check-Port 8000) {
    Show-Status "Port 8000 is already in use. Python Worker might already be running." "warning"
}

# ─── Start Database via Docker Compose ────────────────────────────────────────
Show-Status "Starting database container via Docker Compose..." "info"
try {
    docker-compose up -d
    Show-Status "Database container started successfully (pgvector:pg16)." "success"
} catch {
    Show-Status "Could not start Docker Compose. If Docker is not running, local Sqlite is used as fallback." "warning"
}

# ─── Start NestJS Server ──────────────────────────────────────────────────────
Show-Status "Launching NestJS Server (Port 3005)..." "info"
$serverCommand = "powershell -NoExit -Command `"cd apps/server; Set-Location -Path . ; Write-Host '🚀 Launching Telecode NestJS Server...' -ForegroundColor Cyan; npm run start:dev`""
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd apps/server; npm run start:dev" -WindowStyle Normal
Start-Sleep -Seconds 3

# ─── Start FastAPI Python Worker ──────────────────────────────────────────────
Show-Status "Launching Python AI Worker (Port 8000)..." "info"
$workerCommand = "powershell -NoExit -Command `"cd apps/worker; .\.venv\Scripts\activate.ps1; Write-Host '🐍 Launching Telecode Python Worker...' -ForegroundColor Green; uvicorn main:app --reload --port 8000`""
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd apps/worker; .venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000" -WindowStyle Normal
Start-Sleep -Seconds 3

# ─── Start Telegram Bot ───────────────────────────────────────────────────────
Show-Status "Launching Telegram Bot Service..." "info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd apps/bot; npm run start:dev" -WindowStyle Normal

# ─── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Show-Status "All services spawned in separate terminal windows successfully!" "success"
Write-Host " ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  👉 Telegram Bot  : Running and listening to Telegram updates."
Write-Host "  👉 NestJS Server : http://localhost:3005/api"
Write-Host "  👉 AI Worker     : http://localhost:8000 (Health Check: http://localhost:8000/health)"
Write-Host " ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  💡 Tip: To sync VS Code, use /sync in Telegram, then connect in extension." -ForegroundColor Yellow
Write-Host ""
