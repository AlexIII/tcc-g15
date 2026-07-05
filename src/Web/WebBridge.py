import queue
import threading
from typing import Any, Optional
from PySide6 import QtCore


class WebBridge(QtCore.QObject):
    commandQueued = QtCore.Signal()

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._state: dict[str, Any] = {}
        self._state_lock = threading.Lock()
        self._commands: queue.Queue = queue.Queue()

    def update(self, gpu_temp: Optional[int], gpu_rpm: Optional[int],
               cpu_temp: Optional[int], cpu_rpm: Optional[int],
               mode: str, gpu_fan_speed: Optional[int], cpu_fan_speed: Optional[int]) -> None:
        new_state = {
            "gpu_temp": gpu_temp,
            "gpu_rpm": gpu_rpm,
            "cpu_temp": cpu_temp,
            "cpu_rpm": cpu_rpm,
            "mode": mode,
            "gpu_fan_speed": gpu_fan_speed,
            "cpu_fan_speed": cpu_fan_speed,
        }
        with self._state_lock:
            self._state = new_state

    def get_status(self) -> dict:
        with self._state_lock:
            return dict(self._state)

    def set_mode(self, mode: str) -> None:
        self._commands.put(("mode", mode))
        self.commandQueued.emit()

    def set_fan_speeds(self, gpu_speed: int, cpu_speed: int) -> None:
        self._commands.put(("fan", gpu_speed, cpu_speed))
        self.commandQueued.emit()

    def processCommands(self, callback) -> None:
        while True:
            try:
                cmd = self._commands.get_nowait()
            except queue.Empty:
                break
            if cmd[0] == "mode":
                callback("mode", cmd[1])
            elif cmd[0] == "fan":
                callback("fan", cmd[1], cmd[2])
