import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx


SETTINGS_PATH = Path(__file__).resolve().parent / "radius_settings.json"


DEFAULT_FIELD_MAP = {
    "external_id": "id",
    "username": "username",
    "phone": "phone",
    "status": "status",
    "package": "package",
    "expires_at": "expires_at",
    "online": "online",
    "last_seen_at": "last_seen_at",
    "balance": "balance",
    "ip_address": "ip_address",
    "reseller": "reseller",
    "download_rate": "download_rate",
    "upload_rate": "upload_rate",
    "traffic_used": "traffic_used",
}


DEFAULT_SETTINGS = {
    "enabled": False,
    "base_url": "",
    "auth_mode": "none",
    "api_key": "",
    "api_key_param": "api_key",
    "username": "",
    "password": "",
    "verify_ssl": True,
    "timeout_seconds": 10,
    "search_path": "/api/subscribers/search?q={query}",
    "detail_path": "/api/subscribers/{external_id}",
    "sessions_path": "/api/subscribers/{external_id}/sessions",
    "action_paths": {
        "renew": "",
        "activate": "",
        "suspend": "",
        "disconnect": "",
        "change_package": "",
    },
    "field_map": DEFAULT_FIELD_MAP.copy(),
    "reminders_enabled": False,
    "reminder_days_before": [3, 1],
    "expired_reminder_days_after": [0, 3],
    "renewal_message": "اشتراكك هينتهي يوم {expires_at}. للتجديد تواصل معنا أو ابعت جدد.",
}


STATUS_ACTIVE = {"active", "enabled", "ok", "open", "1", "true", "online"}
STATUS_EXPIRED = {"expired", "expire", "ended", "inactive", "0"}
STATUS_DISABLED = {"disabled", "blocked", "suspended", "closed"}


