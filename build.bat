@cd %~dp0
@RD dist /s /Q
@RD build /s /Q
setup.py clean 
setup.py py2exe 
@RD .\bin\lib /s /Q
@xcopy dist\*.* .\bin /s /y /q
@cd .\bin