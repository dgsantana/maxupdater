@echo off
set slave_list=(4arq-10 4arq-12 4arq-14 4arq-15 4arq-16 4arq-18 4arq-mob05 4arq-slave13 4arq-slave14 4arq-19 4arq-20)
for %%i in %slave_list% do (
call %~dp0install_service.bat %%i
)
pause