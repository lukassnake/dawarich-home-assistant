# Changelog

## 1.0.0-lukas.6 — 2026-11-13

### Added
- Configurable High Accuracy interval for activity `unknown` (default: 30 seconds) when no configured car Bluetooth device is connected.
- Optional detailed Bluetooth diagnostic logging in Home Assistant logs.
- Re-evaluation of the requested interval on both Bluetooth sensor changes and activity sensor changes.
- Diagnostic context includes connected MAC addresses, configured car MAC addresses, matched car devices, activity state, selected interval, and notify-service call outcome.

### Changed
- Interval priority is now explicit: connected car Bluetooth (7 s) → activity `unknown` without car (30 s) → all other states (15 s).
- A connected car always takes priority over the activity state.
- Startup evaluation runs after Bluetooth and activity listeners are registered.

### Notes
- The notify service completing successfully confirms that Home Assistant completed the service call; it does not provide a device-side acknowledgement that Android has already applied the interval.
- High Accuracy ON/OFF remains controlled by the user's separate Home Assistant automation. This integration changes only the Companion App update interval.

### Tests
- Added unit tests for car priority, unknown without car, known activity without car, and missing activity sensor.
