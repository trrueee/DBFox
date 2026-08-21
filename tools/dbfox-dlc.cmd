@echo off
pushd "%~dp0.."
python -m engine.dlc.cli %*
set DBFOX_DLC_EXIT=%ERRORLEVEL%
popd
exit /b %DBFOX_DLC_EXIT%
