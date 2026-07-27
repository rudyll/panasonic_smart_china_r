"""Compatibility entrypoint for the LD5C SET diagnostic profile.

Existing commands remain unchanged:

    python3 tools/probe_ld5c_set.py inspect
    python3 tools/probe_ld5c_set.py probe
    python3 tools/probe_ld5c_set.py control ...

The implementation is provided by ``probe_set_endpoints.py`` and the editable
JSON profile at ``tools/set_probe_profiles/ld5c.json``.
"""

from pathlib import Path

from probe_set_endpoints import cli


PROFILE_PATH = Path(__file__).with_name("set_probe_profiles") / "ld5c.json"


if __name__ == "__main__":
    cli(default_profile=PROFILE_PATH)
