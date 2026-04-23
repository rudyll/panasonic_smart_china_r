"""Config / Options / Reauth flows.

登录逻辑统一走 api.authenticate()；entry.data 里始终持久化 CONF_USERNAME 和 CONF_PASSWORD，
coordinator / climate 在 SSID 过期时可以静默调 relogin_entry。
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .api import authenticate, generate_device_token
from .const import (
    CONF_CONTROLLER_MODEL,
    CONF_DEVICE_ID,
    CONF_DEVICE_KIND,
    CONF_SENSOR_ID,
    CONF_SSID,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    CONF_USR_ID,
    DEFAULT_UPDATE_INTERVAL,
    DEVICE_KIND_AC,
    DEVICE_KIND_FRESH_AIR,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
    SUPPORTED_CONTROLLERS,
    detect_device_kind,
)
from .exceptions import LoginFailed

_LOGGER = logging.getLogger(__name__)

URL_GET_DEV = "https://app.psmartcloud.com/App/UsrGetBindDevInfo"


class PanasonicConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._login_data: dict[str, Any] = {}
        self._devices: dict[str, Any] = {}
        self._creds: dict[str, str] = {}
        self._selected_dev_id: str | None = None
        self._selected_dev_kind: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    # ---------- 首次登录 ----------

    async def async_step_user(self, user_input=None):
        """步骤 1：检查缓存 Session 或登录。"""
        errors: dict[str, str] = {}

        domain_data = self.hass.data.get(DOMAIN, {})
        cached = domain_data.get("session")

        if cached and cached.get("username") and cached.get("password"):
            _LOGGER.info("Found cached session, verifying validity...")
            valid_devices = await self._get_devices_with_ssid(
                cached[CONF_USR_ID],
                cached[CONF_SSID],
                cached.get("familyId"),
                cached.get("realFamilyId"),
            )
            if valid_devices:
                self._login_data = {
                    CONF_USR_ID: cached[CONF_USR_ID],
                    CONF_SSID: cached[CONF_SSID],
                    "familyId": cached.get("familyId"),
                    "realFamilyId": cached.get("realFamilyId"),
                }
                self._creds = {
                    CONF_USERNAME: cached["username"],
                    CONF_PASSWORD: cached["password"],
                }
                self._devices = valid_devices
                return await self.async_step_device()
            _LOGGER.warning("Cached session expired.")
            if DOMAIN in self.hass.data:
                self.hass.data[DOMAIN]["session"] = None

        if user_input is not None:
            try:
                result = await authenticate(
                    async_get_clientsession(self.hass),
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except LoginFailed as err:
                _LOGGER.error("Login failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Login error: %s", err)
                errors["base"] = "cannot_connect"
            else:
                if not result["devices"]:
                    return self.async_abort(reason="no_devices_found")

                self._creds = {
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                self._login_data = {
                    CONF_USR_ID: result["usrId"],
                    CONF_SSID: result["ssId"],
                    "familyId": result.get("familyId"),
                    "realFamilyId": result.get("realFamilyId"),
                }
                self._devices = result["devices"]

                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN]["session"] = {
                    CONF_USR_ID: result["usrId"],
                    CONF_SSID: result["ssId"],
                    "familyId": result.get("familyId"),
                    "realFamilyId": result.get("realFamilyId"),
                    "devices": result["devices"],
                    "username": user_input[CONF_USERNAME],
                    "password": user_input[CONF_PASSWORD],
                }
                return await self.async_step_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_device(self, user_input=None):
        errors: dict[str, str] = {}
        existing_ids = self._async_current_ids()

        available_devices: dict[str, str] = {}
        for did, info in self._devices.items():
            if f"panasonic_{did}" in existing_ids:
                continue
            kind = detect_device_kind(did)
            label = f"{info.get('deviceName', did)} ({did})"
            if kind == DEVICE_KIND_FRESH_AIR:
                label = f"[新风] {label}"
            elif kind == DEVICE_KIND_AC:
                label = f"[空调] {label}"
            else:
                label = f"[未支持] {label}"
            available_devices[did] = label

        if not available_devices:
            return self.async_abort(reason="all_devices_configured")

        if user_input is not None:
            self._selected_dev_id = user_input[CONF_DEVICE_ID]
            self._selected_dev_kind = detect_device_kind(self._selected_dev_id)

            if self._selected_dev_kind == DEVICE_KIND_AC:
                return await self.async_step_ac_config()

            if self._selected_dev_kind == DEVICE_KIND_FRESH_AIR:
                return await self._create_fresh_air_entry()

            errors["base"] = "unsupported_device"

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): vol.In(available_devices)}
            ),
            errors=errors,
        )

    async def async_step_ac_config(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            token = generate_device_token(self._selected_dev_id)
            if not token:
                errors["base"] = "token_generation_failed"
            else:
                dev_info = self._devices.get(self._selected_dev_id) or {}
                dev_name = dev_info.get("deviceName", "Panasonic AC")
                return self.async_create_entry(
                    title=dev_name,
                    data={
                        CONF_USERNAME: self._creds[CONF_USERNAME],
                        CONF_PASSWORD: self._creds[CONF_PASSWORD],
                        CONF_USR_ID: self._login_data[CONF_USR_ID],
                        CONF_SSID: self._login_data[CONF_SSID],
                        CONF_DEVICE_ID: self._selected_dev_id,
                        CONF_TOKEN: token,
                        CONF_SENSOR_ID: user_input[CONF_SENSOR_ID],
                        CONF_CONTROLLER_MODEL: user_input[CONF_CONTROLLER_MODEL],
                        CONF_DEVICE_KIND: DEVICE_KIND_AC,
                        "familyId": self._login_data.get("familyId"),
                        "realFamilyId": self._login_data.get("realFamilyId"),
                    },
                )

        controller_options = {k: v["name"] for k, v in SUPPORTED_CONTROLLERS.items()}
        return self.async_show_form(
            step_id="ac_config",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONTROLLER_MODEL, default="CZ-RD501DW2"): vol.In(
                        controller_options
                    ),
                    vol.Required(CONF_SENSOR_ID): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            errors=errors,
        )

    async def _create_fresh_air_entry(self):
        token = generate_device_token(self._selected_dev_id) or ""
        dev_info = self._devices.get(self._selected_dev_id) or {}
        dev_name = dev_info.get("deviceName", "Panasonic Fresh Air")
        return self.async_create_entry(
            title=dev_name,
            data={
                CONF_USERNAME: self._creds[CONF_USERNAME],
                CONF_PASSWORD: self._creds[CONF_PASSWORD],
                CONF_USR_ID: self._login_data[CONF_USR_ID],
                CONF_SSID: self._login_data[CONF_SSID],
                CONF_DEVICE_ID: self._selected_dev_id,
                CONF_TOKEN: token,
                CONF_DEVICE_KIND: DEVICE_KIND_FRESH_AIR,
                "familyId": self._login_data.get("familyId"),
                "realFamilyId": self._login_data.get("realFamilyId"),
            },
        )

    # ---------- Reauth ----------

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """HA 触发 reauth flow（ConfigEntryAuthFailed 后自动调）。"""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """让用户重新输入密码，只更新 entry.data。"""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}

        existing_username = self._reauth_entry.data.get(CONF_USERNAME, "")

        if user_input is not None:
            username = user_input.get(CONF_USERNAME, existing_username)
            password = user_input[CONF_PASSWORD]
            try:
                result = await authenticate(
                    async_get_clientsession(self.hass), username, password
                )
            except LoginFailed as err:
                _LOGGER.error("Reauth failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                new_data = {
                    **self._reauth_entry.data,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_USR_ID: result["usrId"],
                    CONF_SSID: result["ssId"],
                }
                if result.get("familyId") is not None:
                    new_data["familyId"] = result["familyId"]
                if result.get("realFamilyId") is not None:
                    new_data["realFamilyId"] = result["realFamilyId"]
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry, data=new_data
                )
                self.hass.data.setdefault(DOMAIN, {})
                self.hass.data[DOMAIN]["session"] = {
                    CONF_USR_ID: result["usrId"],
                    CONF_SSID: result["ssId"],
                    "familyId": result.get("familyId"),
                    "realFamilyId": result.get("realFamilyId"),
                    "devices": result["devices"],
                    "username": username,
                    "password": password,
                }
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=existing_username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    # ---------- Helpers ----------

    async def _get_devices_with_ssid(
        self, usr_id: str, ssid: str, family_id, real_family_id
    ):
        if family_id is None or real_family_id is None:
            return None
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
            "Cookie": f"SSID={ssid}",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    URL_GET_DEV,
                    json={
                        "id": 3,
                        "uiVersion": 4.0,
                        "params": {
                            "realFamilyId": real_family_id,
                            "familyId": family_id,
                            "usrId": usr_id,
                        },
                    },
                    headers=headers,
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        return None
                    dev_res = await resp.json()
                    if "results" not in dev_res:
                        return None
                    devices: dict[str, Any] = {}
                    for dev in dev_res["results"].get("devList", []):
                        devices[dev["deviceId"]] = dev["params"]
                    return devices
        except Exception:  # noqa: BLE001
            return None

    # ---------- Options ----------

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "OptionsFlowHandler":
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """单一 interval 设置：每个 entry（对应一台设备）独立调。"""

    def __init__(self, entry: ConfigEntry):
        self._entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self._entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
        )
