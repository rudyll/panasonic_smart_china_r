"""Pure-Python checks for the LD5C SET diagnostic helper."""

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "tools/probe_ld5c_set.py"
SPEC = importlib.util.spec_from_file_location("probe_ld5c_set", MODULE_PATH)
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


class ProbeLd5cSetTest(unittest.TestCase):
    def test_minimal_probe_has_no_control_fields(self):
        params = PROBE.build_set_params(
            "minimal", "device", "token", "user"
        )
        self.assertEqual(
            params,
            {"deviceId": "device", "token": "token", "usrId": "user"},
        )

    def test_ld5c_schema_uses_status_all_field_names(self):
        params = PROBE.build_set_params(
            "ld5c", "device", "token", "user", "power", 0
        )
        self.assertEqual(params["runningStatus"], 0)
        self.assertEqual(params["runningMode"], 255)
        self.assertNotIn("runSta", params)

    def test_ld6c_schema_uses_complete_skip_payload(self):
        params = PROBE.build_set_params(
            "ld6c", "device", "token", "user", "mode", 5
        )
        self.assertEqual(params["runM"], 5)
        self.assertEqual(params["airVo"], 255)
        self.assertEqual(params["tH1"], 255)
        self.assertEqual(params["res10"], 255)

    def test_dcerv_timer_hour_uses_127_skip(self):
        params = PROBE.build_set_params(
            "dcerv", "device", "token", "user"
        )
        self.assertEqual(params["tH1"], 127)
        self.assertEqual(params["tMin6"], 127)

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
