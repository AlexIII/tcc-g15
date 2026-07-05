import json
import datetime
import urllib.request
import threading

from typing import Optional
from PySide6 import QtCore, QtWidgets

from GUI.Settings import SettingsKey, WEBHOOK_DEFAULTS, WEB_DEFAULTS, setting_bool, setting_str, setting_int, setting_float


def _replace_webhook_variables(template: str, values: dict) -> str:
    """Replace template variables in a webhook body string.

    Supported placeholders: {alert_message}, {gpu_rpm}, {cpu_rpm},
    {gpu_temp}, {cpu_temp}, {gpu_threshold}, {cpu_threshold}.
    """
    result = template
    for key, val in values.items():
        if isinstance(val, str):
            escaped = json.dumps(val)[1:-1]
        else:
            escaped = str(val)
        result = result.replace('{' + key + '}', escaped)
    return result


class WebhookDialog(QtWidgets.QDialog):
    # 信号定义
    testComplete = QtCore.Signal(int, str)

    # 灵敏度预设：(window_size, sigma)
    SENSITIVITY_PRESETS = {
        "Low": (8, 2.5),
        "Medium": (5, 2.0),
        "High": (3, 1.5),
    }
    # 发送频率预设：(base_interval, max_interval)
    FREQUENCY_PRESETS = {
        "Immediate (30s max 2min)": (30, 120),
        "Moderate (1min max 5min)": (60, 300),
        "Conservative (2min max 10min)": (120, 600),
    }

    def __init__(self, parent, settings, webhook_status=None):
        super().__init__(parent)
        self.settings = settings
        self.webhook_status = webhook_status or {}
        self.setWindowTitle("Webhook Alert Settings")
        self.setMinimumWidth(500)

        layout = QtWidgets.QVBoxLayout(self)

        # 功能说明
        descLabel = QtWidgets.QLabel(
            "Send HTTP notifications when fan speed exceeds threshold.\n"
            "Configure when to trigger and how often to alert."
        )
        descLabel.setStyleSheet("color: #666; font-size: 11px; margin-bottom: 10px;")
        descLabel.setWordWrap(True)
        layout.addWidget(descLabel)

        # 启用开关
        self.enableCB = QtWidgets.QCheckBox("Enable Webhook Alert")
        layout.addWidget(self.enableCB)

        # URL 输入
        urlLayout = QtWidgets.QHBoxLayout()
        urlLayout.addWidget(QtWidgets.QLabel("Webhook URL:"))
        self.urlEdit = QtWidgets.QLineEdit()
        self.urlEdit.setPlaceholderText("https://your-webhook-url.com/endpoint")
        urlLayout.addWidget(self.urlEdit)
        layout.addLayout(urlLayout)

        # 模式过滤
        filterGroup = QtWidgets.QGroupBox("Mode Filter (only alert in selected modes)")
        filterLayout = QtWidgets.QHBoxLayout(filterGroup)
        self.filterBalancedCB = QtWidgets.QCheckBox("Balanced")
        self.filterGModeCB = QtWidgets.QCheckBox("G-Mode")
        self.filterCustomCB = QtWidgets.QCheckBox("Custom")
        self.filterBalancedCB.setChecked(True)
        self.filterGModeCB.setChecked(True)
        self.filterCustomCB.setChecked(True)
        filterLayout.addWidget(self.filterBalancedCB)
        filterLayout.addWidget(self.filterGModeCB)
        filterLayout.addWidget(self.filterCustomCB)
        layout.addWidget(filterGroup)

        # 阈值设置
        thresholdGroup = QtWidgets.QGroupBox("Threshold Settings")
        thresholdLayout = QtWidgets.QFormLayout(thresholdGroup)

        self.gpuThresholdSpin = QtWidgets.QSpinBox()
        self.gpuThresholdSpin.setRange(1000, 6000)
        self.gpuThresholdSpin.setSuffix(" RPM")
        thresholdLayout.addRow("GPU RPM Threshold:", self.gpuThresholdSpin)

        self.cpuThresholdSpin = QtWidgets.QSpinBox()
        self.cpuThresholdSpin.setRange(1000, 6000)
        self.cpuThresholdSpin.setSuffix(" RPM")
        thresholdLayout.addRow("CPU RPM Threshold:", self.cpuThresholdSpin)

        layout.addWidget(thresholdGroup)

        # 行为设置（人性化选项）
        behaviorGroup = QtWidgets.QGroupBox("Alert Behavior")
        behaviorLayout = QtWidgets.QFormLayout(behaviorGroup)

        self.sensitivityCombo = QtWidgets.QComboBox()
        self.sensitivityCombo.addItems(list(self.SENSITIVITY_PRESETS.keys()))
        self.sensitivityCombo.setToolTip("Low = less sensitive, fewer false alarms\nMedium = balanced\nHigh = more sensitive, faster detection")
        behaviorLayout.addRow("Sensitivity:", self.sensitivityCombo)

        self.frequencyCombo = QtWidgets.QComboBox()
        self.frequencyCombo.addItems(list(self.FREQUENCY_PRESETS.keys()))
        self.frequencyCombo.setToolTip("How often to send alerts when threshold is exceeded")
        behaviorLayout.addRow("Alert Frequency:", self.frequencyCombo)

        # 动态说明标签
        self.behaviorHint = QtWidgets.QLabel()
        self.behaviorHint.setStyleSheet("color: grey; font-size: 10px;")
        self.behaviorHint.setWordWrap(True)
        behaviorLayout.addRow(self.behaviorHint)

        def updateBehaviorHint():
            s = self.sensitivityCombo.currentText()
            f = self.frequencyCombo.currentText()
            ws, _ = self.SENSITIVITY_PRESETS[s]
            sDesc = {
                "Low": f"Averages {ws} readings, ignores brief spikes",
                "Medium": f"Averages {ws} readings, balanced response",
                "High": f"Averages {ws} readings, reacts quickly to changes"
            }
            base, max_ = self.FREQUENCY_PRESETS[f]
            fDesc = {
                "Immediate (30s max 2min)": f"First alert after {base}s, then every {base*2}s, {base*4}s... up to {max_}s",
                "Moderate (1min max 5min)": f"First alert after {base}s, then every {base*2}s, {base*4}s... up to {max_}s",
                "Conservative (2min max 10min)": f"First alert after {base}s, then every {base*2}s, {base*4}s... up to {max_}s"
            }
            self.behaviorHint.setText(f"Detection: {sDesc.get(s, '')}\nAlerts: {fDesc.get(f, '')}")

        self.sensitivityCombo.currentIndexChanged.connect(updateBehaviorHint)
        self.frequencyCombo.currentIndexChanged.connect(updateBehaviorHint)
        updateBehaviorHint()

        layout.addWidget(behaviorGroup)

        # Body 模板
        bodyGroup = QtWidgets.QGroupBox("Request Body (JSON Template)")
        bodyLayout = QtWidgets.QVBoxLayout(bodyGroup)

        # 模板选择
        templateLayout = QtWidgets.QHBoxLayout()
        templateLayout.addWidget(QtWidgets.QLabel("Template:"))
        self.templateCombo = QtWidgets.QComboBox()
        self.templateCombo.addItems([
            "Custom",
            "Default",
            "WeChat Work (企业微信)",
            "Feishu (飞书)",
            "DingTalk (钉钉)",
            "Slack",
            "Discord",
        ])
        templateLayout.addWidget(self.templateCombo)
        templateLayout.addStretch()
        bodyLayout.addLayout(templateLayout)

        self.bodyEdit = QtWidgets.QPlainTextEdit()
        self.bodyEdit.setMaximumHeight(150)
        self.bodyEdit.setPlaceholderText('{"text": "Alert: {alert_message}", "gpu_rpm": {gpu_rpm}}')
        bodyLayout.addWidget(self.bodyEdit)

        # 模板定义（URL 示例 + Body）
        self._templates = {
            "Default": {
                "url": "https://your-webhook-url.com/endpoint",
                "body": WEBHOOK_DEFAULTS["body"],
            },
            "WeChat Work (企业微信)": {
                "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
                "body": '{"msgtype": "text", "text": {"content": "[TCC-G15] 风扇速度告警\\n{alert_message}\\nGPU: {gpu_rpm} RPM, CPU: {cpu_rpm} RPM\\nGPU温度: {gpu_temp}°C, CPU温度: {cpu_temp}°C"}}',
            },
            "Feishu (飞书)": {
                "url": "https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_HOOK",
                "body": '{"msg_type": "text", "content": {"text": "[TCC-G15] 风扇速度告警\\n{alert_message}\\nGPU: {gpu_rpm} RPM, CPU: {cpu_rpm} RPM\\nGPU温度: {gpu_temp}°C, CPU温度: {cpu_temp}°C"}}',
            },
            "DingTalk (钉钉)": {
                "url": "https://oapi.dingtalk.com/robot/send?access_token=YOUR_TOKEN",
                "body": '{"msgtype": "text", "text": {"content": "[TCC-G15] 风扇速度告警\\n{alert_message}\\nGPU: {gpu_rpm} RPM, CPU: {cpu_rpm} RPM\\nGPU温度: {gpu_temp}°C, CPU温度: {cpu_temp}°C"}}',
            },
            "Slack": {
                "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                "body": '{"text": "[TCC-G15] 风扇速度告警\\n{alert_message}\\nGPU: {gpu_rpm} RPM, CPU: {cpu_rpm} RPM\\nGPU温度: {gpu_temp}°C, CPU温度: {cpu_temp}°C"}',
            },
            "Discord": {
                "url": "https://discord.com/api/webhooks/YOUR/WEBHOOK",
                "body": '{"content": "[TCC-G15] 风扇速度告警\\n{alert_message}\\nGPU: {gpu_rpm} RPM, CPU: {cpu_rpm} RPM\\nGPU温度: {gpu_temp}°C, CPU温度: {cpu_temp}°C"}',
            },
        }

        def onTemplateChange():
            template = self.templateCombo.currentText()
            if template in self._templates:
                self.bodyEdit.setPlainText(self._templates[template]["body"])
                self.urlEdit.setText(self._templates[template]["url"])

        self.templateCombo.currentIndexChanged.connect(onTemplateChange)

        helpLabel = QtWidgets.QLabel(
            "Variables: {alert_message}, {gpu_rpm}, {cpu_rpm}, {gpu_temp}, {cpu_temp}, {gpu_rpm_threshold}, {cpu_rpm_threshold}"
        )
        helpLabel.setStyleSheet("color: grey; font-size: 10px;")
        helpLabel.setWordWrap(True)
        bodyLayout.addWidget(helpLabel)

        layout.addWidget(bodyGroup)

        # 状态信息
        statusGroup = QtWidgets.QGroupBox("Status")
        statusLayout = QtWidgets.QFormLayout(statusGroup)

        self.lastTriggerLabel = QtWidgets.QLabel("Never")
        statusLayout.addRow("Last Triggered:", self.lastTriggerLabel)

        self.alertCountLabel = QtWidgets.QLabel("0")
        statusLayout.addRow("Total Alerts Sent:", self.alertCountLabel)

        layout.addWidget(statusGroup)

        # 按钮行
        buttonLayout = QtWidgets.QHBoxLayout()

        self.testBtn = QtWidgets.QPushButton("Test Send")
        self.testBtn.setToolTip("Send a test webhook to verify your configuration")
        self.testBtn.clicked.connect(self._testSend)
        self.testComplete.connect(self._onTestComplete)
        buttonLayout.addWidget(self.testBtn)

        buttonLayout.addStretch()

        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        buttonLayout.addWidget(buttonBox)

        layout.addLayout(buttonLayout)

        # 加载当前设置
        self._loadSettings()

    def _onTestComplete(self, status, error):
        self.testBtn.setEnabled(True)
        self.testBtn.setText("Test Send")
        if status:
            QtWidgets.QMessageBox.information(self, "Test Successful", f"Webhook sent successfully!\nHTTP Status: {status}")
        else:
            QtWidgets.QMessageBox.warning(self, "Test Failed", f"Failed to send webhook:\n{error}")

    def _testSend(self):
        """发送测试 webhook"""
        url = self.urlEdit.text().strip()
        body = self.bodyEdit.toPlainText().strip()

        if not url:
            QtWidgets.QMessageBox.warning(self, "Test Failed", "Please enter a Webhook URL first.")
            return

        if not body:
            QtWidgets.QMessageBox.warning(self, "Test Failed", "Please enter a Request Body first.")
            return

        # 替换变量为测试值
        testBody = _replace_webhook_variables(body, {
            'alert_message': 'Test alert from TCC-G15',
            'gpu_rpm': 3500,
            'cpu_rpm': 4200,
            'gpu_temp': 72,
            'cpu_temp': 85,
            'gpu_rpm_threshold': 4000,
            'cpu_rpm_threshold': 4000,
        })

        try:
            json.loads(testBody)
        except json.JSONDecodeError as e:
            QtWidgets.QMessageBox.warning(self, "Test Failed", f"Invalid JSON body:\n{e}")
            return

        def _doRequest():
            try:
                payload = testBody.encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status, None
            except Exception as e:
                return None, str(e)

        # 在后台线程执行
        self.testBtn.setEnabled(False)
        self.testBtn.setText("Sending...")

        def _doTest():
            status, error = _doRequest()
            self.testComplete.emit(status if status else 0, error if error else "")

        thread = threading.Thread(target=_doTest, daemon=True)
        thread.start()

    def _loadSettings(self):
        self.enableCB.setChecked(setting_bool(self.settings, SettingsKey.WebhookEnabled.value, WEBHOOK_DEFAULTS["enabled"]))
        self.urlEdit.setText(setting_str(self.settings, SettingsKey.WebhookUrl.value, WEBHOOK_DEFAULTS["url"]))
        savedBody = setting_str(self.settings, SettingsKey.WebhookBody.value, WEBHOOK_DEFAULTS["body"])
        self.bodyEdit.setPlainText(savedBody)
        self.gpuThresholdSpin.setValue(setting_int(self.settings, SettingsKey.WebhookGpuRpmThreshold.value, WEBHOOK_DEFAULTS["gpu_rpm_threshold"]))
        self.cpuThresholdSpin.setValue(setting_int(self.settings, SettingsKey.WebhookCpuRpmThreshold.value, WEBHOOK_DEFAULTS["cpu_rpm_threshold"]))

        # 加载模式过滤设置
        self.filterBalancedCB.setChecked(setting_bool(self.settings, SettingsKey.WebhookFilterBalanced.value, WEBHOOK_DEFAULTS["filter_balanced"]))
        self.filterGModeCB.setChecked(setting_bool(self.settings, SettingsKey.WebhookFilterGMode.value, WEBHOOK_DEFAULTS["filter_gmode"]))
        self.filterCustomCB.setChecked(setting_bool(self.settings, SettingsKey.WebhookFilterCustom.value, WEBHOOK_DEFAULTS["filter_custom"]))

        # 匹配模板
        matchedTemplate = "Custom"
        for name, tmpl in self._templates.items():
            if savedBody.strip() == tmpl["body"].strip():
                matchedTemplate = name
                break
        self.templateCombo.blockSignals(True)
        self.templateCombo.setCurrentText(matchedTemplate)
        self.templateCombo.blockSignals(False)

        # 加载灵敏度预设
        savedSigma = setting_float(self.settings, SettingsKey.WebhookSigma.value, WEBHOOK_DEFAULTS["sigma"])
        sensitivity = "Medium"
        for name, (_, sigma) in self.SENSITIVITY_PRESETS.items():
            if abs(sigma - savedSigma) < 0.01:
                sensitivity = name
                break
        self.sensitivityCombo.setCurrentText(sensitivity)

        # 加载频率预设
        savedBase = setting_int(self.settings, SettingsKey.WebhookBaseInterval.value, WEBHOOK_DEFAULTS["base_interval"])
        savedMax = setting_int(self.settings, SettingsKey.WebhookMaxInterval.value, WEBHOOK_DEFAULTS["max_interval"])
        frequency = "Immediate (30s max 2min)"
        for name, (base, max_) in self.FREQUENCY_PRESETS.items():
            if base == savedBase and max_ == savedMax:
                frequency = name
                break
        self.frequencyCombo.setCurrentText(frequency)

        # 加载状态信息
        lastTrigger = self.webhook_status.get('last_trigger_time', 0)
        alertCount = self.webhook_status.get('alert_count', 0)
        if lastTrigger > 0:
            triggerTime = datetime.datetime.fromtimestamp(lastTrigger).strftime("%Y-%m-%d %H:%M:%S")
            self.lastTriggerLabel.setText(triggerTime)
        else:
            self.lastTriggerLabel.setText("Never")
        self.alertCountLabel.setText(str(alertCount))

    def getSettings(self):
        window_size, sigma = self.SENSITIVITY_PRESETS[self.sensitivityCombo.currentText()]
        base_interval, max_interval = self.FREQUENCY_PRESETS[self.frequencyCombo.currentText()]
        return {
            'enabled': self.enableCB.isChecked(),
            'url': self.urlEdit.text().strip(),
            'body': self.bodyEdit.toPlainText().strip(),
            'gpu_rpm_threshold': self.gpuThresholdSpin.value(),
            'cpu_rpm_threshold': self.cpuThresholdSpin.value(),
            'window_size': window_size,
            'sigma': sigma,
            'base_interval': base_interval,
            'max_interval': max_interval,
            'cooldown': setting_int(self.settings, SettingsKey.WebhookCooldownAfterReset.value, WEBHOOK_DEFAULTS["cooldown_after_reset"]),
            'filter_balanced': self.filterBalancedCB.isChecked(),
            'filter_gmode': self.filterGModeCB.isChecked(),
            'filter_custom': self.filterCustomCB.isChecked(),
        }


