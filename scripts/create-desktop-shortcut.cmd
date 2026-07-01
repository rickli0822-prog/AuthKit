@echo off
cd /d "%~dp0.."
python "%~dp0create_desktop_shortcut.py"
if errorlevel 1 pause
