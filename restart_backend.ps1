# PowerShell script to restart the Flask backend
Write-Host "🔄 Restarting Flask backend server..." -ForegroundColor Yellow

# Find and kill processes on port 5000
$port = 5000
$connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue

if ($connections) {
    Write-Host "🛑 Stopping processes on port $port..." -ForegroundColor Red
    foreach ($conn in $connections) {
        $pid = $conn.OwningProcess
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "   Killing process: $($process.ProcessName) (PID: $pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host "✅ No processes found on port $port" -ForegroundColor Green
}

# Wait a moment
Start-Sleep -Seconds 1

# Start the Flask server
Write-Host "🚀 Starting Flask server..." -ForegroundColor Green
$scriptPath = Join-Path $PSScriptRoot "app.py"
Start-Process -FilePath "py" -ArgumentList $scriptPath -WindowStyle Normal

Write-Host "✅ Backend restart initiated!" -ForegroundColor Green
Write-Host "📝 Check the Flask console window for startup messages" -ForegroundColor Cyan

