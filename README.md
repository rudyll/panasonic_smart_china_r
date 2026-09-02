# Panasonic Smart China R

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![version](https://img.shields.io/badge/version-2.2.5-blue.svg)]()

Home Assistant 自定义集成，对接**松下智能家电（中国大陆）**云端 API，支持中央空调和新风换气设备。

本项目基于 [mcdona1d/panasonic_smart_china](https://github.com/mcdona1d/panasonic_smart_china) 开发，在此基础上加入了新风设备支持，并大幅扩展了云端通信逻辑。感谢 arthurfsy 最早公开松下云端登录算法，感谢 Hassbian 论坛 omegaojian 对 MidERV 设备的抓包分析，为本项目逆向 DCERV-03 端点提供了关键线索。MidERV 与 SmallERV 机型的 payload 字段、运行模式值域和风量档位数据，参考自社区 [dkong5ssss/panasonic_smart_china_erv](https://github.com/dkong5ssss/panasonic_smart_china_erv) 项目，感谢该项目作者的实测和整理；LD5C（FY-25ZDP1C）的真实控制端点也由该项目作者从松下官方 Web 控制页的 JS 源码中定位并公开，另感谢 [accpowered](https://github.com/accpowered) 全程提供 FY-25ZDP1C 实机测试报告。

---

## 支持设备

### 中央空调（category `0900`）✅ 完全可用

- 型号：配合 `CZ-RD501DW2` 线控器的松下家用多联/风管机
- 提供标准 `climate` 实体，支持开关机、模式切换、温度设定、风速调节
- 当前温度优先读取空调云端的 `inhaleTemperature`；云端没有有效值时才回退到可选的外部室温传感器

### 新风换气机（category `0800` / `0850`）

集成会根据松下设备列表返回的 `devSubTypeId` 自动选择机型协议和云端端点（DCERV / NewDCERV / MidERV / SmallERV / LD5C / LD6C），无需手动配置。旧版配置缺少该字段时，集成会在加载时从设备列表补全。

#### 机型支持状态

| 机型 | devSubTypeId | category | 状态 |
|------|-------------|----------|------|
| FY-35ZJD2C | DCERV-03 | 0800 | ✅ 实测可用 |
| FV-RZ06VD1 | MIDERV | 0800 | ✅ 用户确认可用 |
| FV-25ZDP2C | LD6C | 0800 | 🟡 专用状态接口与风量已获用户验证 |
| FY-25ZDP1C | LD5C | 0800 | ✅ 控制协议已确认并实机验证（[#11](https://github.com/rudyll/panasonic_smart_china_r/issues/11)） |
| SmallERV 系列 | SmallERV-\* | 0850 | 🟡 `SMALLERV02`（FY-25ZM1C）已加入专用适配，待用户验证（[#5](https://github.com/rudyll/panasonic_smart_china_r/issues/5)） |
| NewDCERV 系列 | NEWDCERV-\* | 0800 | 🟡 代码完整，征集测试（[#6](https://github.com/rudyll/panasonic_smart_china_r/issues/6)） |

#### MidERV（FV-RZ06VD1 等）

**控件：**
- 开关机 (`runSta`)
- 假日模式 (`holM`)
- 运行模式：热交换 / 内循环 / 睡眠 / 自动ECO (`runM` 0/2/3/4)
- 风量：低 / 中 / 高 (`airVo` 1/2/3)
- PM2.5 滤网更换周期：60 / 90 / 120 天 (`saFilEx`)
- 回风滤网更换周期：180–365 天，7 档 (`raFilEx`)
- PM2.5 滤网清洗提醒：30 / 60 天 (`saFilCl`)
- 回风滤网清洗提醒：30 / 60 天 (`raFilCl`)

#### LD6C（FV-25ZDP2C 等）

- 使用 App 对应的 `ADevGetStatusLD6C` / `ADevSetStatusLD6C` 专用端点
- 运行模式：热交换 / 内循环 / 自动ECO / 消毒 (`runM` 1/4/6/7)
- 风量：静音 / 低 / 高 (`airVo` 0/1/2)
- 开关机与假日模式使用 LD6C 完整控制 payload；其他设置待设备实测确认值域后开放
- 已验证传感器：室外 PM2.5、室外温湿度、室内/回风 PM2.5，以及四类滤网剩余寿命
- 不创建设备以 `127 / 255 / 65535` 占位的送风 PM2.5、CO₂、TVOC 和送风/回风温湿度实体

> 从 2.1.3 或更早版本升级后，旧实体可能残留为“不可用”。要彻底清理，请升级并重启后删除该设备对应的集成配置项，再重新添加设备。

#### LD5C（FY-25ZDP1C）

- 使用松下官方 Web 控制页对应的 `ADevGetStatusInfoLD5C` / `ADevSetStatusInfoLD5C` 端点
- 运行模式：热交换 / 内循环 / 外循环 (`runningMode` 0/2/5)
- 风量：低 / 中 / 高 (`airVolume` 1/2/3)
- 控制状态从实时端点读取，不走设备列表缓存，操作后界面不会跳回旧状态
- 传感器：室外 PM2.5、室外温度、室外湿度、回风滤网剩余寿命（从 MidERV 端点读取并合并）
- 假日模式字段存在但未实机验证，暂不创建控件

#### SmallERV

- 通用 SmallERV 风量：低 / 高 (`airVo` 0/1)
- `SMALLERV02`（FY-25ZM1C）风量：低 / 高 (`airVo` 1/3)，状态从 `ADevGetStatusSmallERV` 实时端点读取
- `SMALLERV02` 创建室外 PM2.5、室外温度、室外湿度传感器；未提供 `runM`，不创建运行模式控件
- `SMALLERV02` 还提供滤网清洁倒计时，以及回风侧、PM2.5、初效滤网三个更换倒计时（单位：小时）
- 使用 App 对应的六组定时字段和 SmallERV 专用控制 payload

#### NewDCERV

- 运行模式与风量枚举沿用 DCERV（`runM` 48–53、`airVo` 0/1）
- 使用 NewDCERV 独立控制 payload；滤网周期等设置待设备实测确认值域后开放

#### DCERV-03（FY-35ZJD2C 等）

- 使用 App 对应的 `ADevGetStatusDCERV` 专用端点读取实时状态

**传感器（稳定可用）：**

| 传感器 | 字段 | 说明 |
|--------|------|------|
| 室外 PM2.5 | `oaPMC` | µg/m³ |
| 送风 PM2.5 | `saPMC` | µg/m³ |
| 回风 PM2.5 | `raPMC` | µg/m³ |
| 室外湿度 | `oaHumC` | % |
| 送风湿度 | `saHumC` | % |
| 回风湿度 | `raHumC` | % |
| 室外温度 | `oaTeC` | °C |
| 送风温度 | `saTeC` | °C |
| 回风温度 | `raTeC` | °C |
| 回风 CO₂ | `raCO2C` | ppm |
| 回风 TVOC | `raTVC` | 等级 |
| 外滤网寿命 | `oaFilExTL` | 小时 |
| 送风滤网寿命 | `saFilExTL` | 小时 |
| 回风滤网寿命 | `raFilExTL` | 小时 |

**控件（稳定可用）：**

- 开关机 (`runSta`)
- 假日模式 (`holM`)
- 运行模式：热交换 / 静音 / 普通换气 / 内循环 / 混风 / 自动ECO (`runM` 48–53)
- 风量：弱 / 强 (`airVo` 0/1)
- 压差模式：标准 / 正压 / 自定义 (`preSet`)
- 正压强度：弱 / 中 / 强 (`preM`)
- 自定义送风量 / 排风量：0%–100%，步长 20% (`userSupWind` / `userExhWind`)
- 外滤网更换周期：90 / 120 / 150 / 180 天 (`oaFilEx`)
- PM2.5 触发阈值：35 / 50 / 75 µg/m³ (`pmSen`)
- CO₂ 触发阈值：800 / 1000 / 1500 ppm (`coSen`)
- TVOC 触发阈值：低 / 高 (`tvSen`)

---

## 核心特性

- **无需手动抓包**：内置双重 SHA-512 token 算法，账号密码直接登录
- **会话保活（Anti-Kickout）**：10 分钟重登冷却，避免跟手机 App 互踢 session
- **静默重登**：SSID 过期时自动用存储的凭证续期，无需手动 re-auth
- **多设备支持**：按 deviceId 区分，可同时添加多台设备

---

## 安装

### HACS（推荐）

1. HACS → 集成 → 右上角菜单 → Custom repositories
2. 填入 `https://github.com/rudyll/panasonic_smart_china_r`，类别选 Integration
3. 搜索 `Panasonic Smart China R`，下载
4. 重启 Home Assistant

### 手动安装

1. 下载本项目，将 `custom_components/panasonic_smart_china_r` 复制到 HA 配置目录的 `custom_components/` 下
2. 确认路径：`/config/custom_components/panasonic_smart_china_r/__init__.py`
3. 重启 Home Assistant

---

## 配置

1. 配置 → 设备与服务 → 添加集成 → 搜索 **Panasonic Smart China R**
2. 输入松下智家 App 的手机号和密码
3. 选择设备（空调选控制器型号；新风机直接确认）

> 松下云端为单点登录。HA 接管 session 后，手机 App 再次登录会把 HA 踢下线（反之亦然）。内置冷却机制可减少抢占频率，但无法完全避免。若需长期稳定共存，建议用第二个松下账号并通过 App 内设备分享授权。

---

## Token 算法

松下 DCERV-03 设备 token 为双层 SHA-512：

```python
parts = device_id.split("_")   # 格式：MAC_CATEGORY_SUFFIX
mac = parts[0].upper()
category = parts[1].upper()
suffix = parts[2]               # 注意：suffix 保持原始大小写，不能 upper()
inner = sha512(f"{mac[6:]}_{category}_{mac[:6]}")
token = sha512(f"{inner}_{suffix}")
```

**注意**：suffix 全转大写会导致 token 校验失败，这与 App JS 源码的 `toUpperCase` 不一致，是 DCERV-03 型号的特殊行为。

---

## 兼容性

- Home Assistant 2024.1+
- Python 3.11+
- 仅适用于中国大陆地区"松下智能家电" App（蓝色图标），不支持国际版 Comfort Cloud

---

## 其他设备型号

| 设备类型 | Category | 状态 | 说明 |
|----------|----------|------|------|
| 中央空调（CZ-RD501DW2） | 0900 | ✅ 实测 | |
| DCERV-03 大型新风 | 0800 | ✅ 实测 | |
| MidERV 中型新风 | 0800 | ✅ 用户确认 | FV-RZ06VD1 |
| LD6C 新风 | 0800 | 🟡 待设备验证 | FV-25ZDP2C（使用 LD6C 专用接口） |
| LD5C 新风 | 0800 | ✅ 用户确认 | FY-25ZDP1C（使用官方 Web 页的 Info 端点，[#11](https://github.com/rudyll/panasonic_smart_china_r/issues/11)） |
| SmallERV 小型新风 | 0850 | 🟡 `SMALLERV02` 专用适配待验证 | [issue #5](https://github.com/rudyll/panasonic_smart_china_r/issues/5) |
| NewDCERV 新一代大型新风 | 0800 | 🟡 征集测试 | [issue #6](https://github.com/rudyll/panasonic_smart_china_r/issues/6) |
| 空气净化器（Aircle） | 0830 | 🔍 待开发 | [issue #3](https://github.com/rudyll/panasonic_smart_china_r/issues/3) |
| 其他 0900 空调控制器 | 0900 | 🔍 征集数据 | [issue #7](https://github.com/rudyll/panasonic_smart_china_r/issues/7) |

如果你的松下设备不在以上列表，可参考 [Wiki：如何适配新设备](https://github.com/rudyll/panasonic_smart_china_r/wiki/适配新设备型号) 自行逆向并提交 PR。

### 提供脱敏设备报告

如果已支持的新风机出现传感器“未知”、数值异常或部分功能不可用，可在仓库根目录运行：

```bash
python3 -m pip install requests
PMS_USER='松下智家账号' PMS_PASS='密码' python3 tools/probe_endpoints.py --report
```

命令会生成 `endpoint_report_*.json`，自动隐藏账号、会话、token 和设备唯一标识，可附加到 GitHub issue。请勿上传 `dump_*.json`，原始 dump 可能包含个人设备信息。完整步骤见 [Wiki：适配新设备型号](https://github.com/rudyll/panasonic_smart_china_r/wiki/适配新设备型号)。

### 通用 SET 协议探测

`tools/probe_set_endpoints.py` 可用于其他设备，不需要修改 Python 源码。复制一个 JSON profile，配置设备子类型/category、GET 端点、候选 SET 端点、payload 的 skip 字段、控制字段和值域即可：

```bash
cp tools/set_probe_profiles/ld5c.json my_device.json
# 编辑 my_device.json 后先做纯本地校验，不登录、不请求云端
python3 tools/probe_set_endpoints.py --profile my_device.json validate

# 校验通过后分阶段运行
python3 tools/probe_set_endpoints.py --profile my_device.json inspect
python3 tools/probe_set_endpoints.py --profile my_device.json probe
```

工具只允许访问 `https://app.psmartcloud.com/App/` 下格式合法且写在 profile `probeMatrix` 中的端点；真实控制只能使用同一矩阵中的 endpoint/schema 组合，并且控制值必须预先列入 schema 的 `allowedValues`。详细 profile 格式和安全约束见 [Wiki](https://github.com/rudyll/panasonic_smart_china_r/wiki/适配新设备型号#第四步验证-set-端点)。

### LD5C 控制端点诊断（已完成）

FY-25ZDP1C（`devSubTypeId=LD5C`）的控制协议已经确认并实机验证，普通用户升级插件即可，不需要再跑探测工具。

真实端点是松下官方 Web 控制页（`ca/cn/0800/LD5C/`）使用的 `ADevSetStatusInfoLD5C` / `ADevGetStatusInfoLD5C`——注意中间的 `Info`，此前探测矩阵里的 `ADevSetStatusLD5C` 返回 404 正是因为漏了这一段。`ADevSetStatusLD6C`、`ADevSetStatusDCERV`、`ADevSetStatusMidERV` 都会返回 `todoId` 但设备不动作：**云端返回 `todoId` 只代表请求入队，不代表设备执行**。

这条线索由 [dkong5ssss](https://github.com/dkong5ssss/panasonic_smart_china_erv) 从官方 Web 页 JS 源码中定位，[accpowered](https://github.com/accpowered) 提供了本仓库 issue 全程的 FY-25ZDP1C 实机报告。完整协议和「Info 端点家族」的通用规律见 [Wiki：适配新设备型号](https://github.com/rudyll/panasonic_smart_china_r/wiki/适配新设备型号)。

其他机型如需收敛 SET 协议，参考 `tools/set_probe_profiles/ld5c.json` 编写自己的 profile 后按上文流程运行。

---

## 效果截图

<img src="custom_components/panasonic_smart_china_r/assets/screenshot1.png" width="380" alt="设备控制页">

---

## 免责声明

本项目为社区开源作品，非松下官方出品。通过模拟 App API 请求实现功能，请合理使用。因使用本项目导致的设备异常或账号问题，开发者不承担责任。

---
