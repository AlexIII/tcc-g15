import sys, os
from enum import Enum
from typing import Callable, Literal
from PySide6 import QtCore, QtGui, QtWidgets
from Backend.AWCCThermal import AWCCThermal, NoAWCCWMIClass, CannotInstAWCCWMI
from GUI.QRadioButtonSet import QRadioButtonSet
from GUI.AppColors import Colors
from GUI.ThermalUnitWidget import ThermalUnitWidget
from GUI.QGaugeTrayIcon import QGaugeTrayIcon

GUI_ICON = 'icons/gaugeIcon.png'

def resourcePath(relativePath: str = '.'):
    return os.path.join(sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath('.'), relativePath)

def alert(title: str, message: str, message2: str = None, type: QtWidgets.QMessageBox.Icon = QtWidgets.QMessageBox.Icon.Information) -> None:
        msg = QtWidgets.QMessageBox()
        msg.setWindowIcon(QtGui.QIcon(resourcePath(GUI_ICON)))
        msg.setIcon(type)
        msg.setWindowTitle(title)
        msg.setText(message)
        if message2: msg.setInformativeText(message2)
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg.exec()

class QPeriodic:
    def __init__(self, parent: QtCore.QObject, periodMs: int, callback: Callable) -> None:
        self._tmr = QtCore.QTimer(parent)
        self._tmr.setInterval(periodMs)
        self._tmr.setSingleShot(False)
        self._tmr.timeout.connect(callback)
    def start(self):
        self._tmr.start()
    def stop(self):
        self._tmr.stop()

class ThermalMode(Enum):
    Custom = 'Custom'
    Balanced = 'Balanced'
    G_Mode = 'G_Mode'
    
class SettingsKey(Enum):
    Mode = "app/mode"
    CPUFanSpeed = "app/fan/cpu/speed"
    GPUFanSpeed = "app/fan/gpu/speed"

def errorExit(message: str, message2: str = None) -> None:
    alert("Oh-oh", message, message2, QtWidgets.QMessageBox.Icon.Critical)
    sys.exit(1)

