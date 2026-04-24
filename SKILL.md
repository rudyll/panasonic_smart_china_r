---
description: 从中国品牌 App APK 逆向分析云端 API，并落地为标准 Home Assistant 自定义集成（含 HACS 支持）。适用于没有公开 API 文档、需要从 App 反编译 + 抓包推断协议的智能家居设备。
argument-hint: 品牌名或设备类型（如 "松下新风机"）
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, Agent
---

# SOP：APK 逆向 → Home Assistant 集成

## 概览

本 Skill 覆盖从零开始的完整流程：

```
APK 逆向 → API 协议推断 → 工具脚本验证 → HA 集成实现 → HACS 发布
```

参考实现：`panasonic_smart_china_r`（松下中国智家 App，新风 + 空调）

---

## Phase 0：获取可分析的 APK

**目标**：找到没有 VMP/Jiagu 保护的旧版 APK，jadx 可以直接反编译。

```bash
# 方案 A：从 apkpure / apkmirror 找旧版（3.x 时代通常无加固）
# 方案 B：从手机提取已安装 APK
adb shell pm list packages | grep <品牌关键词>
adb shell pm path <package_name>
adb pull <path> app.apk

# 检查是否有 Jiagu / Payegis 加固
unzip -l app.apk | grep -E "libegis|libjg|libshella|libprotect"
# 若存在 → 只能用旧版；新版需 Frida bypass（极难，见注①）

# jadx 反编译（有效的旧版）
jadx -d app_src/ app.apk
wc -l app_src/sources/**/*.java | tail -1  # > 5000 行才算有效
```

> **注①**：Payegis/Jiagu 加固的外部 watchdog 会从进程外 SIGKILL，in-process Frida hook 无法拦截。遇到加固优先找旧版 APK，不要在 bypass 上耗费太多时间。

---

## Phase 1：API 协议逆向

### 1.1 找端点 URL

```bash
grep -r "URL_\|https://" app_src/sources/ --include="*.java" | grep -v "//.*https" | grep "=" | head -40
# 或搜索 API 域名
grep -r "app\.\|cloud\.\|api\." app_src/sources/ --include="*.java" | grep "http" | head -20
```

关键类通常是 `Common.java`、`ApiUrl.java`、`NetConfig.java`，查找形如：
```java
public static final String URL_LOGIN = "https://xxx/App/UsrLogin";
public static final String URL_ADEV_GET_STATUS = "https://xxx/App/ADevGetStatusDCERV";
```

### 1.2 推断认证流程

典型模式（松下案例）：
```
Step 1  UsrGetToken → token_seed
Step 2  UsrLogin(phone, SHA-hash(pwd, token_seed)) → SSID + usrId
Step 3  每次请求：Header Cookie: SSID=xxx
```

搜索登录相关类：
```bash
grep -r "login\|Login\|authenticate\|password\|sha\|md5" app_src/sources/ -l | grep -v test | head -10
```

### 1.3 找设备 Token 算法

大多数品牌对每台设备有独立的请求 token，通常基于 deviceId 派生：

```bash
grep -r "token\|Token\|sha512\|sha256\|deviceId" app_src/sources/ --include="*.java" -l | head -10
# 找到后读对应文件，重点看 generate*Token 或 calc*Token 方法
```

松下案例（双层 SHA-512）：
```python
mac, cat, suf = deviceId.split("_")  # MAC_CATEGORY_SUFFIX
inner = sha512(f"{mac[6:].upper()}_{cat.upper()}_{mac[:6].upper()}")
token = sha512(f"{inner}_{suf}")     # suf 保持原始大小写！
```

> **陷阱**：suffix 大小写敏感，App 源码写 toUpperCase 但实测不能转大写——遇到 token 校验失败先检查这里。

### 1.4 找设备类型和 SET payload

```bash
# 找所有 StatusSetBean
find app_src/sources/ -name "*StatusSet*Bean*.java" -o -name "*SetState*Bean*.java"

# 找 payload 构造逻辑
grep -r "generateSetStatusJson\|createSetStatus\|buildPayload" app_src/sources/ -l
```

重点读：
- `*DevStatusSetBean.java`：所有可写字段及默认值（255 = skip，127 = timer skip）
- `*ParamSettingUtil.java`：`generateSetStatusJson()` 中的完整字段列表

