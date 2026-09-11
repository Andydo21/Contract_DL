@echo off
chcp 65001 >nul
title DENSO Factory Intelligence - Starter
cd /d "%~dp0"

echo ====================================================================
echo   🏭 DENSO FACTORY INTELLIGENCE SYSTEM - KHỞI ĐỘNG HỆ THỐNG
echo   Hybrid RAG: Qdrant Vector DB + Neo4j Graph + Multilingual BGE
echo ====================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_project.ps1"

pause
