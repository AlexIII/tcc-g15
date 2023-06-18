@echo off

echo Compiling Portable version...
pyinstaller --icon=icons/gaugeIcon.ico --add-data icons/gaugeIcon.png;icons -w -F -y tcc-g15.py || goto :error

echo Compiling version for installer...
pyinstaller --icon=icons/gaugeIcon.ico --add-data icons/gaugeIcon.png;icons -w -y tcc-g15.py || goto :error

echo Compiling installer...
"C:\Program Files (x86)\Inno Setup 6\iscc.exe" installer-inno-config.iss || goto :error



:error
echo Failed with error #%errorlevel%.
exit /b %errorlevel%
