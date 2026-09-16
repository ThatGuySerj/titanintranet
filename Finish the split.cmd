@echo off
rem ---------------------------------------------------------------------------
rem  Removes the files the intranet left behind in the ticket repository, and
rem  the duplicates it left here.
rem
rem  The intranet was part of the ticket site for a fortnight. This deletes that
rem  version of it. Run it ONCE, from this folder, after the new site is up and
rem  answering on intranet.tetransports.com - not before, because until then the
rem  old one is the one people are using.
rem ---------------------------------------------------------------------------
setlocal
set "TIX=%USERPROFILE%\OneDrive - tetransports.com\Desktop\Ticket Import Review"

echo.
echo   This will delete:
echo.
echo     From the ticket repository
echo       webapp\intranet\                    the page, config and logos
echo       webapp\intranet_access.py           permissions
echo       webapp\test_intranet_access.py
echo       webapp\orientation.py               packet printing
echo       webapp\test_orientation.py
echo       webapp\Intranet permissions - walkthrough.md
echo       webapp\Orientation printing - walkthrough.md
echo       .github\workflows\main_titanintranet.yml
echo       Publish Intranet.cmd                no longer needed - one copy now
echo.
echo     From this folder
echo       Titan_Enterprises_Intranet_Homepage.html   moved to site\index.html
echo       config.json                                moved to site\config.json
echo       images\                                    moved to site\images\
echo       staticwebapp.config.json                   was for a hosting route
echo                                                  that never got used
echo       _auth_core.py                              scratch from the split
echo.
set /p GO="  Type YES to go ahead: "
if /i not "%GO%"=="YES" (echo   Nothing was deleted. & pause & exit /b 0)

echo.
echo   Ticket repository...
pushd "%TIX%" 2>nul || (echo   Could not find %TIX% & pause & exit /b 1)

rem Some of these were committed and some never were. `git rm` only removes
rem what git is tracking and skips the rest without a word, so anything still
rem untracked is deleted from disk afterwards. Doing only the first would have
rem left half of it sitting there looking deployed.
git rm -r --quiet --ignore-unmatch "webapp/intranet"
git rm --quiet --ignore-unmatch "webapp/intranet_access.py" "webapp/test_intranet_access.py"
git rm --quiet --ignore-unmatch "webapp/orientation.py" "webapp/test_orientation.py"
git rm --quiet --ignore-unmatch "webapp/Intranet permissions - walkthrough.md"
git rm --quiet --ignore-unmatch "webapp/Orientation printing - walkthrough.md"
git rm --quiet --ignore-unmatch ".github/workflows/main_titanintranet.yml"
git rm --quiet --ignore-unmatch "Publish Intranet.cmd"

rem whatever git was not tracking
if exist "webapp\intranet"   rmdir /s /q "webapp\intranet"
del /q "webapp\intranet_access.py" 2>nul
del /q "webapp\test_intranet_access.py" 2>nul
del /q "webapp\orientation.py" 2>nul
del /q "webapp\test_orientation.py" 2>nul
del /q "webapp\Intranet permissions - walkthrough.md" 2>nul
del /q "webapp\Orientation printing - walkthrough.md" 2>nul
del /q ".github\workflows\main_titanintranet.yml" 2>nul
del /q "Publish Intranet.cmd" 2>nul
popd

echo   This folder...
del /q "Titan_Enterprises_Intranet_Homepage.html" 2>nul
del /q "config.json" 2>nul
del /q "staticwebapp.config.json" 2>nul
del /q "_auth_core.py" 2>nul
rmdir /s /q "images" 2>nul

echo.
echo   Done. Two things left, both by hand:
echo.
echo     1. In the ticket repository:  git commit -m "Intranet moved to its own repo"
echo                                   git push
echo     2. Here: make this folder a git repo if it is not one yet, and push it
echo        to a new GitHub repository called titan-intranet.
echo.
pause
