@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  THE MUSICIAN -- Build Script
REM  Creates a standalone Windows executable with custom icon
REM ============================================================

set "BOT_NAME=THE_MUSICIAN"

echo ============================================================
echo    [ THE MUSICIAN ]  --  Build Script
echo ============================================================
echo.

REM ============================================================
REM  STEP 1 -- Check Python
REM ============================================================
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)
python --version
echo.

REM ============================================================
REM  STEP 2 -- Check PyInstaller
REM ============================================================
echo [2/5] Checking PyInstaller...
pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] PyInstaller not found -- installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo [ERROR] Failed to install PyInstaller.
        echo Try running: pip install pyinstaller
        pause
        exit /b 1
    )
)
pyinstaller --version
echo.

REM ============================================================
REM  STEP 3 -- Verify required files
REM ============================================================
echo [3/5] Checking required files...
if not exist "src\bot.py" (
    echo [ERROR] src\bot.py not found!
    pause
    exit /b 1
)
if not exist "src\secret.py" (
    echo [ERROR] src\secret.py not found!
    echo Create it with your Discord bot token:
    echo DISCORD_TOKEN = "your_token_here"
    pause
    exit /b 1
)
if exist "assets\ffmpeg.exe" (
    echo [OK] ffmpeg.exe found
) else (
    echo [WARN] ffmpeg.exe not found in assets\ -- it will be downloaded on first run.
)
if exist "assets\icon.ico" (
    echo [OK] icon.ico found -- will be embedded
) else (
    echo [WARN] icon.ico not found -- using default PyInstaller icon.
)
echo.

REM ============================================================
REM  STEP 4 -- Clean previous builds
REM ============================================================
echo [4/5] Cleaning old builds...
taskkill /f /im "%BOT_NAME%.exe" 2>nul
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del "%BOT_NAME%.spec" 2>nul
echo [OK] Clean complete
echo.

REM ============================================================
REM  STEP 5 -- Build the executable
REM ============================================================
echo [5/5] Building %BOT_NAME%.exe...
echo This may take several minutes...
echo.

REM Build command with icon explicitly specified
pyinstaller --onefile ^
    --name "%BOT_NAME%" ^
    --icon=assets\icon.ico ^
    --console ^
    --hidden-import=pretty_midi ^
    --hidden-import=pydub ^
    --hidden-import=transkun ^
    --add-data "src\secret.py;." ^
    --add-data "assets\ffmpeg.exe;." ^
    src\bot.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed! Check the error messages above.
    pause
    exit /b 1
)

REM ============================================================
REM  Show results
REM ============================================================
echo.
echo ============================================================
echo    [ SUCCESS ]  Build complete!
echo ============================================================
echo.

set "EXE_PATH=dist\%BOT_NAME%.exe"
if exist "%EXE_PATH%" (
    for %%A in ("%EXE_PATH%") do set "EXE_SIZE=%%~zA"
    set /a EXE_SIZE_MB=!EXE_SIZE! / 1048576
    echo [FILE] %EXE_PATH%
    echo [SIZE] !EXE_SIZE_MB! MB
    echo.
) else (
    echo [ERROR] Executable not found at %EXE_PATH%
    pause
    exit /b 1
)

REM ============================================================
REM  Optional version tracking
REM ============================================================
if exist "version.txt" (
    set /p VERSION=<version.txt
    echo [VERSION] !VERSION!
) else (
    echo 1.0.0 > version.txt
    echo [VERSION] 1.0.0 (created)
)
echo.

REM ============================================================
REM  Ask to run the bot now
REM ============================================================
echo ------------------------------------------------------------
echo  Options:
echo    [1]  Done - exit
echo    [2]  Run the bot now
echo.
set /p CHOICE="Choose (1 or 2): "

if "%CHOICE%"=="2" (
    echo.
    echo [START] Launching %BOT_NAME%.exe...
    start "" "%EXE_PATH%"
    echo [OK] Bot started in a new window.
)

echo.
echo [DONE] The exe is in the dist folder.
pause
exit /b 0