import threading
import win32con
from ctypes import *
from ctypes.wintypes import *
from PySide6.QtCore import *

G_MODE_KEY = 0x80

_STOP_SIGNAL_CODE = 0x9AB10000 # This number was picked randomly

class HotKey(QThread):
    def __init__(self, key: int, keyPressedSignal: Signal):
        super(HotKey, self).__init__()
        self.keyPressedSignal = keyPressedSignal
        self.key = key

    def run(self):
        self.nativeThreadId = threading.get_native_id()
        user32 = windll.user32

        if not user32.RegisterHotKey(None, 1, 0, self.key):
            print(f"Could not register hot key {self.key}")
            return
        msg = MSG()

        while user32.GetMessageA(byref(msg), None, 0, 0):
            if msg.message == win32con.WM_USER and msg.wParam == _STOP_SIGNAL_CODE:
                break
            if msg.message == win32con.WM_HOTKEY and msg.wParam == 1:
                self.keyPressedSignal.emit()
        user32.UnregisterHotKey(None, 1)

    def stop(self):
        windll.user32.PostThreadMessageW(self.nativeThreadId, win32con.WM_USER, _STOP_SIGNAL_CODE, 0)