> **核心规则**：SET payload 必须包含 bean 里的**所有字段**，缺字段会导致 todoId 返回但设备不执行。这是最常见的卡点。

### 1.5 找 devSubTypeId 和端点映射

```bash
grep -r "devSubTypeId\|SubType\|getBaseSubTypeId" app_src/sources/ --include="*.java" | head -20
# 找 DevSubType.java 或类似文件
```

确认每个 subTypeId 对应哪个 GET/SET 端点（通常在 IntentService 或 Repository 类里）。

---

## Phase 2：验证工具脚本（必做）

在写 HA 集成之前，先用纯 Python 脚本验证 API 可用。

### tools/dump_device_params.py 模板

```python
"""登录并 dump 所有设备 params。"""
import os, json, requests

USERNAME = os.environ.get("APP_USER", "")  # 不要硬编码
PASSWORD = os.environ.get("APP_PASS", "")
BASE = "https://xxx.example.com/App/"

def login():
    # Step 1: get token seed
    r1 = requests.post(BASE + "UsrGetToken", json={"id":1,"uiVersion":4.0,"params":{}}, ...)
    token_seed = r1.json()["results"]["token"]
    # Step 2: login
    pwd_hash = compute_hash(PASSWORD, token_seed)
    r2 = requests.post(BASE + "UsrLogin", json={"id":1,"params":{"phone":USERNAME,"password":pwd_hash}}, ...)
    res = r2.json()["results"]
    return res["usrId"], res["ssId"], res.get("devList", [])

def main():
    usr_id, ssid, devs = login()
    for dev in devs:
        print(json.dumps(dev, ensure_ascii=False, indent=2))
        with open(f"dump_{dev['deviceId']}.json", "w") as f:
            json.dump(dev, f, ensure_ascii=False, indent=2)
```

### tools/probe_endpoints.py 模板

```python
"""测试所有已知 GET 端点，找出该设备支持哪个。"""
GET_ENDPOINTS = [
    "ADevGetStatusDCERV", "ADevGetStatusNewDCERV",
    "ADevGetStatusMidERV", "ADevGetStatusSmallERV",
    # 按品牌 APK 里找到的端点列表补充
]
# 对每台设备 × 每个端点发请求，打印 ✅/❌ + 返回字段
```

### tools/test_set_field.py 模板

```python
"""通用 SET 验证：python3 test_set_field.py [get|set] [field] [value]"""
PAYLOAD_DEFAULTS = {
    # 从 *DevStatusSetBean.java 复制所有字段，默认 255
    # timer 的 tH*/tMin* 用 127
}
# get → 读当前状态；set → 发全 255 payload（验证端点）；set field val → 改指定字段
```

---

## Phase 3：HA 集成文件结构

```
custom_components/<domain>/
├── __init__.py          # 平台路由、session 缓存
├── api.py               # 认证、重登、response 校验
├── config_flow.py       # 登录 → 选设备 → 设备特定配置
├── const.py             # 所有常量、endpoint 映射、控制器数据库
├── coordinator.py       # DataUpdateCoordinator（共享轮询设备用）
├── exceptions.py        # LoginFailed、ReloginCooldown
├── manifest.json
├── hacs.json
├── icon.png             # 256×256，从 APK mipmap-xxhdpi 提取
├── climate.py           # thin dispatcher → devices/ac/
├── sensor.py            # thin dispatcher → devices/<type>/
├── select.py            # thin dispatcher
├── switch.py            # thin dispatcher
└── devices/
    ├── ac/
    │   └── climate.py   # PanasonicACEntity（独立轮询）
    └── <device_type>/
        ├── __init__.py  # payload builder + 字段常量
        ├── sensor.py
        ├── select.py
        └── switch.py
```

### __init__.py 关键模式

```python
DOMAIN = "your_integration"

def _platforms_for_entry(entry):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_FRESH_AIR:
        return ["sensor", "select", "switch"]
    return ["climate"]

async def async_setup_entry(hass, entry):
    # 存 coordinator
    coordinator = MyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, _platforms_for_entry(entry))
    return True

async def async_unload_entry(hass, entry):
    ok = await hass.config_entries.async_unload_platforms(entry, _platforms_for_entry(entry))
    if ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return ok
```

