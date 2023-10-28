from typing import *
from PySide6 import QtCore, QtGui
from GUI.AppColors import Colors

class QGaugeTrayIcon(QtGui.QPixmap):
    _SIZE = (16, 16)

    def __init__(self, tempColorLimits: Optional[Tuple[Tuple[int,int], Tuple[int,int]]]) -> None:
        super().__init__(*self._SIZE)
        self.fill(QtCore.Qt.transparent)
        self._tempColorLimits = tempColorLimits

    def update(self, temps: Tuple[int, int]) -> None:
        self.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(self)
        font = QtGui.QFont("Consolas", self._SIZE[1] // 2)
        painter.setFont(font)

        def drawVal(y: int, val: int, limits: Optional[Tuple[int,int]]):
            color = Colors.GREEN
            if limits:
                if val >= limits[1]: color = Colors.RED
                elif val >= limits[0]: color = Colors.YELLOW
            painter.setPen(QtGui.QColor.fromRgb(*color.rgb()))
            x = 2 if val < 100 else -1
            painter.drawText(x, y, str(val))

        drawVal(self._SIZE[1] // 2 - 1, temps[0], self._tempColorLimits[0] if self._tempColorLimits else None)
        drawVal(self._SIZE[1], temps[1], self._tempColorLimits[1] if self._tempColorLimits else None)

        painter.end()
