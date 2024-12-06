from typing import *
from PySide6 import QtCore, QtGui, QtWidgets
from GUI.AppColors import Colors

class QGaugeTrayIcon(QtGui.QPixmap):
    def __init__(self, tempColorLimits: Optional[Tuple[Tuple[int,int], Tuple[int,int]]]) -> None:
        self._SIZE = QGaugeTrayIcon._bestTrayIconSize()
        super().__init__(*self._SIZE)
        self.fill(QtCore.Qt.transparent)
        self._tempColorLimits = tempColorLimits

    def update(self, temps: Tuple[int, int], stars: bool = False) -> None:
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

        if stars:
            painter.setPen(QtGui.QColor.fromRgb(*Colors.WHITE.rgb()))
            painter.drawPoint(0, 0)
            painter.drawPoint(0, self._SIZE[1]-1)
            painter.drawPoint(self._SIZE[0] - 1, 0)
            painter.drawPoint(self._SIZE[0] - 1, self._SIZE[1]-1)
            if self._SIZE[0] > 16:
                painter.drawPoint(0, 1)
                painter.drawPoint(0, self._SIZE[1] - 2)
                painter.drawPoint(self._SIZE[0] - 1, 1)
                painter.drawPoint(self._SIZE[0] - 1, self._SIZE[1] - 2)

        painter.end()

    @staticmethod
    def _bestTrayIconSize() -> Tuple[int,int]:
        sz = int(QtWidgets.QApplication.style().pixelMetric(QtWidgets.QStyle.PM_SmallIconSize) * QtWidgets.QApplication.primaryScreen().devicePixelRatio())
        return (sz, sz)
