@echo off
call %~dp0..\build.bat
set slave_list=(4arq-10 4arq-12 4arq-14 4arq-15 4arq-16 4arq-18 4arq-19 4arq-20 4arq-21 4arq-mob05)
for %%i in %slave_list% do (
call %~dp0install_service.bat %%i
)
pause