class TCC_GUI(QtWidgets.QWidget):
    TEMP_UPD_PERIOD_MS = 1000
    FAILSAFE_CPU_TEMP = 95
    FAILSAFE_GPU_TEMP = 85
    APP_NAME = "Thermal Control Center for Dell G15 5515"
    APP_VERSION = "1.2.0"
    APP_DESCRIPTION = "This app is an open-source replacement for Alienware Control Center "
    APP_URL = "github.com/AlexIII/tcc-g15"

    # Green to Yellow and Yellow to Red thresholds
    GPU_COLOR_LIMITS = (72, 85)
    CPU_COLOR_LIMITS = (85, 95)

    def __init__(self, awcc: AWCCThermal):
        super().__init__()
        self._awcc = awcc

        self.settings = QtCore.QSettings(self.APP_URL, "AWCC")

        # Set main window props
        self.setFixedSize(600, 0)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMinimizeButtonHint | QtCore.Qt.WindowCloseButtonHint)
        self.setWindowIcon(QtGui.QIcon(resourcePath(GUI_ICON)))
        self.mouseReleaseEvent = lambda evt: (
            evt.button() == QtCore.Qt.RightButton and
            alert("About", f"{self.APP_NAME} v{self.APP_VERSION}", f"{self.APP_DESCRIPTION}\n{self.APP_URL}")
        )

        # Set up tray icon
        trayIcon = QGaugeTrayIcon((self.GPU_COLOR_LIMITS, self.CPU_COLOR_LIMITS))
        menu = QtWidgets.QMenu()
        showAction = menu.addAction("Show")
        showAction.triggered.connect(self.showNormal)
        exitAction = menu.addAction("Exit")
        exitAction.triggered.connect(self.close)
        tray = QtWidgets.QSystemTrayIcon(self)
        tray.setIcon(trayIcon)
        tray.setContextMenu(menu)
        tray.show()

        def onTrayIconActivated(trigger):
            if trigger == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
                self.showNormal()
                self.activateWindow()
        self.connect(tray, QtCore.SIGNAL("activated(QSystemTrayIcon::ActivationReason)"), onTrayIconActivated)

        # Set up GUI
        self.setObjectName('QMainWindow')
        self.setWindowTitle(self.APP_NAME)

        self._thermalGPU = ThermalUnitWidget(self, 'GPU', tempMinMax= (0, 95), tempColorLimits= self.GPU_COLOR_LIMITS, fanMinMax= (0, 5500), sliderMaxAndTick= (120, 20))
        self._thermalCPU = ThermalUnitWidget(self, 'CPU', tempMinMax= (0, 110), tempColorLimits= self.CPU_COLOR_LIMITS, fanMinMax= (0, 5500), sliderMaxAndTick= (120, 20))

        lTherm = QtWidgets.QHBoxLayout()
        lTherm.addWidget(self._thermalGPU)
        lTherm.addWidget(self._thermalCPU)

        self._modeSwitch = QRadioButtonSet(None, None, [
            ('Balanced', ThermalMode.Balanced.value),
            ('G mode', ThermalMode.G_Mode.value),
            ('Custom', ThermalMode.Custom.value)
        ])

        self._failsafeCB = QtWidgets.QCheckBox("Fail-safe")
        self._failsafeCB.setToolTip(f"Switch to G-mode (fans on max) when GPU temp reaches {self.FAILSAFE_GPU_TEMP}°C or CPU reaches {self.FAILSAFE_CPU_TEMP}°C")
        self._failsafeOn = True
        def onFailsafeCB():
            self._failsafeOn = self._failsafeCB.isChecked()
        self._failsafeCB.toggled.connect(onFailsafeCB)
        self._failsafeCB.setChecked(True)

        modeBox = QtWidgets.QHBoxLayout()
        modeBox.addWidget(self._modeSwitch, alignment= QtCore.Qt.AlignLeft)
        modeBox.addWidget(self._failsafeCB, alignment= QtCore.Qt.AlignRight)

        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.addLayout(lTherm)
        mainLayout.addLayout(modeBox)
        mainLayout.setAlignment(QtCore.Qt.AlignTop)
        mainLayout.setContentsMargins(10, 0, 10, 0)

        # Glue GUI to backend
        def setFanSpeed(fan: Literal['GPU', 'CPU'], speed: int):
            res = self._awcc.setFanSpeed(self._awcc.GPUFanIdx if fan == 'GPU' else self._awcc.CPUFanIdx, speed)
            print(f'Set {fan} fan speed to {speed}: ' + ('ok' if res else 'fail'))

        def updateFanSpeed():
            if self._modeSwitch.getChecked() != ThermalMode.Custom.value:
                return
            setFanSpeed('GPU', self._thermalGPU.getSpeedSlider())
            setFanSpeed('CPU', self._thermalCPU.getSpeedSlider())

        def onModeChange(val: str):
            self._thermalGPU.setSpeedDisabled(val != ThermalMode.Custom.value)
            self._thermalCPU.setSpeedDisabled(val != ThermalMode.Custom.value)
            res = self._awcc.setMode(self._awcc.Mode[val])
            print(f'Set mode {val}: ' + ('ok' if res else 'fail'))
            if not res:
                errorExit(f"Failed to set mode {val}", "Program is terminated")
            updateFanSpeed()

        self._modeSwitch.setChecked(ThermalMode.Balanced.value)
        onModeChange(ThermalMode.Balanced.value)
        self._modeSwitch.setOnChange(onModeChange)

        def updateOutput():
            gpuTemp = self._awcc.getFanRelatedTemp(self._awcc.GPUFanIdx)
            gpuRPM = self._awcc.getFanRPM(self._awcc.GPUFanIdx)
            cpuTemp = self._awcc.getFanRelatedTemp(self._awcc.CPUFanIdx)
            cpuRPM = self._awcc.getFanRPM(self._awcc.CPUFanIdx)
            if gpuTemp is not None: self._thermalGPU.setTemp(gpuTemp)
            if gpuRPM is not None: self._thermalGPU.setFanRPM(gpuRPM)
            if cpuTemp is not None: self._thermalCPU.setTemp(cpuTemp)
            if cpuRPM is not None: self._thermalCPU.setFanRPM(cpuRPM)
            # print(gpuTemp, gpuRPM, cpuTemp, cpuRPM)

            # Handle fail-safe
            if self._failsafeOn and self._modeSwitch.getChecked() != ThermalMode.G_Mode.value and (
                (gpuTemp is None) or
                (gpuTemp >= self.FAILSAFE_GPU_TEMP) or
                (cpuTemp is None) or
                (cpuTemp >= self.FAILSAFE_CPU_TEMP)
            ): 
                self._modeSwitch.setChecked(ThermalMode.G_Mode.value)
                print('Fail-safe tripped!')

            # Update tray icon
            trayIcon.update((gpuTemp, cpuTemp))
            tray.setIcon(trayIcon)
            
        self._updateGaugesTask = QPeriodic(self, self.TEMP_UPD_PERIOD_MS, updateOutput)
        updateOutput()
        self._updateGaugesTask.start()
        
        self._thermalGPU.speedSliderChanged(updateFanSpeed)
        self._thermalCPU.speedSliderChanged(updateFanSpeed)

        # Restore saved settings
        savedMode = self.settings.value(SettingsKey.Mode.value)
        if savedMode: self._modeSwitch.setChecked(savedMode)
        savedSpeed = self.settings.value(SettingsKey.CPUFanSpeed.value)
        self._thermalCPU.setSpeedSlider(savedSpeed)
        savedSpeed = self.settings.value(SettingsKey.GPUFanSpeed.value)
        self._thermalGPU.setSpeedSlider(savedSpeed)

    def closeEvent(self, event):
        # Save settings
        self.settings.setValue(SettingsKey.Mode.value, self._modeSwitch.getChecked())
        self.settings.setValue(SettingsKey.CPUFanSpeed.value, self._thermalCPU.getSpeedSlider())
        self.settings.setValue(SettingsKey.GPUFanSpeed.value, self._thermalGPU.getSpeedSlider())
        # Set mode to Balanced before exit
        self._updateGaugesTask.stop()
        prevMode = self._modeSwitch.getChecked()
        self._modeSwitch.setChecked(ThermalMode.Balanced.value)
        if prevMode != ThermalMode.Balanced.value:
            alert("Mode changed", "Thermal mode has been reset to Balanced")
        event.accept()

    def changeEvent(self, event):
        # Intercept minimize event, hide window instead
        if event.type() == QtCore.QEvent.WindowStateChange and self.windowState() & QtCore.Qt.WindowMinimized:
            event.ignore()
            self.hide()
            return
        super().changeEvent(event)

    def testWMIsupport(self):
        try:
            pass
        except: 
            pass

def runApp() -> int:
    app = QtWidgets.QApplication([])

    # Setup backend
    try:
        awcc = AWCCThermal()
    except NoAWCCWMIClass:
        errorExit("AWCC WMI class not found in the system.", "You don't have some drivers installed or your system is not supported.")
    except CannotInstAWCCWMI:
        errorExit("Couldn't instantiate AWCC WMI class.", "Make sure you're running as Admin.")

    mainWindow = TCC_GUI(awcc)
    mainWindow.setStyleSheet(f"""
        QGauge {{
            border: 1px solid gray;
            border-radius: 3px;
            background-color: {Colors.GREY.value};
        }}
        QGauge::chunk {{
            background-color: {Colors.BLUE.value};
        }}
        * {{
            color: {Colors.WHITE.value};
            background-color: {Colors.DARK_GREY.value};
        }}
        QToolTip {{
            background-color: black; 
            color: {Colors.WHITE.value};
            border: black solid 1px
        }}
    """)

    mainWindow.show()
    return app.exec()