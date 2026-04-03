@echo off
REM Push to GitHub - Run this after creating the repo on GitHub.com
REM
REM Steps:
REM 1. Go to https://github.com/new and create a new repo named "auto-assistance"
REM 2. Make sure it's EMPTY (don't initialize with README)
REM 3. Run this script

echo.
echo Pushing auto-assistance to GitHub...
echo.

REM Replace with your GitHub username
set GITHUB_USER=jeremyko11

REM Add remote and push
git remote add origin https://github.com/%GITHUB_USER%/auto-assistance.git
git branch -M main
git push -u origin main

echo.
echo Done! Your repo should be at: https://github.com/%GITHUB_USER%/auto-assistance
echo.
pause