from typing import Callable, Optional, Tuple
from PySide6 import QtCore, QtWidgets
from GUI.QGauge import QGauge
from GUI.AppColors import Colors
import inspect

class ThermalUnitWidget(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget], title: str, tempMinMax: Tuple[int,int], tempColorLimits: Optional[Tuple[int,int]], fanMinMax: Tuple[int,int], sliderMaxAndTick: Tuple[int,int]):
        super().__init__(parent)

        self._title = QtWidgets.QLabel(title, )
        self._title.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self._title.setToolTip("Triple left-click and Crtl+C to copy")

        self._tempBar, _tempBarLabel = self._makeGaugeWithLabel(tempMinMax, ' °C', tempColorLimits)

        self._fanBar, _fanBarLabel = self._makeGaugeWithLabel(fanMinMax, ' RPM')

        self._speedSliderCallback = None
        self._speedSlider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self._speedSlider.setMaximum(sliderMaxAndTick[0])
        self._speedSlider.setTickInterval(sliderMaxAndTick[1])
        self._speedSlider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        _speedSliderLabel = QtWidgets.QLabel("Fan Speed")
        self._speedSliderDebounce = QtCore.QTimer()
        self._speedSliderDebounce.setInterval(500)
        self._speedSliderDebounce.setSingleShot(True)
        self._speedSliderDebounce.timeout.connect(self._onSpeedSliderChange)
        self._speedSlider.valueChanged.connect(lambda: self._speedSliderDebounce.start())
        
        grid = QtWidgets.QGridLayout() # type: QtWidgets.QWidget
        grid.addWidget(self._title,         0, 0, 1, 2, QtCore.Qt.AlignCenter if len(title) < 10 else QtCore.Qt.AlignLeft)
        grid.addWidget(self._tempBar,       1, 0, QtCore.Qt.AlignTop)
        grid.addWidget(_tempBarLabel,       1, 1, QtCore.Qt.AlignLeft)
        grid.addWidget(self._fanBar,        2, 0, QtCore.Qt.AlignTop)
        grid.addWidget(_fanBarLabel,        2, 1, QtCore.Qt.AlignLeft)
        grid.addWidget(self._speedSlider,   3, 0, QtCore.Qt.AlignTop)
        grid.addWidget(_speedSliderLabel,   3, 1, QtCore.Qt.AlignLeft)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        self.setLayout(grid)

    def _makeGaugeWithLabel(self, minMax: Tuple[int,int], units: str, colorLimits: Optional[Tuple[int,int]] = None) -> Tuple[QGauge, QtWidgets.QLabel]:
        g = QGauge()
        g.setTextVisible(False)
        g.setMinimum(minMax[0])
        g.setMaximum(minMax[1])
        if colorLimits:
            g.setColorScheme({colorLimits[0]: Colors.GREEN.value, colorLimits[1]: Colors.YELLOW.value, minMax[1]: Colors.RED.value})
        g.setFormat(f'%v{units}')
        return (g, g.createLabel())

    def setTemp(self, temp: int) -> None:
        self._tempBar.setValue(temp)

    def getTemp(self) -> int:
        return self._tempBar.value()

    def setFanRPM(self, rpm: int) -> None:
        self._fanBar.setValue(rpm)

    def speedSliderChanged(self, callback: Callable) -> None:
        self._speedSliderCallback = callback

    def setSpeedDisabled(self, disabled: bool) -> None:
        self._speedSlider.setDisabled(disabled)

    def getSpeedSlider(self) -> int:
        return self._speedSlider.value()

    def setSpeedSlider(self, value: Optional[int] = None) -> None:
        if value is None: value = (self._speedSlider.minimum() + self._speedSlider.maximum()) // 2
        if value < self._speedSlider.minimum(): value = self._speedSlider.minimum()
        if value > self._speedSlider.maximum(): value = self._speedSlider.maximum()
        self._speedSlider.setValue(value)

    @QtCore.Slot()
    def _onSpeedSliderChange(self) -> None:
        if self._speedSliderCallback:
            self._speedSliderCallback()
