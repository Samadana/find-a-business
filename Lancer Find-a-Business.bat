@echo off
chcp 65001 >nul
title Find-a-Business
cd /d "%~dp0"

echo.
echo   ==============================
echo     Find-a-Business - tableau de bord
echo   ==============================
echo.

set "PY="
where py >nul 2>nul && py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul && set "PY=python"
)
if not defined PY (
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
)

if not defined PY (
  echo   Python n'est pas installe sur cet ordinateur.
  echo   Il est necessaire pour faire tourner l'application. Il est gratuit et officiel.
  echo.
  choice /c ON /m "  L'installer maintenant (environ 1 minute) ? O = oui, N = non"
  if errorlevel 2 goto :nopython
  echo.
  echo   Installation de Python en cours...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe""
  ) else (
    goto :nopython
  )
)

echo   Demarrage... Le tableau de bord va s'ouvrir dans ton navigateur.
echo   Laisse cette fenetre ouverte tant que tu utilises l'application.
echo   Pour arreter : ferme cette fenetre.
echo.
%PY% "%~dp0app\serveur.py"
echo.
echo   L'application s'est arretee.
pause
exit /b 0

:nopython
echo.
echo   Impossible d'installer Python automatiquement.
echo   Installe-le depuis https://www.python.org/downloads/ (coche "Add python.exe to PATH"),
echo   puis relance ce fichier.
start "" "https://www.python.org/downloads/"
pause
exit /b 1
