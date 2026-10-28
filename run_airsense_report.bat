@echo off
REM AirSense 10 complete report generator - Windows version
REM AirSense 10 完整报告生成器 - Windows 版
REM Double-click to run. Insert the SD card first.
REM 双击运行，使用前先插好 SD 卡。
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not in PATH. Please install Python 3.10+ from python.org and tick "Add python.exe to PATH".
  echo 未找到 Python，请先安装 Python 3.10 以上版本，安装时勾选 Add python.exe to PATH。
  pause
  exit /b 1
)
python generate_airsense_report.py
if errorlevel 1 (
  echo Failed. Check that the card is inserted, or run: python generate_airsense_report.py --sd D:
  echo 失败了，请确认卡已插好，或手动指定盘符，例如：python generate_airsense_report.py --sd D:
  pause
  exit /b 1
)
echo.
echo Report generated in output\airsense_report.html, opening...
echo 报告已生成在 output\airsense_report.html，正在打开……
start "" "output\airsense_report.html"
pause
