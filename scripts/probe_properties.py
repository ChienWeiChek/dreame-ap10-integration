"""Read-only probe: dump every readable siid/piid on your Dreame air purifiers.

Usage:  python scripts/probe_properties.py [model-filter] [max-siid] [max-piid]
        (defaults: ".airp." 10 20)
Only sends get_properties; never writes or calls actions.
"""
import getpass
import importlib.util
import pathlib
import sys

# Load api.py directly so we don't pull in Home Assistant via the package __init__.
_api_path = pathlib.Path(__file__).resolve().parent.parent / "custom_components/dreame_airpurifier/api.py"
_spec = importlib.util.spec_from_file_location("dreame_api", _api_path)
api_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api_mod)

BATCH = 5  # small batches: big get_properties calls time out


def load_env() -> dict:
    """Optional repo-root .env (KEY=value lines, gitignored)."""
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                env[key.strip()] = value.strip().strip("'\"")
    return env


def main():
    model_filter = sys.argv[1] if len(sys.argv) > 1 else ".airp."
    max_siid = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    max_piid = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    env = load_env()  # missing values are prompted for
    user = env.get("DREAME_USERNAME") or input("Dreamehome email: ").strip()
    password = env.get("DREAME_PASSWORD") or getpass.getpass("Password: ")
    country = env.get("DREAME_COUNTRY") or input("Region [us/eu/cn/sg/kr/ru] (us): ").strip() or "us"

    api = api_mod.DreameCloudAPI(user, password, country)
    if not api.login():
        sys.exit("Login failed (check region and password).")

    devices = [d for d in (api.get_devices() or []) if model_filter in d.get("model", "")]
    if not devices:
        sys.exit(f"No devices matching {model_filter!r} on this account.")

    for d in devices:
        did, host = str(d["did"]), d.get("bindDomain")
        print(f"\n=== {d.get('model')}  did={did}  host={host}  name={d.get('customName')}")
        props = [{"siid": s, "piid": p} for s in range(1, max_siid + 1) for p in range(1, max_piid + 1)]
        found = {}
        for i in range(0, len(props), BATCH):
            found.update(api.get_properties(did, props[i:i + BATCH], host))
        for (siid, piid), value in sorted(found.items()):
            print(f"siid={siid:<3} piid={piid:<3} value={value!r}")
        if not found:
            print("No readable properties (device offline or in deep standby?).")


if __name__ == "__main__":
    main()
