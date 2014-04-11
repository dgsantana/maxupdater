@echo off
ping %1 -n 2 -w 200 | find "Lost = 0" >NUL
if %errorlevel%==0 (echo %1 is alive) ELSE goto END

echo Stoppping updater service on %1
sc \\%1 stop 3dsmaxupdatesvc >NUL
IF %errorlevel% NEQ 0 echo Error stopping service on %1 with error %errorlevel%
IF %errorlevel% == 1062 GOTO COPY_FILES
IF %errorlevel% == 0 GOTO COPY_FILES
taskkill /s \\%1 /f /im maxupdaterservice.exe /t >NUL
taskkill /s \\%1 /f /im updater_service.exe /t >NUL

echo Installing updater service on %1
echo Copying services files to %1
xcopy %~dp0*.* \\%1\c$\Tools\Updater\ /s /y /q
del \\%1\c$\Tools\Updater\debug*.log* /F /Q
del \\%1\c$\Tools\Updater\install_service.bat /F /Q
del \\%1\c$\Tools\Updater\update_tools.bat /F /Q
sc \\%1 delete 3dsmaxupdatesvc 
sc \\%1 create 3dsmaxupdatesvc binPath=c:\Tools\Updater\updater_service.exe start=auto obj="4ARQ\slaveuser" password="slaveuser"
if %errorlevel% NEQ 0 echo Error installing service on %1 with error %errorlevel%
echo Starting updater service on %1
sc \\%1 start 3dsmaxupdatesvc >NUL
if %errorlevel% NEQ 0 echo Error starting service on %1 with error %errorlevel%
GOTO end

:COPY_FILES
taskkill /s \\%1 /f /im maxupdaterservice.exe /t >NUL
taskkill /s \\%1 /f /im updater_service.exe /t >NUL
echo Copying services files to %1
del \\%1\c$\Tools\Updater\*.* /f /q /s >nul
xcopy %~dp0*.* \\%1\c$\Tools\Updater\ /s /y /q 
del \\%1\c$\Tools\Updater\debug*.log* /F /Q
del \\%1\c$\Tools\Updater\install_service.bat /F /Q
del \\%1\c$\Tools\Updater\update_tools.bat /F /Q
echo Starting updater service on %1
sc \\%1 delete 3dsmaxupdatesvc 
sc \\%1 create 3dsmaxupdatesvc binPath=c:\Tools\Updater\updater_service.exe start=auto obj="4ARQ\slaveuser" password="slaveuser"
sc \\%1 start 3dsmaxupdatesvc >NUL
if %errorlevel% NEQ 0 echo Error starting service on %1 with error %errorlevel%
IF %errorlevel% == 1063 GOTO RETRY
GOTO END
:RETRY
echo Workaround to bad services
taskkill /s \\%1 /f /im maxupdaterservice.exe /t >NUL;
taskkill /s \\%1 /f /im updater_service.exe /t >NUL
sc \\%1 delete 3dsmaxupdatesvc 
sc \\%1 create 3dsmaxupdatesvc binPath=c:\Tools\Updater\updater_service.exe start=auto obj="4ARQ\slaveuser" password="slaveuser"
sc \\%1 start 3dsmaxupdatesvc >NUL;
if %errorlevel% NEQ 0 (echo Error starting service on %1 with error %errorlevel%) ELSE (echo Workaround done.)
:END