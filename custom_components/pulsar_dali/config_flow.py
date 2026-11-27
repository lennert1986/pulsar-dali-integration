from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import PulsarDaliApi, PulsarDaliApiError, normalize_fingerprint
from .const import CONF_FINGERPRINT, CONF_SCAN_ON_SETUP, CONF_TOKEN, CONF_URL, DEFAULT_URL, DOMAIN

CONF_BUSES = "buses"
CONF_BUS = "bus"
CONF_GEAR = "gear"
CONF_GROUPS = "groups"
CONF_NEW_ADDRESS = "new_address"
CONF_CONFIRM = "confirm"
CONF_SCENE = "scene"
CONF_LEVEL = "level"
CONF_REMOVE = "remove"
CONF_INPUT = "input"
CONF_HOST = "host"
CONF_PORT = "port"


def _overview_markdown(snapshot: dict) -> str:
    lines = [
        "| Bus | Adr | Type | DT | Niveau | Min | Max | Power-on | Fail | Grupper | Adresse | Status |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    gear = sorted(snapshot.get("gear", []), key=lambda x: (int(x.get("bus", 0)), int(x.get("address", 0))))
    if not gear:
        lines.append("| - | - | Ingen armaturer fundet | - | - | - | - | - | - | - | - | - |")
    for item in gear:
        groups = ", ".join(str(x) for x in item.get("groups", [])) or "-"
        address_state = "⚠ KONFLIKT" if item.get("address_conflict") else "OK"
        lines.append(
            "| {bus} | {address} | {kind} | {dt} | {level} | {minv} | {maxv} | {power} | {fail} | {groups} | {addrstate} | {status} |".format(
                bus=item.get("bus", "-"), address=item.get("address", "-"), kind=item.get("entity_kind", "-"),
                dt=item.get("device_type", "-"), level=item.get("actual_level", "-"), minv=item.get("min_level", "-"),
                maxv=item.get("max_level", "-"), power=item.get("power_on_level", "-"), fail=item.get("system_failure_level", "-"),
                groups=groups, addrstate=address_state, status="OK" if item.get("online") else "Offline",
            )
        )
    lines.append("")
    scenes = sorted(snapshot.get("scenes", []), key=lambda x: (int(x.get("bus", 0)), int(x.get("scene", 0))))
    if scenes:
        lines.append("**Scener:** " + " · ".join(
            f"DALI {x['bus']} S{x['scene']} ({x.get('member_count', 0)} gear)" for x in scenes
        ))
        lines.append("")
    inputs = sorted(snapshot.get("input_instances", []), key=lambda x: (int(x.get("bus", 0)), int(x.get("address", 0)), int(x.get("instance", 0))))
    if inputs:
        lines.append("**DALI-2 inputs:**")
        for x in inputs:
            value = x.get("relative_illuminance", x.get("input_value", "-"))
            if int(x.get("instance_type", -1)) == 3:
                value = f"occupied={x.get('occupied')} movement={x.get('movement')}"
            lines.append(
                f"- DALI {x['bus']} · device {x['address']} · instance {x['instance']} · {x.get('instance_type_name')} · value {value} · event scheme {x.get('event_scheme')}"
            )
        lines.append("")
    for bus in (1, 2, 3):
        b = snapshot.get("buses", {}).get(str(bus), {})
        conflicts = b.get("conflicts", [])
        unaddressed = b.get("unaddressed_present")
        untext = "ja" if unaddressed is True else "nej" if unaddressed is False else "ukendt"
        lines.append(
            f"**DALI {bus}:** {b.get('gear_count', 0)} gear · konflikter: {', '.join(map(str, conflicts)) if conflicts else 'ingen'} · unaddressed: {untext}"
        )
    return "\n".join(lines)


def _summary(snapshot: dict) -> str:
    buses = snapshot.get("buses", {})
    parts = []
    for bus in (1, 2, 3):
        item = buses.get(str(bus), {})
        conflict_count = int(item.get("conflict_count", 0))
        unaddressed = item.get("unaddressed_present")
        flag = []
        if conflict_count:
            flag.append(f"⚠ {conflict_count} konflikt")
        if unaddressed is True:
            flag.append("nyt/unaddressed gear")
        suffix = f" ({', '.join(flag)})" if flag else ""
        parts.append(f"DALI {bus}: {item.get('gear_count', 0)} gear / {item.get('group_count', 0)} grupper / {item.get('scene_count', 0)} scener / {item.get('input_instance_count', 0)} inputs{suffix}")
    return " · ".join(parts)


def _bus_selector(default=None):
    options = [SelectOptionDict(value=str(x), label=f"DALI {x}") for x in (1, 2, 3)]
    return vol.Schema({
        vol.Required(CONF_BUS, default=str(default or 1)): SelectSelector(
            SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
        )
    })


class PulsarDaliConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["local", "remote"])

    async def async_step_local(self, user_input=None):
        errors = {}
        if user_input is not None:
            url = str(user_input[CONF_URL]).rstrip("/")
            api = PulsarDaliApi(async_get_clientsession(self.hass), url)
            try:
                status = await api.status()
            except PulsarDaliApiError:
                errors["base"] = "cannot_connect"
            else:
                controller_id = status["controller_id"]
                await self.async_set_unique_id(controller_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Pulsar DALI",
                    data={CONF_URL: url, CONF_SCAN_ON_SETUP: bool(user_input.get(CONF_SCAN_ON_SETUP, True))},
                )
        schema = vol.Schema({
            vol.Required(CONF_URL, default=DEFAULT_URL): str,
            vol.Required(CONF_SCAN_ON_SETUP, default=True): bool,
        })
        return self.async_show_form(step_id="local", data_schema=schema, errors=errors)

    async def async_step_remote(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            token = str(user_input[CONF_TOKEN]).strip()
            try:
                fingerprint = normalize_fingerprint(str(user_input[CONF_FINGERPRINT]))
            except ValueError:
                errors[CONF_FINGERPRINT] = "invalid_fingerprint"
            else:
                if len(token) < 32:
                    errors[CONF_TOKEN] = "invalid_token"
                else:
                    host_part = host
                    if "://" in host_part:
                        host_part = host_part.split("://", 1)[1].split("/", 1)[0]
                        if host_part.startswith("[") and "]" in host_part:
                            host_part = host_part[1:host_part.index("]")]
                        elif host_part.count(":") == 1 and host_part.rsplit(":", 1)[1].isdigit():
                            host_part = host_part.rsplit(":", 1)[0]
                    host_for_url = f"[{host_part}]" if ":" in host_part and not host_part.startswith("[") else host_part
                    url = f"https://{host_for_url}:{port}"
                    api = PulsarDaliApi(async_get_clientsession(self.hass), url, token, fingerprint)
                    try:
                        status = await api.status()
                    except PulsarDaliApiError:
                        errors["base"] = "cannot_connect"
                    else:
                        controller_id = status["controller_id"]
                        await self.async_set_unique_id(controller_id)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Pulsar DALI · {host_part}",
                            data={
                                CONF_URL: url,
                                CONF_TOKEN: token,
                                CONF_FINGERPRINT: fingerprint,
                                CONF_SCAN_ON_SETUP: bool(user_input.get(CONF_SCAN_ON_SETUP, True)),
                            },
                        )
        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_PORT, default=8443): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(CONF_TOKEN): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
            ),
            vol.Required(CONF_FINGERPRINT): TextSelector(),
            vol.Required(CONF_SCAN_ON_SETUP, default=True): bool,
        })
        return self.async_show_form(step_id="remote", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PulsarDaliOptionsFlow()


class PulsarDaliOptionsFlow(config_entries.OptionsFlow):
    def __init__(self) -> None:
        self._selected_gear: tuple[int, int] | None = None
        self._message = ""

    def _api(self) -> PulsarDaliApi:
        return PulsarDaliApi(
            async_get_clientsession(self.hass),
            self.config_entry.data[CONF_URL],
            self.config_entry.data.get(CONF_TOKEN),
            self.config_entry.data.get(CONF_FINGERPRINT),
        )

    async def _devices(self) -> dict:
        return await self._api().devices()

    async def _refresh_runtime(self) -> None:
        runtime = getattr(self.config_entry, "runtime_data", None)
        coordinator = getattr(runtime, "coordinator", None)
        if coordinator is not None:
            await coordinator.async_request_refresh()

    async def async_step_init(self, user_input=None):
        try:
            snapshot = await self._devices()
            summary = _summary(snapshot)
        except PulsarDaliApiError as exc:
            summary = f"Kan ikke hente DALI-status: {exc}"
        if self._message:
            summary = f"{self._message}\n\n{summary}"
            self._message = ""
        return self.async_show_menu(
            step_id="init",
            menu_options=["overview", "scan", "groups", "scenes", "inputs", "addresses", "backup", "connection", "finish"],
            description_placeholders={"summary": summary},
        )

    async def async_step_overview(self, user_input=None):
        try:
            snapshot = await self._devices()
            overview = _overview_markdown(snapshot)
        except PulsarDaliApiError as exc:
            overview = f"Kunne ikke hente overblik: {exc}"
        return self.async_show_menu(
            step_id="overview",
            menu_options=["scan", "groups", "scenes", "inputs", "addresses", "backup", "connection", "finish"],
            description_placeholders={"overview": overview},
        )

    async def async_step_scan(self, user_input=None):
        errors = {}
        if user_input is not None:
            buses = [int(x) for x in user_input[CONF_BUSES]]
            try:
                result = await self._api().scan(buses)
                await self._refresh_runtime()
            except PulsarDaliApiError as exc:
                errors["base"] = "action_failed"
                self._message = str(exc)
            else:
                counts = []
                for x in result.get("results", []):
                    gear_result = x.get("gear", x)
                    input_result = x.get("control_devices", {})
                    text = f"DALI {x['bus']}: {gear_result.get('count', 0)} gear / {input_result.get('control_device_count', 0)} control devices"
                    if gear_result.get("conflicts"):
                        text += f" · konflikter {gear_result['conflicts']}"
                    if gear_result.get("unaddressed_present") is True:
                        text += " · unaddressed fundet"
                    counts.append(text)
                self._message = "Scan færdig — " + ", ".join(counts)
                return await self.async_step_overview()
        options = [SelectOptionDict(value=str(x), label=f"DALI {x}") for x in (1, 2, 3)]
        schema = vol.Schema({
            vol.Required(CONF_BUSES, default=["1", "2", "3"]): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN)
            )
        })
        return self.async_show_form(step_id="scan", data_schema=schema, errors=errors)

    async def async_step_groups(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        gear = sorted(snapshot.get("gear", []), key=lambda x: (int(x["bus"]), int(x["address"])))
        if not gear:
            return self.async_show_menu(step_id="groups", menu_options=["scan", "finish"], description_placeholders={"group_summary": "Ingen fundne armaturer. Kør først en scan."})
        options = [SelectOptionDict(value=f"{x['bus']}:{x['address']}", label=f"DALI {x['bus']} · adresse {x['address']} · grupper {x.get('groups', []) or '-'}") for x in gear]
        if user_input is not None:
            bus_s, address_s = user_input[CONF_GEAR].split(":", 1)
            self._selected_gear = (int(bus_s), int(address_s))
            return await self.async_step_group_edit()
        schema = vol.Schema({vol.Required(CONF_GEAR): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="groups", data_schema=schema, description_placeholders={"group_summary": f"{len(gear)} armaturer fundet."})

    async def async_step_group_edit(self, user_input=None):
        if self._selected_gear is None:
            return await self.async_step_groups()
        bus, address = self._selected_gear
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        item = next((x for x in snapshot.get("gear", []) if int(x["bus"]) == bus and int(x["address"]) == address), None)
        if item is None:
            self._selected_gear = None
            return await self.async_step_groups()
        errors = {}
        if user_input is not None:
            selected = sorted(int(x) for x in user_input.get(CONF_GROUPS, []))
            try:
                await self._api().set_groups(bus, address, selected)
                await self._refresh_runtime()
            except PulsarDaliApiError as exc:
                errors["base"] = "action_failed"
                self._message = str(exc)
            else:
                self._message = f"DALI {bus} adresse {address}: grupper gemt som {selected or 'ingen'}."
                self._selected_gear = None
                return await self.async_step_overview()
        group_options = [SelectOptionDict(value=str(x), label=f"Gruppe {x}") for x in range(16)]
        schema = vol.Schema({vol.Required(CONF_GROUPS, default=[str(x) for x in item.get("groups", [])]): SelectSelector(SelectSelectorConfig(options=group_options, multiple=True, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="group_edit", data_schema=schema, errors=errors, description_placeholders={"gear": f"DALI {bus} · adresse {address}", "current_groups": ", ".join(str(x) for x in item.get("groups", [])) or "Ingen"})

    async def async_step_scenes(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        gear = [x for x in snapshot.get("gear", []) if not x.get("address_conflict")]
        if not gear:
            self._message = "Ingen entydige control gear fundet. Kør først en scan."
            return await self.async_step_init()
        errors = {}
        if user_input is not None:
            bus_s, address_s = user_input[CONF_GEAR].split(":", 1)
            scene = int(user_input[CONF_SCENE])
            remove = bool(user_input.get(CONF_REMOVE, False))
            level = None if remove else int(user_input[CONF_LEVEL])
            try:
                await self._api().set_scene_level(int(bus_s), int(address_s), scene, level)
                await self._refresh_runtime()
            except PulsarDaliApiError as exc:
                errors["base"] = "action_failed"
                self._message = str(exc)
            else:
                action = "fjernet fra" if remove else f"sat til niveau {level} i"
                self._message = f"DALI {bus_s} adresse {address_s}: {action} scene {scene}."
                return await self.async_step_overview()
        gear_options = [
            SelectOptionDict(
                value=f"{x['bus']}:{x['address']}",
                label=f"DALI {x['bus']} · adresse {x['address']} · scener " +
                    (", ".join(f"{k}:{v}" for k, v in x.get("scenes", {}).items() if v is not None and int(v) != 255) or "-"),
            ) for x in gear
        ]
        scene_options = [SelectOptionDict(value=str(x), label=f"Scene {x}") for x in range(16)]
        schema = vol.Schema({
            vol.Required(CONF_GEAR): SelectSelector(SelectSelectorConfig(options=gear_options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_SCENE, default="0"): SelectSelector(SelectSelectorConfig(options=scene_options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_LEVEL, default=254): vol.All(vol.Coerce(int), vol.Range(min=0, max=254)),
            vol.Required(CONF_REMOVE, default=False): bool,
        })
        return self.async_show_form(step_id="scenes", data_schema=schema, errors=errors)

    async def async_step_inputs(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        instances = sorted(
            snapshot.get("input_instances", []),
            key=lambda x: (int(x.get("bus", 0)), int(x.get("address", 0)), int(x.get("instance", 0))),
        )
        if not instances:
            return self.async_show_menu(
                step_id="inputs",
                menu_options=["scan", "finish"],
                description_placeholders={"input_summary": "Ingen DALI-2 input instances fundet. Kør en scan."},
            )
        summary = "\n".join(
            f"DALI {x['bus']} · device {x['address']} · inst {x['instance']} · {x.get('instance_type_name')} · scheme {x.get('event_scheme')} · enabled {x.get('enabled')}"
            for x in instances
        )
        errors = {}
        if user_input is not None:
            bus_s, address_s, inst_s = user_input[CONF_INPUT].split(":", 2)
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirmation_required"
            else:
                try:
                    await self._api().recommended_event_profile(int(bus_s), int(address_s), int(inst_s))
                    await self._refresh_runtime()
                except PulsarDaliApiError as exc:
                    errors["base"] = "action_failed"
                    self._message = str(exc)
                else:
                    self._message = f"DALI {bus_s} device {address_s} instance {inst_s}: event scheme 2 aktiveret og instance enabled."
                    return await self.async_step_overview()
        options = [
            SelectOptionDict(
                value=f"{x['bus']}:{x['address']}:{x['instance']}",
                label=f"DALI {x['bus']} · dev {x['address']} · inst {x['instance']} · {x.get('instance_type_name')} · scheme {x.get('event_scheme')}",
            ) for x in instances
        ]
        schema = vol.Schema({
            vol.Required(CONF_INPUT): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_CONFIRM, default=False): bool,
        })
        return self.async_show_form(
            step_id="inputs",
            data_schema=schema,
            errors=errors,
            description_placeholders={"input_summary": summary},
        )

    async def async_step_addresses(self, user_input=None):
        try:
            snapshot = await self._devices()
            summary = _summary(snapshot)
        except PulsarDaliApiError as exc:
            summary = f"Kunne ikke hente commissioning-status: {exc}"
        return self.async_show_menu(
            step_id="addresses",
            menu_options=["detect_conflicts", "change_address", "repair_conflict", "commission_unaddressed", "clear_address", "overview", "finish"],
            description_placeholders={"address_summary": summary},
        )

    async def async_step_detect_conflicts(self, user_input=None):
        errors = {}
        if user_input is not None:
            buses = [int(x) for x in user_input[CONF_BUSES]]
            try:
                result = await self._api().detect_conflicts(buses)
                await self._refresh_runtime()
            except PulsarDaliApiError as exc:
                errors["base"] = "action_failed"
                self._message = str(exc)
            else:
                texts = [f"DALI {r['bus']}: {r.get('conflicts', []) or 'ingen'}" for r in result.get("results", [])]
                self._message = "Konflikttest færdig — " + " · ".join(texts)
                return await self.async_step_overview()
        options = [SelectOptionDict(value=str(x), label=f"DALI {x}") for x in (1, 2, 3)]
        schema = vol.Schema({vol.Required(CONF_BUSES, default=["1", "2", "3"]): SelectSelector(SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="detect_conflicts", data_schema=schema, errors=errors)

    async def async_step_change_address(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        gear = [x for x in snapshot.get("gear", []) if not x.get("address_conflict")]
        if not gear:
            self._message = "Ingen entydige control gear fundet."
            return await self.async_step_addresses()
        if user_input is not None:
            bus_s, address_s = user_input[CONF_GEAR].split(":", 1)
            self._selected_gear = (int(bus_s), int(address_s))
            return await self.async_step_change_address_edit()
        options = [SelectOptionDict(value=f"{x['bus']}:{x['address']}", label=f"DALI {x['bus']} · adresse {x['address']} · {x.get('entity_kind', 'gear')}") for x in gear]
        schema = vol.Schema({vol.Required(CONF_GEAR): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="change_address", data_schema=schema)

    async def async_step_change_address_edit(self, user_input=None):
        if self._selected_gear is None:
            return await self.async_step_change_address()
        bus, old = self._selected_gear
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        used = {int(x["address"]) for x in snapshot.get("gear", []) if int(x["bus"]) == bus}
        free = [x for x in range(64) if x not in used]
        if not free:
            self._message = f"DALI {bus} har ingen ledige short addresses."
            return await self.async_step_addresses()
        errors = {}
        if user_input is not None:
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirmation_required"
            else:
                new = int(user_input[CONF_NEW_ADDRESS])
                try:
                    await self._api().change_address(bus, old, new)
                    await self._refresh_runtime()
                except PulsarDaliApiError as exc:
                    errors["base"] = "action_failed"
                    self._message = str(exc)
                else:
                    self._message = f"DALI {bus}: short address {old} ændret til {new}. Backup blev lavet automatisk."
                    self._selected_gear = None
                    return await self.async_step_overview()
        options = [SelectOptionDict(value=str(x), label=f"Adresse {x}") for x in free]
        schema = vol.Schema({
            vol.Required(CONF_NEW_ADDRESS): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_CONFIRM, default=False): bool,
        })
        return self.async_show_form(step_id="change_address_edit", data_schema=schema, errors=errors, description_placeholders={"gear": f"DALI {bus} · adresse {old}"})

    async def async_step_repair_conflict(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        conflicted = [x for x in snapshot.get("gear", []) if x.get("address_conflict")]
        if not conflicted:
            self._message = "Ingen short-address konflikter er markeret. Kør evt. konflikttesten først."
            return await self.async_step_addresses()
        errors = {}
        if user_input is not None:
            bus_s, address_s = user_input[CONF_GEAR].split(":", 1)
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirmation_required"
            else:
                try:
                    result = await self._api().repair_conflict(int(bus_s), int(address_s))
                    await self._refresh_runtime()
                except PulsarDaliApiError as exc:
                    errors["base"] = "action_failed"
                    self._message = str(exc)
                else:
                    mode = "kendt gear bevaret" if result.get("identity_preserved") else "identitet kunne ikke garanteres"
                    self._message = f"Konflikt på DALI {bus_s} adresse {address_s} repareret ({mode}). Backup blev lavet automatisk."
                    return await self.async_step_overview()
        options = [SelectOptionDict(value=f"{x['bus']}:{x['address']}", label=f"DALI {x['bus']} · adresse {x['address']} · KONFLIKT") for x in conflicted]
        schema = vol.Schema({
            vol.Required(CONF_GEAR): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_CONFIRM, default=False): bool,
        })
        return self.async_show_form(step_id="repair_conflict", data_schema=schema, errors=errors)

    async def async_step_commission_unaddressed(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        candidate_buses = [bus for bus in (1, 2, 3) if snapshot.get("buses", {}).get(str(bus), {}).get("unaddressed_present") is True]
        if not candidate_buses:
            candidate_buses = [1, 2, 3]
        errors = {}
        if user_input is not None:
            bus = int(user_input[CONF_BUS])
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirmation_required"
            else:
                try:
                    result = await self._api().commission_unaddressed(bus)
                    await self._refresh_runtime()
                except PulsarDaliApiError as exc:
                    errors["base"] = "action_failed"
                    self._message = str(exc)
                else:
                    self._message = f"DALI {bus}: {result.get('count', 0)} unaddressed gear commissioneret. Backup blev lavet automatisk hvis der var noget at ændre."
                    return await self.async_step_overview()
        options = [SelectOptionDict(value=str(x), label=f"DALI {x}") for x in candidate_buses]
        schema = vol.Schema({
            vol.Required(CONF_BUS, default=str(candidate_buses[0])): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_CONFIRM, default=False): bool,
        })
        return self.async_show_form(step_id="commission_unaddressed", data_schema=schema, errors=errors)

    async def async_step_clear_address(self, user_input=None):
        try:
            snapshot = await self._devices()
        except PulsarDaliApiError:
            return self.async_abort(reason="cannot_connect")
        gear = [x for x in snapshot.get("gear", []) if not x.get("address_conflict")]
        if not gear:
            self._message = "Ingen entydige gear kan få ryddet adressen."
            return await self.async_step_addresses()
        errors = {}
        if user_input is not None:
            bus_s, address_s = user_input[CONF_GEAR].split(":", 1)
            if not user_input.get(CONF_CONFIRM, False):
                errors["base"] = "confirmation_required"
            else:
                try:
                    await self._api().clear_address(int(bus_s), int(address_s))
                    await self._refresh_runtime()
                except PulsarDaliApiError as exc:
                    errors["base"] = "action_failed"
                    self._message = str(exc)
                else:
                    self._message = f"DALI {bus_s}: short address {address_s} ryddet. Gear'et er nu unaddressed."
                    return await self.async_step_overview()
        options = [SelectOptionDict(value=f"{x['bus']}:{x['address']}", label=f"DALI {x['bus']} · adresse {x['address']}") for x in gear]
        schema = vol.Schema({
            vol.Required(CONF_GEAR): SelectSelector(SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required(CONF_CONFIRM, default=False): bool,
        })
        return self.async_show_form(step_id="clear_address", data_schema=schema, errors=errors)

    async def async_step_backup(self, user_input=None):
        errors = {}
        if user_input is not None:
            buses = [int(x) for x in user_input[CONF_BUSES]]
            try:
                result = await self._api().create_backup(buses, "manual-home-assistant")
            except PulsarDaliApiError as exc:
                errors["base"] = "action_failed"
                self._message = str(exc)
            else:
                self._message = f"Backup oprettet: {result.get('filename')} ({result.get('gear_count', 0)} gear)."
                return await self.async_step_init()
        options = [SelectOptionDict(value=str(x), label=f"DALI {x}") for x in (1, 2, 3)]
        schema = vol.Schema({vol.Required(CONF_BUSES, default=["1", "2", "3"]): SelectSelector(SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.DROPDOWN))})
        return self.async_show_form(step_id="backup", data_schema=schema, errors=errors)

    async def async_step_connection(self, user_input=None):
        errors = {}
        current = self.config_entry.data
        if user_input is not None:
            url = str(user_input[CONF_URL]).rstrip("/")
            token = str(user_input.get(CONF_TOKEN, "")).strip() or None
            try:
                fingerprint = normalize_fingerprint(str(user_input.get(CONF_FINGERPRINT, "")))
            except ValueError:
                errors[CONF_FINGERPRINT] = "invalid_fingerprint"
            else:
                try:
                    api = PulsarDaliApi(async_get_clientsession(self.hass), url, token, fingerprint)
                    await api.status()
                except PulsarDaliApiError:
                    errors["base"] = "cannot_connect"
                else:
                    data = dict(current)
                    data[CONF_URL] = url
                    if token:
                        data[CONF_TOKEN] = token
                    else:
                        data.pop(CONF_TOKEN, None)
                    if fingerprint:
                        data[CONF_FINGERPRINT] = fingerprint
                    else:
                        data.pop(CONF_FINGERPRINT, None)
                    self.hass.config_entries.async_update_entry(self.config_entry, data=data)
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    return self.async_create_entry(title="", data={})
        schema = vol.Schema({
            vol.Required(CONF_URL, default=current.get(CONF_URL, DEFAULT_URL)): str,
            vol.Optional(CONF_TOKEN, default=current.get(CONF_TOKEN, "")): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
            ),
            vol.Optional(CONF_FINGERPRINT, default=current.get(CONF_FINGERPRINT, "")): TextSelector(),
        })
        return self.async_show_form(step_id="connection", data_schema=schema, errors=errors)

    async def async_step_finish(self, user_input=None):
        return self.async_create_entry(title="", data=dict(self.config_entry.options))
