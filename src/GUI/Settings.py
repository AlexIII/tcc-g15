from enum import Enum


class SettingsKey(Enum):
    Mode = "app/mode"
    CPUFanSpeed = "app/fan/cpu/speed"
    CPUThresholdTemp = "app/fan/cpu/threshold_temp"
    GPUFanSpeed = "app/fan/gpu/speed"
    GPUThresholdTemp = "app/fan/gpu/threshold_temp"
    FailSafeIsOnFlag = "app/failsafe_is_on_flag"
    MinimizeOnCloseFlag = "app/minimize_on_close_flag"
    WebPort = "app/web_port"
    WebEnabled = "app/web_enabled"
    WebhookEnabled = "app/webhook_enabled"
    WebhookUrl = "app/webhook_url"
    WebhookBody = "app/webhook_body"
    WebhookGpuRpmThreshold = "app/webhook_gpu_rpm_threshold"
    WebhookCpuRpmThreshold = "app/webhook_cpu_rpm_threshold"
    WebhookWindowSize = "app/webhook_window_size"
    WebhookSigma = "app/webhook_sigma"
    WebhookBaseInterval = "app/webhook_base_interval"
    WebhookMaxInterval = "app/webhook_max_interval"
    WebhookCooldownAfterReset = "app/webhook_cooldown_after_reset"
    WebhookFilterBalanced = "app/webhook_filter_balanced"
    WebhookFilterGMode = "app/webhook_filter_gmode"
    WebhookFilterCustom = "app/webhook_filter_custom"
    WebBindAddr = "app/web_bind_addr"
    WebAuthEnabled = "app/web_auth_enabled"
    WebAuthUser = "app/web_auth_user"
    WebAuthPass = "app/web_auth_pass"

WEBHOOK_DEFAULTS = {
    "enabled": False,
    "url": "",
    "body": '{"text": "Fan speed alert: {alert_message}", "source": "tcc-g15", "gpu_rpm": {gpu_rpm}, "cpu_rpm": {cpu_rpm}, "gpu_temp": {gpu_temp}, "cpu_temp": {cpu_temp}}',
    "gpu_rpm_threshold": 4000,
    "cpu_rpm_threshold": 4000,
    "window_size": 5,
    "sigma": 2.0,
    "base_interval": 30,
    "max_interval": 600,
    "cooldown_after_reset": 60,
    "filter_balanced": True,
    "filter_gmode": True,
    "filter_custom": True,
}

WEB_DEFAULTS = {
    "web_enabled": False,
    "web_port": 8080,
    "bind_addr": "0.0.0.0",
    "auth_enabled": False,
    "auth_user": "admin",
    "auth_pass": "",
}


# ---------------------------------------------------------------------------
# QSettings helper functions (shared by TCC_GUI, WebhookDialog, WebServerDialog)
# ---------------------------------------------------------------------------

def setting_bool(settings, key: str, default: bool) -> bool:
    val = settings.value(key)
    if val is None:
        return default
    return str(val).lower() == 'true'


def setting_str(settings, key: str, default: str) -> str:
    return settings.value(key, default) or default


def setting_int(settings, key: str, default: int) -> int:
    return int(settings.value(key, default))


def setting_float(settings, key: str, default: float) -> float:
    return float(settings.value(key, default))
