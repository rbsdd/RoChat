@echo off
chcp 65001 >nul
echo.
echo  ╔═══════════════════════════════════════════╗
echo  ║   🎮 RoChat — Сборка приложений (.exe)    ║
echo  ╚═══════════════════════════════════════════╝
echo.

python build.py %*

if %ERRORLEVEL% EQU 0 (
    echo.
    echo  Готово! Откройте папку dist\ для получения .exe файлов.
    echo.
    explorer dist
) else (
    echo.
    echo  Ошибка сборки. Проверьте вывод выше.
)

pause
