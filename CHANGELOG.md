# Changelog

## 2.2.0

- 新增 LD5C（FY-25ZDP1C）支持：开关机、运行模式（热交换 / 内循环 / 外循环）、风量（低 / 中 / 高）现在可以真实控制。
- LD5C 改用松下官方 Web 控制页使用的 `ADevSetStatusInfoLD5C` / `ADevGetStatusInfoLD5C` 端点。这类 Info 家族端点把 `usrId`/`deviceId`/`token` 放在请求体顶层，另外需要 `xtoken` 认证头，payload 用 `runningStatus`/`runningMode`/`airVolume` 等长字段名。此前的 LD5C / LD6C / DCERV / MidERV 端点组合都会返回 `todoId` 但设备不动作。
- LD5C 的控制状态从实时端点读取，不再依赖设备列表的 `statusAll` 缓存——该缓存在控制后不刷新，会让界面几秒后跳回旧状态。
- LD5C 传感器只创建实机确认存在的四项（室外 PM2.5、室外温度、室外湿度、回风滤网剩余寿命），数据从 MidERV 端点读取并与控制字段合并。
- 文档新增「官方 Web 控制页」适配捷径：该页面无证书固定，其 JS 源码即官方协议，比反编译 APK 或抓包更快；并说明 `Info` 端点家族的命名和请求形状差异。

> 感谢 [@dkong5ssss](https://github.com/dkong5ssss/panasonic_smart_china_erv) 定位 LD5C 真实端点并公开完整协议，感谢 [@accpowered](https://github.com/accpowered) 持续提供 FY-25ZDP1C 实机测试报告。协议细节见 [issue #11](https://github.com/rudyll/panasonic_smart_china_r/issues/11)。
>
> LD5C 的假日模式在 SET 字段表里有对应字段但尚未实机验证，本版本暂不创建该控件。

## 2.1.6

- DCERV 改用 App 对应的 `ADevGetStatusDCERV` 专用端点读取实时状态，修复送风温度和滤网寿命因设备列表状态字段缺失而显示“未知”的问题。
- 根据 FY-35ZJD2C 实机报告收敛 DCERV 传感器，不再创建设备未返回的送风湿度和 LD6C 专属新风集尘滤网实体。

## 2.1.5

- 将集成品牌图片放入 Home Assistant 与 HACS 识别的 `brand` 目录，并同时提供图标和 Logo。

> 项目内品牌图片需要 Home Assistant 2026.3 或更高版本；更早版本仍需通过 Home Assistant 官方 brands 仓库提供图片。

## 2.1.4

- 根据 FV-25ZDP2C 的 LD6C 专用端点报告，只创建 App 实际支持的室外 PM2.5、室外温湿度、室内/回风 PM2.5 和滤网寿命实体。
- 不再为 LD6C 创建送风 PM2.5、CO₂、TVOC、送风/回风温湿度等设备未提供有效数据的实体。
- 按字段过滤温度 `127/255`、湿度/TVOC `255`、PM2.5/CO₂ `65535` 等协议占位值，避免显示为真实测量结果。
- 新增新风集尘滤网剩余寿命实体，对应 LD6C App 展示的第四类滤网更换倒计时。

> 升级后旧实体可能继续残留为“不可用”；若需彻底清理，请删除该设备对应的集成配置项后重新添加。

## 2.1.3

- 根据松下 App 解包代码，将 SmallERV 风量修正为低 / 高（`0 / 1`），并改用该机型实际的六组定时控制 payload。
- 为 NewDCERV 增加独立控制 payload，不再发送该机型不存在的 DCERV 自定义送排风等字段；控制时保留 App 要求的当前室外 PM2.5 值。
- 移除 NewDCERV 尚未确认值域的 DCERV 专属设置控件，避免误操作。
- 根据 FV-25ZDP2C App 实机截图，将 LD6C 的 `runM=6` 显示文案修正为“自动ECO”。

> SmallERV 与 NewDCERV 协议结构来自 App 解包代码，仍需对应型号完成设备端控制验证。

## 2.1.2

- 将 FV-25ZDP2C（`LD6C`）改为松下 App 使用的 LD6C 专用状态与控制端点，不再借用 MidERV 接口。
- 按 App 协议修正 LD6C 运行模式为热交换、内循环、自动、消毒，并修正风量为静音、低、高。
- 为 LD6C 控制使用全部未修改字段填 `255` 的专用 payload，开关机、假日模式、运行模式和风量不再发送 DCERV/MidERV 字段结构。
- 端点探测工具新增 `ADevGetStatusLD6C`，便于用户生成脱敏报告验证该型号实际提供的传感器字段。

> LD6C 的专用端点、字段和枚举来自 App 反编译结果；仍需 FV-25ZDP2C 用户完成设备端读取与控制验证。

## 2.1.1

- 新增 FV-25ZDP2C（`LD6C`）的 MidERV 实时状态接口适配，避免读取到错误端点返回的填充值。
- 为旧配置自动补全 `devSubTypeId`，并修正新配置中设备子类型的保存位置。
- 将 LD6C 的实时读取限定在该机型，其他新风机保持原有状态读取逻辑。
- 修正端点探测工具获取设备列表的方式；新增 `--report` 脱敏报告，并忽略可能包含个人设备信息的输出文件。

> FV-25ZDP2C / LD6C 适配尚待贡献者完成设备端验证。
