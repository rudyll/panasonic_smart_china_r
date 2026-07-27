"""Generic, profile-driven SET endpoint diagnostic tool.

This tool does not guess device protocols. A JSON profile defines:

- which device subtype/category to select;
- the optional GET endpoint;
- candidate SET endpoints and payload schemas;
- skip/default fields and repeated field groups;
- logical control fields and their explicitly allowed values.

Use a device-specific wrapper when one exists, or pass ``--profile`` directly:

    python3 tools/probe_set_endpoints.py \
      --profile tools/set_probe_profiles/ld5c.json inspect
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

BASE = "https://app.psmartcloud.com/App/"
COMMANDS = ("validate", "inspect", "probe", "control")
_ENDPOINT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]+$")
_SENSITIVE_KEYS = {
    "deviceid", "devid", "deviceuuid", "mac", "devicemac", "sn", "devicesn",
    "usrid", "userid", "ssid", "token", "password", "pwd", "tel", "mobile",
    "familyid", "realfamilyid",
}
_DEVICE_ID_RE = re.compile(
    r"\b[0-9a-f]{12}_\d{4}_[a-z0-9.-]+\b", re.IGNORECASE
)
_IDENTITY_FIELDS = frozenset({"usrId", "deviceId", "token"})


def redact(value: Any) -> Any:
    """Recursively remove account, session, and device identifiers."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            result[key] = (
                "<redacted>" if normalized in _SENSITIVE_KEYS else redact(item)
            )
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
    mac, category, suffix = parts[0].upper(), parts[1].upper(), parts[2]
    inner = hashlib.sha512(
        (mac[6:] + "_" + category + "_" + mac[:6]).encode()
    ).hexdigest()
    return hashlib.sha512((inner + "_" + suffix).encode()).hexdigest()


def _network_helpers():
    """Load optional runtime dependencies only after CLI validation."""
    try:
        requests = importlib.import_module("requests")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "缺少 requests；请先运行 python3 -m pip install requests"
        ) from error
    dump = importlib.import_module("dump_device_params")
    requests.packages.urllib3.disable_warnings()
    return requests, dump


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 JSON object")
    return value


def _validate_endpoint(endpoint: Any, label: str) -> str:
    if not isinstance(endpoint, str) or not _ENDPOINT_RE.fullmatch(endpoint):
        raise ValueError(f"{label} 不是合法的松下 API 端点名: {endpoint!r}")
    return endpoint


def _validate_scalar(value: Any, label: str) -> int | float | str | bool | None:
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    raise ValueError(f"{label} 必须是 JSON scalar")


