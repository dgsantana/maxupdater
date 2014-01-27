@C:\Python27\scripts\pyside-uic %~n1.ui -o %~n1_ui.py
echo %~n1.qrc
@"C:\Python27\Lib\site-packages\PySide\pyside-rcc" %~n1.qrc -o %~n1_rc.py