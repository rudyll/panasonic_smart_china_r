"""
Route A: 登录松下云并 dump 所有已绑定设备的完整响应 JSON。

目的：看 UsrGetBindDevInfo 返回里新风机（category=0800, DCERV-03）的 params
字典有哪些字段，以此推断云端 API 的字段名空间——不需要抓包。

用法：
    python3 dump_device_params.py
或：
    PMS_USER=手机号 PMS_PASS=密码 python3 dump_device_params.py

输出：
    - 控制台打印每台设备的完整 params（新风机会加 [FRESH-AIR] 标记）
    - dump_<timestamp>.json：原始 UsrGetBindDevInfo 响应，方便回看/diff
"""

import os
import sys
import json
import time
import hashlib
import requests

# ---- 配置：优先读环境变量，回退到下面的默认值 ----
USERNAME = os.environ.get("PMS_USER", "改成你的名字")
PASSWORD = os.environ.get("PMS_PASS", "改成你的密码")

URL_GET_TOKEN = "https://app.psmartcloud.com/App/UsrGetToken"
URL_LOGIN     = "https://app.psmartcloud.com/App/UsrLogin"
URL_GET_DEV   = "https://app.psmartcloud.com/App/UsrGetBindDevInfo"


def headers(ssid=None):
    h = {"User-Agent": "SmartApp", "Content-Type": "application/json"}
    if ssid:
        h["Cookie"] = f"SSID={ssid}"
    return h


def login():
    """返回 (usr_id, ssid, family_id, real_family_id) 或在失败时抛出异常。"""
    s = requests.Session()

    # 1) GetToken
    r = s.post(URL_GET_TOKEN,
               json={"id": 1, "uiVersion": 4.0, "params": {"usrId": USERNAME}},
               headers=headers(), verify=False, timeout=10)
    j = r.json()
    if "results" not in j:
        raise RuntimeError(f"GetToken 失败: {j}")
    token_start = j["results"]["token"]

    # 2) 派生密码
    pwd_md5     = hashlib.md5(PASSWORD.encode()).hexdigest().upper()
    inter_md5   = hashlib.md5((pwd_md5 + USERNAME).encode()).hexdigest().upper()
    final_token = hashlib.md5((inter_md5 + token_start).encode()).hexdigest().upper()

    # 3) Login
    r = s.post(URL_LOGIN,
               json={"id": 2, "uiVersion": 4.0,
                     "params": {"telId": "00:00:00:00:00:00",
                                "checkFailCount": 0,
                                "usrId": USERNAME,
                                "pwd": final_token}},
               headers=headers(), verify=False, timeout=10)
    j = r.json()
    if "results" not in j:
        raise RuntimeError(f"登录失败: {j}")
    res = j["results"]
    return res["usrId"], res["ssId"], res["familyId"], res["realFamilyId"]


def get_bind_dev_info(usr_id, ssid, family_id, real_family_id):
    """拉全部绑定设备，返回原始 JSON。"""
    r = requests.post(
        URL_GET_DEV,
        json={"id": 3, "uiVersion": 4.0,
              "params": {"realFamilyId": real_family_id,
                         "familyId": family_id,
                         "usrId": usr_id}},
        headers=headers(ssid), verify=False, timeout=10,
    )
    return r.json()


def classify(device_id: str) -> str:
    """根据 deviceId 的 category 段粗分类。"""
    parts = device_id.split("_")
    if len(parts) < 2:
        return "UNKNOWN"
    cat = parts[1]
    return {
        "0900": "AC",            # 空调
        "0800": "FRESH-AIR",     # 新风/DCERV
        "0600": "WASHER",        # 洗衣机
    }.get(cat, f"CATEGORY-{cat}")


def pretty(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def main():
    requests.packages.urllib3.disable_warnings()

    print(f"登录中 (user={USERNAME}) ...")
    usr_id, ssid, family_id, real_family_id = login()
    print(f"  OK  usrId={usr_id}  ssid={ssid[:12]}...  "
          f"familyId={family_id}  realFamilyId={real_family_id}")

    print("拉取设备列表 ...")
    raw = get_bind_dev_info(usr_id, ssid, family_id, real_family_id)

    # 保存原始响应，方便后续比对/复用
    ts = time.strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"dump_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"  原始响应已保存: {out_path}")

    if "results" not in raw or "devList" not in raw["results"]:
        print("!! 返回无 devList，原始响应如下：")
        print(pretty(raw))
        sys.exit(1)

    dev_list = raw["results"]["devList"]
    print(f"\n共 {len(dev_list)} 台设备。\n" + "=" * 72)

    for i, dev in enumerate(dev_list, 1):
        device_id = dev.get("deviceId", "?")
        kind = classify(device_id)
        print(f"\n[{i}] {kind}  deviceId={device_id}")
        print(f"    顶层 key: {sorted(dev.keys())}")

        # 顶层字段（非 params），逐个打印
        for k, v in dev.items():
            if k == "params":
                continue
            print(f"    - {k}: {v!r}")

        # params（重点）
        params = dev.get("params", {})
        print(f"    params ({len(params)} keys):")
        if not params:
            print("      <空>")
        else:
            # 先按 key 排序打印，方便肉眼扫字段
            for k in sorted(params.keys()):
                v = params[k]
                # 长字符串截断
                vs = repr(v)
                if len(vs) > 120:
                    vs = vs[:117] + "..."
                print(f"      {k}: {vs}")

        if kind == "FRESH-AIR":
            print(f"\n  >> [FRESH-AIR] 完整 params JSON:")
            print("     " + pretty(params).replace("\n", "\n     "))

    print("\n" + "=" * 72)
    print("下一步建议：把新风机的 params keys 贴回来，我们据此设计字段映射 / 枚举读写端点。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"!! 出错: {e}")
        sys.exit(1)