def expand_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Expand skipFields and fieldSeries into one protocol payload."""
    skip_fields = _require_mapping(schema.get("skipFields", {}), "skipFields")
    payload = {
        str(field): _validate_scalar(value, f"skipFields.{field}")
        for field, value in skip_fields.items()
    }
    forbidden = _IDENTITY_FIELDS.intersection(payload)
    if forbidden:
        raise ValueError(
            "schema 不得覆盖身份字段: " + ", ".join(sorted(forbidden))
        )

    groups = schema.get("fieldSeries", [])
    if not isinstance(groups, list):
        raise ValueError("fieldSeries 必须是 JSON array")
    for position, raw_group in enumerate(groups):
        group = _require_mapping(raw_group, f"fieldSeries[{position}]")
        prefixes = group.get("prefixes")
        if not isinstance(prefixes, list) or not prefixes:
            raise ValueError(f"fieldSeries[{position}].prefixes 必须是非空 array")
        if not all(isinstance(prefix, str) and prefix for prefix in prefixes):
            raise ValueError(f"fieldSeries[{position}].prefixes 包含无效字段前缀")
        start = group.get("start", 1)
        end = group.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end < start:
            raise ValueError(f"fieldSeries[{position}] 的 start/end 无效")
        value = _validate_scalar(
            group.get("value"), f"fieldSeries[{position}].value"
        )
        for index in range(start, end + 1):
            for prefix in prefixes:
                field = f"{prefix}{index}"
                if field in _IDENTITY_FIELDS:
                    raise ValueError(f"schema 不得覆盖身份字段: {field}")
                if field in payload:
                    raise ValueError(f"schema 重复定义字段: {field}")
                payload[field] = value
    return payload


def validate_profile(raw_profile: Any) -> dict[str, Any]:
    """Validate and normalize a profile loaded from JSON."""
    profile = _require_mapping(raw_profile, "profile")
    name = profile.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("profile.name 必须是非空字符串")

    device_filter = _require_mapping(
        profile.get("deviceFilter"), "profile.deviceFilter"
    )
    subtype_prefix = device_filter.get("devSubTypePrefix")
    if not isinstance(subtype_prefix, str) or not subtype_prefix.strip():
        raise ValueError("deviceFilter.devSubTypePrefix 必须是非空字符串")
    category = device_filter.get("category")
    if category is not None and (
        not isinstance(category, str) or not re.fullmatch(r"\d{4}", category)
    ):
        raise ValueError("deviceFilter.category 必须是四位字符串")

    get_endpoint = profile.get("getEndpoint")
    if get_endpoint is not None:
        _validate_endpoint(get_endpoint, "getEndpoint")

    schemas = _require_mapping(profile.get("schemas"), "profile.schemas")
    if not schemas:
        raise ValueError("profile.schemas 不得为空")
    normalized_schemas: dict[str, Any] = {}
    for schema_name, raw_schema in schemas.items():
        if not isinstance(schema_name, str) or not schema_name:
            raise ValueError("schema 名称必须是非空字符串")
        schema = _require_mapping(raw_schema, f"schemas.{schema_name}")
        expanded = expand_schema(schema)
        control_fields = _require_mapping(
            schema.get("controlFields", {}),
            f"schemas.{schema_name}.controlFields",
        )
        allowed_values = _require_mapping(
            schema.get("allowedValues", {}),
            f"schemas.{schema_name}.allowedValues",
        )
        normalized_control_fields: dict[str, str] = {}
        normalized_allowed_values: dict[str, list[int]] = {}
        for logical_name, protocol_name in control_fields.items():
            if not isinstance(logical_name, str) or not logical_name:
                raise ValueError(f"schemas.{schema_name} 的逻辑字段名无效")
            if not isinstance(protocol_name, str) or not protocol_name:
                raise ValueError(
                    f"schemas.{schema_name}.controlFields.{logical_name} 无效"
                )
            if protocol_name in _IDENTITY_FIELDS:
                raise ValueError(
                    f"schemas.{schema_name}.controlFields 不得覆盖身份字段: "
                    f"{protocol_name}"
                )
            if protocol_name in normalized_control_fields.values():
                raise ValueError(
                    f"schemas.{schema_name}.controlFields 重复映射字段: "
                    f"{protocol_name}"
                )
            values = allowed_values.get(logical_name)
            if not isinstance(values, list) or not values:
                raise ValueError(
                    f"schemas.{schema_name}.allowedValues.{logical_name} "
                    "必须是非空整数 array"
                )
            if not all(isinstance(value, int) and not isinstance(value, bool)
                       for value in values):
                raise ValueError(
                    f"schemas.{schema_name}.allowedValues.{logical_name} "
                    "只能包含整数"
                )
            normalized_control_fields[logical_name] = protocol_name
            normalized_allowed_values[logical_name] = values
        unknown_allowed = set(allowed_values) - set(control_fields)
        if unknown_allowed:
            raise ValueError(
                f"schemas.{schema_name}.allowedValues 包含未知逻辑字段: "
                + ", ".join(sorted(unknown_allowed))
            )
        normalized_schemas[schema_name] = {
            "payload": expanded,
            "controlFields": normalized_control_fields,
            "allowedValues": normalized_allowed_values,
        }

    matrix = profile.get("probeMatrix")
    if not isinstance(matrix, list) or not matrix:
        raise ValueError("profile.probeMatrix 必须是非空 array")
    normalized_matrix = []
    for position, raw_item in enumerate(matrix):
        item = _require_mapping(raw_item, f"probeMatrix[{position}]")
        endpoint = _validate_endpoint(
            item.get("endpoint"), f"probeMatrix[{position}].endpoint"
        )
        schema_name = item.get("schema")
        if schema_name not in normalized_schemas:
            raise ValueError(
                f"probeMatrix[{position}].schema 未定义: {schema_name!r}"
            )
        normalized_matrix.append({"endpoint": endpoint, "schema": schema_name})

    report_prefix = profile.get("reportPrefix", "set_probe_report")
    if not isinstance(report_prefix, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", report_prefix
    ):
        raise ValueError("reportPrefix 只能包含字母、数字、下划线和连字符")

    return {
        "name": name.strip(),
        "deviceFilter": {
            "devSubTypePrefix": subtype_prefix.strip(),
            "category": category,
        },
        "getEndpoint": get_endpoint,
        "schemas": normalized_schemas,
        "probeMatrix": normalized_matrix,
        "reportPrefix": report_prefix,
    }


def load_profile(path: str | Path) -> dict[str, Any]:
    profile_path = Path(path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"profile 文件不存在: {profile_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"profile JSON 无效: {error}") from error
    return validate_profile(raw)


def build_set_params(
    profile: dict[str, Any],
    schema_name: str,
    device_id: str,
    token: str,
    usr_id: str,
    field: str | None = None,
    value: int | None = None,
) -> dict[str, Any]:
    schema = profile["schemas"].get(schema_name)
    if schema is None:
        raise ValueError(f"未知 schema: {schema_name}")
    params: dict[str, Any] = {
        **schema["payload"],
        "usrId": usr_id,
        "deviceId": device_id,
        "token": token,
    }
    if field is not None:
        protocol_field = schema["controlFields"].get(field)
        if protocol_field is None:
            raise ValueError(f"schema {schema_name!r} 不支持控制字段 {field!r}")
        if value is None:
            raise ValueError("control value is required")
        allowed = schema["allowedValues"][field]
        if value not in allowed:
            raise ValueError(
                f"{field}={value} 不在 profile 允许值 {allowed} 中"
            )
        params[protocol_field] = value
    return params


def summarize_response(response: Any) -> dict[str, Any]:
    """Capture enough HTTP detail for diagnosis while keeping output bounded."""
    content_type = response.headers.get("Content-Type", "")
    summary: dict[str, Any] = {
        "httpStatus": response.status_code,
        "contentType": content_type,
    }
    try:
        body = response.json()
    except ValueError:
        summary["body"] = redact(response.text[:500])
        return summary
    summary["json"] = redact(body)
    if isinstance(body, dict):
        results = body.get("results")
        if isinstance(results, dict) and "todoId" in results:
            summary["todoId"] = results["todoId"]
        if "errorCode" in body:
            summary["errorCode"] = body["errorCode"]
        error = body.get("error")
        if isinstance(error, dict) and "code" in error:
            summary["errorCode"] = error["code"]
    return summary


def _post(endpoint: str, payload: dict[str, Any], ssid: str) -> dict[str, Any]:
    requests, dump = _network_helpers()
    try:
        response = requests.post(
            BASE + endpoint,
            json={"id": 1, "uiVersion": 4.0, "params": payload},
            headers=dump.headers(ssid),
            verify=False,
            timeout=10,
        )
    except requests.RequestException as error:
        return {"requestError": redact(str(error))}
    return summarize_response(response)


def _device_category(device_id: str) -> str | None:
    parts = device_id.split("_")
    return parts[1] if len(parts) >= 2 else None


def find_device(
    devices: list[dict[str, Any]], profile: dict[str, Any], index: int
) -> dict[str, Any]:
    device_filter = profile["deviceFilter"]
    normalized_prefix = (
        device_filter["devSubTypePrefix"].upper().replace("-", "")
    )
    matches = []
    for device in devices:
        params = device.get("params", {})
        subtype = str(params.get("devSubTypeId", "")).upper().replace("-", "")
        if not subtype.startswith(normalized_prefix):
            continue
        category = device_filter.get("category")
        if category is not None and _device_category(
            str(device.get("deviceId", ""))
        ) != category:
            continue
        matches.append(device)
    if not matches:
        raise RuntimeError(
            "账号中没有检测到匹配设备："
            f"devSubTypePrefix={device_filter['devSubTypePrefix']!r}, "
            f"category={device_filter.get('category')!r}"
        )
    if index < 1 or index > len(matches):
        raise RuntimeError(
            f"检测到 {len(matches)} 台匹配设备；"
            f"--device-index 必须在 1..{len(matches)}"
        )
    return matches[index - 1]


def _status_snapshot(device: dict[str, Any]) -> dict[str, Any]:
    params = device.get("params", {})
    return {
        "model": params.get("deviceMNO"),
        "devSubTypeId": params.get("devSubTypeId"),
        "statusAll": redact(params.get("statusAll") or {}),
    }


def _get_live_status(
    endpoint: str | None,
    device_id: str,
    usr_id: str,
    ssid: str,
    token: str,
) -> dict[str, Any] | None:
    if endpoint is None:
        return None
    payload = {"usrId": usr_id, "deviceId": device_id, "token": token}
    return _post(endpoint, payload, ssid)


def _refresh_device(
    usr_id: str,
    ssid: str,
    family_id: Any,
    real_family_id: Any,
    device_id: str,
) -> dict[str, Any]:
    _, dump = _network_helpers()
    raw = dump.get_bind_dev_info(usr_id, ssid, family_id, real_family_id)
    for device in raw.get("results", {}).get("devList", []):
        if device.get("deviceId") == device_id:
            return device
    raise RuntimeError("刷新后设备未出现在 UsrGetBindDevInfo 中")


def _write_report(
    report: dict[str, Any], path_arg: str | None, prefix: str
) -> Path:
    path = Path(
        path_arg or f"{prefix}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    )
    path.write_text(
        json.dumps(redact(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def parse_args(
    argv: list[str] | None = None,
    default_profile: str | Path | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=COMMANDS, nargs="?", default="inspect"
    )
    parser.add_argument(
        "--profile",
        default=str(default_profile) if default_profile is not None else None,
        required=default_profile is None,
        help="设备协议 JSON profile",
    )
    parser.add_argument(
        "--device-index",
        type=int,
        default=1,
        help="匹配结果中的设备序号（默认 1）",
    )
    parser.add_argument("--report", help="脱敏 JSON 报告路径")
    parser.add_argument("--endpoint", help="control 使用的 SET 端点")
    parser.add_argument("--schema", help="control 使用的 profile schema 名")
    parser.add_argument("--field", help="control 使用的逻辑控制字段")
    parser.add_argument("--value", type=int)
    parser.add_argument(
        "--confirm-model",
        help="control 时必须填写设备列表显示的完整型号",
    )
    return parser.parse_args(argv)


def _validate_credentials() -> None:
    if not os.environ.get("PMS_USER") or not os.environ.get("PMS_PASS"):
        raise RuntimeError("请通过 PMS_USER 和 PMS_PASS 环境变量提供账号密码")


def main(
    argv: list[str] | None = None,
    default_profile: str | Path | None = None,
) -> int:
    args = parse_args(argv, default_profile)
    profile = load_profile(args.profile)
    if args.command == "validate":
        print(
            f"profile 有效：{profile['name']}；"
            f"{len(profile['schemas'])} 个 schema；"
            f"{len(profile['probeMatrix'])} 个探测组合"
        )
        return 0
    if args.command == "control":
        missing = [
            flag
            for flag, value in (
                ("--endpoint", args.endpoint),
                ("--schema", args.schema),
                ("--field", args.field),
                ("--value", args.value),
                ("--confirm-model", args.confirm_model),
            )
            if value is None
        ]
        if missing:
            raise RuntimeError("control 缺少参数: " + ", ".join(missing))
        _validate_endpoint(args.endpoint, "--endpoint")
        allowed_pairs = {
            (item["endpoint"], item["schema"])
            for item in profile["probeMatrix"]
        }
        if (args.endpoint, args.schema) not in allowed_pairs:
            raise RuntimeError(
                "--endpoint/--schema 组合不在 profile probeMatrix 中: "
                f"{args.endpoint} / {args.schema}"
            )
        build_set_params(
            profile,
            args.schema,
            "validation-device",
            "validation-token",
            "validation-user",
            args.field,
            args.value,
        )
    _validate_credentials()

    print(f"登录并查找 {profile['name']} profile 匹配设备……")
    _, dump = _network_helpers()
    usr_id, ssid, family_id, real_family_id = dump.login()
    raw = dump.get_bind_dev_info(usr_id, ssid, family_id, real_family_id)
    device = find_device(
        raw.get("results", {}).get("devList", []), profile, args.device_index
    )
    device_id = device["deviceId"]
    token = gen_token(device_id)
    if token is None:
        raise RuntimeError("设备 token 生成失败")

    snapshot = _status_snapshot(device)
    model = str(snapshot.get("model") or "")
    print(
        f"已选择设备：型号={model or '?'}，"
        f"devSubTypeId={snapshot.get('devSubTypeId')}"
    )
    report: dict[str, Any] = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": args.command,
        "profile": {
            "name": profile["name"],
            "deviceFilter": profile["deviceFilter"],
            "getEndpoint": profile["getEndpoint"],
        },
        "device": snapshot,
        "liveStatus": _get_live_status(
            profile["getEndpoint"], device_id, usr_id, ssid, token
        ),
    }

    if args.command == "inspect":
        print("只读检查完成；未发送 SET 请求。")
    elif args.command == "probe":
        print("开始发送 profile 定义的 skip/no-op payload。")
        probes = []
        for item in profile["probeMatrix"]:
            endpoint, schema_name = item["endpoint"], item["schema"]
            print(f"  {endpoint} / {schema_name}")
            response = _post(
                endpoint,
                build_set_params(
                    profile, schema_name, device_id, token, usr_id
                ),
                ssid,
            )
            probes.append(
                {
                    "endpoint": endpoint,
                    "schema": schema_name,
                    "response": response,
                }
            )
            time.sleep(0.5)
        report["probes"] = probes
    else:
        if args.confirm_model != model:
            raise RuntimeError(
                f"--confirm-model 必须与设备型号完全一致；检测到 {model!r}"
            )
        before = snapshot
        print(
            "即将真实控制："
            f"{args.endpoint} / {args.schema} / {args.field}={args.value}"
        )
        response = _post(
            args.endpoint,
            build_set_params(
                profile,
                args.schema,
                device_id,
                token,
                usr_id,
                args.field,
                args.value,
            ),
            ssid,
        )
        print("请求已发送，等待 5 秒后读取 statusAll……")
        time.sleep(5)
        after_device = _refresh_device(
            usr_id, ssid, family_id, real_family_id, device_id
        )
        report["control"] = {
            "endpoint": args.endpoint,
            "schema": args.schema,
            "field": args.field,
            "value": args.value,
            "response": response,
            "before": before,
            "after": _status_snapshot(after_device),
        }

    path = _write_report(report, args.report, profile["reportPrefix"])
    print(f"脱敏报告已生成：{path}")
    print("请把该 JSON 附加到 GitHub issue；不要上传 dump_*.json。")
    return 0


def cli(
    argv: list[str] | None = None,
    default_profile: str | Path | None = None,
) -> None:
    try:
        raise SystemExit(main(argv, default_profile))
    except Exception as error:  # noqa: BLE001 - CLI boundary presents concise error
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
