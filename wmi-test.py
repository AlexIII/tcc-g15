from Backend.AWCCThermal import AWCCThermal, NoAWCCWMIClass, CannotInstAWCCWMI
from time import sleep
import sys

CPU_SENSOR_ID = 1
GPU_SENSOR_ID = 6
CPU_FAN_ID = 0x33
GPU_FAN_ID = 0x32

try:
    therm = AWCCThermal()
    while True:
        print(therm.getAllTemp(), therm.getAllFanRPM())
        sleep(5)

except (NoAWCCWMIClass, CannotInstAWCCWMI) as e:
    print(e)
    sys.exit(0)
