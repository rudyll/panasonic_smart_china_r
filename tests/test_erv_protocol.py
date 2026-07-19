"""Pure-Python checks for ERV protocol maps and payloads."""

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components/panasonic_smart_china_r/devices/erv/__init__.py"
)
SPEC = importlib.util.spec_from_file_location("erv_protocol", MODULE_PATH)
ERV = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ERV)


class ErvProtocolTest(unittest.TestCase):
    def test_ld6c_mode_and_air_volume_maps(self):
        self.assertEqual(
            ERV.LD6C_RUN_MODE_GET_MAP,
            {1: "热交换", 4: "内循环", 6: "自动ECO", 7: "消毒"},
        )
        self.assertEqual(ERV.LD6C_AIR_VOLUME_MAP, {0: "静音", 1: "低", 2: "高"})

    def test_ld6c_payload_uses_app_field_names_and_skip_values(self):
        payload = ERV.build_ld6c_payload("device", "token", "user", runM=6)

        self.assertEqual(payload["runM"], 6)
        self.assertEqual(payload["airVo"], 255)
        self.assertEqual(payload["saFilEX"], 255)
        self.assertNotIn("saFilEx", payload)
        self.assertEqual(payload["tH1"], 255)
        self.assertEqual(payload["tMin6"], 255)
        self.assertEqual(payload["res10"], 255)

    def test_miderv_payload_keeps_its_distinct_timer_skip_values(self):
        payload = ERV.build_miderv_payload("device", "token", "user")
        self.assertEqual(payload["tOnH"], 127)
        self.assertEqual(payload["tOffMin"], 127)

    def test_smallerv_uses_app_wind_values_and_six_timer_payloads(self):
        self.assertEqual(ERV.SMALLERV_AIR_VOLUME_MAP, {0: "低", 1: "高"})
        payload = ERV.build_smallerv_payload("device", "token", "user", airVo=1)
        self.assertEqual(payload["airVo"], 1)
        self.assertEqual(payload["filSet"], 0)
        self.assertEqual(payload["tH1"], 255)
        self.assertEqual(payload["tMin6"], 255)
        self.assertNotIn("tOnH", payload)

    def test_newdcerv_has_its_own_payload_and_preserves_current_oa_pm(self):
        payload = ERV.build_newdcerv_payload(
            "device", "token", "user", runSta=1, oaPMC=18
        )
        self.assertEqual(payload["runSta"], 1)
        self.assertEqual(payload["oaPMC"], 18)
        self.assertEqual(payload["nanoe"], 255)
        self.assertEqual(payload["tH1"], 127)
        self.assertEqual(payload["tMin6"], 127)
        self.assertNotIn("preSet", payload)
        self.assertNotIn("userSupWind", payload)


if __name__ == "__main__":
    unittest.main()
