"""Self-check for per-model logic in api.py. Run: .venv/bin/python tests/test_api.py"""
import importlib.util
import pathlib

_path = pathlib.Path(__file__).resolve().parent.parent / "custom_components/dreame_airpurifier/api.py"
_spec = importlib.util.spec_from_file_location("dreame_api", _path)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)


class FakeAPI:
    def __init__(self, values):
        self.values, self.writes = values, []

    def get_properties(self, did, props, host=None):
        return {(p["siid"], p["piid"]): self.values[(p["siid"], p["piid"])] for p in props if (p["siid"], p["piid"]) in self.values}

    def get_cached_properties(self, did, props):
        return self.get_properties(did, props)

    def set_property(self, did, siid, piid, value, host=None):
        self.writes.append((siid, piid, value))
        return True


# NP10 values captured from a real u2532 (Custom mode, speed 2, child lock on, timer 2h)
np10_api = FakeAPI({(2, 1): 1, (2, 3): 3, (2, 4): 2, (6, 8): 2, (6, 10): 1,
                    (4, 7): 100, (4, 8): 30, (4, 9): 100, (4, 10): 90, (3, 4): 1, (3, 5): 13})
np10 = api.DreameAirPurifier(np10_api, {"did": 1, "model": "dreame.airp.u2532", "mac": "AA:BB"})
assert np10.update()
assert np10.is_np10 and np10.speed_count == 3
assert np10.preset_modes == ["AI Purify", "Sleep Purification", "Custom Mode"]
assert np10.mode == "Custom Mode" and np10.fan_speed_percent == 67 and np10.is_on
assert np10.child_lock is True and np10.timer_hours == 2
assert np10.pm25 == 13 and np10.air_quality_level == 1  # from the cloud cache
assert (np10.prefilter_life, np10.prefilter_days_left, np10.electrode_life, np10.electrode_days_left) == (100, 30, 100, 90)
np10.set_child_lock(False)
np10.set_fan_speed_percent(100)
assert np10_api.writes == [(6, 10, 0), (2, 4, 3)], np10_api.writes
np10_api.writes.clear()
np10.turn_off()
assert np10_api.writes == [(2, 3, 2)], np10_api.writes  # Sleep only, no speed write
np10_api.values[(2, 3)], np10_api.values[(2, 4)] = 2, 2
np10.update()
assert not np10.is_on  # NP10 Sleep counts as off whatever the speed
np10_api.values[(2, 1)] = 2  # real standby
np10.update()
np10_api.writes.clear()
assert np10.turn_on() is False and np10_api.writes == []  # no toggle, no writes

# AP10 keeps its 5 modes / 5 speeds / child lock at 6/5
ap10_api = FakeAPI({(2, 1): 1, (2, 3): 3, (2, 4): 4, (6, 5): 1})
ap10 = api.DreameAirPurifier(ap10_api, {"did": 2, "model": "dreame.airp.u2507", "mac": "CC:DD"})
assert ap10.update()
assert not ap10.is_np10 and ap10.speed_count == 5 and len(ap10.preset_modes) == 5
assert ap10.fan_speed_percent == 80 and ap10.child_lock is True and ap10.prefilter_life is None
ap10.set_child_lock(False)
ap10.set_fan_speed_percent(40)
assert ap10_api.writes == [(6, 5, 0), (2, 4, 2)], ap10_api.writes

print("ok")
