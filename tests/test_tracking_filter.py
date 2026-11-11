"""Regression scenarios for forwarding and restart behaviour."""

import importlib.util
import sys
import unittest
from pathlib import Path

path = (
    Path(__file__).resolve().parents[1]
    / "custom_components/dawarich/tracking_filter.py"
)
spec = importlib.util.spec_from_file_location("tracking_filter", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
FilterSettings, TrackingFilter = module.FilterSettings, module.TrackingFilter
parse_bluetooth_macs = module.parse_bluetooth_macs


class TestTrackingFilter(unittest.TestCase):
    def setUp(self):
        self.policy = TrackingFilter(FilterSettings(enabled=True))

    def decide(self, when, zone="zone.work_rieter", activity="still", since=0, speed=0):
        return self.policy.decision(when, zone, activity, since, speed)

    def test_arrival_then_hour_after_last_success(self):
        self.assertEqual(self.decide(1000), (True, "arrival_window"))
        self.assertTrue(self.decide(1299)[0])
        self.policy.last_sent_at = 1299
        self.assertFalse(self.decide(1300)[0])
        self.assertFalse(self.decide(4898)[0])
        self.assertEqual(self.decide(4899), (True, "zone_interval_due"))
        self.policy.last_sent_at = 4899
        self.assertFalse(self.decide(4900)[0])

    def test_gps_excursion_does_not_reset_or_bypass_zone_filter(self):
        self.decide(1000)
        self.policy.last_sent_at = 1290
        self.assertFalse(self.decide(1500, zone=None, activity="walking")[0])
        self.assertFalse(self.decide(1550)[0])
        self.assertEqual(self.policy.entered_at, 1000)

    def test_real_exit_resumes_tracking(self):
        self.decide(1000)
        self.policy.last_sent_at = 1290
        self.assertFalse(self.decide(1500, zone=None, activity="walking")[0])
        self.assertTrue(self.decide(1620, zone=None, activity="walking")[0])
        self.assertIsNone(self.policy.active_zone)
        self.assertEqual(self.decide(1700), (True, "arrival_window"))
        self.assertEqual(self.policy.entered_at, 1700)

    def test_return_after_long_exit_with_no_intermediate_update(self):
        self.decide(1000)
        self.decide(1500, zone=None)
        self.assertEqual(self.decide(1800), (True, "arrival_window"))
        self.assertEqual(self.policy.entered_at, 1800)

    def test_other_zones_are_not_protected_and_still_requires_both_signals(self):
        self.policy.last_sent_at = 999
        self.assertEqual(self.decide(1000, zone=None), (False, "confirmed_still"))
        for activity, since, speed in [
            ("walking", 0, 0),
            ("unknown", 0, 0),
            ("unavailable", 0, 0),
            (None, None, 0),
            ("still", 950, 0),
            ("still", 0, None),
            ("still", 0, -1),
            ("still", 0, 0.5),
            ("still", 0, "nan"),
            ("still", 0, "inf"),
            ("still", 0, True),
            ("still", 0, "unknown"),
        ]:
            with self.subTest(activity=activity, speed=speed):
                self.assertTrue(self.decide(1000, None, activity, since, speed)[0])

    def test_hourly_point_bypasses_stationary_filter(self):
        self.decide(1000)
        self.policy.last_sent_at = 1250
        self.assertEqual(self.decide(4850), (True, "zone_interval_due"))

    def test_failed_send_does_not_start_another_hour(self):
        self.decide(1000)
        self.policy.last_sent_at = 1250
        self.assertTrue(self.decide(4850)[0])
        # Caller only advances last_sent_at on a successful API response.
        self.assertTrue(self.decide(4860)[0])

    def test_restart_keeps_arrival_and_last_send(self):
        self.decide(1000)
        self.policy.last_sent_at = 1250
        saved = self.policy.snapshot()
        restored = TrackingFilter(FilterSettings(enabled=True))
        restored.restore(saved, {"zone.work_rieter"}, 1500)
        self.policy = restored
        self.assertFalse(self.decide(1500)[0])
        self.assertEqual(self.policy.entered_at, 1000)
        self.assertTrue(self.decide(4850)[0])

    def test_restart_keeps_pending_exit(self):
        self.decide(1000)
        self.policy.last_sent_at = 1250
        self.decide(1500, zone=None)
        restored = TrackingFilter(FilterSettings(enabled=True))
        restored.restore(self.policy.snapshot(), {"zone.work_rieter"}, 1550)
        self.policy = restored
        self.assertFalse(self.decide(1560)[0])
        self.assertEqual(restored.entered_at, 1000)

    def test_corrupt_restore_does_not_break_tracking(self):
        self.policy.restore(
            {"entered_at": "nan", "active_zone": [], "last_sent_at": 99999},
            {"zone.home"},
            1000,
        )
        self.assertIsNone(self.policy.active_zone)
        self.assertIsNone(self.policy.last_sent_at)
        self.assertTrue(self.decide(1000)[0])

    def test_different_protected_zone_starts_its_own_window(self):
        self.decide(1000)
        self.policy.last_sent_at = 1290
        self.assertEqual(self.decide(1800, "zone.home"), (True, "arrival_window"))
        self.assertEqual(self.policy.entered_at, 1800)

    def test_still_detection_can_be_disabled(self):
        self.policy = TrackingFilter(FilterSettings(enabled=True, still_detection_enabled=False))
        self.assertEqual(self.decide(1000, zone=None), (True, "outside_zone"))

    def test_confirmed_still_sends_periodic_checkpoint(self):
        self.policy = TrackingFilter(
            FilterSettings(enabled=True, still_seconds=120, still_update_interval_seconds=300)
        )
        self.assertEqual(self.decide(120, zone=None, since=0), (True, "still_interval_due"))
        self.policy.last_sent_at = 120
        self.assertEqual(self.decide(419, zone=None, since=0), (False, "confirmed_still"))
        self.assertEqual(self.decide(420, zone=None, since=0), (True, "still_interval_due"))

    def test_still_checkpoint_interval_is_measured_from_last_success(self):
        self.policy = TrackingFilter(
            FilterSettings(enabled=True, still_seconds=120, still_update_interval_seconds=300)
        )
        self.policy.last_sent_at = 100
        self.assertEqual(self.decide(399, zone=None, since=0), (False, "confirmed_still"))
        self.assertEqual(self.decide(400, zone=None, since=0), (True, "still_interval_due"))

    def test_disabled_filter_is_pass_through(self):
        self.policy = TrackingFilter(FilterSettings())
        self.assertEqual(self.decide(1000), (True, "filter_disabled"))

    def test_zero_delays_and_long_stay_without_updates(self):
        self.policy = TrackingFilter(
            FilterSettings(enabled=True, arrival_seconds=0, exit_seconds=0)
        )
        self.assertTrue(self.decide(1000)[0])
        self.policy.last_sent_at = 1000
        self.assertFalse(self.decide(1001)[0])
        self.assertTrue(self.decide(10000)[0])
        self.assertTrue(self.decide(10001, None, "walking")[0])


if __name__ == "__main__":
    unittest.main()


class TestHighAccuracyResidence(unittest.TestCase):
    def test_override_tracks_exit_without_resetting_or_waiting(self):
        policy = TrackingFilter(FilterSettings(enabled=True))
        policy.observe_zone("zone.work_rieter", 1000)
        policy.last_sent_at = 4999
        self.assertEqual(
            policy.decision(5000, None, "still", 0, 0, True), (True, "high_accuracy")
        )
        self.assertEqual(policy.outside_since, 5000)
        self.assertEqual(policy.entered_at, 1000)
        self.assertEqual(
            policy.decision(5060, "zone.work_rieter", "still", 0, 0, True),
            (True, "high_accuracy"),
        )
        self.assertEqual(policy.entered_at, 1000)
        self.assertEqual(
            policy.decision(5070, "zone.work_rieter", "still", 0, 0, False),
            (False, "zone_interval_wait"),
        )
        policy.decision(5100, None, "walking", 0, 0, True)
        policy.decision(5220, None, "walking", 0, 0, True)
        self.assertIsNone(policy.active_zone)


class TestBluetoothMacParsing(unittest.TestCase):
    def test_parses_multiple_macs_and_normalizes_case(self):
        self.assertEqual(
            parse_bluetooth_macs(
                "Mazda FC:35:E6:A3:1C:32\n"
                "Skoda 48:F0:7B:C4:DE:21\n"
                "smartBox E2:C0:B3:05:A3:DF"
            ),
            {"FC:35:E6:A3:1C:32", "48:F0:7B:C4:DE:21", "E2:C0:B3:05:A3:DF"},
        )

    def test_ignores_invalid_values(self):
        self.assertEqual(parse_bluetooth_macs("not a MAC\n00:11:22:33:44"), set())
