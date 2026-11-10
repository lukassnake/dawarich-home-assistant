"""Stateful forwarding rules, independent of Home Assistant for testing."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class FilterSettings:
    """Durations in seconds and speed in metres per second."""

    enabled: bool = False
    arrival_seconds: float = 300
    zone_interval_seconds: float = 3600
    exit_seconds: float = 120
    still_detection_enabled: bool = True
    still_seconds: float = 120
    still_update_interval_seconds: float = 300
    still_speed: float = 0.5


def finite_number(value: object) -> float | None:
    """Convert finite numbers, rejecting absent values and booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if isfinite(result) else None


@dataclass
class TrackingFilter:
    """Remember continuous protected-zone residence and successful sends."""

    settings: FilterSettings
    active_zone: str | None = None
    entered_at: float | None = None
    outside_since: float | None = None
    last_sent_at: float | None = None

    def observe_zone(self, zone: str | None, now: float) -> None:
        """Ignore short GPS excursions without resetting arrival time."""
        if zone is not None:
            # An observed outside interval lasting long enough is a real exit,
            # even when there was no intermediate location update at its end.
            if (
                self.outside_since is not None
                and now - self.outside_since >= self.settings.exit_seconds
            ):
                self.active_zone = None
                self.entered_at = None
            if self.active_zone != zone:
                self.active_zone = zone
                self.entered_at = now
            self.outside_since = None
            return
        if self.active_zone is None:
            return
        if self.outside_since is None:
            self.outside_since = now
        if now - self.outside_since >= self.settings.exit_seconds:
            self.active_zone = None
            self.entered_at = None
            self.outside_since = None

    def decision(
        self,
        now: float,
        zone: str | None,
        activity: str | None,
        activity_since: float | None,
        speed: object,
        high_accuracy: bool = False,
    ) -> tuple[bool, str]:
        """Return whether this fresh update may be forwarded and why."""
        if not self.settings.enabled:
            return True, "filter_disabled"
        self.observe_zone(zone, now)
        if high_accuracy:
            return True, "high_accuracy"
        if self.active_zone is not None:
            if self.entered_at is not None and (
                now - self.entered_at < self.settings.arrival_seconds
            ):
                return True, "arrival_window"
            if self.last_sent_at is None or (
                now - self.last_sent_at >= self.settings.zone_interval_seconds
            ):
                return True, "zone_interval_due"
            return False, "zone_interval_wait"
        numeric_speed = finite_number(speed)
        confirmed_still = (
            self.settings.still_detection_enabled
            and activity == "still"
            and activity_since is not None
            and now - activity_since >= self.settings.still_seconds
            and numeric_speed is not None
            and 0 <= numeric_speed < self.settings.still_speed
        )
        if confirmed_still:
            if self.last_sent_at is None or (
                now - self.last_sent_at >= self.settings.still_update_interval_seconds
            ):
                return True, "still_interval_due"
            return False, "confirmed_still"
        return True, "outside_zone"

    def snapshot(self) -> dict:
        """Produce JSON-safe state for restart persistence."""
        return {
            "active_zone": self.active_zone,
            "entered_at": self.entered_at,
            "outside_since": self.outside_since,
            "last_sent_at": self.last_sent_at,
        }

    def restore(self, data: dict, zones: set[str], now: float) -> None:
        """Restore compatible state, rejecting future or malformed timestamps."""
        for field in ("entered_at", "outside_since", "last_sent_at"):
            value = finite_number(data.get(field))
            setattr(
                self, field, value if value is not None and 0 <= value <= now else None
            )
        zone = data.get("active_zone")
        self.active_zone = zone if isinstance(zone, str) and zone in zones else None
        if self.active_zone is None or self.entered_at is None:
            self.active_zone = None
            self.entered_at = None
            self.outside_since = None
