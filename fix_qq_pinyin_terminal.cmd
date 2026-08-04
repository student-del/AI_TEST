@echo off
chcp 65001 >nul
title 修复 QQ 拼音在 CMD / PowerShell 中不显示候选词

echo [1/3] 正在重启 Windows 文字输入服务...
taskkill /f /im ctfmon.exe >nul 2>&1
start "" "%WINDIR%\System32\ctfmon.exe"

echo [2/3] 正在启用新版 Windows 控制台宿主...
reg add "HKCU\Console" /v ForceV2 /t REG_DWORD /d 1 /f >nul
if errorlevel 1 (
    echo 写入控制台设置失败。请右键此脚本，选择“以管理员身份运行”。
    pause
    exit /b 1
)

echo [3/3] 检查 Windows Terminal...
where wt.exe >nul 2>&1
if errorlevel 1 (
    echo 未检测到 Windows Terminal，正在打开微软商店官方安装页...
    start "" "ms-windows-store://pdp/?ProductId=9N0DX20HK701"
) else (
    echo 已检测到 Windows Terminal，正在启动...
    start "" wt.exe
)

echo.
echo 修复设置已完成。请关闭所有旧的 CMD 和 PowerShell 窗口，然后重新打开测试。
pause
