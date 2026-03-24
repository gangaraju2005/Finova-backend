# ─── Finovo Backend Startup Script ────────────────────────────────────────────
# Run this instead of manually typing manage.py commands.
# Usage: .\start.ps1

$env:DJANGO_SETTINGS_MODULE = "core.settings"

Write-Host "Starting Finovo backend on http://0.0.0.0:8000 ..." -ForegroundColor Cyan
.\venv\Scripts\python manage.py runserver 0.0.0.0:8000
