@echo off
REM ============================================================
REM 虚拟资料项目 — Windows 定时任务配置脚本
REM ============================================================
REM 用途：自动配置每日定时任务，运行内容分发流水线
REM
REM 使用方法：
REM   1. 以管理员身份运行此脚本
REM   2. 选择要配置的任务
REM
REM ============================================================

setlocal enabledelayedexpansion

set PROJECT_ROOT=C:\Users\jeremyko11\WorkBuddy\Claw
set PYTHON_EXE=python

echo.
echo ============================================================
echo   虚拟资料项目 — 定时任务配置
echo ============================================================
echo.
echo 请选择操作：
echo   [1] 配置每日早6点自动运行完整流水线
echo   [2] 配置每小时爬虫 + 早8点提炼分发
echo   [3] 查看当前已配置的任务
echo   [4] 删除所有已配置的任务
echo   [0] 退出
echo.

set /p choice=请输入选项 [1-4, 0退出]:

if "%choice%"=="1" goto FULL_PIPELINE
if "%choice%"=="2" goto HOURLY_CRAWL
if "%choice%"=="3" goto LIST_TASKS
if "%choice%"=="4" goto DELETE_TASKS
if "%choice%"=="0" goto END

:FULL_PIPELINE
echo.
echo [1] 配置每日完整流水线任务...
echo.

REM 检查是否已存在
schtasks /query /tn "VirtualInfo_DailyPipeline" >nul 2>&1
if %errorlevel%==0 (
    echo 任务已存在，跳过创建。
) else (
    schtasks /create /tn "VirtualInfo_DailyPipeline" ^
        /tr "cmd /c cd /d %PROJECT_ROOT% && %PYTHON_EXE% scripts\dispatcher\content_dispatcher.py --mode full" ^
        /sc daily /st 06:00 ^
        /f
    echo ✅ 任务创建成功！每天 06:00 自动运行完整流水线
)
goto END

:HOURLY_CRAWL
echo.
echo [2] 配置爬虫定时任务...
echo.

REM 每6小时爬虫任务
schtasks /create /tn "VirtualInfo_Crawler" ^
    /tr "cmd /c cd /d %PROJECT_ROOT% && %PYTHON_EXE% scripts\dispatcher\content_dispatcher.py --mode crawl" ^
    /sc hourly /mo 6 ^
    /f
echo ✅ 爬虫任务创建成功！每6小时自动爬取

REM 早8点提炼分发
schtasks /create /tn "VirtualInfo_RefineDispatch" ^
    /tr "cmd /c cd /d %PROJECT_ROOT% && %PYTHON_EXE% scripts\dispatcher\content_dispatcher.py --mode refine" ^
    /sc daily /st 08:00 ^
    /f
echo ✅ 提炼任务创建成功！每天 08:00 自动提炼

REM 早9点改写分发
schtasks /create /tn "VirtualInfo_RewriteDispatch" ^
    /tr "cmd /c cd /d %PROJECT_ROOT% && %PYTHON_EXE% scripts\dispatcher\content_dispatcher.py --mode rewrite" ^
    /sc daily /st 09:00 ^
    /f
echo ✅ 改写分发任务创建成功！每天 09:00 自动改写分发

goto END

:LIST_TASKS
echo.
echo [3] 当前已配置的定时任务：
echo.
schtasks /query /fo LIST | findstr /i "VirtualInfo"
echo.
goto END

:DELETE_TASKS
echo.
echo [4] 删除所有定时任务...
echo.

schtasks /delete /tn "VirtualInfo_DailyPipeline" /f >nul 2>&1
schtasks /delete /tn "VirtualInfo_Crawler" /f >nul 2>&1
schtasks /delete /tn "VirtualInfo_RefineDispatch" /f >nul 2>&1
schtasks /delete /tn "VirtualInfo_RewriteDispatch" /f >nul 2>&1

echo ✅ 所有任务已删除
goto END

:END
echo.
echo 操作完成！
echo.
pause