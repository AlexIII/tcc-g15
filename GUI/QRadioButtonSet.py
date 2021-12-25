from typing import Callable, Optional, Tuple, Union
from PySide6 import QtCore, QtWidgets

class QRadioButtonSet(QtWidgets.QWidget):
    _buttons: dict[str, QtWidgets.QRadioButton]
    _userCallback: Optional[Callable[[str], None]]

    def __init__(self, parent: Optional[QtWidgets.QWidget], title: Optional[str], options: list[Tuple[str, str]], layout: Union[QtWidgets.QHBoxLayout, QtWidgets.QVBoxLayout] = QtWidgets.QHBoxLayout()) -> None:
        super().__init__(parent)
        if len(options) == 0:
            raise RuntimeError('"options" list length can not be 0')

        self.setLayout(layout)

        if title:
            layout.addWidget(QtWidgets.QLabel(title))

        self._userCallback = None

        self._buttons = {}
        for title, value in options:
            rb = QtWidgets.QRadioButton(title)
            rb._value = value
            layout.addWidget(rb)
            self._buttons[value] = rb
            rb.setChecked(True)
            rb.toggled.connect(self._onClicked)

    def setChecked(self, value: str):
        self._buttons[value].setChecked(True)

    def getChecked(self) -> Optional[str]:
        for rb in self._buttons.values():
            if rb.isChecked():
                return rb._value
        return None

    def setOnChange(self, callback: Callable[[str], None]) -> None:
        self._userCallback = callback

    @QtCore.Slot()
    def _onClicked(self):
        rb = self.sender() # type: QtWidgets.QRadioButton
        if self._userCallback and rb.isChecked():
            self._userCallback(rb._value)