class WebServerDialog(QtWidgets.QDialog):
    def __init__(self, parent, settings):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Web Server Settings")
        self.setMinimumWidth(450)

        layout = QtWidgets.QVBoxLayout(self)

        # 功能说明
        descLabel = QtWidgets.QLabel(
            "Embedded web server for remote monitoring and control.\n"
            "Access the dashboard from any device on your network."
        )
        descLabel.setStyleSheet("color: #666; font-size: 11px; margin-bottom: 10px;")
        descLabel.setWordWrap(True)
        layout.addWidget(descLabel)

        # 启用开关
        self.enableCB = QtWidgets.QCheckBox("Enable Web Server")
        layout.addWidget(self.enableCB)

        # 网络设置
        networkGroup = QtWidgets.QGroupBox("Network Settings")
        networkLayout = QtWidgets.QFormLayout(networkGroup)

        self.portSpin = QtWidgets.QSpinBox()
        self.portSpin.setRange(1024, 65535)
        networkLayout.addRow("Port:", self.portSpin)

        self.bindEdit = QtWidgets.QLineEdit()
        self.bindEdit.setPlaceholderText("0.0.0.0")
        self.bindEdit.setToolTip("0.0.0.0 = all interfaces, or specific IP like 192.168.1.100")
        networkLayout.addRow("Bind Address:", self.bindEdit)

        layout.addWidget(networkGroup)

        # 认证设置
        authGroup = QtWidgets.QGroupBox("Authentication")
        authLayout = QtWidgets.QFormLayout(authGroup)

        self.authEnableCB = QtWidgets.QCheckBox("Enable Authentication")
        authLayout.addRow(self.authEnableCB)

        self.userEdit = QtWidgets.QLineEdit()
        self.userEdit.setPlaceholderText("admin")
        authLayout.addRow("Username:", self.userEdit)

        self.passEdit = QtWidgets.QLineEdit()
        self.passEdit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.passEdit.setPlaceholderText("password")
        authLayout.addRow("Password:", self.passEdit)

        layout.addWidget(authGroup)

        # 按钮
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)

        self._loadConfig()

    def _loadConfig(self):
        self.enableCB.setChecked(setting_bool(self.settings, SettingsKey.WebEnabled.value, WEB_DEFAULTS["web_enabled"]))
        self.portSpin.setValue(setting_int(self.settings, SettingsKey.WebPort.value, WEB_DEFAULTS["web_port"]))
        self.bindEdit.setText(setting_str(self.settings, SettingsKey.WebBindAddr.value, WEB_DEFAULTS["bind_addr"]))
        self.authEnableCB.setChecked(setting_bool(self.settings, SettingsKey.WebAuthEnabled.value, WEB_DEFAULTS["auth_enabled"]))
        self.userEdit.setText(setting_str(self.settings, SettingsKey.WebAuthUser.value, WEB_DEFAULTS["auth_user"]))
        self.passEdit.setText(setting_str(self.settings, SettingsKey.WebAuthPass.value, WEB_DEFAULTS["auth_pass"]))

    def getConfig(self):
        return {
            "web_enabled": self.enableCB.isChecked(),
            "web_port": self.portSpin.value(),
            "bind_addr": self.bindEdit.text().strip() or "0.0.0.0",
            "auth_enabled": self.authEnableCB.isChecked(),
            "auth_user": self.userEdit.text().strip() or "admin",
            "auth_pass": self.passEdit.text(),
        }
