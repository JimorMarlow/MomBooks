@echo off
call chcp 65001 >nul
echo ==================================================
echo MomBooks Server Starting...
echo ==================================================

echo.
echo [1/2] Generating index.html...
python "I:\Downloads\MomBooks\update_books_index.py"
if errorlevel 1 (
    echo.
    echo ERROR: Failed to generate index.html
    pause
    exit /b 1
)

echo.
echo [2/2] Starting server...
echo Local URL: http://192.168.31.208:8080/
echo External URL: http://95.174.116.112:8080/
start "MomBooks Server" python "I:\Downloads\MomBooks\start_server.py"

echo.
echo Server started in separate window!
echo Open in browser: http://books:3011@192.168.31.208:8080/
echo Login: books / Password: 3011
echo To stop: close server window or press Ctrl+C in it
pause
