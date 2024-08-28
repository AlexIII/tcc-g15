import win32con
from ctypes import *
from ctypes.wintypes import *
from PySide6.QtCore import *

class HotKey(QThread):

    Change_Mode = Signal(int)
    def __init__(self):
        super(HotKey, self).__init__()
    def run(self):
        user32 = windll.user32
        while True:
            if not user32.RegisterHotKey(None, 1, 0, 128):# G_Mode_key
                print("Hotkey registration failed")
            try:
                msg = MSG()
                if user32.GetMessageA(byref(msg), None, 0, 0) != 0:
                    if msg.message == win32con.WM_HOTKEY:
                        if msg.wParam == 1:
                            self.Change_Mode.emit(msg.lParam)
            finally:
                user32.UnregisterHotKey(None, 1)

