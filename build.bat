@cd %~dp0
@del dist\*.* /s /Q
setup.py clean 
setup.py py2exe 
@xcopy dist\*.* .\bin /s /y /q
@cd .\bin