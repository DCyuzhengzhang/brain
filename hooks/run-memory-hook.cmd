@echo off
REM Memory Management Hook Runner for Windows
setlocal

set CLAUDE_PLUGIN_ROOT=%~dp0..
set NODE_PATH=node

if "%1"=="" (
    echo Usage: %0 [command]
    echo Commands: record, retrieve, process-feedback, status
    exit /b 1
)

set COMMAND=%1
shift

cd /d "%CLAUDE_PLUGIN_ROOT%"

if "%COMMAND%"=="record" (
    if "%2"=="" (
        echo Error: Need user input and Claude output
        exit /b 1
    )
    %NODE_PATH% hooks\memory-hook.js record "%2" "%3"
) else if "%COMMAND%"=="retrieve" (
    if "%2"=="" (
        echo Error: Need user query
        exit /b 1
    )
    %NODE_PATH% hooks\memory-hook.js retrieve "%2"
) else if "%COMMAND%"=="process-feedback" (
    if "%2"=="" (
        echo Error: Need feedback file path
        exit /b 1
    )
    %NODE_PATH% hooks\memory-hook.js process-feedback "%2"
) else if "%COMMAND%"=="status" (
    %NODE_PATH% hooks\memory-hook.js status
) else if "%COMMAND%"=="handle-user-input" (
    REM This is called by Claude Code hooks system
    %NODE_PATH% hooks\memory-hook.js handle-user-input "%2" "%3"
) else if "%COMMAND%"=="handle-tool-result" (
    REM This is called by Claude Code hooks system
    %NODE_PATH% hooks\memory-hook.js handle-tool-result "%2" "%3" "%4"
) else if "%COMMAND%"=="session-start" (
    echo Starting memory management session...
    %NODE_PATH% hooks\memory-hook.js session-start
) else (
    echo Unknown command: %COMMAND%
    exit /b 1
)

endlocal