### const.py 关键模式

```python
DOMAIN = "your_integration"

# 设备类型
CATEGORY_MAP = {"0900": "ac", "0800": "fresh_air"}
def detect_device_kind(device_id):
    parts = device_id.split("_")
    return CATEGORY_MAP.get(parts[1]) if len(parts) >= 2 else None

# 端点路由（按 devSubTypeId 前缀匹配）
_BASE = "https://cloud.example.com/App/"
_ENDPOINT_MAP = {
    "DCERV":    (_BASE + "ADevGetStatusDCERV",    _BASE + "ADevSetStatusDCERV"),
    "NEWDCERV": (_BASE + "ADevGetStatusNewDCERV", _BASE + "ADevSetStatusNewDCERV"),
}
def get_endpoints(sub_type_id):
    upper = (sub_type_id or "").upper().replace("-", "")
    for prefix, urls in _ENDPOINT_MAP.items():
        if upper.startswith(prefix):
            return urls
    return list(_ENDPOINT_MAP.values())[0]  # fallback

# 空调控制器数据库（可扩展）
SUPPORTED_CONTROLLERS = {
    "MODEL-001": {
        "name": "控制器显示名",
        "temp_scale": 2,
        "hvac_mapping": {HVACMode.COOL: 3, HVACMode.HEAT: 4},
        "fan_mapping": {FAN_AUTO: 10, FAN_LOW: 4},
        "fan_payload_overrides": {FAN_MUTE: {"windSet": 10, "muteMode": 1}},
    }
}
```

### 平台 dispatcher 模式（4 行）

```python
# climate.py / sensor.py / select.py / switch.py（根目录）
from .const import CONF_DEVICE_KIND, DEVICE_KIND_AC  # 或 DEVICE_KIND_FRESH_AIR

async def async_setup_entry(hass, entry, async_add_entities):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_AC:
        from .devices.ac.climate import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
    # 新设备类型：elif kind == DEVICE_KIND_XXX: ...
```

---

## Phase 4：核心实现模式

### 4.1 CoordinatorEntity 轮询（共享设备推荐）

```python
class MyCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self):
        try:
            data = await self._fetch()
        except Exception as err:
            raise UpdateFailed(str(err)) from err

        if response_looks_bad(data):
            try:
                self._ssid = await relogin_entry(self.hass, self._entry)
            except ReloginCooldown as err:
                # 不抛 ConfigEntryAuthFailed，保持轮询
                pn_create(self.hass, "会话被抢占，10 分钟后重试", ...)
                raise UpdateFailed(str(err)) from err
            except LoginFailed as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            data = await self._fetch()  # retry

        # 从响应里提取本设备的 statusAll
        for dev in data["results"]["devList"]:
            if dev["deviceId"] == self._device_id:
                return dev["params"]["statusAll"] or {}
        return self.data or {}
```

### 4.2 SET 后延迟刷新

```python
async def async_select_option(self, option):
    # ... 构建 payload，发 POST ...
    await self._post_with_retry(url_set, payload, headers)
    await asyncio.sleep(5)          # 等设备处理（实测 3 秒不够）
    await self.coordinator.async_request_refresh()
```

### 4.3 payload 完整性（最重要！）

```python
def build_payload(device_id, token, usr_id, **overrides):
    """必须包含 bean 里的所有字段，缺一不可。"""
    p = {
        "deviceId": device_id, "token": token, "usrId": usr_id,
        # 从 *DevStatusSetBean.java 复制全部字段，默认 255
        "runSta": 255, "runM": 255, "airVo": 255,
        "field_a": 255, "field_b": 255, ...
    }
    # timer 字段用 127（来自 BaseDevStateBean.java）
    for i in range(1, 7):
        p[f"tH{i}"] = 127
        p[f"tMin{i}"] = 127
    p.update(overrides)
    return p
```

### 4.4 会话保活（anti-kickout）

