# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Home Assistant custom integration (HACS) for the **Dreame AP-10** air purifier (`dreame.airp.u2507`), talking to the Dreame cloud. There is no local API. Domain: `dreame_airpurifier`. All code lives in `custom_components/dreame_airpurifier/`.

## Commands

There is no build step or linter config. A local `.venv` (gitignored, has `requests`) runs the scripts below. Check it compiles and passes the self-check with:

```bash
.venv/bin/python -m py_compile custom_components/dreame_airpurifier/*.py
.venv/bin/python tests/test_api.py
```

Real testing means copying `custom_components/dreame_airpurifier/` into a Home Assistant `config/custom_components/`, restarting, and adding the integration with Dreamehome credentials. Logs are under the `dreame_airpurifier` logger.

## Releasing

- Version is in `manifest.json` (`version`). Bump it there.
- HACS installs the latest **GitHub release**, not `main`. Releases come from the manual `Publish Release` workflow (`.github/workflows/publish-release.yml`, `workflow_dispatch` with `tag`/`title` inputs). Its release `body` and input defaults are hardcoded for v2.1.0, so update them before running it for a new version.
- `hacs.json` sets the minimum Home Assistant version (2024.6.0).

## Architecture

- **`api.py` holds everything device-specific.** `DreameCloudAPI` is a synchronous `requests` client (login with MD5(password + salt), token refresh, `sendCommand` for `get_properties` / `set_properties` / `action`). `DreameAirPurifier` wraps one device: it holds cached state, the `PROP_*` siid/piid map, the value↔label maps (modes, light, volume), and all setters.
- **`__init__.py`** logs in, finds devices whose model contains `.airp.`, makes one `DreameAirPurifier` each, and runs one `DataUpdateCoordinator` (30 s, `SCAN_INTERVAL` in `const.py`) that calls `update()` on every purifier. It stores `{"coordinator", "purifiers", "api"}` in `hass.data[DOMAIN][entry_id]`.
- **Platform files** (`fan`, `sensor`, `switch`, `select`, `number`, `button`) are thin `CoordinatorEntity` wrappers. They read properties off the purifier and call its setters through `hass.async_add_executor_job` (the API blocks), then `coordinator.async_request_refresh()`. Unique IDs are `<mac without colons>_<key>`; device identifiers are `(DOMAIN, unique_id)`.
- Device commands go to a per-device host: `bindDomain` from the device list becomes a `dreame-iot-com-<prefix>` URL path segment. The region picks the base URL `https://<country>.iot.dreame.tech:13267`. `cn` also needs the `Dreame-Rlc` header.
- `update()` polls in small `POLL_BATCHES` because large `get_properties` calls time out. It keys results by `(siid, piid)` tuples and keeps the old value when a property is missing.

## Device quirks that must be preserved

- **Never send a hard power-off.** The AP-10 drops off the cloud in standby and cannot be woken remotely. "Off" in HA = Sleep Purification mode + fan speed 1, and `is_on` reports that state as off. "On" = AI Purify.
- Writing power (`siid=2, piid=1`) times out. Power only uses the toggle action `siid=2, aiid=3`. Filter reset is action `siid=4, aiid=1`.
- Fan speed is 1–5, shown as percent ×20. Setting a speed manually switches to Custom Mode first.
- The full verified property map is in `README.md` and in the `PROP_*` constants in `api.py`. Keep both in sync when either changes.
- Model differences hang off `DreameAirPurifier.is_np10` (`dreame.airp.u2532`, NP10): its own `NP10_POLL_BATCHES`, 3 modes, 3 speeds, child lock at 6/10, two filters at siid 4 piid 7–10. Platforms skip entities the NP10 lacks. Any other `.airp.` model falls back to the AP-10 map.

## Tools

- `tests/test_api.py`: assert-based self-check of the per-model logic with a fake API (`.venv/bin/python tests/test_api.py`).
- `scripts/probe_properties.py [model] [max-siid] [max-piid]`: read-only dump of every readable property, used to map new models. Credentials come from a gitignored `.env` (`DREAME_USERNAME`, `DREAME_PASSWORD`, `DREAME_COUNTRY`) or prompts. Map a property by changing one setting in the app, re-running, and diffing.

## Scope rules (from README)

AP-10 only. Do not guess mappings from other models, add `dreame.fan.*` / MF10 support, or merge PM10 or vacuum code. A new `dreame.airp.*` model needs a probed property map and someone with the hardware to test it.
