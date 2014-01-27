@cd %~dp0
setup.py clean 
setup.py py2exe 
@xcopy dist\*.* .\bin /s /y /q
@cd .\bin
