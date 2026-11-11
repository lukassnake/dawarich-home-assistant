"""Forwarding tests using actual Home Assistant State and flow classes."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import State

from custom_components.dawarich import sensor as component
from custom_components.dawarich.config_flow import DawarichConfigFlow


def build_sensor(monkeypatch):
    monkeypatch.setattr(component, "Store", MagicMock())
    monkeypatch.setattr(
        component.dt_util, "utcnow", lambda: datetime.fromtimestamp(5000, UTC)
    )
    states = {
        "zone.work_rieter": State("zone.work_rieter", "1", {"friendly_name": "Rieter"}),
        "sensor.s26ultra_detected_activity": State(
            "sensor.s26ultra_detected_activity",
            "still",
            last_changed=datetime.fromtimestamp(0, UTC),
        ),
    }
    api = SimpleNamespace(
        add_one_point=AsyncMock(return_value=SimpleNamespace(success=True))
    )
    item = component.DawarichTrackerSensor(
        entry_id="test-entry",
        options={
            "filter_enabled": True,
            "protected_zones": ["zone.work_rieter", "zone.home"],
            "activity_sensor": "sensor.s26ultra_detected_activity",
        },
        device_name="S26Ultra",
        mobile_app="device_tracker.s26ultra",
        api=api,
        hass=SimpleNamespace(states=SimpleNamespace(get=states.get)),
        device_info={},
        description=component.TRACKER_SENSOR_TYPES,
    )
    item._async_check_is_disabled = AsyncMock(return_value=False)
    item.async_write_ha_state = MagicMock()
    item._filter.active_zone = "zone.work_rieter"
    item._filter.entered_at = 1000
    item._filter.last_sent_at = 1300
    return item, api, states


def event(memberships=None, state="Rieter", **attrs):
    values = {
        "latitude": 49.22,
        "longitude": 16.62,
        "speed": 0,
        "gps_accuracy": 12,
        "altitude": 294,
        "vertical_accuracy": 1,
    }
    if memberships is not None:
        values["in_zones"] = memberships
    values.update(attrs)
    return SimpleNamespace(
        data={
            "new_state": State(
                "device_tracker.s26ultra",
                state,
                values,
                last_updated=datetime.fromtimestamp(4999, UTC),
            )
        }
    )


@pytest.mark.asyncio
async def test_hourly_send_then_suppression_and_payload(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 1
    payload = api.add_one_point.call_args.kwargs
    assert payload["timestamp"] == "1970-01-01T01:23:19+00:00"
    assert payload["speed"] == 0
    assert payload["altitude"] == 294
    assert payload["horizontal_accuracy"] == 12
    assert item._filter.last_sent_at == 5000
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 1
    assert item.extra_state_attributes["filter_reason"] == "zone_interval_wait"


@pytest.mark.asyncio
async def test_simultaneous_hourly_updates_send_once(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)

    async def slow_response(**kwargs):
        await asyncio.sleep(0)
        return SimpleNamespace(success=True)

    api.add_one_point.side_effect = slow_response
    await asyncio.gather(
        *(item._async_update_callback(event(["zone.work_rieter"])) for _ in range(10))
    )
    assert api.add_one_point.await_count == 1


@pytest.mark.asyncio
async def test_error_does_not_consume_hourly_slot(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)
    api.add_one_point.return_value = SimpleNamespace(
        success=False, response_code=503, error="offline"
    )
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert item._filter.last_sent_at == 1300
    api.add_one_point.return_value = SimpleNamespace(success=True)
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 2
    assert item._filter.last_sent_at == 5000


@pytest.mark.asyncio
async def test_still_only_filters_outside_and_unknown_speed_does_not_block(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)
    item._filter.active_zone = None
    item._filter.entered_at = None
    await item._async_update_callback(event([], state="not_home"))
    assert api.add_one_point.await_count == 0
    assert item._filter_reason == "confirmed_still"
    await item._async_update_callback(event([], state="not_home", speed=None))
    assert api.add_one_point.await_count == 1


@pytest.mark.asyncio
async def test_invalid_coordinates_are_skipped(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)
    for value in ("nan", "inf", True, 91):
        await item._async_update_callback(event(["zone.work_rieter"], latitude=value))
    assert api.add_one_point.await_count == 0


@pytest.mark.asyncio
async def test_zone_name_fallback_and_explicit_empty_membership(monkeypatch):
    item, _, _ = build_sensor(monkeypatch)
    assert item._get_protected_zone(event().data["new_state"]) == "zone.work_rieter"
    assert item._get_protected_zone(event([]).data["new_state"]) is None
    assert (
        item._get_protected_zone(event("zone.work_rieter").data["new_state"])
        == "zone.work_rieter"
    )


@pytest.mark.asyncio
async def test_options_schema_roundtrip(monkeypatch):
    flow = DawarichConfigFlow.async_get_options_flow(None)
    entry = SimpleNamespace(options={})
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda key: entry)
    )
    flow.handler = "test-entry"
    form = await flow.async_step_init()
    data = form["data_schema"](
        {
            "filter_enabled": True,
            "protected_zones": ["zone.home"],
            "activity_sensor": "sensor.s26ultra_detected_activity",
        }
    )
    assert data["arrival_minutes"] == 5
    assert data["zone_interval_minutes"] == 60
    assert data["exit_seconds"] == 120
    saved = await flow.async_step_init(data)
    assert saved["data"]["protected_zones"] == ["zone.home"]


@pytest.mark.asyncio
async def test_network_exception_allows_retry(monkeypatch):
    item, api, _ = build_sensor(monkeypatch)
    api.add_one_point.side_effect = TimeoutError()
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert item._filter.last_sent_at == 1300
    assert item._filter_reason == "api_error"
    api.add_one_point.side_effect = None
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 2


@pytest.mark.asyncio
async def test_real_storage_survives_entity_reload(monkeypatch, tmp_path):
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.storage import Store

    hass = HomeAssistant(str(tmp_path))
    hass.states.async_set(
        "device_tracker.s26ultra", "Rieter", {"in_zones": ["zone.work_rieter"]}
    )
    item, _, _ = build_sensor(monkeypatch)
    item._filter_store = Store(hass, 1, "dawarich.test")
    await item._filter_store.async_save(item._filter_snapshot())
    restored, _, _ = build_sensor(monkeypatch)
    restored._filter_store = Store(hass, 1, "dawarich.test")
    restored._hass = hass
    restored.hass = hass
    monkeypatch.setattr(component.SensorEntity, "async_added_to_hass", AsyncMock())
    await restored.async_added_to_hass()
    assert restored._filter.entered_at == 1000
    assert restored._filter.last_sent_at == 1300
    await restored.async_will_remove_from_hass()
    await hass.async_stop()


@pytest.mark.asyncio
async def test_high_accuracy_forwards_every_update_inside_zone(monkeypatch):
    item, api, states = build_sensor(monkeypatch)
    item._high_accuracy_sensor = "binary_sensor.s26ultra_high_accuracy_mode"
    states[item._high_accuracy_sensor] = State(item._high_accuracy_sensor, "on")
    item._filter.last_sent_at = 4999
    for _ in range(3):
        await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 3
    assert item._filter_reason == "high_accuracy"
    assert item.extra_state_attributes["high_accuracy_active"] is True
    assert item._filter.entered_at == 1000
    states[item._high_accuracy_sensor] = State(item._high_accuracy_sensor, "off")
    await item._async_update_callback(event(["zone.work_rieter"]))
    assert api.add_one_point.await_count == 3
    assert item._filter_reason == "zone_interval_wait"


@pytest.mark.asyncio
async def test_high_accuracy_bypasses_still_then_restores_it(monkeypatch):
    item, api, states = build_sensor(monkeypatch)
    item._high_accuracy_sensor = "binary_sensor.s26ultra_high_accuracy_mode"
    states[item._high_accuracy_sensor] = State(item._high_accuracy_sensor, "on")
    item._filter.active_zone = None
    item._filter.entered_at = None
    await item._async_update_callback(event([], state="not_home"))
    assert api.add_one_point.await_count == 1
    assert item._filter_reason == "high_accuracy"
    states[item._high_accuracy_sensor] = State(item._high_accuracy_sensor, "off")
    await item._async_update_callback(event([], state="not_home"))
    assert api.add_one_point.await_count == 1
    assert item._filter_reason == "confirmed_still"


@pytest.mark.asyncio
async def test_only_confirmed_high_accuracy_on_bypasses(monkeypatch):
    item, api, states = build_sensor(monkeypatch)
    item._high_accuracy_sensor = "binary_sensor.s26ultra_high_accuracy_mode"
    item._filter.last_sent_at = 4999
    for state in (None, "off", "unknown", "unavailable"):
        if state is not None:
            states[item._high_accuracy_sensor] = State(
                item._high_accuracy_sensor, state
            )
        await item._async_update_callback(event(["zone.work_rieter"]))
        assert item._filter_reason == "zone_interval_wait"
        assert item._high_accuracy_active is False
    assert api.add_one_point.await_count == 0


@pytest.mark.asyncio
async def test_high_accuracy_still_requires_valid_coordinates(monkeypatch):
    item, api, states = build_sensor(monkeypatch)
    item._high_accuracy_sensor = "binary_sensor.s26ultra_high_accuracy_mode"
    states[item._high_accuracy_sensor] = State(item._high_accuracy_sensor, "on")
    await item._async_update_callback(event(["zone.work_rieter"], latitude="nan"))
    assert api.add_one_point.await_count == 0
    assert item._filter_reason == "invalid_coordinates"


@pytest.mark.asyncio
async def test_high_accuracy_selector_accepts_binary_sensor(monkeypatch):
    flow = DawarichConfigFlow.async_get_options_flow(None)
    entry = SimpleNamespace(options={})
    flow.hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_get_known_entry=lambda key: entry)
    )
    flow.handler = "test-entry"
    form = await flow.async_step_init()
    data = form["data_schema"](
        {
            "filter_enabled": True,
            "high_accuracy_sensor": "binary_sensor.s26ultra_high_accuracy_mode",
        }
    )
    saved = await flow.async_step_init(data)
    assert (
        saved["data"]["high_accuracy_sensor"]
        == "binary_sensor.s26ultra_high_accuracy_mode"
    )


@pytest.mark.asyncio
async def test_bluetooth_car_devices_set_seven_second_interval(monkeypatch):
    item, _, states = build_sensor(monkeypatch)
    service_call = AsyncMock()
    item._hass.services = SimpleNamespace(
        has_service=MagicMock(return_value=True), async_call=service_call
    )
    states["sensor.s26ultra_bluetooth_connection"] = State(
        "sensor.s26ultra_bluetooth_connection", "3",
        {"Connected Paired Devices": "FC:35:E6:A3:1C:32 (Mazda), 48:F0:7B:C4:DE:21 (Skoda BT 9667), E2:C0:B3:05:A3:DF (smartBox-1203)"},
    )
    await item._async_update_high_accuracy_interval()
    assert service_call.await_count == 1
    payload = service_call.call_args.args[2]
    assert payload["data"]["high_accuracy_update_interval"] == 7
    assert payload["data"]["command"] == "high_accuracy_set_update_interval"


@pytest.mark.asyncio
async def test_bluetooth_disconnect_restores_normal_interval(monkeypatch):
    item, _, states = build_sensor(monkeypatch)
    service_call = AsyncMock()
    item._hass.services = SimpleNamespace(
        has_service=MagicMock(return_value=True), async_call=service_call
    )
    states["sensor.s26ultra_bluetooth_connection"] = State(
        "sensor.s26ultra_bluetooth_connection", "1",
        {"connected_paired_devices": "E2:C0:B3:05:A3:DF (smartBox-1203)"},
    )
    await item._async_update_high_accuracy_interval()
    assert service_call.call_args.args[2]["data"]["high_accuracy_update_interval"] == 7

    states["sensor.s26ultra_bluetooth_connection"] = State(
        "sensor.s26ultra_bluetooth_connection", "0",
        {"connected_paired_devices": []},
    )
    await item._async_update_high_accuracy_interval()
    assert service_call.await_count == 2
    assert service_call.call_args.args[2]["data"]["high_accuracy_update_interval"] == 15
