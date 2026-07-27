"""Safely diagnose LD5C (FY-25ZDP1C) SET endpoints without packet capture.

The default ``inspect`` command is read-only. ``probe`` sends only skip/no-op
payloads. ``control`` can change the device and therefore requires an explicit
endpoint, payload schema, field/value, and exact model confirmation.

Examples:
    PMS_USER='account' PMS_PASS='password' \
      python3 tools/probe_ld5c_set.py inspect

    PMS_USER='account' PMS_PASS='password' \
      python3 tools/probe_ld5c_set.py probe

    PMS_USER='account' PMS_PASS='password' \
      python3 tools/probe_ld5c_set.py control \
        --endpoint ADevSetStatusLD5C --schema ld5c \
        --field power --value 0 --confirm-model FY-25ZDP1C
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
GET_ENDPOINT = "ADevGetStatusLD6C"
SET_ENDPOINTS = (
    "ADevSetStatusLD5C",
    "ADevSetStatusLD6C",
    "ADevSetStatusDCERV",
)
SCHEMAS = ("minimal", "ld5c", "ld6c", "dcerv")
CONTROL_FIELDS = ("power", "mode", "volume")
_SENSITIVE_KEYS = {
    "deviceid", "devid", "deviceuuid", "mac", "devicemac", "sn", "devicesn",
    "usrid", "userid", "ssid", "token", "password", "pwd", "tel", "mobile",
    "familyid", "realfamilyid",
}
_DEVICE_ID_RE = re.compile(
    r"\b[0-9a-f]{12}_\d{4}_[a-z0-9.-]+\b", re.IGNORECASE
)

# Probe only combinations that can distinguish the most likely routing choices
# without sending every schema to every endpoint.
PROBE_MATRIX = (
    ("ADevSetStatusLD5C", "minimal"),
    ("ADevSetStatusLD5C", "ld5c"),
    ("ADevSetStatusLD5C", "ld6c"),
    ("ADevSetStatusLD6C", "ld5c"),
    ("ADevSetStatusLD6C", "ld6c"),
    ("ADevSetStatusDCERV", "ld5c"),
    ("ADevSetStatusDCERV", "dcerv"),
)

_FIELD_NAMES = {
    "minimal": {"power": "runSta", "mode": "runM", "volume": "airVo"},
    "ld5c": {
        "power": "runningStatus",
        "mode": "runningMode",
        "volume": "airVolume",
    },
    "ld6c": {"power": "runSta", "mode": "runM", "volume": "airVo"},
    "dcerv": {"power": "runSta", "mode": "runM", "volume": "airVo"},
}


def redact(value: Any) -> Any:
    """Recursively remove account, session, and device identifiers."""
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


def _timer_fields(prefixes: tuple[str, ...], hour_skip: int) -> dict[str, int]:
    fields: dict[str, int] = {}
    for index in range(1, 7):
        for prefix in prefixes:
            fields[f"{prefix}{index}"] = (
                hour_skip if prefix in {"tH", "tMin"} else 255
            )
    return fields


def build_schema_payload(schema: str) -> dict[str, int]:
    """Return only protocol fields; identity fields are added before sending."""
    if schema == "minimal":
        return {}
    if schema == "ld5c":
        return {
            "runningStatus": 255,
            "runningMode": 255,
            "airVolume": 255,
            "holidayMode": 255,
        }
    if schema == "ld6c":
        fields = (
            "runSta", "runM", "airVo", "winDir", "heatM", "nanoe",
            "preSet", "preM", "holM", "pmSen", "co2Sen", "tvSen",
            "saFilCl", "oaFilCl", "resFilCl", "saFilEX", "oaFilEx",
            "resFilEx", "saFilSet", "tSet", "slfSendW", "slfOutW",
            "airBind", "clFilReset", "saFilExReset", "oaFilExReset",
            "raFilExReset", "resFilExReset", "dehumid", "humidSet",
            "breathLight",
        )
        payload = {field: 255 for field in fields}
        payload.update(
            _timer_fields(
                ("tSta", "tM", "tWind", "tSet", "tH", "tMin", "tWeek"),
                255,
            )
        )
        payload.update({f"res{index}": 255 for index in range(1, 11)})
        return payload
    if schema == "dcerv":
        payload = {
            field: 255
            for field in (
                "runSta", "runM", "airVo", "preSet", "preM", "holM",
                "pmSen", "coSen", "tvSen", "userSupWind", "userExhWind",
                "aircJoi", "oaFilEx",
            )
        }
        payload.update(
            _timer_fields(
                ("tSta", "tM", "tWind", "tSet", "tH", "tMin", "tWeek"),
                127,
            )
        )
        return payload
    raise ValueError(f"unknown schema: {schema}")


def build_set_params(
    schema: str,
    device_id: str,
    token: str,
    usr_id: str,
    field: str | None = None,
    value: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        **build_schema_payload(schema),
        "usrId": usr_id,
        "deviceId": device_id,
        "token": token,
    }
    if field is not None:
        if value is None:
            raise ValueError("control value is required")
        params[_FIELD_NAMES[schema][field]] = value
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
    response = requests.post(
        BASE + endpoint,
        json={"id": 1, "uiVersion": 4.0, "params": payload},
        headers=dump.headers(ssid),
        verify=False,
        timeout=10,
    )
    return summarize_response(response)


def _find_ld5c_device(devices: list[dict[str, Any]], index: int) -> dict[str, Any]:
    matches = [
        device
        for device in devices
        if str(device.get("params", {}).get("devSubTypeId", ""))
        .upper()
        .replace("-", "")
        .startswith("LD5C")
    ]
    if not matches:
        raise RuntimeError("账号中没有检测到 devSubTypeId=LD5C 的设备")
    if index < 1 or index > len(matches):
        raise RuntimeError(
            f"检测到 {len(matches)} 台 LD5C；--device-index 必须在 1..{len(matches)}"
        )
    return matches[index - 1]


def _status_snapshot(device: dict[str, Any]) -> dict[str, Any]:
    params = device.get("params", {})
    status = params.get("statusAll") or {}
    return {
        "model": params.get("deviceMNO"),
        "devSubTypeId": params.get("devSubTypeId"),
        "statusAll": redact(status),
    }


def _get_live_status(
    device_id: str, usr_id: str, ssid: str, token: str
) -> dict[str, Any]:
    payload = {"usrId": usr_id, "deviceId": device_id, "token": token}
    return _post(GET_ENDPOINT, payload, ssid)


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


def _write_report(report: dict[str, Any], path_arg: str | None) -> Path:
    path = Path(
        path_arg or f"ld5c_set_report_{time.strftime('%Y%m%d-%H%M%S')}.json"
    )
    path.write_text(
        json.dumps(redact(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("inspect", "probe", "control"),
        nargs="?",
        default="inspect",
    )
    parser.add_argument(
        "--device-index",
        type=int,
        default=1,
        help="账号中第几台 LD5C 设备（默认 1）",
    )
    parser.add_argument("--report", help="脱敏 JSON 报告路径")
    parser.add_argument("--endpoint", choices=SET_ENDPOINTS)
    parser.add_argument("--schema", choices=SCHEMAS)
    parser.add_argument("--field", choices=CONTROL_FIELDS)
    parser.add_argument("--value", type=int)
    parser.add_argument(
        "--confirm-model",
        help="control 时必须填写设备列表显示的完整型号，例如 FY-25ZDP1C",
    )
    return parser.parse_args(argv)


def _validate_credentials() -> None:
    if not os.environ.get("PMS_USER") or not os.environ.get("PMS_PASS"):
        raise RuntimeError("请通过 PMS_USER 和 PMS_PASS 环境变量提供账号密码")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _validate_credentials()
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

    print("登录并查找 LD5C 设备……")
    _, dump = _network_helpers()
    usr_id, ssid, family_id, real_family_id = dump.login()
    raw = dump.get_bind_dev_info(usr_id, ssid, family_id, real_family_id)
    device = _find_ld5c_device(
        raw.get("results", {}).get("devList", []), args.device_index
    )
    device_id = device["deviceId"]
    token = gen_token(device_id)
    if token is None:
        raise RuntimeError("设备 token 生成失败")

    snapshot = _status_snapshot(device)
    model = str(snapshot.get("model") or "")
    print(
        f"已选择 LD5C 设备：型号={model or '?'}，"
        f"devSubTypeId={snapshot.get('devSubTypeId')}"
    )
    report: dict[str, Any] = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": args.command,
        "device": snapshot,
        "liveStatus": _get_live_status(device_id, usr_id, ssid, token),
    }

    if args.command == "inspect":
        print("只读检查完成；未发送 SET 请求。")
    elif args.command == "probe":
        print("开始发送 skip/no-op payload；不会主动修改控制字段。")
        probes = []
        for endpoint, schema in PROBE_MATRIX:
            print(f"  {endpoint} / {schema}")
            response = _post(
                endpoint,
                build_set_params(schema, device_id, token, usr_id),
                ssid,
            )
            probes.append(
                {"endpoint": endpoint, "schema": schema, "response": response}
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

    path = _write_report(report, args.report)
    print(f"脱敏报告已生成：{path}")
    print("请把该 JSON 附加到 GitHub issue；不要上传 dump_*.json。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - CLI boundary presents concise error
        print(f"错误：{error}", file=sys.stderr)
        raise SystemExit(1)
