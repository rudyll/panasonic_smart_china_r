import logging
import async_timeout
from datetime import timedelta

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature, 
    HVACMode, 
    FAN_AUTO, FAN_LOW, FAN_MEDIUM, FAN_HIGH,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .api import relogin_entry, response_looks_bad
from .const import (
    CONF_USR_ID, CONF_DEVICE_ID, CONF_TOKEN, CONF_SSID,
    CONF_SENSOR_ID, CONF_CONTROLLER_MODEL, CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    SUPPORTED_CONTROLLERS, FAN_MUTE, FAN_MIN, FAN_MAX,
)
from .exceptions import LoginFailed, ReloginCooldown

_LOGGER = logging.getLogger(__name__)

URL_SET = "https://app.psmartcloud.com/App/ACDevSetStatusInfoAW"
URL_GET = "https://app.psmartcloud.com/App/ACDevGetStatusInfoAW"


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup climate entity."""
    async_add_entities([PanasonicACEntity(hass, entry, entry.title)])

class PanasonicACEntity(ClimateEntity):
    def __init__(self, hass, entry, name):
        self._hass = hass
        self._entry = entry
        config = entry.data
        self._usr_id = config[CONF_USR_ID]
        self._device_id = config[CONF_DEVICE_ID]
        self._token = config[CONF_TOKEN]
        self._ssid = config[CONF_SSID]
        self._sensor_id = config[CONF_SENSOR_ID]
        self._attr_name = name
        self._attr_unique_id = f"panasonic_{self._device_id}"

        # === 加载控制器配置 ===
        model = config.get(CONF_CONTROLLER_MODEL, "CZ-RD501DW2")
        self._profile = SUPPORTED_CONTROLLERS.get(model)
        if not self._profile:
            _LOGGER.error(f"Controller model {model} not found, using default.")
            self._profile = list(SUPPORTED_CONTROLLERS.values())[0]

        # 提取配置到本地变量
        self._temp_scale = self._profile.get("temp_scale", 2)
        self._hvac_map = self._profile.get("hvac_mapping", {})
        self._fan_map = self._profile.get("fan_mapping", {})
        self._fan_overrides = self._profile.get("fan_payload_overrides", {})

        # 内部状态
        self._is_on = False
        self._hvac_mode = HVACMode.OFF
        self._target_temperature = 26.0
        self._fan_mode = FAN_AUTO
        self._last_params = {} 
        
        # 定时器句柄
        self._unsub_polling = None

    @property
    def should_poll(self):
        """关闭 HA 默认慢速轮询"""
        return False

    async def async_added_to_hass(self):
        """实体添加时启动定时轮询"""
        await super().async_added_to_hass()
        interval = self._entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        self._unsub_polling = async_track_time_interval(
            self._hass,
            self._async_update_interval_wrapper,
            timedelta(seconds=interval),
        )

    async def async_will_remove_from_hass(self):
        """实体移除时销毁定时器"""
        if self._unsub_polling:
            self._unsub_polling()
            self._unsub_polling = None
        await super().async_will_remove_from_hass()

    async def _async_update_interval_wrapper(self, now):
        """定时器回调"""
        await self.async_update()
        self.async_write_ha_state()

    @property
    def supported_features(self):
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE | 
            ClimateEntityFeature.TURN_ON | 
            ClimateEntityFeature.TURN_OFF | 
            ClimateEntityFeature.FAN_MODE
        )

    @property
    def temperature_unit(self):
        return UnitOfTemperature.CELSIUS

    @property
    def min_temp(self):
        return 16.0

    @property
    def max_temp(self):
        return 30.0

    @property
    def target_temperature_step(self):
        return 1.0

    @property
    def hvac_modes(self):
        modes = [HVACMode.OFF]
        modes.extend(self._hvac_map.keys())
        return modes

    @property
    def hvac_mode(self):
        if not self._is_on:
            return HVACMode.OFF
        return self._hvac_mode

    @property
    def fan_modes(self):
        modes = list(self._fan_map.keys())
        for mode in self._fan_overrides.keys():
            if mode not in modes:
                modes.append(mode)
        return modes

    @property
    def fan_mode(self):
        return self._fan_mode

    @property
    def current_temperature(self):
        state = self._hass.states.get(self._sensor_id)
        if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            try: return float(state.state)
            except ValueError: pass
        return None

    @property
    def target_temperature(self):
        return self._target_temperature

    async def async_update(self):
        """轮询更新"""
        await self._fetch_status(update_internal_state=True)

    async def _post_get(self):
        headers = self._get_headers()
        payload = {
            "id": 100,
            "usrId": self._usr_id,
            "deviceId": self._device_id,
            "token": self._token,
        }
        session = async_get_clientsession(self._hass)
        async with async_timeout.timeout(5):
            response = await session.post(
                URL_GET, json=payload, headers=headers, ssl=False
            )
            return await response.json()

    async def _fetch_status(self, update_internal_state=True):
        """通用方法：获取设备当前最新状态。SSID 过期时静默重登一次。"""
        try:
            json_data = await self._post_get()
        except Exception as e:  # noqa: BLE001
            _LOGGER.debug("Fetch status failed: %s", e)
            return None

        if response_looks_bad(json_data):
            _LOGGER.warning(
                "AC response looks bad (errorCode=%s); attempting silent re-login. Raw=%s",
                json_data.get("errorCode") if isinstance(json_data, dict) else None,
                json_data,
            )
            try:
                self._ssid = await relogin_entry(self._hass, self._entry)
            except ReloginCooldown as err:
                _LOGGER.debug("%s", err)
                return None
            except LoginFailed as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            try:
                json_data = await self._post_get()
            except Exception as e:  # noqa: BLE001
                _LOGGER.debug("Fetch status (post-relogin) failed: %s", e)
                return None
            if response_looks_bad(json_data):
                raise ConfigEntryAuthFailed(
                    f"Still bad after re-login: errorCode={json_data.get('errorCode') if isinstance(json_data, dict) else None}"
                )

        if "results" in json_data and "runStatus" in json_data["results"]:
            res = json_data["results"]
            self._last_params = res
            if update_internal_state:
                self._update_local_state(res)
            return res
        return None

    def _update_local_state(self, res):
        """更新 HA 实体状态"""
        self._is_on = (res.get('runStatus') == 1)
        
        p_mode = res.get('runMode')
        for ha_mode, pm in self._hvac_map.items():
            if pm == p_mode:
                self._hvac_mode = ha_mode
                break
        
        self._target_temperature = res.get('setTemperature', 52) / self._temp_scale
        
        p_wind = res.get('windSet')
        p_mute = res.get('muteMode')
        
        if p_wind == 10 and p_mute == 1:
            self._fan_mode = FAN_MUTE
        else:
            found_normal = False
            for name, val in self._fan_map.items():
                if val == p_wind:
                    self._fan_mode = name
                    found_normal = True
                    break
            
            if not found_normal:
                self._fan_mode = FAN_AUTO

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            await self._send_command({"runStatus": 0})
        else:
            p_mode = self._hvac_map.get(hvac_mode, 3)
            await self._send_command({"runStatus": 1, "runMode": p_mode})

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None: return
        await self._send_command({"setTemperature": int(temp * self._temp_scale)})

    async def async_set_fan_mode(self, fan_mode):
        changes = {}
        if fan_mode == FAN_MUTE:
            changes = {"windSet": 10, "muteMode": 1}
        else:
            val = self._fan_map.get(fan_mode, 10)
            changes = {"windSet": val, "muteMode": 0}
        await self._send_command(changes)

    async def async_turn_on(self):
        await self._send_command({"runStatus": 1})

    async def async_turn_off(self):
        await self._send_command({"runStatus": 0})

    async def _send_command(self, changes):
        """Read-Modify-Write 核心逻辑"""
        
        # 1. Read
        latest_params = await self._fetch_status(update_internal_state=False)
        
        if latest_params:
            current_params = latest_params.copy()
        else:
            _LOGGER.warning("Could not fetch latest status, using cached params.")
            current_params = self._last_params.copy()

        # 2. Modify
        current_params.update(changes)
        
        # 3. Filter
        safe_keys = [
            "runMode", "forceRunning", "runStatus", "remoteForbidMode", "remoteMode",
            "setTemperature", "setHumidity", "windSet", "exchangeWindSet", 
            "portraitWindSet", "orientationWindSet", "nanoeG", "nanoe", "ecoMode", 
            "muteMode", "filterReset", "powerful", "powerfulMode", "thermoMode", "buzzer", 
            "autoRunMode", "unusualPresent", "runForbidden", "inhaleTemperature", 
            "outsideTemperature", "insideHumidity", "alarmCode", "nanoeModule", "TDWindModule"
        ]
        params = {k: v for k, v in current_params.items() if k in safe_keys}

        # 4. Write
        body = {
            "id": 200,
            "usrId": self._usr_id,
            "deviceId": self._device_id,
            "token": self._token,
            "params": params,
        }
        try:
            resp_json = await self._post_set(body)
            if response_looks_bad(resp_json):
                _LOGGER.warning(
                    "AC SET response looks bad (errorCode=%s); attempting silent re-login. Raw=%s",
                    resp_json.get("errorCode") if isinstance(resp_json, dict) else None,
                    resp_json,
                )
                try:
                    self._ssid = await relogin_entry(self._hass, self._entry)
                except ReloginCooldown as err:
                    _LOGGER.warning("SET skipped: %s", err)
                    return
                except LoginFailed as err:
                    raise ConfigEntryAuthFailed(str(err)) from err
                resp_json = await self._post_set(body)
                if response_looks_bad(resp_json):
                    raise ConfigEntryAuthFailed(
                        f"Still bad after re-login: errorCode={resp_json.get('errorCode') if isinstance(resp_json, dict) else None}"
                    )

            # 5. 更新本地状态 (乐观)
            self._update_local_state(current_params)
            self._last_params = current_params
            self.async_write_ha_state()
        except ConfigEntryAuthFailed:
            raise
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Set failed: %s", e)

    async def _post_set(self, body):
        session = async_get_clientsession(self._hass)
        async with async_timeout.timeout(10):
            resp = await session.post(
                URL_SET, json=body, headers=self._get_headers(), ssl=False
            )
            try:
                return await resp.json()
            except Exception:  # noqa: BLE001
                return {}

    def _get_headers(self):
        return {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)',
            'xtoken': f'SSID={self._ssid}',
            'DNT': '1', 'Origin': 'https://app.psmartcloud.com', 'X-Requested-With': 'XMLHttpRequest'
        }