class RadiusConnector:
    def load_settings(self) -> dict[str, Any]:
        data = json.loads(json.dumps(DEFAULT_SETTINGS))
        if SETTINGS_PATH.exists():
            try:
                loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                default_actions = data.get("action_paths", {}).copy()
                default_map = data.get("field_map", {}).copy()
                data.update(loaded)
                default_actions.update(loaded.get("action_paths", {}))
                default_map.update(loaded.get("field_map", {}))
                data["action_paths"] = default_actions
                data["field_map"] = default_map
            except Exception:
                pass
        return data

    def save_from_form(self, form) -> None:
        current = self.load_settings()
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        settings.update({
            "enabled": form.get("enabled") == "on",
            "base_url": (form.get("base_url") or "").strip().rstrip("/"),
            "auth_mode": form.get("auth_mode") or "none",
            "api_key": (form.get("api_key") or current.get("api_key") or "").strip(),
            "api_key_param": (form.get("api_key_param") or "api_key").strip(),
            "username": (form.get("username") or current.get("username") or "").strip(),
            "password": (form.get("password") or current.get("password") or "").strip(),
            "verify_ssl": form.get("verify_ssl") == "on",
            "search_path": (form.get("search_path") or DEFAULT_SETTINGS["search_path"]).strip(),
            "detail_path": (form.get("detail_path") or DEFAULT_SETTINGS["detail_path"]).strip(),
            "sessions_path": (form.get("sessions_path") or DEFAULT_SETTINGS["sessions_path"]).strip(),
            "reminders_enabled": form.get("reminders_enabled") == "on",
            "renewal_message": (form.get("renewal_message") or DEFAULT_SETTINGS["renewal_message"]).strip(),
        })
        settings["timeout_seconds"] = self.form_int(form, "timeout_seconds", 10, 2, 60)
        settings["reminder_days_before"] = self.parse_int_list(form.get("reminder_days_before"), [3, 1])
        settings["expired_reminder_days_after"] = self.parse_int_list(form.get("expired_reminder_days_after"), [0, 3])

        for action in settings["action_paths"]:
            settings["action_paths"][action] = (form.get(f"action_{action}") or "").strip()
        for field in settings["field_map"]:
            settings["field_map"][field] = (form.get(f"map_{field}") or DEFAULT_FIELD_MAP.get(field, field)).strip()

        SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def status_for_ui(self) -> dict[str, Any]:
        settings = self.load_settings()
        return {
            **settings,
            "configured": bool(settings.get("base_url")),
            "has_secret": bool(settings.get("api_key") or settings.get("password")),
            "masked_api_key": self.mask(settings.get("api_key", "")),
            "masked_password": "***" if settings.get("password") else "غير مضاف",
        }

    async def test_connection(self) -> dict[str, Any]:
        settings = self.load_settings()
        if not settings.get("enabled") or not settings.get("base_url"):
            return {"ok": False, "error": "Radius integration is disabled or base URL is missing."}
        try:
            result = await self.search_subscribers("test", limit=1)
            return {"ok": True, "message": "Connected", "sample_count": len(result)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:500]}

    async def search_subscribers(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        settings = self.load_settings()
        if not settings.get("enabled"):
            raise RuntimeError("Radius integration is disabled.")
        path = settings.get("search_path", "").format(query=query)
        data = await self.request_json(settings, "GET", path)
        return [self.normalize_subscriber(item, settings) for item in self.extract_items(data)[:limit]]

    async def get_subscriber(self, external_id: str) -> dict[str, Any]:
        settings = self.load_settings()
        if not settings.get("enabled"):
            raise RuntimeError("Radius integration is disabled.")
        path = settings.get("detail_path", "").format(external_id=external_id)
        data = await self.request_json(settings, "GET", path)
        if isinstance(data, list):
            if not data:
                raise RuntimeError("Subscriber not found.")
            data = data[0]
        if isinstance(data, dict):
            for key in ("subscriber", "user", "data", "item"):
                if isinstance(data.get(key), dict):
                    data = data[key]
                    break
        return self.normalize_subscriber(data, settings)

    async def get_sessions(self, external_id: str) -> list[dict[str, Any]]:
        settings = self.load_settings()
        path = settings.get("sessions_path", "").format(external_id=external_id)
        if not path:
            return []
        data = await self.request_json(settings, "GET", path)
        return self.extract_items(data)

    async def execute_action(self, external_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self.load_settings()
        path = settings.get("action_paths", {}).get(action)
        if not path:
            raise RuntimeError(f"Radius action '{action}' is not configured.")
        path = path.format(external_id=external_id)
        return await self.request_json(settings, "POST", path, json_body=payload or {})

    async def request_json(
        self,
        settings: dict[str, Any],
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        if not settings.get("base_url"):
            raise RuntimeError("Radius base URL is missing.")
        url = f"{settings['base_url'].rstrip('/')}/{path.lstrip('/')}"
        headers = {"Accept": "application/json"}
        auth = None
        params = {}
        auth_mode = settings.get("auth_mode", "none")
        if auth_mode == "bearer" and settings.get("api_key"):
            headers["Authorization"] = f"Bearer {settings['api_key']}"
        elif auth_mode == "header" and settings.get("api_key"):
            headers["X-API-Key"] = settings["api_key"]
        elif auth_mode == "query" and settings.get("api_key"):
            params[settings.get("api_key_param") or "api_key"] = settings["api_key"]
        elif auth_mode == "basic" and settings.get("username"):
            auth = (settings.get("username"), settings.get("password", ""))

        async with httpx.AsyncClient(
            timeout=float(settings.get("timeout_seconds") or 10),
            verify=bool(settings.get("verify_ssl", True)),
        ) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json_body, auth=auth)
        if response.status_code >= 400:
            raise RuntimeError(f"Radius HTTP {response.status_code}: {response.text[:500]}")
        if not response.content:
            return {"ok": True}
        try:
            return response.json()
        except Exception:
            return {"raw": response.text}

    def normalize_subscriber(self, data: Any, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = settings or self.load_settings()
        item = data if isinstance(data, dict) else {}
        field_map = settings.get("field_map", DEFAULT_FIELD_MAP)

        normalized = {}
        for target, source in field_map.items():
            normalized[target] = self.pick(item, source)

        username = normalized.get("username") or normalized.get("external_id") or self.pick(item, "login")
        external_id = normalized.get("external_id") or username or self.pick(item, "userid") or self.pick(item, "user_id")
        normalized["external_id"] = str(external_id or "").strip()
        normalized["username"] = str(username or normalized["external_id"] or "").strip()
        normalized["phone"] = self.clean_phone(normalized.get("phone") or self.pick(item, "mobile") or self.pick(item, "phone_number"))
        normalized["status"] = self.normalize_status(normalized.get("status"), normalized.get("expires_at"))
        normalized["online"] = self.to_bool(normalized.get("online"))
        normalized["expires_at"] = self.parse_datetime(normalized.get("expires_at"))
        normalized["last_seen_at"] = self.parse_datetime(normalized.get("last_seen_at"))
        normalized["balance"] = self.to_float(normalized.get("balance"))
        normalized["raw"] = item
        return normalized

    def extract_items(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("subscribers", "users", "items", "data", "results", "rows"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [data]
        return []

    def pick(self, data: dict[str, Any], path: str | None) -> Any:
        if not path:
            return None
        current = data
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def normalize_status(self, status: Any, expires_at: Any = None) -> str:
        raw = str(status or "").strip().lower()
        expires = self.parse_datetime(expires_at)
        if expires and expires < datetime.now(timezone.utc):
            return "expired"
        if raw in STATUS_ACTIVE:
            return "active"
        if raw in STATUS_EXPIRED:
            return "expired"
        if raw in STATUS_DISABLED:
            return "disabled"
        return raw or "unknown"

    def parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, tz=timezone.utc)
            except Exception:
                return None
        text = str(value).strip()
        for suffix in ("Z", "+00:00"):
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                break
        for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None

    def clean_phone(self, value: Any) -> str:
        if not value:
            return ""
        return "".join(ch for ch in str(value) if ch.isdigit())

    def to_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "online", "active", "connected"}

    def to_float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def parse_int_list(self, value: str | None, default: list[int]) -> list[int]:
        if not value:
            return default
        result = []
        for part in str(value).replace(";", ",").split(","):
            try:
                result.append(int(part.strip()))
            except ValueError:
                pass
        return result or default

    def form_int(self, form, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(form.get(key) or default)
        except ValueError:
            value = default
        return max(minimum, min(value, maximum))

    def mask(self, value: str) -> str:
        if not value:
            return "غير مضاف"
        if len(value) <= 10:
            return "***"
        return f"{value[:4]}...{value[-4:]}"


def format_radius_status_ar(snapshot) -> str:
    status_labels = {
        "active": "نشط",
        "expired": "منتهي",
        "disabled": "موقوف",
        "unknown": "غير معروف",
    }
    status = status_labels.get(getattr(snapshot, "status", "unknown"), getattr(snapshot, "status", "unknown"))
    expires = getattr(snapshot, "expires_at", None)
    expires_text = expires.strftime("%Y-%m-%d") if expires else "غير محدد"
    online = "متصل" if getattr(snapshot, "online", False) else "غير متصل"
    package = getattr(snapshot, "package_name", None) or "غير محددة"
    return f"الحالة: {status}\nالباقة: {package}\nالانتهاء: {expires_text}\nالاتصال: {online}"


radius_connector = RadiusConnector()
