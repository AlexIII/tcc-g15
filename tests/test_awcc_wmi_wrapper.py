"""Hardware-free regression tests: python -m unittest discover -s tests -v."""
import sys
import importlib
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def no_wmi(*args, **kwargs):
    raise AssertionError('Real WMI connections are forbidden in these tests')


# Importing the real wmi module can itself connect to winmgmts. Stub it before
# importing either backend module; the tests need no Windows packages.
wmi_stub = types.ModuleType('wmi')
wmi_stub._wmi_object = object
wmi_stub.WMI = no_wmi
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
with patch.dict(sys.modules, {'wmi': wmi_stub}):
    wrapper_module = importlib.import_module('Backend.AWCCWmiWrapper')
    from Backend.AWCCWmiWrapper import AWCCWmiWrapper
    from Backend.AWCCThermal import AWCCThermal


CURRENT = object()


class FakeWMI:
    def __init__(self, balanced=151, statuses=None, readback=CURRENT):
        self.balanced = balanced
        self.statuses = statuses or {}
        self.readback = readback
        self.active = 171
        self.reads = []
        self.writes = []

    def Thermal_Information(self, arg):
        self.reads.append(arg)
        if arg == 10:
            result = self.balanced
        elif arg == 11:
            result = self.active if self.readback is CURRENT else self.readback
        else:
            result = 4200 if arg & 255 == 5 else 55
        if isinstance(result, Exception):
            raise result
        return (result,)

    def Thermal_Control(self, arg):
        self.writes.append(arg)
        result = self.statuses.get(arg >> 8, 0) if arg & 255 == 1 else 0
        if isinstance(result, Exception):
            raise result
        if type(result) is int and result == 0 and arg & 255 == 1:
            self.active = arg >> 8
        return (result,)

    def GetFanSensors(self, arg):
        return (int(arg >> 8 in (50, 51)) if arg & 255 == 1 else 1,)


