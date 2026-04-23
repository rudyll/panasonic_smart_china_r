"""
通用 SET 字段测试工具。适配新设备型号时用来验证端点是否可用。

用法：
    python3 test_set_field.py get            # 读取当前状态（GET 端点）
    python3 test_set_field.py set            # 发送全 255 payload（不改任何字段，验证 SET 端点）
    python3 test_set_field.py set runSta 0   # 发送指定字段值（例：关机）
    python3 test_set_field.py set runSta 1   # 发送指定字段值（例：开机）

配置说明（修改下方 CONFIG 区域）：
  1. GET_ENDPOINT / SET_ENDPOINT — 把 Get/Set 换成你的端点名
  2. DEVICE_ID — 从 dump_device_params.py 输出中复制
  3. PAYLOAD_DEFAULTS — 从 App 源码的 *DevStatusSetBean.java 复制所有字段
     可写字段默认 255，定时器小时/分钟默认 127

成功判断：
  - GET：返回包含控制字段（如 runSta）的 results 字典
  - SET：返回 {"results": {"todoId": N}}，且设备在约 3 秒内响应
"""
import sys, json, requests
from dump_device_params import login, headers
from probe_endpoints import gen_token

requests.packages.urllib3.disable_warnings()

BASE = "https://app.psmartcloud.com/App/"

# ── 用户配置区 ────────────────────────────────────────────────────────────────
# 1. 把下面两行换成你的端点（probe_endpoints.py 测出来的 GET 端点，Set 照规律推）
GET_ENDPOINT = "ADevGetStatusDCERV"
SET_ENDPOINT = "ADevSetStatusDCERV"

# 2. 粘贴你的 deviceId（MAC_CATEGORY_SUFFIX 格式）
#    留空则自动用账号下第一台设备
DEVICE_ID = ""

# 3. 在这里列出你的设备所有可写字段及默认 skip 值
#    规则：来自 App 源码 *DevStatusSetBean.java，未知字段一律填 255
#    例外：定时器的 tH*/tMin* 填 127（来自 BaseDevStateBean.java）
PAYLOAD_DEFAULTS: dict = {
    # === 以下是 DCERV-03 示例，请替换为你设备的字段 ===
    "runSta": 255,
    "runM": 255,
    "airVo": 255,
    "preSet": 255,
    "preM": 255,
    "holM": 255,
    "pmSen": 255,
    "coSen": 255,
    "tvSen": 255,
    "userSupWind": 255,
    "userExhWind": 255,
    "aircJoi": 255,
    "oaFilEx": 255,
    # 定时器（6 组）
    **{f"tSta{i}": 255 for i in range(1, 7)},
    **{f"tM{i}": 255 for i in range(1, 7)},
    **{f"tWind{i}": 255 for i in range(1, 7)},
    **{f"tSet{i}": 255 for i in range(1, 7)},
    **{f"tH{i}": 127 for i in range(1, 7)},    # 小时用 127
    **{f"tMin{i}": 127 for i in range(1, 7)},  # 分钟用 127
    **{f"tWeek{i}": 255 for i in range(1, 7)},
}
# ── 配置区结束 ────────────────────────────────────────────────────────────────


def do_get(usr_id: str, ssid: str, device_id: str) -> dict:
    token = gen_token(device_id)
    r = requests.post(
        BASE + GET_ENDPOINT,
        json={"id": 1, "uiVersion": 4.0,
              "params": {"usrId": usr_id, "deviceId": device_id, "token": token}},
        headers=headers(ssid), verify=False, timeout=10,
    )
    return r.json()


def do_set(usr_id: str, ssid: str, device_id: str, overrides: dict) -> dict:
    token = gen_token(device_id)
    payload = {**PAYLOAD_DEFAULTS, "usrId": usr_id, "deviceId": device_id, "token": token}
    payload.update(overrides)
    r = requests.post(
        BASE + SET_ENDPOINT,
        json={"id": 1, "uiVersion": 4.0, "params": payload},
        headers=headers(ssid), verify=False, timeout=10,
    )
    return r.json()


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ("get", "set"):
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    print("登录中...")
    usr_id, ssid, dev_list, *_ = login()
    print(f"  usrId={usr_id}  ssid={ssid[:12]}...\n")

    device_id = DEVICE_ID
    if not device_id:
        if not dev_list:
            print("账号下没有绑定设备")
            sys.exit(1)
        device_id = dev_list[0]["deviceId"]
        print(f"  未指定 DEVICE_ID，自动选取: {device_id}")

    if cmd == "get":
        print(f"GET {GET_ENDPOINT}")
        resp = do_get(usr_id, ssid, device_id)
        results = resp.get("results", {})
        if isinstance(results, dict) and results:
            print(f"  ✅ 返回 {len(results)} 个字段")
            for k, v in sorted(results.items()):
                print(f"    {k} = {v}")
        else:
            print(f"  响应: {json.dumps(resp, ensure_ascii=False)}")

    elif cmd == "set":
        overrides: dict = {}
        if len(args) == 3:
            field, raw_val = args[1], args[2]
            try:
                overrides[field] = int(raw_val)
            except ValueError:
                print(f"字段值必须是整数，收到: {raw_val!r}")
                sys.exit(1)
            print(f"SET {SET_ENDPOINT}  {field}={overrides[field]}")
        else:
            print(f"SET {SET_ENDPOINT}  (全 255/127，不修改任何字段)")

        resp = do_set(usr_id, ssid, device_id, overrides)
        todo_id = resp.get("results", {}).get("todoId") if isinstance(resp.get("results"), dict) else None
        if todo_id is not None:
            print(f"  ✅ todoId={todo_id}  — 等待设备响应（约 3 秒）")
        else:
            print(f"  响应: {json.dumps(resp, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
