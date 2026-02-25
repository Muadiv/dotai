@echo off
REM setup.bat — One-time setup for dotai on Windows
REM
REM Creates a Python virtual environment, installs the package, and places
REM a wrapper script so "dotai" works from any directory.
REM
REM Usage:
REM   setup.bat              — install
REM   setup.bat --uninstall  — remove venv and wrapper
REM

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "VENV_DIR=%SCRIPT_DIR%\.venv"
set "WRAPPER_NAME=dotai.cmd"

REM ---------------------------------------------------------------------------
REM Uninstall
REM ---------------------------------------------------------------------------
if "%~1"=="--uninstall" (
    echo Uninstalling dotai...
    if exist "%VENV_DIR%" (
        rmdir /s /q "%VENV_DIR%"
        echo   Removed %VENV_DIR%
    )
    if exist "%USERPROFILE%\.local\bin\%WRAPPER_NAME%" (
        del "%USERPROFILE%\.local\bin\%WRAPPER_NAME%"
        echo   Removed wrapper from %USERPROFILE%\.local\bin
    )
    echo   Done.
    exit /b 0
)

REM ---------------------------------------------------------------------------
REM Check Python
REM ---------------------------------------------------------------------------
set "PYTHON="
where python3 >nul 2>&1 && set "PYTHON=python3" && goto :found_python
where python >nul 2>&1 && set "PYTHON=python" && goto :found_python
where py >nul 2>&1 && set "PYTHON=py -3" && goto :found_python

echo   Error: Python 3 is required but not found.
echo   Install it from https://www.python.org
exit /b 1

:found_python
for /f "tokens=*" %%v in ('%PYTHON% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set "PY_VERSION=%%v"
echo   Using %PYTHON% (%PY_VERSION%)

REM ---------------------------------------------------------------------------
REM Create venv and install
REM ---------------------------------------------------------------------------
if exist "%VENV_DIR%" (
    echo   Virtual environment already exists. Updating...
) else (
    echo   Creating virtual environment...
    %PYTHON% -m venv "%VENV_DIR%"
)

echo   Installing dotai...
"%VENV_DIR%\Scripts\pip.exe" install --quiet --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install --quiet -e "%SCRIPT_DIR%"

REM ---------------------------------------------------------------------------
REM Create wrapper script
REM ---------------------------------------------------------------------------
set "BIN_DIR=%USERPROFILE%\.local\bin"
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
set "WRAPPER=%BIN_DIR%\%WRAPPER_NAME%"

(
echo @echo off
echo "%VENV_DIR%\Scripts\dotai.exe" %%*
) > "%WRAPPER%"

echo.
echo   Installed successfully!
echo.
echo   Command:  %WRAPPER%
echo   Venv:     %VENV_DIR%
echo.

REM Check if BIN_DIR is on PATH
echo %PATH% | findstr /i /c:"%BIN_DIR%" >nul 2>&1
if errorlevel 1 (
    echo   NOTE: %BIN_DIR% is not on your PATH.
    echo   Add it by running:
    echo.
    echo     setx PATH "%BIN_DIR%;%%PATH%%"
    echo.
    echo   Then restart your terminal.
) else (
    echo   Try it:  dotai --help
)
