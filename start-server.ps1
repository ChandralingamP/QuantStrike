# QuantStrike Server Startup Script (Windows)
# Starts backend, frontend, and Cloudflare tunnel automatically.
# Usage: Right-click -> Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File start-server.ps1

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  QuantStrike Server Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Start Backend ────────────────────────────────────────
Write-Host "[1/3] Starting Django backend..." -ForegroundColor Yellow
$backendDir = Join-Path $ROOT "backend"
$venvPython = Join-Path $backendDir "venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Python venv not found at $venvPython" -ForegroundColor Red
    Write-Host "Run: cd backend && python -m venv venv && venv\Scripts\activate && pip install -r requirements.txt" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$backendProcess = Start-Process -FilePath $venvPython `
    -ArgumentList "manage.py", "runserver", "0.0.0.0:8000" `
    -WorkingDirectory $backendDir `
    -PassThru -WindowStyle Normal
Write-Host "  Backend started (PID: $($backendProcess.Id))" -ForegroundColor Green

Start-Sleep -Seconds 3

# ── 2. Start Cloudflare Tunnel ──────────────────────────────
Write-Host "[2/3] Starting Cloudflare tunnel..." -ForegroundColor Yellow

# Check if cloudflared is installed
$cfPath = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cfPath) {
    Write-Host "ERROR: cloudflared not found. Install it:" -ForegroundColor Red
    Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Start cloudflared and capture output to find the URL
$tunnelLogFile = Join-Path $ROOT "tunnel.log"
$tunnelProcess = Start-Process -FilePath "cloudflared" `
    -ArgumentList "tunnel", "--url", "http://localhost:5173" `
    -RedirectStandardError $tunnelLogFile `
    -PassThru -WindowStyle Normal

Write-Host "  Waiting for tunnel URL..." -ForegroundColor Gray

# Poll the log file for the tunnel URL (cloudflared writes to stderr)
$tunnelHost = $null
$maxWait = 30
for ($i = 0; $i -lt $maxWait; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $tunnelLogFile) {
        $logContent = Get-Content $tunnelLogFile -Raw -ErrorAction SilentlyContinue
        if ($logContent -match "https://([a-z0-9-]+\.trycloudflare\.com)") {
            $tunnelHost = $Matches[1]
            $tunnelUrl = "https://$tunnelHost"
            break
        }
    }
}

if (-not $tunnelHost) {
    Write-Host "  WARNING: Could not capture tunnel URL after ${maxWait}s" -ForegroundColor Red
    Write-Host "  Check the cloudflared window for the URL" -ForegroundColor Red
    $tunnelHost = "unknown.trycloudflare.com"
    $tunnelUrl = "Check cloudflared window"
} else {
    Write-Host "  Tunnel URL: $tunnelUrl" -ForegroundColor Green
}

# ── 3. Start Frontend with tunnel host ──────────────────────
Write-Host "[3/3] Starting React frontend..." -ForegroundColor Yellow

$frontendDir = Join-Path $ROOT "frontend"
$env:TUNNEL_HOST = $tunnelHost

# Use cmd to run npm (handles PATH better on Windows)
$frontendProcess = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/k", "cd /d `"$frontendDir`" && set TUNNEL_HOST=$tunnelHost && npm run dev -- --host 0.0.0.0" `
    -PassThru -WindowStyle Normal
Write-Host "  Frontend started (PID: $($frontendProcess.Id))" -ForegroundColor Green

Start-Sleep -Seconds 3

# ── Done ────────────────────────────────────────────────────
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  All services running!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Local:  http://localhost:5173" -ForegroundColor White
Write-Host "  Tunnel: $tunnelUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Backend PID:  $($backendProcess.Id)" -ForegroundColor Gray
Write-Host "  Tunnel PID:   $($tunnelProcess.Id)" -ForegroundColor Gray
Write-Host "  Frontend PID: $($frontendProcess.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Enter to STOP all services..." -ForegroundColor Yellow
Read-Host

# ── Cleanup ─────────────────────────────────────────────────
Write-Host "Stopping all services..." -ForegroundColor Yellow

try { Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
try { Stop-Process -Id $tunnelProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
try { Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue } catch {}

# Clean up temp log
Remove-Item $tunnelLogFile -Force -ErrorAction SilentlyContinue

Write-Host "All services stopped." -ForegroundColor Green
