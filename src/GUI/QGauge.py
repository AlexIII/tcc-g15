from typing import Optional
from PySide6 import QtCore, QtWidgets

class QGauge(QtWidgets.QProgressBar):
    _colorScheme: Optional[dict[int, str]]
    _extLabel: Optional[QtWidgets.QLabel]

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName('QGauge')
        self._updColor_connected = False
        self._colorScheme = None
        self._extLabel = None

    def setColorScheme(self, colorScheme: dict[int, str]) -> None:
        self._colorScheme = colorScheme
        self._updateColor()

    def createLabel(self) -> QtWidgets.QLabel:
        if not self._extLabel:
            self._extLabel = QtWidgets.QLabel()
        return self._extLabel

    def setValue(self, value: int):
        # Update label
        if self._extLabel:
            self._extLabel.setText(self.format().replace('%v', str(value)))
        if value < self.minimum(): value = self.minimum()
        if value > self.maximum(): value = self.maximum()
        super().setValue(value)
        self._updateColor()

    def _updateColor(self):
        if self._colorScheme:
            val = self.value()
            color = '#000'
            for lim, c in self._colorScheme.items():
                color = c
                if val < lim: break
            self.setStyleSheet(f"QGauge::chunk {{background: {color};}}")
