from enum import Enum
from typing import Optional, Tuple
import logging
import time
from wmi import _wmi_object # type: ignore

log = logging.getLogger(__name__)

class AWCCWmiWrapper:
    SENSOR_ID_FIRST = 0x01
    SENSOR_ID_LAST = 0x30
    FAN_ID_FIRST = 0x31
    FAN_ID_LAST = 0x63

    class ThermalMode(Enum):
        Custom = 0
        Balanced = 0x97
        G_Mode = 0xAB

    _USTT_Balanced = 0xA0

    def __init__(self, awcc: _wmi_object) -> None:
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
        candidates = (mode.value,)
        if mode == self.ThermalMode.Balanced:
            # Query each transition; a cached failed USTT probe (False) must
            # never become the Custom profile ID (0).
            value = self._call('Thermal_Information', 0x0A)
            if value not in (self.ThermalMode.Balanced.value, self._USTT_Balanced):
                log.error('Invalid or unavailable Balanced profile ID: %r', value)
                return False
            candidates = (value, self.ThermalMode.Balanced.value) if value == self._USTT_Balanced else (value,)

        for value in candidates:
            if not self._Thermal_Control(value):
                log.warning('Thermal profile %d was rejected', value)
                continue
            # Allow a short firmware settling period, but never report success
            # solely from the command status (0).
            for attempt in range(3):
                if attempt:
                    time.sleep(0.1)
                actual = self._call('Thermal_Information', 0x0B)
                if actual == value:
                    return True
            log.error('Thermal profile readback mismatch: expected=%d, actual=%r', value, actual)
        return False

    def SetAddonSpeedPercent(self, fanId: int, speed: int) -> bool:
        if not (fanId in range(self.FAN_ID_FIRST, self.FAN_ID_LAST + 1)): return False
        if speed > 0xFF: speed = 0xFF
        arg = ((speed & 0xFF) << 16) | ((fanId & 0xFF) << 8) | 2
        return self._call('Thermal_Control', arg) == 0

    def _Thermal_Control(self, arg: int) -> bool:
        if type(arg) is not int or not 0 <= arg <= 0xFF:
            return False
        arg = ((arg & 0xFF) << 8) | 1
        return self._call('Thermal_Control', arg) == 0
        
    def _call(self, method: str, arg: int) -> Optional[int]:
        try:
            func = getattr(self._awcc, method, None)
            if not callable(func):
                return None
            result = func(arg)
            if not isinstance(result, (tuple, list)) or len(result) != 1:
                return None
            val = result[0]
        except Exception:
            log.exception('WMI %s failed (arg=0x%08X)', method, arg)
            return None
        # bool subclasses int, but is neither a profile ID nor a WMI status.
        if type(val) is not int or not 0 <= val < 0xFFFFFFFF:
            return None
        return val
