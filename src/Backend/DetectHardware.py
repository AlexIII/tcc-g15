from typing import Optional
import wmi # type: ignore

class DetectHardware:
    CPUFanIdx = 0
    GPUFanIdx = 1

    def __init__(self) -> None:
        self._wmi = wmi.WMI()

    def getHardwareName(self, fanIdx: int) -> Optional[str]:
        if fanIdx == self.CPUFanIdx:
            wmiClass = self._wmi.Win32_Processor
            wmiInst = wmiClass()[0]
            return wmiInst.Name.strip() if hasattr(wmiInst, 'Name') else None
        elif fanIdx == self.GPUFanIdx:
            wmiClass = self._wmi.Win32_VideoController
            wmiInst = max(wmiClass(), key=lambda inst: inst.AdapterRAM & 0xFFFFFFFF if hasattr(inst, 'AdapterRAM') and isinstance(inst.AdapterRAM, int) else 0) # Assume the one with the largest memory is the main GPU
            return wmiInst.Name.strip() if hasattr(wmiInst, 'Name') else None
        else:
            return None