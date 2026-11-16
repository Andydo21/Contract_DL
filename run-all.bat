@echo off
REM Bam dup de bat toan bo du an Contract Guard AI.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-all.ps1" %*
pause