class ThermalModeTests(unittest.TestCase):
    def setUp(self):
        sleeper = patch.object(wrapper_module.time, 'sleep')
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        logger = patch.object(wrapper_module, 'log')
        self.log = logger.start()
        self.addCleanup(logger.stop)

    def apply(self, firmware, mode='Balanced'):
        wrapper = AWCCWmiWrapper(firmware)
        return wrapper.ApplyThermalMode(wrapper.ThermalMode[mode])

    def test_standard_profile_skips_unsupported_ustt(self):
        firmware = FakeWMI(statuses={160: -1})
        self.assertTrue(self.apply(firmware))
        self.assertEqual(firmware.writes, [0x9701])
        self.assertEqual(firmware.active, 151)

    def test_ustt_profile_is_applied_once(self):
        firmware = FakeWMI(balanced=160)
        self.assertTrue(self.apply(firmware))
        self.assertEqual(firmware.writes, [0xA001])
        self.assertEqual(firmware.active, 160)

    def test_ustt_failure_falls_back_to_verified_standard(self):
        firmware = FakeWMI(balanced=160, statuses={160: -1})
        self.assertTrue(self.apply(firmware))
        self.assertEqual(firmware.writes, [0xA001, 0x9701])
        self.assertEqual(firmware.active, 151)

    def test_both_balanced_profiles_rejected(self):
        firmware = FakeWMI(balanced=160, statuses={160: 1, 151: 1})
        self.assertFalse(self.apply(firmware))
        self.assertEqual(firmware.writes, [0xA001, 0x9701])
        self.log.warning.assert_called()

    def test_old_cached_values_cannot_select_custom(self):
        for cached in (False, None, 0, 151, 160):
            with self.subTest(cached=cached):
                firmware = FakeWMI()
                wrapper = AWCCWmiWrapper(firmware)
                wrapper._balancedModePatch = cached
                self.assertTrue(wrapper.ApplyThermalMode(wrapper.ThermalMode.Balanced))
                self.assertEqual(firmware.writes, [0x9701])

    def test_custom_and_g_mode_ids_are_preserved(self):
        for mode, profile in (('Custom', 0), ('G_Mode', 171)):
            with self.subTest(mode=mode):
                firmware = FakeWMI()
                self.assertTrue(self.apply(firmware, mode))
                self.assertEqual(firmware.writes, [(profile << 8) | 1])
                self.assertEqual(firmware.active, profile)
                self.assertEqual(firmware.reads, [11])

    def test_invalid_balanced_query_never_writes(self):
        for value in (None, -1, 0xFFFFFFFF, False, True, 0, 171, 256, RuntimeError('WMI error')):
            with self.subTest(value=value):
                firmware = FakeWMI(balanced=value)
                self.assertFalse(self.apply(firmware))
                self.assertEqual(firmware.writes, [])

    def test_invalid_control_status_is_not_success(self):
        for value in (None, -1, 0xFFFFFFFF, False, True, 1, 256, RuntimeError('WMI error')):
            with self.subTest(value=value):
                firmware = FakeWMI(statuses={151: value})
                self.assertFalse(self.apply(firmware))
                self.assertEqual(firmware.writes, [0x9701])
                self.assertNotIn(11, firmware.reads)

    def test_success_status_requires_matching_readback(self):
        for value in (None, -1, 0xFFFFFFFF, False, True, 0, 171, 256, RuntimeError('WMI error')):
            with self.subTest(value=value):
                firmware = FakeWMI(readback=value)
                self.assertFalse(self.apply(firmware))
                self.assertEqual(firmware.reads.count(11), 3)
                self.assertEqual(firmware.writes, [0x9701])
                self.log.error.assert_called()

    def test_special_modes_also_require_readback(self):
        for mode in ('Custom', 'G_Mode'):
            with self.subTest(mode=mode):
                self.assertFalse(self.apply(FakeWMI(readback=151), mode))

    def test_readback_can_settle_on_second_attempt(self):
        firmware = FakeWMI()
        original = firmware.Thermal_Information
        values = iter((0, 151))
        firmware.Thermal_Information = lambda arg: (next(values),) if arg == 11 else original(arg)
        self.assertTrue(self.apply(firmware))
        self.sleep.assert_called_once_with(0.1)

    def test_ustt_readback_mismatch_can_fall_back(self):
        firmware = FakeWMI(balanced=160, readback=151)
        self.assertTrue(self.apply(firmware))
        self.assertEqual(firmware.writes, [0xA001, 0x9701])
        self.assertEqual(firmware.reads.count(11), 4)

    def test_mode_transitions_refresh_profile_support(self):
        firmware = FakeWMI(balanced=160)
        wrapper = AWCCWmiWrapper(firmware)
        for mode in ('Balanced', 'G_Mode', 'Custom'):
            self.assertTrue(wrapper.ApplyThermalMode(wrapper.ThermalMode[mode]))
        firmware.balanced = 151
        self.assertTrue(wrapper.ApplyThermalMode(wrapper.ThermalMode.Balanced))
        self.assertEqual(firmware.writes, [0xA001, 0xAB01, 1, 0x9701])
        self.assertEqual(firmware.reads.count(10), 2)

    def test_failed_attempt_does_not_poison_next_transition(self):
        firmware = FakeWMI(balanced=160, statuses={160: 1, 151: 1})
        wrapper = AWCCWmiWrapper(firmware)
        self.assertFalse(wrapper.ApplyThermalMode(wrapper.ThermalMode.Balanced))
        firmware.balanced, firmware.statuses = 151, {}
        self.assertTrue(wrapper.ApplyThermalMode(wrapper.ThermalMode.Balanced))
        self.assertEqual(firmware.writes[-1], 0x9701)

    def test_invalid_profile_arguments_never_write(self):
        for value in (False, None, -1, 256, 0xFFFFFFFF):
            with self.subTest(value=value):
                firmware = FakeWMI()
                self.assertFalse(AWCCWmiWrapper(firmware)._Thermal_Control(value))
                self.assertEqual(firmware.writes, [])

    def test_malformed_wmi_results_are_rejected(self):
        for result in (None, (), [], (0, 0), (None,), (False,), ('0',), (0x100000000,)):
            with self.subTest(result=result):
                firmware = FakeWMI()
                firmware.Thermal_Control = lambda arg: result
                self.assertFalse(self.apply(firmware, 'Custom'))

    def test_missing_method_is_a_failure(self):
        self.assertFalse(self.apply(object()))

    def test_invalid_mode_is_rejected_without_writes(self):
        firmware = FakeWMI()
        with self.assertRaisesRegex(Exception, 'Invalid argument'):
            AWCCWmiWrapper(firmware).ApplyThermalMode(False)
        self.assertEqual(firmware.writes, [])

    def test_existing_backend_telemetry_and_boost_contracts(self):
        firmware = FakeWMI()
        backend = AWCCThermal(AWCCWmiWrapper(firmware))
        self.assertEqual(backend.getAllFanRPM(), [4200, 4200])
        self.assertEqual(backend.getAllTemp(), [55, 55])
        self.assertTrue(backend.setFanSpeed(0, 80))
        self.assertEqual(firmware.writes, [(80 << 16) | (50 << 8) | 2])
        self.assertTrue(backend.setMode(backend.Mode.Custom))
        firmware.statuses[151] = 1
        self.assertFalse(backend.setMode(backend.Mode.Balanced))


if __name__ == '__main__':
    unittest.main()
