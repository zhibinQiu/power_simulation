@echo off
REM ============================================================
REM  工业能碳智控平台 - Windows exe 一键打包脚本
REM  位置：platform\windows-deploy\
REM  前提：已安装 Python 3.10+ 与 Node.js 18+（均已加入 PATH）
REM  用法：在 Windows 上双击运行本脚本（或在 cmd 中执行）
REM  产物：dist\SteelCarbonTwin\SteelCarbonTwin.exe（整个文件夹一起分发）
REM
REM  说明：
REM   - 本目录为 Windows 打包全部资源，自包含：build_windows.bat（打包脚本）、
REM     steelcarbon_twin.iss（安装包脚本）、icon.ico（图标）、icon.png（图标设计稿源）、
REM     desktop_launcher.py（打包入口）、build_icons.py（图标生成）；
REM   - --windowed 打包：双击 exe 直接显示客户端窗口，不再弹出控制台黑框；
REM   - pywebview 在 Windows 依赖 WebView2 + pythonnet(clr)，已一并收集；
REM   - 若目标机器窗口空白，请安装 WebView2 运行时（微软官网搜索 WebView2 Runtime）。
REM ============================================================
cd /d "%~dp0..\.."
setlocal

REM 强制所有 Python 输出使用 UTF-8，避免 GitHub Actions 控制台编码不支持中文报错
set PYTHONIOENCODING=utf-8
chcp 65001 >nul

echo [1/4] 安装 Python 依赖（pip + pyinstaller + pywebview + Pillow）...
python -m pip install --upgrade pip
python -m pip install -r backend\config\requirements.txt
python -m pip install pyinstaller pywebview Pillow
if errorlevel 1 goto :fail

echo [1.5/4] 生成 Windows 图标 (.ico)...
python platform\windows-deploy\build_icons.py
if errorlevel 1 goto :fail

echo [2/4] 构建前端静态资源...
cd frontend
call npm install
if errorlevel 1 goto :fail
call npm run build
if errorlevel 1 goto :fail
cd ..

echo [3/4] PyInstaller 打包（windowed，无控制台窗口）...
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name SteelCarbonTwin ^
  --icon "%CD%\platform\windows-deploy\icon.ico" ^
  --collect-all uvicorn --collect-all websockets ^
  --collect-all webview --collect-all pythonnet --hidden-import clr ^
  --add-data "%CD%\frontend\dist;frontend\dist" ^
  --paths backend ^
  --specpath platform\windows-deploy ^
  platform\windows-deploy\desktop_launcher.py
if errorlevel 1 goto :fail

echo [4/4] 完成！
echo   产物目录: %~dp0..\..\dist\SteelCarbonTwin\
echo   分发时请整体拷贝该文件夹，双击 SteelCarbonTwin.exe 即打开客户端窗口。
echo   排查：日志文件位于 %USERPROFILE%\.steel_carbon_twin\launcher.log
goto :eof

:fail
echo 打包失败，请检查上方错误信息。
exit /b 1
