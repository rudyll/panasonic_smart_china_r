"""
探测账号下所有设备支持哪些 GET/SET 端点。
用法：python3 tools/probe_endpoints.py --report

对每台设备测试所有已知端点，帮助识别新设备型号的正确 API 路径。
--report 会另外生成可公开分享的脱敏 JSON，用于 issue 反馈。
"""
import argparse
import hashlib
import json
import re
import time

import requests

from dump_device_params import login, headers, get_bind_dev_info

requests.packages.urllib3.disable_warnings()

BASE = "https://app.psmartcloud.com/App/"

# 所有已知的 GET 端点（SET = Get → Set）
GET_ENDPOINTS = [
    "ADevGetStatusDCERV",
    "ADevGetStatusNewDCERV",
    "ADevGetStatusMidERV",
    "ADevGetStatusSmallERV",
    "ADevGetStatusLD6C",
    "ADevGetStatusNeedsAP",
    "ADevGetStatusJDNeedsAP",
    "ADevGetStatusInfoERV",
    "ADevGetStatusInfoFloorPlacedERV",
    "ACDevGetStatusInfoAW",
]

_SENSITIVE_KEYS = {
    "deviceid", "devid", "deviceuuid", "mac", "devicemac", "sn", "devicesn",
    "usrid", "userid", "ssid", "token", "password", "pwd", "tel", "mobile",
    "familyid", "realfamilyid",
}
_DEVICE_ID_RE = re.compile(
    r"\b[0-9a-f]{12}_\d{4}_[a-z0-9.-]+\b", re.IGNORECASE
)


def redact(value):
    """递归脱敏账号、会话和设备唯一标识，保留传感器字段与数值。"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            result[key] = "<redacted>" if normalized in _SENSITIVE_KEYS else redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _DEVICE_ID_RE.sub("<redacted-device-id>", value)
    return value


def gen_token(device_id: str) -> str | None:
    parts = device_id.split("_")
    if len(parts) != 3:
        return None
    mac, cat, suf = parts[0].upper(), parts[1].upper(), parts[2]
    inner = hashlib.sha512((mac[6:] + "_" + cat + "_" + mac[:6]).encode()).hexdigest()
    return hashlib.sha512((inner + "_" + suf).encode()).hexdigest()


def probe_device(device_id: str, usr_id: str, ssid: str) -> dict:
    token = gen_token(device_id)
    if not token:
        print("  [!] token 生成失败，跳过")
        return {"error": "token generation failed"}
    hdrs = headers(ssid)
    endpoint_results = {}
    for ep in GET_ENDPOINTS:
        try:
            r = requests.post(
                BASE + ep,
                json={"id": 1, "uiVersion": 4.0,
                      "params": {"usrId": usr_id, "deviceId": device_id, "token": token}},
                headers=hdrs, verify=False, timeout=8,
            )
            j = r.json()
            if "results" in j and isinstance(j["results"], dict) and j["results"]:
                results = redact(j["results"])
                endpoint_results[ep] = {"status": "ok", "results": results}
                print(f"  ✅  {ep:<42} fields: {len(results)}")
            elif "error" in j:
                code = j["error"].get("code", "?")
                msg = redact(str(j["error"].get("message", "")))[:40]
                endpoint_results[ep] = {
                    "status": "error", "code": code, "message": msg
                }
                print(f"  ❌  {ep:<42} error {code}: {msg}")
            else:
                endpoint_results[ep] = {
                    "status": "unexpected", "response": redact(j)
                }
                print(f"  ⚠️   {ep:<42} {str(j)[:60]}")
        except Exception as e:
            endpoint_results[ep] = {
                "status": "request_failed", "message": redact(str(e))
            }
            print(f"  💥  {ep:<42} {e}")
    return endpoint_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        action="store_true",
        help="生成可公开分享的脱敏 endpoint_report_*.json",
    )
    args = parser.parse_args()

    print("登录中...")
    usr_id, ssid, family_id, real_family_id = login()
    print("  登录成功（账号和会话信息已隐藏）")

    print("拉取设备列表 ...")
    raw = get_bind_dev_info(usr_id, ssid, family_id, real_family_id)
    dev_list = raw.get("results", {}).get("devList", [])
    print(f"  共 {len(dev_list)} 台设备\n")

    report = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "devices": []}
    for index, dev in enumerate(dev_list, 1):
        device_id = dev.get("deviceId", "")
        sub_type  = dev.get("params", {}).get("devSubTypeId", "?")
        model     = dev.get("params", {}).get("deviceMNO", "?")
        print(f"━━━ 设备 {index}  [{sub_type} / {model}]")
        endpoint_results = probe_device(device_id, usr_id, ssid)
        report["devices"].append(
            {
                "model": model,
                "devSubTypeId": sub_type,
                "endpoints": endpoint_results,
            }
        )
        print()

    if args.report:
        path = f"endpoint_report_{time.strftime('%Y%m%d-%H%M%S')}.json"
        with open(path, "w", encoding="utf-8") as file:
            json.dump(report, file, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"脱敏报告已生成: {path}")
        print("可以在公开 issue 中附上该文件；不要上传 dump_*.json。")


if __name__ == "__main__":
    main()
