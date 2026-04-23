"""
探测账号下所有设备支持哪些 GET/SET 端点。
用法：python3 probe_endpoints.py

对每台设备测试所有已知端点，帮助识别新设备型号的正确 API 路径。
"""
import hashlib, sys, requests
from dump_device_params import login, headers

requests.packages.urllib3.disable_warnings()

BASE = "https://app.psmartcloud.com/App/"

# 所有已知的 GET 端点（SET = Get → Set）
GET_ENDPOINTS = [
    "ADevGetStatusDCERV",
    "ADevGetStatusNewDCERV",
    "ADevGetStatusMidERV",
    "ADevGetStatusSmallERV",
    "ADevGetStatusNeedsAP",
    "ADevGetStatusJDNeedsAP",
    "ADevGetStatusInfoERV",
    "ADevGetStatusInfoFloorPlacedERV",
    "ACDevGetStatusInfoAW",
]


def gen_token(device_id: str) -> str | None:
    parts = device_id.split("_")
    if len(parts) != 3:
        return None
    mac, cat, suf = parts[0].upper(), parts[1].upper(), parts[2]
    inner = hashlib.sha512((mac[6:] + "_" + cat + "_" + mac[:6]).encode()).hexdigest()
    return hashlib.sha512((inner + "_" + suf).encode()).hexdigest()


def probe_device(device_id: str, usr_id: str, ssid: str):
    token = gen_token(device_id)
    if not token:
        print("  [!] token 生成失败，跳过")
        return
    hdrs = headers(ssid)
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
                keys = list(j["results"].keys())[:8]
                print(f"  ✅  {ep:<42} fields: {keys}")
            elif "error" in j:
                code = j["error"].get("code", "?")
                msg  = j["error"].get("message", "")[:40]
                print(f"  ❌  {ep:<42} error {code}: {msg}")
            else:
                print(f"  ⚠️   {ep:<42} {str(j)[:60]}")
        except Exception as e:
            print(f"  💥  {ep:<42} {e}")


def main():
    print("登录中...")
    usr_id, ssid, dev_list, *_ = login()
    print(f"  usrId={usr_id}  ssid={ssid[:12]}...\n")

    for dev in dev_list:
        device_id = dev.get("deviceId", "")
        sub_type  = dev.get("params", {}).get("devSubTypeId", "?")
        model     = dev.get("params", {}).get("deviceMNO", "?")
        print(f"━━━ {device_id}  [{sub_type} / {model}]")
        probe_device(device_id, usr_id, ssid)
        print()


if __name__ == "__main__":
    main()
