from typing import *
from PySide6 import QtCore, QtGui, QtWidgets
from GUI.AppColors import Colors

class QGaugeTrayIcon(QtGui.QPixmap):
    def __init__(self, tempColorLimits: Optional[Tuple[Tuple[int,int], Tuple[int,int]]]) -> None:
        self._SIZE = QGaugeTrayIcon._bestTrayIconSize()
        super().__init__(*self._SIZE)
        self.fill(QtCore.Qt.transparent)
        self._tempColorLimits = tempColorLimits

    def resizeForScreen(self) -> Optional["QGaugeTrayIcon"]:
        if self._SIZE == QGaugeTrayIcon._bestTrayIconSize():
            return None
        return QGaugeTrayIcon(self._tempColorLimits)

    def update(self, temps: Tuple[int, int], stars: bool = False) -> None:
        self.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(self)
        font = QtGui.QFont("Consolas", self._SIZE[1] // 2)
        painter.setFont(font)

        def drawVal(y: int, val: Optional[int], limits: Optional[Tuple[int,int]]): # val can now be Optional[int]
            text_to_draw = "--"
            # Default color, perhaps a bit dimmer or distinct for placeholder
            color_rgb = Colors.GREY.rgb()

            if val is not None:
                text_to_draw = str(val)
                # Determine color based on value and limits
                current_color_enum = Colors.GREEN # Default for valid numbers
                if limits:
                    if val >= limits[1]: current_color_enum = Colors.RED
                    elif val >= limits[0]: current_color_enum = Colors.YELLOW
                color_rgb = current_color_enum.rgb()

            painter.setPen(QtGui.QColor.fromRgb(*color_rgb))

            # Simplified x calculation:
            if val is not None:
                if val >= 100 or val <= -10: # 3+ digits or negative with 2+ digits
                    x = -1
                elif val >= 0 and val < 10: # 1 digit positive
                    x = 3 # Shift right for single digit
                else: # 2 digits, or negative single digit
                    x = 1
            else: # val is None, text_to_draw is "--"
                x = 1 # Position for "--"

            painter.drawText(x, y, text_to_draw)

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
