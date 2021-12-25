from enum import Enum
from typing import Optional, Tuple
import wmi # type: ignore

class AWCCWmiWrapper:
    SENSOR_ID_FIRST = 0x01
    SENSOR_ID_LAST = 0x30
    FAN_ID_FIRST = 0x31
    FAN_ID_LAST = 0x63

    class ThermalMode(Enum):
        Custom = 0
        Balanced = 0x97
        G_Mode = 0xAB

    def __init__(self, awcc: wmi._wmi_object) -> None:
        self._awcc = awcc

    def GetSensorTemperature(self, sensorId: int) -> Optional[int]:
        if not (sensorId in range(self.SENSOR_ID_FIRST, self.SENSOR_ID_LAST + 1)): return None
        arg = ((sensorId & 0xFF) << 8) | 4
        return self._call('Thermal_Information', arg)

    def GetFanRPMPercent(self, fanId: int) -> Optional[int]:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return None
        arg = ((fanId & 0xFF) << 8) | 6
        return self._call('Thermal_Information', arg)

    def GetFanRPM(self, fanId: int) -> Optional[int]:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return None
        arg = ((fanId & 0xFF) << 8) | 5
        return self._call('Thermal_Information', arg)


    def GetFanRelatedSensorsCountById(self, fanId: int) -> Optional[int]:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return None
        arg = ((fanId & 0xFF) << 8) | 1
        return self._call('GetFanSensors', arg)

    def GetFanRelatdSensorsById(self, fanId: int, sensorIndex: int) -> Optional[int]:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return None
        arg = ((sensorIndex & 0xFF) << 16) | ((fanId & 0xFF) << 8) | 2
        return self._call('GetFanSensors', arg)

    def GetFanIdsAndRelatedSensorsCount(self) -> list[Tuple[int, int]]:
        res: list[Tuple[int, int]] = []
        for idx in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1):
            count = self.GetFanRelatedSensorsCountById(idx)
            if count is not None and count > 0: res.append((idx, count))
        return res

    def GetFanIdsAndRelatedSensorsIds(self) -> list[Tuple[int, Tuple[int, ...]]]:
        return [ 
            (
                fanId, 
                tuple(
                    id for id in (
                        self.GetFanRelatdSensorsById(fanId, idx) for idx in range(sensorCount)
                    ) if id is not None
                )
            ) for fanId, sensorCount in self.GetFanIdsAndRelatedSensorsCount() 
        ]


    def ApplyThermalMode(self, mode: ThermalMode) -> bool:
        if not isinstance(mode, self.ThermalMode):
            raise Exception('Invalid argument: mode is not instance of ThermalMode')
        arg = ((mode.value & 0xFF) << 8) | 1
        return self._call('Thermal_Control', arg) == 0

    def SetAddonSpeedPercent(self, fanId: int, speed: int) -> bool:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return False
        if speed > 0xFF: speed = 0xFF
        arg = ((speed & 0xFF) << 16) | ((fanId & 0xFF) << 8) | 2
        return self._call('Thermal_Control', arg) == 0

        
    def _call(self, method: str, arg: int) -> Optional[int]:
        if not hasattr(self._awcc, method) or not callable(getattr(self._awcc, method)):
            return None
        val: int = getattr(self._awcc, method)(arg)[0]
        if not isinstance(val, int) or val == -1 or val == 0xFFFFFFFF: 
            return None
        return val
