from typing import List, Tuple, Optional, Callable
from PySide6 import QtCore, QtGui, QtWidgets
from GUI.AppColors import Colors

class TemperatureCurve(QtWidgets.QWidget):
    CURVE_POINTS_MIN = 2
    CURVE_POINTS_MAX = 10
    
    def __init__(self, parent=None, 
                 temp_range: Tuple[int, int] = (30, 100), 
                 fan_range: Tuple[int, int] = (0, 100),
                 on_curve_changed: Optional[Callable[[List[Tuple[int, int]]], None]] = None):
        super().__init__(parent)
        
        self.temp_range = temp_range
        self.fan_range = fan_range
        self.points: List[Tuple[int, int]] = []  # [(temp, fan_speed)]
        self.current_point = -1
        self.on_curve_changed = on_curve_changed
        
        # Set default points
        self.reset_points()
        
        # Set curve drawing component properties
        self.setMinimumSize(300, 200)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setMouseTracking(True)
        
        # Create control buttons
        self.add_point_btn = QtWidgets.QPushButton("Add Point", self)
        self.remove_point_btn = QtWidgets.QPushButton("Remove Point", self)
        self.reset_btn = QtWidgets.QPushButton("Reset", self)
        
        # Connect button signals
        self.add_point_btn.clicked.connect(self.add_point)
        self.remove_point_btn.clicked.connect(self.remove_point)
        self.reset_btn.clicked.connect(self.reset_points)
        
        # Create layout
        self.button_layout = QtWidgets.QHBoxLayout()
        self.button_layout.addWidget(self.add_point_btn)
        self.button_layout.addWidget(self.remove_point_btn)
        self.button_layout.addWidget(self.reset_btn)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.addStretch(1)  # Let the curve graph occupy most of the space
        self.main_layout.addLayout(self.button_layout)
        
        # Set tooltips
        self.setToolTip("Left-click: Select/Drag Point\nRight-click: Add New Point\nDouble-click: Remove Point")
        
    def reset_points(self):
        # Set default curve points (30, 30) and (90, 100)
        self.points = [
            (self.temp_range[0], 30),
            (90, 100)
        ]
        self.sort_points()
        self.update()
        self._notify_curve_changed()
        
    def add_point(self):
        if len(self.points) >= self.CURVE_POINTS_MAX:
            return
            
        # Find the largest gap and add a point in the middle
        max_gap = 0
        insert_pos = 0
        
        for i in range(len(self.points) - 1):
            gap = self.points[i+1][0] - self.points[i][0]
            if gap > max_gap:
                max_gap = gap
                insert_pos = i
                
        # Only add if the gap is large enough
        if max_gap > 5:
            new_temp = (self.points[insert_pos][0] + self.points[insert_pos+1][0]) // 2
            new_fan = (self.points[insert_pos][1] + self.points[insert_pos+1][1]) // 2
            self.points.insert(insert_pos + 1, (new_temp, new_fan))
            self.current_point = insert_pos + 1
            self.update()
            self._notify_curve_changed()
    
    def remove_point(self):
        if self.current_point >= 0 and len(self.points) > self.CURVE_POINTS_MIN:
            del self.points[self.current_point]
            self.current_point = -1
            self.update()
            self._notify_curve_changed()
    
    def sort_points(self):
        self.points.sort(key=lambda p: p[0])  # Sort by temperature
    
    def _notify_curve_changed(self):
        if self.on_curve_changed:
            self.on_curve_changed(self.points)
    
    def get_fan_speed_for_temp(self, temp: int) -> int:
        """Calculate fan speed based on current temperature and curve"""
        if not self.points or len(self.points) < 2:
            return 50  # Default value
            
        # If temperature is below the first point
        if temp <= self.points[0][0]:
            return self.points[0][1]
            
        # If temperature is above the last point
        if temp >= self.points[-1][0]:
            return self.points[-1][1]
            
        # Find position in the curve and perform linear interpolation
        for i in range(len(self.points) - 1):
            if self.points[i][0] <= temp <= self.points[i+1][0]:
                t0, f0 = self.points[i]
                t1, f1 = self.points[i+1]
                
                # Linear interpolation to calculate fan speed
                if t1 == t0:  # Avoid division by zero
                    return f0
                ratio = (temp - t0) / (t1 - t0)
                return int(f0 + ratio * (f1 - f0))
                
        return 50  # Default value
    
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Try to select a point
            closest_point = self._find_closest_point(event.position().x(), event.position().y())
            if closest_point >= 0:
                self.current_point = closest_point
                self.update()
        elif event.button() == QtCore.Qt.RightButton and len(self.points) < self.CURVE_POINTS_MAX:
            # Add new point
            temp, fan = self._pixel_to_value(event.position().x(), event.position().y())
            self.points.append((temp, fan))
            self.sort_points()
            self.current_point = self.points.index((temp, fan))
            self.update()
            self._notify_curve_changed()
    
    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            closest_point = self._find_closest_point(event.position().x(), event.position().y())
            if closest_point >= 0 and len(self.points) > self.CURVE_POINTS_MIN:
                del self.points[closest_point]
                self.current_point = -1
                self.update()
                self._notify_curve_changed()
    
    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton and self.current_point >= 0:
            # Drag the currently selected point
            temp, fan = self._pixel_to_value(event.position().x(), event.position().y())
            
            # Restrict temperature range and ensure point order
            if self.current_point > 0:
                temp = max(temp, self.points[self.current_point-1][0] + 1)
            if self.current_point < len(self.points) - 1:
                temp = min(temp, self.points[self.current_point+1][0] - 1)
                
            # Restrict within valid range
            temp = max(self.temp_range[0], min(self.temp_range[1], temp))
            fan = max(self.fan_range[0], min(self.fan_range[1], fan))
            
            self.points[self.current_point] = (temp, fan)
            self.update()
            self._notify_curve_changed()
    
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.current_point >= 0:
            self._notify_curve_changed()
    
    def _find_closest_point(self, x, y, max_distance=10):
        """Find the closest point to the mouse position"""
        closest_dist = float('inf')
        closest_idx = -1
        
        for i, (temp, fan) in enumerate(self.points):
            px, py = self._value_to_pixel(temp, fan)
            dist = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            
            if dist < closest_dist and dist < max_distance:
                closest_dist = dist
                closest_idx = i
                
        return closest_idx
    
    def _pixel_to_value(self, x, y):
        """Convert pixel coordinates to temperature and fan values"""
        width, height = self.width(), self.height() - self.button_layout.sizeHint().height()
        margin = 30  # Margin
        
        # Drawing area
        graph_width = width - 2 * margin
        graph_height = height - 2 * margin
        
        # Conversion
        temp_range = self.temp_range[1] - self.temp_range[0]
        fan_range = self.fan_range[1] - self.fan_range[0]
        
        temp = self.temp_range[0] + temp_range * (x - margin) / graph_width
        fan = self.fan_range[1] - fan_range * (y - margin) / graph_height
        
        return int(round(temp)), int(round(fan))
    
    def _value_to_pixel(self, temp, fan):
        """Convert temperature and fan values to pixel coordinates"""
        width, height = self.width(), self.height() - self.button_layout.sizeHint().height()
        margin = 30  # Margin
        
        # Drawing area
        graph_width = width - 2 * margin
        graph_height = height - 2 * margin
        
        # Conversion
        temp_range = self.temp_range[1] - self.temp_range[0]
        fan_range = self.fan_range[1] - self.fan_range[0]
        
        x = margin + graph_width * (temp - self.temp_range[0]) / temp_range
        y = margin + graph_height * (self.fan_range[1] - fan) / fan_range
        
        return x, y
    
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        width, height = self.width(), self.height() - self.button_layout.sizeHint().height()
        margin = 30  # Margin
        
        # Drawing area
        graph_width = width - 2 * margin
        graph_height = height - 2 * margin
        
        # Draw axes
        painter.setPen(QtGui.QPen(QtGui.QColor(Colors.GREY.value), 1))
        painter.drawRect(margin, margin, graph_width, graph_height)
        
        # Draw temperature scale
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        
        steps = 7  # Number of segments
        step_size = (self.temp_range[1] - self.temp_range[0]) // steps
        for i in range(steps + 1):
            temp = self.temp_range[0] + i * step_size
            x = margin + (temp - self.temp_range[0]) * graph_width / (self.temp_range[1] - self.temp_range[0])
            painter.drawLine(int(x), height - margin, int(x), height - margin + 5)
            painter.drawText(int(x) - 10, height - margin + 20, f"{temp}°C")
        
        # Draw fan speed scale
        steps = 5
        step_size = (self.fan_range[1] - self.fan_range[0]) // steps
        for i in range(steps + 1):
            fan = self.fan_range[0] + i * step_size
            y = height - margin - (fan - self.fan_range[0]) * graph_height / (self.fan_range[1] - self.fan_range[0])
            painter.drawLine(margin - 5, int(y), margin, int(y))
            painter.drawText(margin - 25, int(y) + 5, f"{fan}%")
        
        # Draw labels
        painter.drawText(width // 2 - 20, height - 5, "Temperature")
        painter.save()
        painter.translate(5, height // 2)
        painter.rotate(-90)
        painter.drawText(0, 0, "Fan Speed")
        painter.restore()
        
        # Draw curve
        if len(self.points) > 1:
            path = QtGui.QPainterPath()
            for i, (temp, fan) in enumerate(self.points):
                x, y = self._value_to_pixel(temp, fan)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            
            painter.setPen(QtGui.QPen(QtGui.QColor(Colors.BLUE.value), 2))
            painter.drawPath(path)
        
        # Draw points
        for i, (temp, fan) in enumerate(self.points):
            x, y = self._value_to_pixel(temp, fan)
            if i == self.current_point:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(Colors.RED.value)))
                painter.setPen(QtGui.QPen(QtGui.QColor(Colors.WHITE.value), 1))
                painter.drawEllipse(QtCore.QPointF(x, y), 6, 6)
            else:
                painter.setBrush(QtGui.QBrush(QtGui.QColor(Colors.GREEN.value)))
                painter.setPen(QtGui.QPen(QtGui.QColor(Colors.WHITE.value), 1))
                painter.drawEllipse(QtCore.QPointF(x, y), 5, 5)
            
            # Draw point values
            painter.setPen(QtGui.QPen(QtGui.QColor(Colors.WHITE.value), 1))
            painter.drawText(int(x) + 7, int(y) - 7, f"({temp},{fan})")
        
        painter.end()

    def set_points(self, points: List[Tuple[int, int]]):
        """Set curve points"""
        if len(points) < self.CURVE_POINTS_MIN:
            return
            
        self.points = points.copy()
        self.sort_points()
        self.update()
        self._notify_curve_changed()
    
    def get_points(self) -> List[Tuple[int, int]]:
        """Get curve points"""
        return self.points.copy()
