@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw pet.py & exit /b)
where pythonw >nul 2>nul && (start "" pythonw pet.py & exit /b)
echo Python을 찾을 수 없습니다. Python 설치 후 다시 실행하세요.
pause