```python
# api.py
RELOGIN_COOLDOWN_SECONDS = 600  # 10 分钟

async def relogin_entry(hass, entry):
    last = hass.data[DOMAIN].get("last_relogin", 0)
    if time.time() - last < RELOGIN_COOLDOWN_SECONDS:
        raise ReloginCooldown("冷却中，跳过重登")
    hass.data[DOMAIN]["last_relogin"] = time.time()
    new_ssid = await authenticate(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    # 更新 entry.data
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_SSID: new_ssid})
    return new_ssid
```

### 4.5 response 坏包检测

```python
AUTH_EXPIRED_ERROR_CODES = {"3003", "3004", "4102"}

def response_looks_bad(data):
    if not isinstance(data, dict):
        return True
    # 检查顶层 errorCode
    code = str(data.get("errorCode", ""))
    if code in AUTH_EXPIRED_ERROR_CODES:
        return True
    # 检查嵌套 error.code
    err = data.get("error")
    if isinstance(err, dict):
        if str(err.get("code", "")) in AUTH_EXPIRED_ERROR_CODES:
            return True
    return "results" not in data
```

---

## Phase 5：config_flow.py 结构

```
Step: user      → 输入账号密码 → 调 authenticate()
Step: device    → 展示设备列表（过滤已配置），按 deviceId 推断类型
Step: ac_config → 空调专属：选控制器型号 + 温度传感器 entity
(auto)          → 新风等直接创建 entry，存 devSubTypeId
Step: reauth    → 密码过期时重登
```

entry.data 必存字段：
- `CONF_USERNAME` / `CONF_PASSWORD`（用于静默重登）
- `CONF_USR_ID`、`CONF_SSID`、`CONF_DEVICE_ID`、`CONF_DEVICE_KIND`
- `CONF_DEV_SUB_TYPE_ID`（新风类设备，用于端点路由）
- `familyId`、`realFamilyId`（部分品牌的家庭 ID）

---

## Phase 6：图标和 HACS 配置

```bash
# 从 APK 提取图标（xxhdpi 通常是最高分辨率）
python3 -c "
from PIL import Image
img = Image.open('apk_res/mipmap-xxhdpi/ic_launcher.png')
img.resize((256, 256), Image.LANCZOS).save('custom_components/<domain>/icon.png')
"
```

**manifest.json** 最小字段：
```json
{
  "domain": "<domain>",
  "name": "品牌 + 设备名",
  "documentation": "https://github.com/<user>/<repo>",
  "codeowners": ["@<github_user>"],
  "requirements": [],
  "version": "1.0.0",
  "iot_class": "cloud_polling",
  "config_flow": true
}
```

**hacs.json**：
```json
{
  "name": "集成显示名",
  "domains": ["climate", "sensor", "select", "switch"],
  "iot_class": "cloud_polling",
  "homeassistant": "2024.1.0"
}
```

---

## 常见陷阱

| 现象 | 根因 | 解法 |
|------|------|------|
| todoId 返回但设备不执行 | SET payload 缺字段 | 对照 bean 文件补全所有字段 |
| token 校验失败 | suffix 大小写问题 | suffix 保持原始大小写，不 upper() |
| HA 状态在操作后跳回 | SET 后立刻 GET，设备未处理完 | asyncio.sleep(5) 再 request_refresh |
| 手机 App 和 HA 互踢 | 云端单 session | 10 分钟冷却 + 建议用户开第二账号 |
| jadx 只有 2 个 Java 文件 | APK 有 Jiagu/Payegis 加固 | 找 3.x 旧版无保护 APK |
| HA 集成搜不到 | domain 名与目录不匹配 | manifest.json domain == 文件夹名 |

---

## 扩展新设备类型 checklist

1. [ ] APK 里找 `*DevStatusSetBean.java` → 列出所有可写字段
2. [ ] `probe_endpoints.py` 测出 GET 端点
3. [ ] `test_set_field.py` 验证全 255 payload 能返回 todoId
4. [ ] 确认 5 秒内设备实际响应
5. [ ] 在 `const.py` 的 `_ENDPOINT_MAP` 加新条目
6. [ ] 新建 `devices/<device_type>/` 目录，写 `__init__.py`（payload）+ 各平台文件
7. [ ] 各根目录 dispatcher 加 `elif kind == DEVICE_KIND_NEW: ...`
8. [ ] README 和 `docs/适配新设备型号.md` 更新
