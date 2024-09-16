@echo off

echo Compiling Portable version...
pyinstaller --icon=icons/gaugeIcon.ico --add-data icons/gaugeIcon.png;icons --add-data tcc_g15_task.xml;. --hidden-import PySide6 --collect-all winrt -w -F -y src/tcc-g15.py || goto :error

echo Compiling version for installer...
pyinstaller --icon=icons/gaugeIcon.ico --add-data icons/gaugeIcon.png;icons --add-data tcc_g15_task.xml;. --hidden-import PySide6 --collect-all winrt -w -y src/tcc-g15.py || goto :error

echo Compiling installer...
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" installer-inno-config.iss || goto :error


exit /b 0
:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
