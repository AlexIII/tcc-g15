from typing import Optional, NewType
from Backend.AWCCWmiWrapper import AWCCWmiWrapper
import wmi # type: ignore

class NoAWCCWMIClass(Exception):
    def __init__(self) -> None:
        super().__init__("AWCC WMI class not found in the system")

class CannotInstAWCCWMI(Exception):
    def __init__(self) -> None:
        super().__init__("Couldn't instantiate AWCC WMI class")

class AWCCThermal:
    Mode = AWCCWmiWrapper.ThermalMode
    ModeType = NewType("ModeType", AWCCWmiWrapper.ThermalMode)
    CPUFanIdx = 0
    GPUFanIdx = 1

    def __init__(self, awcc: Optional[AWCCWmiWrapper] = None) -> None:
        if awcc is None:
            try:
                awccClass = wmi.WMI(namespace="root\\WMI").AWCCWmiMethodFunction
            except Exception as ex:
                print(ex)
                raise NoAWCCWMIClass()
            try:
                awcc = AWCCWmiWrapper(awccClass()[0])
            except Exception as ex:
                print(ex)
                raise CannotInstAWCCWMI()
        self._awcc = awcc
        self._fanIdsAndRelatedSensorsIds = self._awcc.GetFanIdsAndRelatedSensorsIds()
        self._fanIds = [ id for id, _ in self._fanIdsAndRelatedSensorsIds ]
        self._sensorIds = [ id for _, ids in self._fanIdsAndRelatedSensorsIds for id in ids ]

    def getAllTemp(self) -> list[Optional[int]]:
        return [ self._awcc.GetSensorTemperature(sensorId) for sensorId in self._sensorIds ]

    def getAllFanRPM(self) -> list[Optional[int]]:
        return [ self._awcc.GetFanRPM(fanId) for fanId in self._fanIds ]

    def setAllFanSpeed(self, speed: int) -> bool:
        res = True
        for fanId in self._fanIds:
            if not self._awcc.SetAddonSpeedPercent(fanId, speed):
                res = False
        return res


    def getFanRelatedTemp(self, fanIdx: int) -> Optional[int]:
        if fanIdx >= len(self._fanIdsAndRelatedSensorsIds):
            return None
        return self._awcc.GetSensorTemperature(self._fanIdsAndRelatedSensorsIds[fanIdx][1][0])

    def getFanRPM(self, fanIdx: int) -> Optional[int]:
        if fanIdx >= len(self._fanIdsAndRelatedSensorsIds):
            return None
        return self._awcc.GetFanRPM(self._fanIdsAndRelatedSensorsIds[fanIdx][0])

    def setFanSpeed(self, fanIdx: int, speed: int) -> bool:
        if fanIdx >= len(self._fanIdsAndRelatedSensorsIds):
            return False
        return self._awcc.SetAddonSpeedPercent(self._fanIdsAndRelatedSensorsIds[fanIdx][0], speed)

    def setMode(self, mode: ModeType) -> bool:
        return self._awcc.ApplyThermalMode(mode)
