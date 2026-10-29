@echo off
rem Wrapper: runs lad-local.ps1 bypassing ExecutionPolicy for this one call only.
rem Usage from project root: .\local\lad-local.cmd up   (see local\README.md)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lad-local.ps1" %*
