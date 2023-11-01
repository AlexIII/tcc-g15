# Thermal Control Center for Dell G15 5511 / 5515 / 5520 / 5525 / 5530

Open-source alternative to AWCC*

[Download link](https://github.com/AlexIII/tcc-g15/releases) *(Note: the app requires to be run as administrator)*

<img src="./screen-1.png" />

<img src="./screen-2.png" />

**AWCC - "Alienware Control Center" is an app for thermal control that Dell ships with their G-series notebooks.*

## Target platform

OS: Windows 10/11.

Supported Dell G15 models: 5511, 5515, 5520, 5525, 5530.

May also work on other Dell G15 notebooks.

Please report if it worked / didn't work for you. Your feedback is highly appreciated.

_Big thanks to @T7imal, @cemkaya-mpi, @THSLP13 for testing and debugging._

## What it can do

- ✔️ Switch thermal mode between G-mode, Balanced and Custom
- ✔️ Shows GPU/CPU temperature and fan speed
- ✔️ Semi-manual fan speed control
- ✔️ An option to automatically enable G-mode when GPU/CPU temperature reaches critical

## Limitations

- Requires Admin system privileges (in order to access WMI interface)
- Manual fan contoll is not *really* manual. If you set fan speed too low the BIOS will takeover and raise the fan speed automatically when the GPU/CPU temperature reaches certain point to prevent overheating.
- **"Autorun on startup" feature may not work for you.** The autorun adds a task to the Windows Task Scheduler that should start the app on first sign-in after a reboot, but it may fail to run the app due to the system's security policy. You can try other approaches to make the app to autostart on your system. [Checkout this issue.](https://github.com/AlexIII/tcc-g15/issues/7)
- On rare occasions, the driver may report bogus GPU temperature. [See this issue.](https://github.com/AlexIII/tcc-g15/issues/9)

## Why AWCC is BAD

- ❌ AWCC has no in-program option to enable/disable G-mode
- ❌ AWCC manual fan control is broken as per this moment
- ❌ AWCC is bulky, slow and visually noisy app that can't even handle basic functions
- ❌ [AWCC is spying on you](#about-the-awcc-telemetry)
- ❌ AWCC sometimes randomly crashes and throws crash reports

If this alternative works out for you, you can safely remove from your PC:

- Alieanware CC Components
- Alieanware Command Center Suite
- Alieanware OC Controls

## TO-DO

I'll implement these things if the project receives sufficient number of stars*

- ✔️ Minimize to tray (10x ⭐)
- ✔️ Save settings between restarts (20x ⭐)
- ✔️ Autorun on system startup option (30x ⭐)
- ✔️ Adjustable fail-safe threshold temperature, drop out of fail-safe mode after the temperature returns to normal (40x ⭐)
- ✔️ Patch for G15 5511 / 5525
- ✔️ Proper Windows installer (50x ⭐)

*or maybe I'll do it regardless, who knows.

## How it works

It is a PyQt based GUI for WMI Dell thermal control interface.

I somewhat documented my findings on the WMI [here](WMI-AWCC-doc.md).

## How to run from the source

```
python3 -m pip install -r ./requirements.txt
python3 src\tcc-g15.py
```

## About the AWCC telemetry

I know it's probably not gonna surprise anyone, giving the times we're living in, 
but AWCC silently sends some telemetry without the possibility of opting-out.

The telemetry is being sent to these URLs:

```
https://tm-sdk.platinumai.net
https://qa-external-tm.plawebsvc01.net
```

## License

© github.com/AlexIII

GPL v3
