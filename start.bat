@echo off
setlocal

cd /d "%~dp0"

if not exist "%~dp0.env\Scripts\python.exe" (
	echo ERROR: .env Python environment not found at "%~dp0.env\Scripts\python.exe"
	echo Please create or restore the .env environment before starting services.
	exit /b 1
)

echo Applying backend migrations...
cd /d "%~dp0backend"
"%~dp0.env\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 (
	echo ERROR: Migration apply failed. Backend startup aborted.
	exit /b 1
)

echo Verifying migration state...
"%~dp0.env\Scripts\python.exe" manage.py migrate --check
if errorlevel 1 (
	echo ERROR: Pending migrations detected after apply. Backend startup aborted.
	exit /b 1
)

cd /d "%~dp0"
echo Starting backend and frontend servers...

start "Backend (Django)" cmd /k "cd /d ""%~dp0backend"" && ""%~dp0.env\Scripts\python.exe"" manage.py runserver"
start "Background Worker" cmd /k "cd /d ""%~dp0backend"" && ""%~dp0.env\Scripts\python.exe"" manage.py run_background_jobs"
start "Frontend (Vite)" cmd /k "cd /d ""%~dp0frontend"" && npm run dev -- --host 127.0.0.1 --port 5173"

echo Backend, worker, and frontend services are launching in separate windows.
endlocal
