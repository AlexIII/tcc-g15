# WMI Alienware Control Center doc

```
namespace: "root\WMI"
class: AWCCWmiMethodFunction
```

## Constants

```
public enum ThermalMode
{
    Custom = 0,                     // ok
    Quiet = 150,
    Balanced = 151,                 // ok
    Performance = 152,
    FullSpeed = 153,
    USTT_Balanced = 160,
    USTT_Performance = 161,
    USTT_Cool = 162,
    USTT_Quiet = 163,
    USTT_FullSpeed = 164,
    USTT_BatterySaver = 165,
    G_Mode = 171                    // ok
}

public enum SensorID
{
    First = 1,
    Last = 48
}

public enum FanID
{
    First = 49,
    Last = 99
}

FanIDOrder = new int[4] { 50, 59, 51, 60 };
```

## Known methods 


```
Thermal_Information(uint32) -> uint32   (return 0xFFFFFFFF - failure)
    GetSensorTemperature                (return *C)
        arg = (sensorId << 8) | 4
    GetFanRPMPercent                    (return RPMPercent)
        arg = (fanId << 8) | 6
    GetFanRPM                           (return RPM)
        arg = (fanId << 8) | 5

GetFanSensors(uint32) -> uint32         (return 0xFFFFFFFF - failure)
    GetFanRelatedSensorsCountById       (return count)
        arg = (fanId << 8) | 1
    GetFanRelatdSensorsById             (return id)
        arg = (i << 16) | (fanId << 8) | 2        , i = 0..num

Thermal_Control(uint32) -> uint32       (return 0 - success)
    ApplyThermalMode
        arg = (thermalMode << 8) | 1
    SetAddonSpeedPercent
        arg = (addonPercent << 16) | (fanId << 8) | 2
```

## Undocumented methods

```
[WmiMethodId(13), Implemented, read, write, Description("Return Overclocking Report.")] void Return_OverclockingReport([out] uint32 argr);
[WmiMethodId(14), Implemented, read, write, Description("Set OCUIBIOS Control.")] void Set_OCUIBIOSControl([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(15), Implemented, read, write, Description("Clear OC FailSafe Flag.")] void Clear_OCFailSafeFlag([out] uint32 argr);
[WmiMethodId(19), Implemented, read, write, Description("Get Fan Sensors.")] void GetFanSensors([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(20), Implemented, read, write, Description("Thermal Information.")] void Thermal_Information([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(21), Implemented, read, write, Description("Thermal Control.")] void Thermal_Control([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(22), Implemented, read, write, Description("BIOS OC Control.")] void BIOSOCControl([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(23), Implemented, read, write, Description("MemoryOCControl.")] void MemoryOCControl([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(24), Implemented, read, write, Description("Set SW OC Status.")] void SetSWOCStatus([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(25), Implemented, read, write, Description("OC Default Value.")] void OCDefaultValue([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(26), Implemented, read, write, Description("System Information.")] void SystemInformation([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(28), Implemented, read, write, Description("Power Information.")] void PowerInformation([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(32), Implemented, read, write, Description("FW Update GPIO toggle.")] void FWUpdateGPIOtoggle([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(33), Implemented, read, write, Description("Read Total of GPIOs.")] void ReadTotalofGPIOs([out] uint32 argr);
[WmiMethodId(34), Implemented, read, write, Description("Read GPIO pin Status.")] void ReadGPIOpPinStatus([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(35), Implemented, read, write, Description("Read Chassis Color.")] void ReadChassisColor([out] uint32 argr);
[WmiMethodId(36), Implemented, read, write, Description("Read Platform Properties.")] void ReadPlatformProperties([out] uint32 argr);
[WmiMethodId(37), Implemented, read, write, Description("Game Shift Status.")] void GameShiftStatus([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(128), Implemented, read, write, Description("Caldera SW installation.")] void CalderaSWInstallation([out] uint32 argr);
[WmiMethodId(129), Implemented, read, write, Description("Caldera SW is released.")] void CalderaSWReleased([out] uint32 argr);
[WmiMethodId(130), Implemented, read, write, Description("Caldera Connection Status.")] void CalderaConnectionStatus([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(131), Implemented, read, write, Description("Surprise Unplugged Flag Status.")] void SurpriseUnpluggedFlagStatus([out] uint32 argr);
[WmiMethodId(132), Implemented, read, write, Description("Clear Surprise Unplugged Flag.")] void ClearSurpriseUnpluggedFlag([out] uint32 argr);
[WmiMethodId(133), Implemented, read, write, Description("Cancel Undock Request.")] void CancelUndockRequest([out] uint32 argr);
[WmiMethodId(135), Implemented, read, write, Description("Devices in Caldera.")] void DevicesInCaldera([in] uint32 arg2, [out] uint32 argr);
[WmiMethodId(136), Implemented, read, write, Description("Notify BIOS for SW ready to disconnect Caldera.")] void NotifyBIOSForSWReadyToDisconnectCaldera([out] uint32 argr);
[WmiMethodId(160), Implemented, read, write, Description("Tobii SW installation.")] void TobiiSWinstallation([out] uint32 argr);
[WmiMethodId(161), Implemented, read, write, Description("Tobii SW Released.")] void TobiiSWReleased([out] uint32 argr);
[WmiMethodId(162), Implemented, read, write, Description("Tobii Camera Power Reset.")] void TobiiCameraPowerReset([out] uint32 argr);
[WmiMethodId(163), Implemented, read, write, Description("Tobii Camera Power On.")] void TobiiCameraPowerOn([out] uint32 argr);
[WmiMethodId(164), Implemented, read, write, Description("Tobii Camera Power Off.")] void TobiiCameraPowerOff([out] uint32 argr);
```