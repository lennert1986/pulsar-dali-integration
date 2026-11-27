from __future__ import annotations

from typing import Any
import re

import aiohttp


class PulsarDaliApiError(Exception):
    pass


def normalize_fingerprint(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9A-Fa-f]", "", str(value))
    if not cleaned:
        return None
    if len(cleaned) != 64:
        raise ValueError("TLS SHA-256 fingerprint must contain exactly 64 hexadecimal characters")
    return cleaned.upper()


class PulsarDaliApi:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        token: str | None = None,
        fingerprint: str | None = None,
    ) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self._token = token or None
        normalized = normalize_fingerprint(fingerprint)
        self._ssl = aiohttp.Fingerprint(bytes.fromhex(normalized)) if normalized else None

    async def _request(self, method: str, path: str, data: dict[str, Any] | None = None, timeout: float = 15.0) -> dict[str, Any]:
        try:
            headers = {}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            request_kwargs: dict[str, Any] = {
                "json": data,
                "timeout": aiohttp.ClientTimeout(total=timeout),
                "headers": headers,
            }
            if self._ssl is not None:
                request_kwargs["ssl"] = self._ssl
            async with self._session.request(
                method,
                f"{self.base_url}{path}",
                **request_kwargs,
            ) as response:
                payload = await response.json(content_type=None)
                if response.status >= 400 or not payload.get("ok", False):
                    raise PulsarDaliApiError(payload.get("error", f"HTTP {response.status}"))
                return payload
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise PulsarDaliApiError(str(exc)) from exc

    async def status(self) -> dict[str, Any]:
        return await self._request("GET", "/api/status")

    async def devices(self) -> dict[str, Any]:
        return await self._request("GET", "/api/devices")

    async def scan(self, buses: list[int] | None = None) -> dict[str, Any]:
        return await self._request("POST", "/api/scan", {"buses": buses or [1, 2, 3]}, timeout=180.0)

    async def set_level(self, bus: int, address: int, level: int) -> dict[str, Any]:
        return await self._request("POST", "/api/gear/control", {"bus": bus, "address": address, "level": level})

    async def set_group_level(self, bus: int, group: int, level: int) -> dict[str, Any]:
        return await self._request("POST", "/api/group/control", {"bus": bus, "group": group, "level": level})

    async def set_groups(self, bus: int, address: int, groups: list[int]) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/gear/groups",
            {"bus": bus, "address": address, "groups": groups},
        )

    async def set_config(self, bus: int, address: int, parameter: str, value: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/gear/config",
            {"bus": bus, "address": address, "parameter": parameter, "value": value},
        )

    async def identify(self, bus: int, address: int) -> dict[str, Any]:
        return await self._request("POST", "/api/gear/identify", {"bus": bus, "address": address})

    async def commissioning(self) -> dict[str, Any]:
        return await self._request("GET", "/api/commissioning")

    async def detect_conflicts(self, buses: list[int] | None = None) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/address/detect-conflicts", {"buses": buses or [1, 2, 3]}, timeout=90.0
        )

    async def change_address(self, bus: int, old_address: int, new_address: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/address/change",
            {"bus": bus, "old_address": old_address, "new_address": new_address, "confirm": True},
            timeout=180.0,
        )

    async def clear_address(self, bus: int, address: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/address/clear",
            {"bus": bus, "address": address, "confirm": True},
            timeout=180.0,
        )

    async def commission_unaddressed(self, bus: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/address/commission-unaddressed",
            {"bus": bus, "confirm": True}, timeout=300.0,
        )

    async def repair_conflict(self, bus: int, address: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/address/repair-conflict",
            {"bus": bus, "address": address, "confirm": True}, timeout=300.0,
        )

    async def events(self, since: int = 0, wait: float = 25.0) -> dict[str, Any]:
        return await self._request("GET", f"/api/events?since={int(since)}&wait={float(wait):.1f}", timeout=max(30.0, wait + 5.0))

    async def set_scene_level(self, bus: int, address: int, scene: int, level: int | None) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/gear/scene",
            {"bus": bus, "address": address, "scene": scene, "level": level},
        )

    async def activate_scene(self, bus: int, scene: int) -> dict[str, Any]:
        return await self._request("POST", "/api/scene/activate", {"bus": bus, "scene": scene})

    async def set_input_config(self, bus: int, address: int, instance: int, parameter: str, value: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/input/config",
            {"bus": bus, "address": address, "instance": instance, "parameter": parameter, "value": value},
        )

    async def recommended_event_profile(self, bus: int, address: int, instance: int) -> dict[str, Any]:
        return await self._request(
            "POST", "/api/input/recommended-event-profile",
            {"bus": bus, "address": address, "instance": instance},
        )

    async def create_backup(self, buses: list[int] | None = None, reason: str = "manual") -> dict[str, Any]:
        return await self._request(
            "POST", "/api/backup", {"buses": buses or [1, 2, 3], "reason": reason}, timeout=30.0
        )
