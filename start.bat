@echo off
setlocal
cd /d "%~dp0"

call :ensure_postgresql
if errorlevel 1 (
  echo.
  echo PostgreSQL setup was not completed.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Run the setup steps in README.md.
  pause
  exit /b 1
)

set "PYTHONPATH=%CD%\app"

if not exist "config\config.json" (
  echo config\config.json was not found.
  echo Starting first setup.
  ".venv\Scripts\python.exe" -m kakeibo.config_wizard
  if errorlevel 1 (
    echo.
    echo config setup was not completed.
    pause
    exit /b 1
  )
)

".venv\Scripts\python.exe" -m kakeibo
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" (
  echo.
  echo Kakeibo DX stopped with error code %APP_EXIT_CODE%.
  echo Check the error above and the latest file in the logs folder.
  pause
)
endlocal & exit /b %APP_EXIT_CODE%

:ensure_postgresql
call :find_psql
if defined PSQL_EXE exit /b 0

echo PostgreSQL was not found in PATH or known folders.
echo If PostgreSQL is already installed, enter its install folder now.
echo Example: C:\Program Files\PostgreSQL\16
echo Press Enter if it is not installed.
set "PG_EXISTING_DIR="
set /p "PG_EXISTING_DIR=Existing PostgreSQL folder: "
if defined PG_EXISTING_DIR (
  call :find_psql_in_dir "%PG_EXISTING_DIR%"
  if defined PSQL_EXE (
    echo PostgreSQL found: %PSQL_EXE%
    exit /b 0
  )
  echo psql.exe was not found under: %PG_EXISTING_DIR%
  echo Check that the folder contains a bin folder with psql.exe.
  exit /b 1
)

echo PostgreSQL was not found on this PC.
echo This app needs PostgreSQL Server and psql.exe.
echo.
choice /c YN /m "Install PostgreSQL with winget now"
if errorlevel 2 exit /b 1

where winget >nul 2>nul
if errorlevel 1 (
  echo winget was not found. Install PostgreSQL manually, then run start.bat again.
  exit /b 1
)

echo.
echo Enter an install folder, or press Enter to use the installer default.
echo Example: C:\Program Files\PostgreSQL
set "PG_INSTALL_DIR="
set /p "PG_INSTALL_DIR=Install folder: "

if defined PG_INSTALL_DIR (
  winget install --id PostgreSQL.PostgreSQL --source winget --location "%PG_INSTALL_DIR%" --accept-package-agreements --accept-source-agreements
) else (
  winget install --id PostgreSQL.PostgreSQL --source winget --accept-package-agreements --accept-source-agreements
)
if errorlevel 1 (
  echo PostgreSQL installer failed or was canceled.
  exit /b 1
)

call :find_psql
if not defined PSQL_EXE (
  echo PostgreSQL may be installed, but psql.exe was not found yet.
  echo Close this window, open a new one, then run start.bat again.
  exit /b 1
)

echo PostgreSQL found: %PSQL_EXE%
echo If this is the first setup, make sure config\config.json has the correct database settings.
echo The database name expected by default is kakeibo_dx.
exit /b 0

:find_psql
set "PSQL_EXE="
where psql >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%P in ('where psql') do (
    if not defined PSQL_EXE set "PSQL_EXE=%%P"
  )
  exit /b 0
)

for /d %%D in ("C:\Program Files\PostgreSQL\*") do (
  if exist "%%~fD\bin\psql.exe" (
    set "PSQL_EXE=%%~fD\bin\psql.exe"
    set "PATH=%%~fD\bin;%PATH%"
  )
)
if defined PG_INSTALL_DIR (
  call :find_psql_in_dir "%PG_INSTALL_DIR%"
)
exit /b 0

:find_psql_in_dir
if exist "%~1\bin\psql.exe" (
  set "PSQL_EXE=%~1\bin\psql.exe"
  set "PATH=%~1\bin;%PATH%"
  exit /b 0
)
for /d %%D in ("%~1\*") do (
  if exist "%%~fD\bin\psql.exe" (
    set "PSQL_EXE=%%~fD\bin\psql.exe"
    set "PATH=%%~fD\bin;%PATH%"
    exit /b 0
  )
)
exit /b 0
