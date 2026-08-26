"""Static regression checks for optional AC room-temperature sensors.

Home Assistant is not installed in the lightweight repository test environment,
so these checks inspect the parsed Python syntax tree instead of importing the
integration modules.
"""

import ast
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
CONFIG_FLOW = ROOT / "custom_components/panasonic_smart_china_r/config_flow.py"
CLIMATE = ROOT / "custom_components/panasonic_smart_china_r/devices/ac/climate.py"
TEMPERATURE = ROOT / "custom_components/panasonic_smart_china_r/devices/ac/temperature.py"
SPEC = importlib.util.spec_from_file_location("ac_temperature", TEMPERATURE)
AC_TEMPERATURE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AC_TEMPERATURE)
decode_temperature = AC_TEMPERATURE.decode_temperature


def _calls_named(tree: ast.AST, attribute: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == attribute
    ]


class ACOptionalSensorTest(unittest.TestCase):
    def test_decode_scaled_cloud_temperature(self):
        self.assertEqual(decode_temperature(52), 26.0)
        self.assertEqual(decode_temperature("49", scale=2), 24.5)

    def test_decode_temperature_rejects_protocol_sentinels(self):
        for value in (None, 127, 255, 65535, "invalid"):
            self.assertIsNone(decode_temperature(value))

    def test_config_flow_marks_sensor_optional_and_reads_it_safely(self):
        tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))

        optional_sensor = any(
            call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "CONF_SENSOR_ID"
            for call in _calls_named(tree, "Optional")
        )
        safe_sensor_read = any(
            call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "CONF_SENSOR_ID"
            for call in _calls_named(tree, "get")
        )

        self.assertTrue(optional_sensor)
        self.assertTrue(safe_sensor_read)

    def test_climate_accepts_entries_without_sensor(self):
        tree = ast.parse(CLIMATE.read_text(encoding="utf-8"))

        safe_config_read = any(
            isinstance(call.func.value, ast.Name)
            and call.func.value.id == "config"
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "CONF_SENSOR_ID"
            for call in _calls_named(tree, "get")
        )

        self.assertTrue(safe_config_read)


if __name__ == "__main__":
    unittest.main()
