@echo off
setlocal

set "ROOT=%~dp0"
set "FRONTEND=%ROOT%..\frontend"
set "BACKEND=%ROOT%"
set "VENV_PY=%BACKEND%.venv\Scripts\python.exe"
set "DIST_DIR=%BACKEND%dist"

echo [0/6] Preparing backend virtual environment...
if not exist "%VENV_PY%" (
  py -3.12 -m venv "%BACKEND%.venv"
  if errorlevel 1 (
    echo Failed to create Python virtual environment.
    exit /b 1
  )
)

call "%VENV_PY%" -m ensurepip --upgrade
if errorlevel 1 (
  echo ensurepip failed.
  exit /b 1
)

call "%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo pip upgrade failed.
  exit /b 1
)

echo [1/6] Installing backend dependencies...
pushd "%BACKEND%"
call "%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Backend requirements install failed.
  popd
  exit /b 1
)

call "%VENV_PY%" -m pip install pyinstaller
if errorlevel 1 (
  echo PyInstaller install failed.
  popd
  exit /b 1
)
popd

echo [2/6] Installing frontend dependencies...
pushd "%FRONTEND%"
call npm install
if errorlevel 1 (
  echo Frontend dependency install failed.
  popd
  exit /b 1
)

echo [3/6] Building frontend...
call npm run build
if errorlevel 1 (
  echo Frontend build failed.
  popd
  exit /b 1
)
popd

echo [4/6] Building production EXE...
pushd "%BACKEND%"
call :prepare_exe "timesheet.exe"
set APP_MODE=production
call "%VENV_PY%" build.py
if errorlevel 1 (
  echo Production build failed.
  popd
  exit /b 1
)

echo [5/6] Building testing EXE...
call :prepare_exe "timesheet-test.exe"
set APP_MODE=testing
call "%VENV_PY%" build.py
if errorlevel 1 (
  echo Testing build failed.
  popd
  exit /b 1
)

echo [6/6] Done.
echo Output files:
echo   %BACKEND%dist\timesheet.exe
echo   %BACKEND%dist\timesheet-test.exe

popd
endlocal
exit /b 0

:prepare_exe
set "EXE_NAME=%~1"
set "EXE_PATH=%DIST_DIR%\%EXE_NAME%"

for %%N in ("%EXE_NAME%") do taskkill /F /IM "%%~N" >nul 2>&1

if exist "%EXE_PATH%" (
  echo Replacing existing %EXE_NAME%...
  for /L %%I in (1,1,6) do (
    del /F /Q "%EXE_PATH%" >nul 2>&1
    if not exist "%EXE_PATH%" goto :prepare_done
    timeout /T 1 /NOBREAK >nul
  )
)

if exist "%EXE_PATH%" (
  echo ERROR: %EXE_NAME% is locked. Close it and try again.
  exit /b 1
)

:prepare_done
exit /b 0
