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

    def test_ld6c_sensor_whitelist_matches_verified_device_report(self):
        self.assertEqual(
            set(ERV.SENSOR_KEYS_BY_PROFILE["LD6C"]),
            {
                "oaPMC", "raPMC", "oaHumC", "oaTeC",
                "oaFilExTL", "saFilExTL", "raFilExTL", "resFilExTL",
            },
        )
        self.assertNotIn("saPMC", ERV.SENSOR_KEYS_BY_PROFILE["LD6C"])
        self.assertNotIn("raCO2C", ERV.SENSOR_KEYS_BY_PROFILE["LD6C"])

    def test_dcerv_uses_live_endpoint_and_only_reported_sensor_fields(self):
        self.assertIn("DCERV", ERV.LIVE_STATUS_PROFILES)
        self.assertIn("LD6C", ERV.LIVE_STATUS_PROFILES)
        self.assertIn("saTeC", ERV.SENSOR_KEYS_BY_PROFILE["DCERV"])
        self.assertIn("saFilExTL", ERV.SENSOR_KEYS_BY_PROFILE["DCERV"])
        self.assertNotIn("saHumC", ERV.SENSOR_KEYS_BY_PROFILE["DCERV"])
        self.assertNotIn("resFilExTL", ERV.SENSOR_KEYS_BY_PROFILE["DCERV"])

    def test_ld5c_payload_uses_official_web_page_field_names(self):
        payload = ERV.build_ld5c_payload("device", "token", "user", runSta=0)

        # 内部短字段名要翻译成官方 Web 控制页的长驼峰名。
        self.assertEqual(payload["runningStatus"], 0)
        self.assertNotIn("runSta", payload)
        self.assertEqual(payload["runningMode"], 255)
        self.assertEqual(payload["airVolume"], 255)
        self.assertEqual(payload["onTimerHour"], 127)
        self.assertEqual(payload["offTimerMinute"], 127)
        self.assertEqual(payload["onTimerSetting"], 255)
        # 身份字段由请求体顶层携带，不能出现在 params 里。
        self.assertNotIn("deviceId", payload)
        self.assertNotIn("token", payload)
        self.assertNotIn("usrId", payload)

    def test_ld5c_status_fields_map_to_internal_names(self):
        status = ERV.normalize_status(
            "LD5C",
            {"runningStatus": "1", "runningMode": "2", "airVolume": "3", "oaTempCur": 26},
        )
        self.assertEqual(status["runSta"], "1")
        self.assertEqual(status["runM"], "2")
        self.assertEqual(status["airVo"], "3")
        self.assertEqual(status["oaTeC"], 26)
        self.assertNotIn("runningStatus", status)

    def test_normalize_status_is_a_no_op_for_short_field_profiles(self):
        results = {"runSta": 1, "airVo": 2}
        self.assertEqual(ERV.normalize_status("LD6C", results), results)

    def test_ld5c_info_endpoints_use_top_level_identity_and_xtoken(self):
        profile = ERV.ERV_PROFILES["LD5C"]

        # LD5C 的请求序号固定为 0，与官方 Web 控制页一致，不跟随调用方自增。
        body = ERV.build_set_body(profile, 7, "device", "token", "user", {"runningStatus": 0})
        self.assertEqual(body["id"], 0)
        self.assertEqual(body["usrId"], "user")
        self.assertEqual(body["deviceId"], "device")
        self.assertEqual(body["token"], "token")
        self.assertEqual(body["params"], {"runningStatus": 0})

        status_body = ERV.build_status_body(profile, 2, "device", "token", "user")
        self.assertEqual(status_body["deviceId"], "device")
        self.assertNotIn("params", status_body)

        headers = ERV.build_headers(profile, "abc")
        self.assertEqual(headers["xtoken"], "SSID=abc")
        ERV.refresh_ssid_headers(headers, "xyz")
        self.assertEqual(headers["xtoken"], "SSID=xyz")
        self.assertEqual(headers["Cookie"], "SSID=xyz")

    def test_other_profiles_keep_the_nested_params_request_shape(self):
        profile = ERV.ERV_PROFILES["LD6C"]

        body = ERV.build_set_body(profile, 1, "device", "token", "user", {"runSta": 0})
        self.assertEqual(body, {"id": 1, "params": {"runSta": 0}})

        status_body = ERV.build_status_body(profile, 1, "device", "token", "user")
        self.assertEqual(status_body["params"]["deviceId"], "device")
        self.assertEqual(status_body["uiVersion"], 4.0)

        headers = ERV.build_headers(profile, "abc")
        self.assertNotIn("xtoken", headers)

    def test_ld5c_reads_live_state_and_takes_sensors_from_aux_endpoint(self):
        self.assertIn("LD5C", ERV.LIVE_STATUS_PROFILES)
        self.assertEqual(
            set(ERV.SENSOR_KEYS_BY_PROFILE["LD5C"]),
            {"oaPMC", "oaHumC", "oaTeC", "raFilExTL"},
        )
        self.assertEqual(
            ERV.ERV_PROFILES["LD5C"]["aux_sensor_keys"],
            ERV.SENSOR_KEYS_BY_PROFILE["LD5C"],
        )
        self.assertEqual(ERV.LD5C_RUN_MODE_GET_MAP, {0: "热交换", 2: "内循环", 5: "外循环"})
        self.assertEqual(ERV.LD5C_AIR_VOLUME_MAP, {1: "低", 2: "中", 3: "高"})

    def test_sensor_sentinels_are_field_specific(self):
        self.assertTrue(ERV.is_invalid_sensor_value("saPMC", 65535))
        self.assertTrue(ERV.is_invalid_sensor_value("raCO2C", "65535"))
        self.assertTrue(ERV.is_invalid_sensor_value("raHumC", 255))
        self.assertTrue(ERV.is_invalid_sensor_value("raTeC", 127))
        self.assertTrue(ERV.is_invalid_sensor_value("saTeC", 255))
        self.assertFalse(ERV.is_invalid_sensor_value("raPMC", 0))
        self.assertFalse(ERV.is_invalid_sensor_value("oaPMC", 255))
        self.assertFalse(ERV.is_invalid_sensor_value("oaFilExTL", 0))


if __name__ == "__main__":
    unittest.main()
