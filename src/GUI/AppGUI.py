import sys, os, time, datetime
import json
import urllib.request
import threading
from enum import Enum
from typing import Callable, Literal, Optional, Tuple, List
from PySide6 import QtCore, QtGui, QtWidgets
from windows_toasts import WindowsToaster, Toast, ToastDuration, ToastDisplayImage
from Backend.AWCCThermal import AWCCThermal, NoAWCCWMIClass, CannotInstAWCCWMI
from GUI.QRadioButtonSet import QRadioButtonSet
from GUI.AppColors import Colors
from GUI.ThermalUnitWidget import ThermalUnitWidget
from GUI.QGaugeTrayIcon import QGaugeTrayIcon
from GUI import HotKey
from Backend.DetectHardware import DetectHardware
from Web.WebBridge import WebBridge
from Web.WebServer import ThreadedHTTPServer
from GUI.Settings import SettingsKey, WEBHOOK_DEFAULTS, WEB_DEFAULTS, setting_bool, setting_str, setting_int, setting_float
from GUI.WebDialogs import WebhookDialog, WebServerDialog, _replace_webhook_variables


GUI_ICON = 'icons/gaugeIcon.png'

def resourcePath(relativePath: str = '.'):
    return os.path.join(sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath('.'), relativePath)

def autorunTask(action: Literal['add', 'remove']) -> int:
    taskXmlFilePath = resourcePath("tcc_g15_task.xml")

    addCmd = f'schtasks /create /xml "{taskXmlFilePath}" /tn "TCC_G15"'
    removeCmd = 'schtasks /delete /tn "TCC_G15" /f'

    if action == 'add':
        # Patch program path in the xml file
        exeFile = os.path.abspath(sys.argv[0])
        if exeFile.endswith('.exe'):
            with open(taskXmlFilePath, 'r') as f:
                xml = f.read()
            xml = xml.replace('<!--EXE_FILE_PATH-->', exeFile)
            with open(taskXmlFilePath, 'w') as f:
                f.write(xml)
        else:
            return -100

        os.system(removeCmd)
        return os.system(addCmd)
    else:
        return os.system(removeCmd)

def alert(title: str, message: str, type: QtWidgets.QMessageBox.Icon = QtWidgets.QMessageBox.Icon.Information, *, message2: Optional[str] = None) -> None:
    msg = QtWidgets.QMessageBox(type, title, message)
    msg.setWindowIcon(QtGui.QIcon(resourcePath(GUI_ICON)))
    if message2: msg.setInformativeText(message2)
    msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
    msg.exec()

def confirm(title: str, message: str, options: Optional[Tuple[str, str]] = None, dontAskAgain: bool = False) -> Tuple[bool, Optional[bool]]:
    msg = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Question, title, message, QtWidgets.QMessageBox.Yes |  QtWidgets.QMessageBox.No)
    msg.setWindowIcon(QtGui.QIcon(resourcePath(GUI_ICON)))

    if options is not None:
        msg.button(QtWidgets.QMessageBox.Yes).setText(options[0])
        msg.button(QtWidgets.QMessageBox.No).setText(options[1])

    cbDontAskAgain = None
    if dontAskAgain:
        cbDontAskAgain = QtWidgets.QCheckBox('Don\'t ask me again.', msg)
        msg.setCheckBox(cbDontAskAgain)

    return (msg.exec_() == QtWidgets.QMessageBox.Yes, cbDontAskAgain is not None and cbDontAskAgain.isChecked() or None)


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
    Balanced = 'Balanced'
    G_Mode = 'G_Mode'
    Custom = 'Custom'

def errorExit(message: str, message2: Optional[str] = None) -> None:
    if not QtWidgets.QApplication.instance():
         QtWidgets.QApplication([])
    alert("Oh-oh", message, QtWidgets.QMessageBox.Icon.Critical, message2 = message2)
    sys.exit(1)


