"""Characterization tests for the per-cycle device-processing skip.

Pins the performance fix in ``_async_update_data_internal`` (Phase 3): per-device
``calculate_data`` must only run for devices that are actually relevant this
cycle (seen on the air, tracked, scanner, metadevice, metadevice source, or a
configured-but-unseen device) and must NOT run over dormant untracked noise that
nothing reads. They also pin that the tracked/configured devices keep their
previous behaviour: always processed, entities still signalled, a configured
device never seen on the air still gets claimed for entity creation.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.bermuda.bermuda_device import BermudaDevice
from custom_components.bermuda.const import CONF_DEVICES, SIGNAL_DEVICE_NEW
from custom_components.bermuda.coordinator import BermudaDataUpdateCoordinator

CYCLE_PHASES = {
    "gather",
    "metadevices",
    "per_device",
    "area_refresh",
    "area_overrides",
    "microlocations",
    "configured_seed",
    "entity_creation",
    "prune",
}


def _get_coordinator(entry) -> BermudaDataUpdateCoordinator:
    """Pull the live coordinator off the loaded config entry."""
    return entry.runtime_data.coordinator


def _addr(i: int) -> str:
    """A deterministic lower-cased MAC address for a test device index.

    The index is spread across two octets so test populations never collide.
    """
    return f"aa:bb:cc:dd:{i // 256:02x}:{i % 256:02x}"


def _make_device(co: BermudaDataUpdateCoordinator, addr: str) -> BermudaDevice:
    """Create a real BermudaDevice bound to the live coordinator."""
    return BermudaDevice(addr, co)


def _patch_noops(co: BermudaDataUpdateCoordinator):
    """Patch out every cycle phase that is not under test."""
    return [
        patch.object(co, "_async_gather_advert_data"),
        patch.object(co, "_refresh_areas_by_min_distance"),
        patch.object(co, "_apply_area_entity_overrides"),
        patch.object(co, "_refresh_microlocations"),
        patch.object(co, "update_metadevices"),
        patch.object(co, "prune_devices"),
    ]


async def test_phase3_skips_dormant_devices_and_keeps_relevant_ones(hass: HomeAssistant, setup_bermuda_entry) -> None:
    """Only relevant devices get calculate_data; dormant noise is skipped.

    Population: 13 tracked, 300 dormant untracked noise, 2 seen-this-cycle,
    1 scanner, 1 metadevice + its source, 1 configured-but-unseen device.
    """
    co = _get_coordinator(setup_bermuda_entry)
    co._waitingfor_load_manufacturer_ids = False
    co.update_in_progress = False

    # The 13 "configured/tracked" devices — the ones whose detection must not
    # be degraded.
    tracked = [_addr(i) for i in range(13)]
    for addr in tracked:
        dev = _make_device(co, addr)
        dev.create_sensor = True
        co.devices[addr] = dev

    # Dormant untracked noise: never seen this cycle, never tracked. This is
    # the population PRUNE_TIME_DEFAULT used to retain for 24h.
    dormant = [_addr(i) for i in range(100, 400)]
    for addr in dormant:
        co.devices[addr] = _make_device(co, addr)

    # Untracked but seen this cycle (fresh adverts must still be processed).
    seen = [_addr(500), _addr(501)]
    for addr in seen:
        co.devices[addr] = _make_device(co, addr)
    co._seen_this_cycle = set(seen)

    # A scanner.
    scanner_addr = _addr(600)
    scanner = _make_device(co, scanner_addr)
    scanner._is_scanner = True
    co.devices[scanner_addr] = scanner

    # A metadevice and its source device.
    source_addr = _addr(700)
    co.devices[source_addr] = _make_device(co, source_addr)
    meta_addr = _addr(701)
    meta = _make_device(co, meta_addr)
    meta.metadevice_sources = [source_addr]
    co.devices[meta_addr] = meta
    co.metadevices = {meta_addr: meta}

    # A configured-but-unseen device (create_sensor False until calculated).
    configured_addr = _addr(800)
    configured = _make_device(co, configured_addr)
    co.devices[configured_addr] = configured
    co.options[CONF_DEVICES] = [configured_addr.upper()]

    with ExitStack() as stack:
        mock_calc = stack.enter_context(patch.object(BermudaDevice, "calculate_data", autospec=True))
        for ctx in _patch_noops(co):
            stack.enter_context(ctx)
        stack.enter_context(patch("custom_components.bermuda.coordinator.async_dispatcher_send"))
        await co._async_update_data_internal()

    called = {call.args[0].address for call in mock_calc.call_args_list}

    # Everything relevant must have been processed...
    for addr in tracked + seen + [scanner_addr, source_addr, meta_addr, configured_addr]:
        assert addr in called, f"{addr} must be processed"
    # ... and the dormant noise must never be touched.
    for addr in dormant:
        assert addr not in called, f"{addr} must NOT be processed"


async def test_tracked_device_always_processed_even_when_dormant(hass: HomeAssistant, setup_bermuda_entry) -> None:
    """A tracked device is processed every cycle, seen on the air or not."""
    co = _get_coordinator(setup_bermuda_entry)
    co._waitingfor_load_manufacturer_ids = False
    co.update_in_progress = False

    addr = _addr(0)
    dev = _make_device(co, addr)
    dev.create_sensor = True
    co.devices[addr] = dev

    with ExitStack() as stack:
        mock_calc = stack.enter_context(patch.object(BermudaDevice, "calculate_data", autospec=True))
        for ctx in _patch_noops(co):
            stack.enter_context(ctx)
        stack.enter_context(patch("custom_components.bermuda.coordinator.async_dispatcher_send"))
        # Two consecutive cycles; the device is never seen on the air in either.
        await co._async_update_data_internal()
        await co._async_update_data_internal()

    assert mock_calc.call_count == 2
    for call in mock_calc.call_args_list:
        assert call.args[0] is dev


async def test_configured_unseen_device_still_claimed(hass: HomeAssistant, setup_bermuda_entry) -> None:
    """A configured device never seen on the air is still processed and claimed.

    Before the fix, the full-device Phase 3 loop set ``create_sensor`` for it the
    cycle after the CONF_DEVICES seed created it; the skip must preserve that.
    """
    co = _get_coordinator(setup_bermuda_entry)
    co._waitingfor_load_manufacturer_ids = False
    co.update_in_progress = False

    addr = _addr(800)
    co.options[CONF_DEVICES] = [addr.upper()]
    configured = _make_device(co, addr)
    co.devices[addr] = configured
    assert configured.create_sensor is False  # never seen on the air yet

    with ExitStack() as stack:
        for ctx in _patch_noops(co):
            stack.enter_context(ctx)
        mock_send = stack.enter_context(patch("custom_components.bermuda.coordinator.async_dispatcher_send"))
        await co._async_update_data_internal()

    # Still present, now flagged for entity creation exactly like before.
    assert co.devices[addr] is configured
    assert configured.create_sensor is True
    new_calls = [call for call in mock_send.call_args_list if call.args[1] == SIGNAL_DEVICE_NEW]
    assert any(call.args[2] == addr for call in new_calls)


async def test_cycle_stats_recorded_each_cycle(hass: HomeAssistant, setup_bermuda_entry) -> None:
    """The cycle records elapsed time, device count and a per-phase breakdown."""
    co = _get_coordinator(setup_bermuda_entry)
    co._waitingfor_load_manufacturer_ids = False
    co.update_in_progress = False

    with ExitStack() as stack:
        for ctx in _patch_noops(co):
            stack.enter_context(ctx)
        stack.enter_context(patch("custom_components.bermuda.coordinator.async_dispatcher_send"))
        await co._async_update_data_internal()

    assert set(co.cycle_stats) == {"elapsed", "devices", "phases"}
    assert co.cycle_stats["devices"] == len(co.devices)
    assert isinstance(co.cycle_stats["elapsed"], float)
    assert set(co.cycle_stats["phases"]) == CYCLE_PHASES
