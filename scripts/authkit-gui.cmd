@echo off

setlocal EnableExtensions

cd /d "%~dp0"

wscript.exe //nologo "%~dp0launch_gui.vbs"

exit /b %ERRORLEVEL%