class TCC_GUI(QtWidgets.QWidget):
    TEMP_UPD_PERIOD_MS = 1000
    FAILSAFE_CPU_TEMP = 95
    FAILSAFE_GPU_TEMP = 85
    FAILSAFE_TRIGGER_DELAY_SEC = 8
    FAILSAFE_RESET_AFTER_TEMP_IS_OK_FOR_SEC = 60
    APP_NAME = "Thermal Control Center for Dell G15"
    APP_VERSION = "1.6.5"
    APP_DESCRIPTION = "This app is an open-source replacement for Alienware Control Center "
    APP_URL = "github.com/AlexIII/tcc-g15"

    # Green to Yellow and Yellow to Red thresholds
    GPU_COLOR_LIMITS = (72, 85)
    CPU_COLOR_LIMITS = (85, 95)

    # private
    _failsafeTempIsHighTs = 0                           # Last time when the temp was registered to be high
    _failsafeTempIsHighStartTs: Optional[int] = None    # Time when the temp first registered to be high (without going lower than the threshold)
    _failsafeTrippedPrevModeStr: Optional[str] = None   # Mode (Custom, Balanced) before fail-safe tripped, as a string
    _failsafeOn = True

    _gModeKeySignal = QtCore.Signal()
    _gModeKeyPrevModeStr: Optional[str] = None

    _toaster = WindowsToaster(APP_NAME)

    _modeSwitch: QRadioButtonSet

    def __init__(self, awcc: AWCCThermal):
        super().__init__()
        self._awcc = awcc

        # Initialize mutable instance attributes (previously class-level mutable defaults)
        self._prevSavedSettingsValues: list = []
        self._webhookEnabled = WEBHOOK_DEFAULTS["enabled"]
        self._webhookUrl = WEBHOOK_DEFAULTS["url"]
        self._webhookBody = WEBHOOK_DEFAULTS["body"]
        self._webhookGpuRpmThreshold = WEBHOOK_DEFAULTS["gpu_rpm_threshold"]
        self._webhookCpuRpmThreshold = WEBHOOK_DEFAULTS["cpu_rpm_threshold"]
        self._webhookWindowSize = WEBHOOK_DEFAULTS["window_size"]
        self._webhookSigma = WEBHOOK_DEFAULTS["sigma"]
        self._webhookBaseInterval = WEBHOOK_DEFAULTS["base_interval"]
        self._webhookMaxInterval = WEBHOOK_DEFAULTS["max_interval"]
        self._webhookCooldownAfterReset = WEBHOOK_DEFAULTS["cooldown_after_reset"]
        self._webhookFilterBalanced = WEBHOOK_DEFAULTS["filter_balanced"]
        self._webhookFilterGMode = WEBHOOK_DEFAULTS["filter_gmode"]
        self._webhookFilterCustom = WEBHOOK_DEFAULTS["filter_custom"]
        self._webhookGpuHistory: list = []
        self._webhookCpuHistory: list = []
        self._webhookLastSendTime = 0
        self._webhookConsecutiveAlerts = 0
        self._webhookIsInAlertState = False
        self._webhookLastAlertStateChange = 0
        self._webhookLastTriggerTime = 0
        self._webhookAlertCount = 0
        self._webhookLock = threading.Lock()

        self.settings = QtCore.QSettings(self.APP_URL, "AWCC")
        print(f'Settings location: {self.settings.fileName()}')

        # Set main window props
        self.setFixedSize(600, 0)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowMinimizeButtonHint | QtCore.Qt.WindowCloseButtonHint)
        self.setWindowIcon(QtGui.QIcon(resourcePath(GUI_ICON)))
        self.mouseReleaseEvent = lambda evt: (
            evt.button() == QtCore.Qt.RightButton and
            alert("About", f"{self.APP_NAME} v{self.APP_VERSION}", message2 = f"{self.APP_DESCRIPTION}\n{self.APP_URL}")
        )

        # Set up tray icon
        self.trayIcon = QGaugeTrayIcon((self.GPU_COLOR_LIMITS, self.CPU_COLOR_LIMITS))
        menu = QtWidgets.QMenu()
        # Mode switch
        menu.addSection("Mode")
        self._trayMenuModeSwitch = {} # Dict[ThermalMode, QtWidgets.QAction]
        for m in ThermalMode:
            modeAction = menu.addAction("-")
            modeAction.triggered.connect(lambda _, m_value=m.value: self._modeSwitch.setChecked(m_value))
            self._trayMenuModeSwitch[m.value] = modeAction
        # Settings
        menu.addSection("Settings")
        showAction = menu.addAction("Show")
        showAction.triggered.connect(self.showNormal)
        addToAutorunAction = menu.addAction("Enable autorun")
        def autorunTaskRun(action: Literal['add', 'remove']) -> None:
            err = autorunTask(action)
            if err != 0 and action == 'add':
                alert("Error", f"Failed to {action} autorun task. Error={err}", QtWidgets.QMessageBox.Icon.Critical)
            else:
                alert("Success", f"Autorun on system startup {'Enabled' if action == 'add' else 'Disabled'}")
            # When in minimized state, a wired bug causes the app to close if we won't touch some of the `self.show*()` methods
            if self.isMinimized():
                self.showMinimized()
                self.hide()
        addToAutorunAction.triggered.connect(lambda: autorunTaskRun('add'))
        removeFromAutorunAction = menu.addAction("Disable autorun")
        removeFromAutorunAction.triggered.connect(lambda: autorunTaskRun('remove'))
        restoreAction = menu.addAction("Restore Default")
        restoreAction.triggered.connect(self.clearAppSettings)
        # Setup tray widget
        tray = QtWidgets.QSystemTrayIcon(self)
        tray.setIcon(self.trayIcon)
        tray.setContextMenu(menu)
        tray.show()

        def onTrayIconActivated(trigger):
            if trigger == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick:
                self.showNormal()
                self.activateWindow()
        self.connect(tray, QtCore.SIGNAL("activated(QSystemTrayIcon::ActivationReason)"), onTrayIconActivated)
        self._tray = tray

        # --- Web Server ---
        # Load web server config from QSettings
        self._webConfig = {
            "web_enabled": setting_bool(self.settings, SettingsKey.WebEnabled.value, WEB_DEFAULTS["web_enabled"]),
            "web_port": setting_int(self.settings, SettingsKey.WebPort.value, WEB_DEFAULTS["web_port"]),
            "bind_addr": setting_str(self.settings, SettingsKey.WebBindAddr.value, WEB_DEFAULTS["bind_addr"]),
            "auth_enabled": setting_bool(self.settings, SettingsKey.WebAuthEnabled.value, WEB_DEFAULTS["auth_enabled"]),
            "auth_user": setting_str(self.settings, SettingsKey.WebAuthUser.value, WEB_DEFAULTS["auth_user"]),
            "auth_pass": setting_str(self.settings, SettingsKey.WebAuthPass.value, WEB_DEFAULTS["auth_pass"]),
        }

        self._webBridge = WebBridge(self)
        self._webServer: Optional[ThreadedHTTPServer] = None
        self._webPort = self._webConfig["web_port"]

        # Web Server 单行（状态显示 + 点击进入设置）
        self._webServerAction = menu.addAction("  Web Server: Disabled")
        self._webServerAction.triggered.connect(self._showWebServerSettings)

        # --- Webhook Alert ---
        self._webhookAction = menu.addAction("  Webhook: Disabled")
        self._webhookAction.triggered.connect(self._showWebhookSettings)

        # Exit at the bottom
        menu.addSeparator()
        exitAction = menu.addAction("Exit")
        exitAction.triggered.connect(self.onExit)

        if self._webConfig["web_enabled"]:
            self._startWebServer()

        # Set up GUI
        self.setObjectName('QMainWindow')
        self.setWindowTitle(self.APP_NAME)

        self._thermalGPU = ThermalUnitWidget(self, tempMinMax= (0, 95), tempColorLimits= self.GPU_COLOR_LIMITS, fanMinMax= (0, 5500), sliderMaxAndTick= (120, 20))
        self._thermalGPU.setTitle('GPU')
        self._thermalCPU = ThermalUnitWidget(self, tempMinMax= (0, 110), tempColorLimits= self.CPU_COLOR_LIMITS, fanMinMax= (0, 5500), sliderMaxAndTick= (120, 20))
        self._thermalCPU.setTitle('CPU')

        # Detecting GPU/CPU model is a slow operation, run asynchronously
        class DetectCpuGpuModelsWorker(QtCore.QObject):
            finished = QtCore.Signal(str, str)
            def __init__(self, parent: QtCore.QObject, on_result: Callable[[Optional[str], Optional[str]], None]) -> None:
                super().__init__()
                self._t = QtCore.QThread(parent)
                self.moveToThread(self._t)
                self.finished.connect(self._t.quit)
                self.finished.connect(on_result)
                self._t.started.connect(self._task)
                self._t.start()
            def _task(self):
                print("DetectCpuGpuModelsWorker: started")
                d = DetectHardware()
                gpuModel = d.getHardwareName(d.GPUFanIdx)
                cpuModel = d.getHardwareName(d.CPUFanIdx)
                print(f"DetectCpuGpuModelsWorker: finished: {gpuModel}, {cpuModel}")
                self.finished.emit(gpuModel, cpuModel)
            def start(self):
                self._t.start()
        detect = DetectCpuGpuModelsWorker(self, self.updateGaugeTitles)
        detect.start()

        lTherm = QtWidgets.QHBoxLayout()
        lTherm.addWidget(self._thermalGPU)
        lTherm.addWidget(self._thermalCPU)

        self._modeSwitch = QRadioButtonSet(None, None, list(map(lambda m: (m.name.replace('_', ' '), m.value), ThermalMode)))

        # Fail-safe indicator
        failsafeIndicator = QtWidgets.QLabel()
        def updFailsafeIndicator() -> None:
            color = Colors.GREEN.value if self._failsafeOn else Colors.DARK_GREY.value
            msg = "Normal"
            if self._failsafeTempIsHighTs > 0: # Fail-safe have tripped at some point in the past
                color = Colors.YELLOW.value
                timeStr = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self._failsafeTempIsHighTs))
                msg = f"Last high temp at {timeStr}"
                if self._failsafeTrippedPrevModeStr is not None: # Fail-safe is in tripped state now
                    color = Colors.RED.value

            failsafeIndicator.setStyleSheet(f"QLabel {{ min-height: 14px; min-width: 14px; max-height: 14px; max-width: 14px; border: 1px solid {Colors.GREY.value}; border-radius: 7px; background: {color}; }}")
            failsafeIndicator.setToolTip(msg)
        updFailsafeIndicator()

        # Fail-safe temp limits
        self._limitTempGPU = QtWidgets.QComboBox()
        self._limitTempGPU.addItems(list(map(lambda v: str(v), range(50, 91))))
        self._limitTempGPU.setToolTip("Threshold GPU temp")
        self._limitTempCPU = QtWidgets.QComboBox()
        self._limitTempCPU.addItems(list(map(lambda v: str(v), range(50, 101))))
        self._limitTempCPU.setToolTip("Threshold CPU temp")
        def onLimitGPUChange():
            val = self._limitTempGPU.currentText()
            if val.isdigit(): self.FAILSAFE_GPU_TEMP = int(val)
        self._limitTempGPU.currentIndexChanged.connect(onLimitGPUChange)
        def onLimitCPUChange():
            val = self._limitTempCPU.currentText()
            if val.isdigit(): self.FAILSAFE_CPU_TEMP = int(val)
        self._limitTempCPU.currentIndexChanged.connect(onLimitCPUChange)

        # Fail-safe checkbox
        self._failsafeCB = QtWidgets.QCheckBox("Fail-safe")
        self._failsafeCB.setToolTip(f"Switch to G-mode (fans on max) when GPU temp reaches {self.FAILSAFE_GPU_TEMP}°C or CPU reaches {self.FAILSAFE_CPU_TEMP}°C")
        def onFailsafeCB():
            self._failsafeOn = self._failsafeCB.isChecked()
            self._failsafeTempIsHighTs = 0
            self._failsafeTrippedPrevModeStr = None
            self._failsafeTempIsHighStartTs = None
            updFailsafeIndicator()
        self._failsafeCB.toggled.connect(onFailsafeCB)
        self._failsafeCB.setChecked(self._failsafeOn)

        failsafeBox = QtWidgets.QHBoxLayout()
        failsafeBox.addWidget(self._failsafeCB)
        failsafeBox.addWidget(self._limitTempGPU)
        failsafeBox.addWidget(self._limitTempCPU)
        failsafeBox.addWidget(failsafeIndicator)

        modeBox = QtWidgets.QHBoxLayout()
        modeBox.addWidget(self._modeSwitch, alignment= QtCore.Qt.AlignLeft)
        modeBox.addWidget(QtWidgets.QWidget(), alignment= QtCore.Qt.AlignRight) # Insert dummy Widget in order to move the following 'failsafeBox' to the right side
        modeBox.addLayout(failsafeBox)

        mainLayout = QtWidgets.QVBoxLayout(self)
        mainLayout.addLayout(lTherm)
        mainLayout.addLayout(modeBox)
        mainLayout.setAlignment(QtCore.Qt.AlignTop)
        mainLayout.setContentsMargins(10, 0, 10, 0)

        # Glue GUI to backend
        self.gModeHotKey = None
        self._updateGaugesTask = None

        def setFanSpeed(fan: Literal['GPU', 'CPU'], speed: int) -> None:
            res = self._awcc.setFanSpeed(self._awcc.GPUFanIdx if fan == 'GPU' else self._awcc.CPUFanIdx, speed)
            print(f'Set {fan} fan speed to {speed}: ' + ('ok' if res else 'fail'))

        def updateFanSpeed():
            if self._modeSwitch.getChecked() != ThermalMode.Custom.value:
                return
            setFanSpeed('GPU', self._thermalGPU.getSpeedSlider())
            setFanSpeed('CPU', self._thermalCPU.getSpeedSlider())
        self._thermalGPU.speedSliderChanged(updateFanSpeed)
        self._thermalCPU.speedSliderChanged(updateFanSpeed)

        def _handleWebCmd(cmd, *args):
            if cmd == "mode":
                onModeChange(args[0])
                self._modeSwitch.setChecked(args[0])
            elif cmd == "fan":
                gpuSpeed, cpuSpeed = args
                self._thermalGPU.setSpeedSlider(gpuSpeed)
                self._thermalCPU.setSpeedSlider(cpuSpeed)
                updateFanSpeed()
        self._handleWebCmd = _handleWebCmd
        self._webBridge.commandQueued.connect(lambda: self._webBridge.processCommands(self._handleWebCmd))

        def onModeChange(val: str):
            self._thermalGPU.setSpeedDisabled(val != ThermalMode.Custom.value)
            self._thermalCPU.setSpeedDisabled(val != ThermalMode.Custom.value)
            res = self._awcc.setMode(self._awcc.Mode[val])
            print(f'Set mode {val}: ' + ('ok' if res else 'fail'))
            if not res:
                self._errorExit(f"Failed to set mode {val}", "Program is terminated")
            updateFanSpeed()
            if val != ThermalMode.G_Mode.value:
                self._failsafeTrippedPrevModeStr = None # In case the mode was switched manually
            updFailsafeIndicator()
            for m in ThermalMode:
                self._trayMenuModeSwitch[m.value].setText(f"{'•' if m.value == val else ' '} {m.name.replace('_', ' ')}")

        self._modeSwitch.setChecked(ThermalMode.Balanced.value)
        onModeChange(ThermalMode.Balanced.value)
        self._modeSwitch.setOnChange(onModeChange)

        def updateAppState():
            # Get temps and RPMs
            gpuTemp = self._awcc.getFanRelatedTemp(self._awcc.GPUFanIdx)
            gpuRPM = self._awcc.getFanRPM(self._awcc.GPUFanIdx)
            cpuTemp = self._awcc.getFanRelatedTemp(self._awcc.CPUFanIdx)
            cpuRPM = self._awcc.getFanRPM(self._awcc.CPUFanIdx)
            # Update UI gauges
            if gpuTemp is not None: self._thermalGPU.setTemp(gpuTemp)
            if gpuRPM is not None: self._thermalGPU.setFanRPM(gpuRPM)
            if cpuTemp is not None: self._thermalCPU.setTemp(cpuTemp)
            if cpuRPM is not None: self._thermalCPU.setFanRPM(cpuRPM)
            # print(gpuTemp, gpuRPM, cpuTemp, cpuRPM)

            # Handle fail-safe
            tempIsHigh = (
                (gpuTemp is None) or (gpuTemp >= self.FAILSAFE_GPU_TEMP) or
                (cpuTemp is None) or (cpuTemp >= self.FAILSAFE_CPU_TEMP)
            )

            if tempIsHigh:
                self._failsafeTempIsHighTs = time.time()

            self._failsafeTempIsHighStartTs = (self._failsafeTempIsHighStartTs or time.time()) if tempIsHigh else None

            # Trip fail-safe
            if (self._failsafeOn and
                self._modeSwitch.getChecked() != ThermalMode.G_Mode.value and
                tempIsHigh and
                time.time() - self._failsafeTempIsHighStartTs > self.FAILSAFE_TRIGGER_DELAY_SEC
            ):
                self._failsafeTrippedPrevModeStr = self._modeSwitch.getChecked()
                self._modeSwitch.setChecked(ThermalMode.G_Mode.value)
                self._toasterMessageCurrentMode(source='failsafe')
                print(f'Fail-safe tripped at GPU={gpuTemp} CPU={cpuTemp}')

            # Auto-reset failsafe
            if (self._failsafeTrippedPrevModeStr is not None and
                time.time() - self._failsafeTempIsHighTs > self.FAILSAFE_RESET_AFTER_TEMP_IS_OK_FOR_SEC
            ):
                self._modeSwitch.setChecked(self._failsafeTrippedPrevModeStr)
                self._toasterMessageCurrentMode(source='failsafe')
                self._failsafeTrippedPrevModeStr = None
                print('Fail-safe reset')

            # Handle fan RPM webhook alert
            if self._webhookEnabled and self._webhookUrl:
                # 检查当前模式是否在过滤列表中
                currentMode = self._modeSwitch.getChecked()
                modeAllowed = (
                    (currentMode == ThermalMode.Balanced.value and self._webhookFilterBalanced) or
                    (currentMode == ThermalMode.G_Mode.value and self._webhookFilterGMode) or
                    (currentMode == ThermalMode.Custom.value and self._webhookFilterCustom)
                )
                if modeAllowed:
                    shouldSend = self._checkWebhookAndDecide(gpuRPM, cpuRPM)
                    if shouldSend:
                        self._sendWebhook(
                            gpuRPM, cpuRPM, gpuTemp, cpuTemp,
                            self._webhookGpuRpmThreshold, self._webhookCpuRpmThreshold
                        )

            # Update tray icon
            self.trayIcon = self.trayIcon.resizeForScreen() or self.trayIcon
            self.trayIcon.update((gpuTemp, cpuTemp), self._modeSwitch.getChecked() == ThermalMode.G_Mode.value)
            tray.setIcon(self.trayIcon)
            webInfo = f"\nWeb:    http://{ThreadedHTTPServer.get_lan_ip()}:{self._webPort}" if self._webServer else ""
            tray.setToolTip(f"GPU:    {gpuTemp} °C    {gpuRPM} RPM\nCPU:    {cpuTemp} °C    {cpuRPM} RPM\nMode:    {self._modeSwitch.getChecked().replace('_', ' ')}{webInfo}")

            self._webBridge.update(
                gpu_temp=gpuTemp, gpu_rpm=gpuRPM,
                cpu_temp=cpuTemp, cpu_rpm=cpuRPM,
                mode=self._modeSwitch.getChecked(),
                gpu_fan_speed=self._thermalGPU.getSpeedSlider() if self._modeSwitch.getChecked() == ThermalMode.Custom.value else None,
                cpu_fan_speed=self._thermalCPU.getSpeedSlider() if self._modeSwitch.getChecked() == ThermalMode.Custom.value else None,
            )

            # Periodically save app settings
            self._saveAppSettings()

        self._loadAppSettings()

        self._updateGaugesTask = QPeriodic(self, self.TEMP_UPD_PERIOD_MS, updateAppState)
        updateAppState()
        self._updateGaugesTask.start()

        self.gModeHotKey = HotKey.HotKey(HotKey.G_MODE_KEY, self._gModeKeySignal)
        self._gModeKeySignal.connect(self._onGModeHotKeyPressed)
        self.gModeHotKey.start()

    def _showWebServerSettings(self) -> None:
        dialog = WebServerDialog(self, self.settings)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            newConfig = dialog.getConfig()
            wasRunning = self._webServer is not None
            if wasRunning:
                self._stopWebServer()
            self._webConfig = newConfig
            self._webPort = newConfig["web_port"]
            # Save to QSettings
            self.settings.setValue(SettingsKey.WebEnabled.value, str(newConfig["web_enabled"]).lower())
            self.settings.setValue(SettingsKey.WebPort.value, newConfig["web_port"])
            self.settings.setValue(SettingsKey.WebBindAddr.value, newConfig["bind_addr"])
            self.settings.setValue(SettingsKey.WebAuthEnabled.value, str(newConfig["auth_enabled"]).lower())
            self.settings.setValue(SettingsKey.WebAuthUser.value, newConfig["auth_user"])
            self.settings.setValue(SettingsKey.WebAuthPass.value, newConfig["auth_pass"])
            self._updateWebServerStatus()
            if newConfig["web_enabled"]:
                self._startWebServer()

    def _updateWebServerStatus(self) -> None:
        if self._webServer is not None:
            self._webServerAction.setText(f"• Web Server: {self._webPort}")
        else:
            self._webServerAction.setText("  Web Server: Disabled")

    def _startWebServer(self) -> None:
        if self._webServer is not None:
            return
        cfg = self._webConfig
        self._webServer = ThreadedHTTPServer(
            self._webBridge, self._webPort,
            bind_addr=cfg.get("bind_addr", "0.0.0.0"),
            auth_enabled=cfg.get("auth_enabled", False),
            auth_user=cfg.get("auth_user", "admin"),
            auth_pass=cfg.get("auth_pass", ""),
        )
        self._webServer.start()
        if self._webServer.wait_until_ready(3):
            ip = ThreadedHTTPServer.get_lan_ip()
            # 注意：不写 QSettings —— 偏好只在 _showWebServerSettings 中保存。
            self._updateWebServerStatus()
            self._tray.setToolTip(f"Web: http://{ip}:{self._webPort}")
            print(f"Web server started: http://{ip}:{self._webPort}")
        else:
            self._webServer.stop()
            self._webServer = None
            self._updateWebServerStatus()
            alert("Web Server", f"Failed to start web server on port {self._webPort}", QtWidgets.QMessageBox.Icon.Warning)

    def _stopWebServer(self) -> None:
        if self._webServer is None:
            return
        self._webServer.stop()
        self._webServer = None
        # 注意：不修改 QSettings 中的 WebEnabled —— 那是用户偏好，不是运行状态。
        # 偏好只在 _showWebServerSettings 中由用户手动修改时写入。
        self._updateWebServerStatus()
        print("Web server stopped")

    def updateGaugeTitles(self, gpuModel, cpuModel):
        if gpuModel: self._thermalGPU.setTitle(gpuModel)
        if cpuModel: self._thermalCPU.setTitle(cpuModel)

    def closeEvent(self, event):
        minimizeOnClose = self.settings.value(SettingsKey.MinimizeOnCloseFlag.value)
        if minimizeOnClose is not None:
            minimizeOnClose = str(minimizeOnClose).lower() == 'true'

        if minimizeOnClose is None:
            # minimizeOnClose is not set, prompt user
            (toExit, dontAskAgain) = confirm("Exit", "Do you want to exit or minimize to tray?", ("Exit", "Minimize"), True)
            minimizeOnClose = not toExit
            if dontAskAgain:
                self.settings.setValue(SettingsKey.MinimizeOnCloseFlag.value, minimizeOnClose)

        if minimizeOnClose:
            event.ignore()
            self.hide()
        else:
            self.onExit()
        return

    # onExit() connected to systray_Exit
    def onExit(self):
        print("exit")
        # Set mode to Balanced before exit
        prevMode = self._modeSwitch.getChecked()
        self._modeSwitch.setChecked(ThermalMode.Balanced.value)
        if prevMode != ThermalMode.Balanced.value:
            self._toasterMessageCurrentMode()
        self._destroy()
        sys.exit(0)

    def _errorExit(self, message: str, message2: Optional[str] = None) -> None:
        self._destroy()
        errorExit(message, message2)

    def _destroy(self):
        try:
            self._stopWebServer()
        except Exception as ex:
            print(f"[Cleanup] web server stop error: {ex}", flush=True)
        if self.gModeHotKey is not None:
            self.gModeHotKey.stop()
            self.gModeHotKey.wait()
        if self._updateGaugesTask is not None:
            self._updateGaugesTask.stop()
        print('Cleanup: done')

    def _onGModeHotKeyPressed(self):
        current = self._modeSwitch.getChecked()
        if current == ThermalMode.G_Mode.value:
            self._modeSwitch.setChecked(self._gModeKeyPrevModeStr or ThermalMode.Balanced.value)
        else:
            self._gModeKeyPrevModeStr = current
            self._modeSwitch.setChecked(ThermalMode.G_Mode.value)
        self._toasterMessageCurrentMode()

    def _toasterMessageCurrentMode(self, source: Optional[Literal['failsafe']] = None) -> None:
        sourceStr = f" [Fail-safe]" if source == 'failsafe' else ""
        self.toasterMessage(
            [
                self._modeSwitch.getChecked().replace('_', ' '),
                f"GPU: {self._thermalGPU.getTemp()}°C, CPU: {self._thermalCPU.getTemp()}°C",
                "Thermal mode changed" + sourceStr
            ],
            source != 'failsafe'
        )

    def toasterMessage(self, message: List[str | None], expire = True) -> None:
        toast = Toast(duration=ToastDuration.Short, expiration_time= (datetime.datetime.now() + datetime.timedelta(seconds=5)) if expire else None)
        toast.text_fields = message
        toast.AddImage(ToastDisplayImage.fromPath(resourcePath(GUI_ICON)))
        self._toaster.show_toast(toast)

    def _checkWebhookAndDecide(self, gpuRPM, cpuRPM) -> bool:
        """原子地完成：更新滑动窗口历史 → 计算动态阈值 → 判断告警状态 → 决定是否发送。

        在单次 UI 线程调用中完成，无需额外加锁（UI 线程是唯一调用者）。
        返回 True 表示应立即发送 webhook。
        """
        now = time.time()

        # 更新历史数据
        if gpuRPM is not None:
            self._webhookGpuHistory.append(gpuRPM)
            if len(self._webhookGpuHistory) > self._webhookWindowSize:
                self._webhookGpuHistory.pop(0)

        if cpuRPM is not None:
            self._webhookCpuHistory.append(cpuRPM)
            if len(self._webhookCpuHistory) > self._webhookWindowSize:
                self._webhookCpuHistory.pop(0)

        # 计算动态阈值
        def calc_dynamic_threshold(history, base_threshold, sigma):
            if len(history) < self._webhookWindowSize:
                return base_threshold
            mean = sum(history) / len(history)
            variance = sum((x - mean) ** 2 for x in history) / len(history)
            std = variance ** 0.5
            dynamic = mean + sigma * std
            return max(base_threshold, dynamic)

        gpu_dynamic_threshold = calc_dynamic_threshold(
            self._webhookGpuHistory, self._webhookGpuRpmThreshold, self._webhookSigma
        )
        cpu_dynamic_threshold = calc_dynamic_threshold(
            self._webhookCpuHistory, self._webhookCpuRpmThreshold, self._webhookSigma
        )

        # 判断是否超阈值
        gpuHigh = gpuRPM is not None and gpuRPM >= gpu_dynamic_threshold
        cpuHigh = cpuRPM is not None and cpuRPM >= cpu_dynamic_threshold
        isHigh = gpuHigh or cpuHigh

        wasInAlertState = self._webhookIsInAlertState
        self._webhookIsInAlertState = isHigh

        if isHigh and not wasInAlertState:
            # 刚进入告警状态 → 立即发送
            self._webhookLastAlertStateChange = now
            return True

        if not isHigh and wasInAlertState:
            # 刚恢复到正常状态
            self._webhookLastAlertStateChange = now
            self._webhookConsecutiveAlerts = 0
            return False

        # 持续告警中 → 检查指数退避间隔
        if isHigh:
            if self._webhookConsecutiveAlerts == 0:
                interval = self._webhookBaseInterval
            else:
                interval = self._webhookBaseInterval * (2 ** (self._webhookConsecutiveAlerts - 1))
                interval = min(interval, self._webhookMaxInterval)
            if now - self._webhookLastSendTime >= interval:
                return True

        return False

    def _sendWebhook(self, gpuRPM, cpuRPM, gpuTemp, cpuTemp, gpuThreshold, cpuThreshold):
        """发送 webhook 请求（调用前应已通过 _canSendWebhook 检查）"""
        if not self._webhookEnabled or not self._webhookUrl:
            return

        # 构建告警消息
        parts = []
        if gpuRPM is not None and gpuRPM >= gpuThreshold:
            parts.append(f"GPU: {gpuRPM} RPM (threshold {gpuThreshold})")
        if cpuRPM is not None and cpuRPM >= cpuThreshold:
            parts.append(f"CPU: {cpuRPM} RPM (threshold {cpuThreshold})")
        alert_message = ', '.join(parts)

        # 替换模板变量
        body = _replace_webhook_variables(self._webhookBody, {
            'alert_message': alert_message,
            'gpu_rpm': gpuRPM or 0,
            'cpu_rpm': cpuRPM or 0,
            'gpu_temp': gpuTemp or 0,
            'cpu_temp': cpuTemp or 0,
            'gpu_rpm_threshold': gpuThreshold,
            'cpu_rpm_threshold': cpuThreshold,
        })

        # 验证 JSON
        try:
            json.loads(body)
        except json.JSONDecodeError:
            return

        url = self._webhookUrl
        def _doRequest():
            try:
                payload = body.encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    with self._webhookLock:
                        self._webhookLastSendTime = time.time()
                        self._webhookConsecutiveAlerts += 1
                        self._webhookLastTriggerTime = time.time()
                        self._webhookAlertCount += 1
            except Exception as ex:
                print(f"[Webhook] send failed: {type(ex).__name__}: {ex}", flush=True)
                with self._webhookLock:
                    # 发送失败也记录时间，防止立即重试
                    self._webhookLastSendTime = time.time()

        threading.Thread(target=_doRequest, daemon=True).start()

    def _showWebhookSettings(self):
        webhook_status = {
            'last_trigger_time': self._webhookLastTriggerTime,
            'alert_count': self._webhookAlertCount,
        }
        dialog = WebhookDialog(self, self.settings, webhook_status)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            settings = dialog.getSettings()
            self._applyWebhookSettings(settings)
            self._saveWebhookSettings(settings)
            self._updateWebhookStatus()

    def _applyWebhookSettings(self, settings):
        # 设置键到实例属性的映射
        settings_map = {
            'enabled': '_webhookEnabled',
            'url': '_webhookUrl',
            'body': '_webhookBody',
            'gpu_rpm_threshold': '_webhookGpuRpmThreshold',
            'cpu_rpm_threshold': '_webhookCpuRpmThreshold',
            'window_size': '_webhookWindowSize',
            'sigma': '_webhookSigma',
            'base_interval': '_webhookBaseInterval',
            'max_interval': '_webhookMaxInterval',
            'cooldown': '_webhookCooldownAfterReset',
            'filter_balanced': '_webhookFilterBalanced',
            'filter_gmode': '_webhookFilterGMode',
            'filter_custom': '_webhookFilterCustom',
        }
        for key, attr_name in settings_map.items():
            setattr(self, attr_name, settings[key])
        # 重置算法状态 (lock to avoid racing with _doRequest background thread)
        with self._webhookLock:
            self._webhookGpuHistory = []
            self._webhookCpuHistory = []
            self._webhookConsecutiveAlerts = 0
            self._webhookIsInAlertState = False

    def _saveWebhookSettings(self, settings):
        # 设置键到 SettingsKey 枚举的映射
        settings_key_map = {
            'enabled': SettingsKey.WebhookEnabled,
            'url': SettingsKey.WebhookUrl,
            'body': SettingsKey.WebhookBody,
            'gpu_rpm_threshold': SettingsKey.WebhookGpuRpmThreshold,
            'cpu_rpm_threshold': SettingsKey.WebhookCpuRpmThreshold,
            'window_size': SettingsKey.WebhookWindowSize,
            'sigma': SettingsKey.WebhookSigma,
            'base_interval': SettingsKey.WebhookBaseInterval,
            'max_interval': SettingsKey.WebhookMaxInterval,
            'cooldown': SettingsKey.WebhookCooldownAfterReset,
            'filter_balanced': SettingsKey.WebhookFilterBalanced,
            'filter_gmode': SettingsKey.WebhookFilterGMode,
            'filter_custom': SettingsKey.WebhookFilterCustom,
        }
        for key, settings_key in settings_key_map.items():
            self.settings.setValue(settings_key.value, settings[key])

    def _updateWebhookStatus(self):
        if self._webhookEnabled:
            self._webhookAction.setText("• Webhook: Enabled")
        else:
            self._webhookAction.setText("  Webhook: Disabled")

    def _saveAppSettings(self):
        curValues = [
            self._modeSwitch.getChecked(),
            self._thermalCPU.getSpeedSlider(),
            self._thermalGPU.getSpeedSlider(),
            self.FAILSAFE_CPU_TEMP,
            self.FAILSAFE_GPU_TEMP,
            self._failsafeOn,
        ]
        if curValues == self._prevSavedSettingsValues:
            return
        self._prevSavedSettingsValues = curValues

        self.settings.setValue(SettingsKey.Mode.value, self._modeSwitch.getChecked())
        self.settings.setValue(SettingsKey.CPUFanSpeed.value, self._thermalCPU.getSpeedSlider())
        self.settings.setValue(SettingsKey.GPUFanSpeed.value, self._thermalGPU.getSpeedSlider())
        self.settings.setValue(SettingsKey.CPUThresholdTemp.value, self.FAILSAFE_CPU_TEMP)
        self.settings.setValue(SettingsKey.GPUThresholdTemp.value, self.FAILSAFE_GPU_TEMP)
        self.settings.setValue(SettingsKey.FailSafeIsOnFlag.value, self._failsafeOn)

    def _loadAppSettings(self):
        savedMode = self.settings.value(SettingsKey.Mode.value)
        if savedMode not in [m.value for m in ThermalMode]:
            savedMode = ThermalMode.Balanced.value
        self._modeSwitch.setChecked(savedMode)
        savedSpeed = self.settings.value(SettingsKey.CPUFanSpeed.value)
        self._thermalCPU.setSpeedSlider(savedSpeed)
        savedSpeed = self.settings.value(SettingsKey.GPUFanSpeed.value)
        self._thermalGPU.setSpeedSlider(savedSpeed)
        savedTemp = self.settings.value(SettingsKey.CPUThresholdTemp.value) or 95
        self._limitTempCPU.setCurrentText(str(savedTemp))
        savedTemp = self.settings.value(SettingsKey.GPUThresholdTemp.value) or 85
        self._limitTempGPU.setCurrentText(str(savedTemp))
        savedFailsafe = self.settings.value(SettingsKey.FailSafeIsOnFlag.value) or 'true'
        self._failsafeCB.setChecked(str(savedFailsafe).lower() == 'true')
        # Webhook settings
        self._webhookEnabled = setting_bool(self.settings, SettingsKey.WebhookEnabled.value, WEBHOOK_DEFAULTS["enabled"])
        self._webhookUrl = setting_str(self.settings, SettingsKey.WebhookUrl.value, WEBHOOK_DEFAULTS["url"])
        self._webhookBody = setting_str(self.settings, SettingsKey.WebhookBody.value, WEBHOOK_DEFAULTS["body"])
        self._webhookGpuRpmThreshold = setting_int(self.settings, SettingsKey.WebhookGpuRpmThreshold.value, WEBHOOK_DEFAULTS["gpu_rpm_threshold"])
        self._webhookCpuRpmThreshold = setting_int(self.settings, SettingsKey.WebhookCpuRpmThreshold.value, WEBHOOK_DEFAULTS["cpu_rpm_threshold"])
        self._webhookWindowSize = setting_int(self.settings, SettingsKey.WebhookWindowSize.value, WEBHOOK_DEFAULTS["window_size"])
        self._webhookSigma = setting_float(self.settings, SettingsKey.WebhookSigma.value, WEBHOOK_DEFAULTS["sigma"])
        self._webhookBaseInterval = setting_int(self.settings, SettingsKey.WebhookBaseInterval.value, WEBHOOK_DEFAULTS["base_interval"])
        self._webhookMaxInterval = setting_int(self.settings, SettingsKey.WebhookMaxInterval.value, WEBHOOK_DEFAULTS["max_interval"])
        self._webhookCooldownAfterReset = setting_int(self.settings, SettingsKey.WebhookCooldownAfterReset.value, WEBHOOK_DEFAULTS["cooldown_after_reset"])
        self._webhookFilterBalanced = setting_bool(self.settings, SettingsKey.WebhookFilterBalanced.value, WEBHOOK_DEFAULTS["filter_balanced"])
        self._webhookFilterGMode = setting_bool(self.settings, SettingsKey.WebhookFilterGMode.value, WEBHOOK_DEFAULTS["filter_gmode"])
        self._webhookFilterCustom = setting_bool(self.settings, SettingsKey.WebhookFilterCustom.value, WEBHOOK_DEFAULTS["filter_custom"])
        self._updateWebhookStatus()
        # Web server settings
        self._webConfig["web_enabled"] = setting_bool(self.settings, SettingsKey.WebEnabled.value, WEB_DEFAULTS["web_enabled"])
        self._webConfig["web_port"] = setting_int(self.settings, SettingsKey.WebPort.value, WEB_DEFAULTS["web_port"])
        self._webConfig["bind_addr"] = setting_str(self.settings, SettingsKey.WebBindAddr.value, WEB_DEFAULTS["bind_addr"])
        self._webConfig["auth_enabled"] = setting_bool(self.settings, SettingsKey.WebAuthEnabled.value, WEB_DEFAULTS["auth_enabled"])
        self._webConfig["auth_user"] = setting_str(self.settings, SettingsKey.WebAuthUser.value, WEB_DEFAULTS["auth_user"])
        self._webConfig["auth_pass"] = setting_str(self.settings, SettingsKey.WebAuthPass.value, WEB_DEFAULTS["auth_pass"])
        self._webPort = self._webConfig["web_port"]
        self._updateWebServerStatus()

    def clearAppSettings(self):
        (isYes, _) = confirm("Reset to Default", "Do you want to reset all settings to default?", ("Reset", "Cancel"))
        if not isYes: return
        wasRunning = self._webServer is not None
        if wasRunning:
            self._stopWebServer()
        self.settings.clear()
        self._loadAppSettings()
        if wasRunning and self._webConfig["web_enabled"]:
            self._startWebServer()

    def G_Mode_key_Pressed(self, val):
        print("G_Mode_key " + str(val))

def runApp(startMinimized = False) -> int:
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
            border: 1px solid {Colors.DARK_GREY.value};
            border-radius: 3;
        }}
        QComboBox {{
            border: 1px solid gray;
            border-radius: 3px;
            padding: 1px 0.6em 1px 3px;
        }}
        QComboBox::disabled {{
            color: {Colors.GREY.value};
        }}
        QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {Colors.GREY.value};
            border-radius: 7px;
            background: {Colors.DARK_GREY.value};
        }}
        QRadioButton::indicator:checked {{
            background: {Colors.BLUE.value};
            border: 1px solid {Colors.BLUE.value};
        }}
    """)

    if startMinimized:
        mainWindow.showMinimized()
        mainWindow.hide()
    else:
        mainWindow.show()

    return app.exec()
