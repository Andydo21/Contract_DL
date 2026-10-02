@echo off
chcp 65001 >nul
title DENSO Plan A - Document Intelligence Starter
cd /d "%~dp0"

echo ====================================================================
echo   📑 DENSO PLAN A - DOCUMENT INTELLIGENCE (VISION & VECTOR)
echo   ColPali Visual Late Interaction + Qdrant Vector Engine + Neo4j
echo ====================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_project.ps1"

pause
