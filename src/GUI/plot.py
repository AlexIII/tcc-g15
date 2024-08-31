import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QSizePolicy
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import matplotlib.pyplot as plt

from src.GUI.AppColors import Colors

plt.style.use({
    'figure.facecolor': '#000000',
    'axes.facecolor': '#000000',
    'axes.edgecolor': '#ffffff',
    'axes.labelcolor': '#ffffff',
    'xtick.color': '#ffffff',
    'ytick.color': '#ffffff',
    'text.color': '#ffffff',
    'lines.color': '#ffffff',
    'patch.edgecolor': '#ffffff',
    'patch.facecolor': '#cccccc',
})


class MplCanvas(FigureCanvas):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi, frameon=False)
        fig.patch.set_facecolor('black')
        fig.subplots_adjust(left=0.1, bottom=0.1, right=0.9, top=0.9)
        self.axes = fig.add_subplot(111)
        super(MplCanvas, self).__init__(fig)

class InteractiveTemperatureFanCurve(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.buttonbox = QVBoxLayout()
        self.setLayout(self.layout)


        self.setFixedSize(600, 250)

        # 创建一个 Matplotlib 图表
        self.canvas = MplCanvas(self, width=5, height=2, dpi=100)
        self.layout.addWidget(self.canvas)



        # 添加切换按钮
        self.switch_button = QPushButton('Switch to GPU', self)
        self.switch_button.clicked.connect(self.switch_active_line)

        self.buttonbox.addWidget(self.switch_button)
        self.layout.addLayout(self.buttonbox)
        # 初始化数据
        self.cpu_temperature = [0, 100]  # 温度范围 0-100
        self.cpu_fan_speed = [0, 100]  # 风扇速度范围 0-100
        self.gpu_temperature = [0, 100]
        self.gpu_fan_speed = [0, 100]

        # 初始化绘图元素
        self.line_cpu = None  # 保存折线图的Line2D对象
        self.line_gpu = None
        self.points_cpu = []  # 保存所有点的Line2D对象
        self.points_gpu = []
        self.active_line = 'cpu'  # 初始激活的折线图

        # 绘制初始折线图
        self.plot()

        # 添加鼠标点击事件
        self.canvas.mpl_connect('button_press_event', self.on_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_release_event', self.on_release)

        # 初始化鼠标状态
        self.press = None
        self.selected_point_index = None



    def switch_active_line(self):
        if self.active_line == 'cpu':
            self.active_line = 'gpu'
            self.switch_button.setText('Switch to CPU')
        else:
            self.active_line = 'cpu'
            self.switch_button.setText('Switch to GPU')
        self.plot()  # 重新绘制图表以突出显示当前激活的折线图

    def plot(self):


        self.canvas.axes.clear()
        if self.active_line == 'cpu':
            self.line_cpu, = self.canvas.axes.plot(self.cpu_temperature , self.cpu_fan_speed , 'g-', lw=2)
            self.line_gpu, = self.canvas.axes.plot(self.gpu_temperature, self.gpu_fan_speed , 'r--')
        else:
            self.line_cpu, = self.canvas.axes.plot(self.cpu_temperature , self.cpu_fan_speed , 'g--')
            self.line_gpu, = self.canvas.axes.plot(self.gpu_temperature , self.gpu_fan_speed , 'r-', lw=2)

        self.canvas.axes.set_xlim(0, 100)
        self.canvas.axes.set_ylim(0, 100)
        self.canvas.axes.set_xlabel('Temperature (°C)')
        self.canvas.axes.set_ylabel('Fan Speed (%)')
        self.canvas.axes.legend([self.line_cpu, self.line_gpu], ['CPU', 'GPU'],loc='lower right')
        self.canvas.axes.grid(True)

        # 高亮显示所有的点
        if self.active_line == 'cpu':
            if not self.points_cpu:
                for i, (temp, speed) in enumerate(zip(self.cpu_temperature, self.cpu_fan_speed)):
                    point, = self.canvas.axes.plot(temp, speed, 'go')
                    self.points_cpu.append(point)
            else:
                for i, (temp, speed) in enumerate(zip(self.cpu_temperature, self.cpu_fan_speed)):
                    self.canvas.axes.plot(temp, speed, 'go')
        else:
            if not self.points_gpu:
                for i, (temp, speed) in enumerate(zip(self.gpu_temperature, self.gpu_fan_speed)):
                    point, = self.canvas.axes.plot(temp, speed, 'ro')
                    self.points_gpu.append(point)
            else:
                for i, (temp, speed) in enumerate(zip(self.gpu_temperature, self.gpu_fan_speed)):
                    self.canvas.axes.plot(temp, speed, 'ro')
        self.canvas.draw_idle()

    def on_press(self, event):

        if event.inaxes != self.canvas.axes:
            return
        active_temperatures, active_fan_speeds, active_points,_ = self.get_active_data()
        if len(active_temperatures) > 1:  # 至少有两个点才能进行距离计算
            distances = [np.sqrt((event.xdata - t) ** 2 + (event.ydata - s) ** 2) for t, s in
                         zip(active_temperatures, active_fan_speeds)]
            min_distance_index = np.argmin(distances)
            if distances[min_distance_index] < 5:
                self.selected_point_index = min_distance_index
                self.canvas.draw_idle()
            else:
                # 如果点击位置靠近折线，则创建新点
                if self._is_near_line(event.xdata, event.ydata):
                    self.insert_new_point(event.xdata, event.ydata)

    def insert_new_point(self, x, y):
        active_temperatures, active_fan_speeds, active_points,_ = self.get_active_data()
        insert_index = self.find_insertion_index(x, active_temperatures)
        if insert_index is not None:
            active_temperatures.insert(insert_index, x)
            active_fan_speeds.insert(insert_index, y)
            point, = self.canvas.axes.plot(x, y, 'ro' if self.active_line == 'gpu' else 'go')
            active_points.insert(insert_index, point)
            self.update_active_line(active_temperatures, active_fan_speeds)
            self.canvas.draw_idle()

    def find_insertion_index(self, x, temperatures):
        for i in range(len(temperatures) - 1):
            if x >= temperatures[i] and x <= temperatures[i + 1]:
                return i + 1
        return None

    def _is_near_line(self, x, y):
        active_temperatures, active_fan_speeds, _ ,_= self.get_active_data()
        for i in range(len(active_temperatures) - 1):
            d = self._distance_from_line_segment(x, y, active_temperatures[i], active_fan_speeds[i], active_temperatures[i + 1], active_fan_speeds[i + 1])
            if d < 3:
                return True
        return False

    def _distance_from_line_segment(self, x, y, x1, y1, x2, y2):
        dx, dy = x2 - x1, y2 - y1
        t = ((x - x1) * dx + (y - y1) * dy) / (dx ** 2 + dy ** 2)
        if t < 0:
            closest_x, closest_y = x1, y1
        elif t > 1:
            closest_x, closest_y = x2, y2
        else:
            closest_x, closest_y = x1 + t * dx, y1 + t * dy
        distance = np.sqrt((x - closest_x) ** 2 + (y - closest_y) ** 2)
        return distance

    def on_motion(self, event):
        if self.selected_point_index is None or event.inaxes != self.canvas.axes:
            return
        active_temperatures, active_fan_speeds, active_points ,_= self.get_active_data()
        new_temp = event.xdata
        new_speed = event.ydata
        if 0 <= new_temp <= 100 and 0 <= new_speed <= 100:
            active_temperatures[self.selected_point_index] = new_temp
            active_fan_speeds[self.selected_point_index] = new_speed
            # 输出points的地址
            # print(hex(id(active_points)))
            active_points[self.selected_point_index].set_data([new_temp], [new_speed])
            self.update_active_line(active_temperatures, active_fan_speeds)
            self.canvas.draw_idle()  # 立即刷新图形
    def on_release(self, event):
        self.selected_point_index = None
        active_temperatures, active_fan_speeds, active_points, avtive_line = self.get_active_data()
        if 100 not in active_temperatures:
            # 如果没有，则找到当前温度的最大值索引
            max_temp_index = active_temperatures.index(max(active_temperatures))
            # 将最大温度值设为100
            active_temperatures[max_temp_index] = 100
            # 更新对应点的位置
            active_points[max_temp_index].set_data([100], [active_fan_speeds[max_temp_index]])
        avtive_line.set_data(active_temperatures, active_fan_speeds)
        self.canvas.draw_idle()


    def get_active_data(self):
        if self.active_line == 'cpu':
            return self.cpu_temperature, self.cpu_fan_speed, self.points_cpu, self.line_cpu
        else:
            return self.gpu_temperature, self.gpu_fan_speed, self.points_gpu, self.line_gpu


    def update_active_line(self, temperatures, fan_speeds):
        if self.active_line == 'cpu':
            self.cpu_temperature = temperatures
            self.cpu_fan_speed = fan_speeds
            self.line_cpu.set_data(self.cpu_temperature, self.cpu_fan_speed)
        else:
            self.gpu_temperature = temperatures
            self.gpu_fan_speed = fan_speeds
            self.line_gpu.set_data(self.gpu_temperature, self.gpu_fan_speed)

    def get_plot_data(self):
        return (self.cpu_temperature, self.cpu_fan_speed, self.gpu_temperature, self.gpu_fan_speed)

    def set_plot_data(self,data):
        self.cpu_temperature, self.cpu_fan_speed, self.gpu_temperature, self.gpu_fan_speed = data
        self.plot()

    def get_fan_speeds(self):
        # 获取当前的温度和风扇速度数据点
        temperatures = np.array(self.temperature)
        fan_speeds = np.array(self.fan_speed)
        temperature_range = np.arange(1, 101)
        interpolated_fan_speeds = np.interp(temperature_range, temperatures, fan_speeds)
        interpolated_fan_speeds = np.round(interpolated_fan_speeds)
        return interpolated_fan_speeds
    def get_plot_fanspeed(self, temp):
        return self.get_fan_speeds()[temp]
class Plot_Tem_Speed(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        widget = InteractiveTemperatureFanCurve()
#        将widget设置在左上角
        self.setCentralWidget(widget)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Plot_Tem_Speed()
    window.setStyleSheet(f"""
        QGauge {{
            border: 1px solid gray;
            border-radius: 3px;
            background-color: {Colors.GREY.value};
        }}
        QGauge::chunk {{
            background-color: {Colors.BLUE.value};
        }}
        * {{
            color: {Colors.WHITE.value};
            background-color: {Colors.DARK_GREY.value};
        }}
        QToolTip {{
            background-color: black; 
            color: {Colors.WHITE.value};
            border: 1px solid {Colors.DARK_GREY.value};
            border-radius: 3;
        }}
        QComboBox {{
            border: 1px solid gray;
            border-radius: 3px;
            padding: 1px 0.6em 1px 3px;
        }}
        QComboBox::disabled {{
            color: {Colors.GREY.value};
        }}
    """)
    window.show()
    sys.exit(app.exec())
