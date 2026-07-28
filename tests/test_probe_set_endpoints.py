"""Pure-Python checks for the generic SET endpoint diagnostic helper."""

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / "tools/probe_set_endpoints.py"
PROFILE_PATH = ROOT / "tools/set_probe_profiles/ld5c.json"
SPEC = importlib.util.spec_from_file_location("probe_set_endpoints", MODULE_PATH)
PROBE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROBE)


class FakeResponse:
    def __init__(self, body, status=200, content_type="application/json"):
        self._body = body
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.text = body if isinstance(body, str) else ""

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class ProbeSetEndpointsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = PROBE.load_profile(PROFILE_PATH)

    def test_ld5c_profile_loads_expected_probe_matrix(self):
        self.assertEqual(self.profile["deviceFilter"]["devSubTypePrefix"], "LD5C")
        self.assertEqual(self.profile["getEndpoint"], "ADevGetStatusLD6C")
        self.assertIn(
            {"endpoint": "ADevSetStatusLD5C", "schema": "ld5c"},
            self.profile["probeMatrix"],
        )
        self.assertIn(
            {"endpoint": "ADevSetStatusMidERV", "schema": "miderv"},
            self.profile["probeMatrix"],
        )

    def test_validate_command_does_not_require_credentials(self):
        old_user = PROBE.os.environ.pop("PMS_USER", None)
        old_password = PROBE.os.environ.pop("PMS_PASS", None)
        try:
            result = PROBE.main(
                ["validate", "--profile", str(PROFILE_PATH)]
            )
        finally:
            if old_user is not None:
                PROBE.os.environ["PMS_USER"] = old_user
            if old_password is not None:
                PROBE.os.environ["PMS_PASS"] = old_password
        self.assertEqual(result, 0)

    def test_minimal_probe_has_no_control_fields(self):
        params = PROBE.build_set_params(
            self.profile, "minimal", "device", "token", "user"
        )
        self.assertEqual(
            params,
            {"deviceId": "device", "token": "token", "usrId": "user"},
        )

    def test_ld5c_schema_uses_status_all_field_names(self):
        params = PROBE.build_set_params(
            self.profile, "ld5c", "device", "token", "user", "power", 0
        )
        self.assertEqual(params["runningStatus"], 0)
        self.assertEqual(params["runningMode"], 255)
        self.assertNotIn("runSta", params)

    def test_field_series_expand_complete_ld6c_payload(self):
        params = PROBE.build_set_params(
            self.profile, "ld6c", "device", "token", "user", "mode", 5
        )
        self.assertEqual(params["runM"], 5)
        self.assertEqual(params["airVo"], 255)
        self.assertEqual(params["tH1"], 255)
        self.assertEqual(params["res10"], 255)

    def test_dcerv_timer_hour_uses_127_skip(self):
        params = PROBE.build_set_params(
            self.profile, "dcerv", "device", "token", "user"
        )
        self.assertEqual(params["tH1"], 127)
        self.assertEqual(params["tMin6"], 127)

    def test_miderv_schema_uses_protocol_sentinels(self):
        params = PROBE.build_set_params(
            self.profile, "miderv", "device", "token", "user", "power", 0
        )
        self.assertEqual(params["runSta"], 0)
        self.assertEqual(params["runM"], 255)
        self.assertEqual(params["airVo"], 255)
        self.assertEqual(params["tOnH"], 127)
        self.assertEqual(params["tOffMin"], 127)

    def test_control_value_must_be_explicitly_allowed(self):
        with self.assertRaisesRegex(ValueError, "允许值"):
            PROBE.build_set_params(
                self.profile,
                "ld5c",
                "device",
                "token",
                "user",
                "mode",
                99,
            )

    def test_profile_rejects_arbitrary_endpoint_url(self):
        raw = {
            "name": "bad",
            "deviceFilter": {"devSubTypePrefix": "BAD"},
            "schemas": {
                "minimal": {
                    "skipFields": {},
                    "controlFields": {},
                    "allowedValues": {},
                }
            },
            "probeMatrix": [
                {"endpoint": "https://example.com/collect", "schema": "minimal"}
            ],
        }
        with self.assertRaisesRegex(ValueError, "端点名"):
            PROBE.validate_profile(raw)

    def test_profile_rejects_identity_field_override(self):
        raw = {
            "name": "bad",
            "deviceFilter": {"devSubTypePrefix": "BAD"},
            "schemas": {
                "bad": {
                    "skipFields": {"token": "attacker-value"},
                    "controlFields": {},
                    "allowedValues": {},
                }
            },
            "probeMatrix": [{"endpoint": "ADevSetStatusBad", "schema": "bad"}],
        }
        with self.assertRaisesRegex(ValueError, "身份字段"):
            PROBE.validate_profile(raw)

    def test_profile_rejects_identity_control_field(self):
        raw = {
            "name": "bad",
            "deviceFilter": {"devSubTypePrefix": "BAD"},
            "schemas": {
                "bad": {
                    "skipFields": {},
                    "controlFields": {"power": "deviceId"},
                    "allowedValues": {"power": [0, 1]},
                }
            },
            "probeMatrix": [{"endpoint": "ADevSetStatusBad", "schema": "bad"}],
        }
        with self.assertRaisesRegex(ValueError, "身份字段"):
            PROBE.validate_profile(raw)

    def test_device_filter_checks_subtype_and_category(self):
        devices = [
            {
                "deviceId": "AABBCC112233_0900_LD5C",
                "params": {"devSubTypeId": "LD5C"},
            },
            {
                "deviceId": "AABBCC112233_0800_LD5C",
                "params": {"devSubTypeId": "LD5C-01"},
            },
        ]
        selected = PROBE.find_device(devices, self.profile, 1)
        self.assertEqual(selected["deviceId"], "AABBCC112233_0800_LD5C")

    def test_response_summary_keeps_top_level_error_code(self):
        summary = PROBE.summarize_response(
            FakeResponse({"errorCode": 4102, "results": {}})
        )
        self.assertEqual(summary["errorCode"], 4102)

    def test_response_summary_handles_empty_non_json_body(self):
        summary = PROBE.summarize_response(
            FakeResponse("", status=404, content_type="text/html")
        )
        self.assertEqual(summary["httpStatus"], 404)
        self.assertEqual(summary["body"], "")

    def test_report_redacts_credentials_and_device_id(self):
        redacted = PROBE.redact(
            {
                "usrId": "account",
                "token": "secret",
                "message": "device AABBCC112233_0800_LD5C rejected",
            }
        )
        self.assertEqual(redacted["usrId"], "<redacted>")
        self.assertEqual(redacted["token"], "<redacted>")
        self.assertNotIn("AABBCC112233", redacted["message"])


if __name__ == "__main__":
    unittest.main()
