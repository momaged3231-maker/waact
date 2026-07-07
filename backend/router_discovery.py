import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

from database.models import Customer, RadiusSnapshot, RadiusSubscriberLink
from radius import radius_connector


SETTINGS_PATH = Path(__file__).resolve().parent / "router_auto_settings.json"

DEFAULT_SESSION_IP_FIELDS = [
    "framed_ip_address",
    "Framed-IP-Address",
    "framed-ip-address",
    "ip_address",
    "ip",
    "address",
    "remote_address",
    "remote-address",
]

DEFAULT_SETTINGS = {
    "enabled": False,
    "source_order": ["radius_sessions", "radius_snapshot", "mikrotik_ppp"],
    "session_ip_fields": DEFAULT_SESSION_IP_FIELDS,
    "default_name": "Auto CPE Router",
    "default_model": "TP-Link/Huawei CPE",
    "default_protocol": "tplink_web",
    "scheme": "http",
    "port": 80,
    "username": "",
    "password": "",
    "ssid": "",
    "wifi_interface": "",
    "wifi_profile": "",
    "http_method": "POST",
    "http_change_password_path": "",
    "http_payload_template": '{"wifi_password":"${password}","ssid":"${ssid}"}',
    "http_status_path": "",
    "http_reboot_path": "",
    "mikrotik_enabled": False,
    "mikrotik_method": "ssh",
    "mikrotik_host": "",
    "mikrotik_port": 22,
    "mikrotik_username": "",
    "mikrotik_password": "",
    "mikrotik_use_ssl": False,
    "mikrotik_verify_ssl": False,
    "mikrotik_timeout_seconds": 10,
}


class RouterAutoDiscovery:
    def load_settings(self) -> dict[str, Any]:
        data = json.loads(json.dumps(DEFAULT_SETTINGS))
        if SETTINGS_PATH.exists():
            try:
                loaded = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                data.update(loaded)
                data["source_order"] = self.parse_list(loaded.get("source_order"), DEFAULT_SETTINGS["source_order"])
                data["session_ip_fields"] = self.parse_list(loaded.get("session_ip_fields"), DEFAULT_SESSION_IP_FIELDS)
            except Exception:
                pass
        return data

    def save_from_form(self, form) -> None:
        current = self.load_settings()
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        settings.update({
            "enabled": form.get("auto_enabled") == "on",
            "source_order": self.parse_list(form.get("source_order"), DEFAULT_SETTINGS["source_order"]),
            "session_ip_fields": self.parse_list(form.get("session_ip_fields"), DEFAULT_SESSION_IP_FIELDS),
            "default_name": (form.get("default_name") or DEFAULT_SETTINGS["default_name"]).strip(),
            "default_model": (form.get("default_model") or DEFAULT_SETTINGS["default_model"]).strip(),
            "default_protocol": form.get("default_protocol") or DEFAULT_SETTINGS["default_protocol"],
            "scheme": form.get("scheme") or "http",
            "username": (form.get("auto_username") or current.get("username") or "").strip(),
            "password": (form.get("auto_password") or current.get("password") or "").strip(),
            "ssid": (form.get("auto_ssid") or "").strip(),
            "wifi_interface": (form.get("auto_wifi_interface") or "").strip(),
            "wifi_profile": (form.get("auto_wifi_profile") or "").strip(),
            "http_method": form.get("auto_http_method") or "POST",
            "http_change_password_path": (form.get("auto_http_change_password_path") or "").strip(),
            "http_payload_template": (form.get("auto_http_payload_template") or DEFAULT_SETTINGS["http_payload_template"]).strip(),
            "http_status_path": (form.get("auto_http_status_path") or "").strip(),
            "http_reboot_path": (form.get("auto_http_reboot_path") or "").strip(),
            "mikrotik_enabled": form.get("mikrotik_enabled") == "on",
            "mikrotik_method": form.get("mikrotik_method") or "ssh",
            "mikrotik_host": (form.get("mikrotik_host") or "").strip(),
            "mikrotik_username": (form.get("mikrotik_username") or current.get("mikrotik_username") or "").strip(),
            "mikrotik_password": (form.get("mikrotik_password") or current.get("mikrotik_password") or "").strip(),
            "mikrotik_use_ssl": form.get("mikrotik_use_ssl") == "on",
            "mikrotik_verify_ssl": form.get("mikrotik_verify_ssl") == "on",
        })
        settings["port"] = self.form_int(form, "auto_port", int(current.get("port") or 80), 1, 65535)
        settings["mikrotik_port"] = self.form_int(form, "mikrotik_port", int(current.get("mikrotik_port") or 22), 1, 65535)
        settings["mikrotik_timeout_seconds"] = self.form_int(form, "mikrotik_timeout_seconds", 10, 2, 60)
        SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def status_for_ui(self) -> dict[str, Any]:
        settings = self.load_settings()
        return {
            **settings,
            "source_order_text": ",".join(settings.get("source_order") or []),
            "session_ip_fields_text": ",".join(settings.get("session_ip_fields") or []),
            "masked_password": "***" if settings.get("password") else "غير مضاف",
            "masked_mikrotik_password": "***" if settings.get("mikrotik_password") else "غير مضاف",
        }

    async def discover_router(self, db, phone: str):
        settings = self.load_settings()
        if not settings.get("enabled"):
            return None
        discovery = await self.discover_host(db, phone, settings)
        if not discovery.get("host"):
            return None
        customer = self.get_customer(db, phone)
        return self.build_router(settings, discovery, customer)

    async def discover_host(self, db, phone: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = settings or self.load_settings()
        identity = await self.resolve_radius_identity(db, phone)
        for source in settings.get("source_order") or []:
            source = str(source).strip()
            if source == "radius_sessions":
                host = await self.host_from_radius_sessions(identity, settings)
                if host:
                    return {**identity, "host": host, "source": "radius_sessions"}
            elif source == "radius_snapshot":
                host = await self.host_from_radius_snapshot(db, phone, identity)
                if host:
                    return {**identity, "host": host, "source": "radius_snapshot"}
            elif source == "mikrotik_ppp" and settings.get("mikrotik_enabled"):
                host = await self.host_from_mikrotik(identity, settings)
                if host:
                    return {**identity, "host": host, "source": "mikrotik_ppp"}
        return {**identity, "host": None, "source": None}

    async def resolve_radius_identity(self, db, phone: str) -> dict[str, Any]:
        clean_phone = radius_connector.clean_phone(phone)
        customer = self.get_customer(db, clean_phone)
        link = None
        if customer:
            link = (
                db.query(RadiusSubscriberLink)
                .filter(RadiusSubscriberLink.customer_id == customer.id)
                .order_by(RadiusSubscriberLink.updated_at.desc())
                .first()
            )
        if not link:
            link = (
                db.query(RadiusSubscriberLink)
                .filter(RadiusSubscriberLink.phone == clean_phone)
                .order_by(RadiusSubscriberLink.updated_at.desc())
                .first()
            )
        snapshot = None
        if link:
            snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.external_id == link.external_id).first()
            return {
                "phone": clean_phone,
                "customer": customer,
                "external_id": link.external_id,
                "username": link.username or link.external_id,
                "snapshot": snapshot,
            }

        if customer:
            snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.customer_id == customer.id).first()
        if not snapshot:
            snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.phone == clean_phone).order_by(RadiusSnapshot.synced_at.desc()).first()
        if snapshot:
            return {
                "phone": clean_phone,
                "customer": customer,
                "external_id": snapshot.external_id,
                "username": snapshot.username or snapshot.external_id,
                "snapshot": snapshot,
            }

        try:
            from radius_service import radius_service
            lookup = await radius_service.lookup_by_phone(db, clean_phone)
            snapshot = lookup.get("snapshot")
            if snapshot:
                return {
                    "phone": clean_phone,
                    "customer": lookup.get("customer") or customer,
                    "external_id": snapshot.external_id,
                    "username": snapshot.username or snapshot.external_id,
                    "snapshot": snapshot,
                }
        except Exception:
            pass

        return {"phone": clean_phone, "customer": customer, "external_id": None, "username": None, "snapshot": None}

    async def host_from_radius_sessions(self, identity: dict[str, Any], settings: dict[str, Any]) -> str | None:
        external_id = identity.get("external_id") or identity.get("username")
        if not external_id:
            return None
        try:
            sessions = await radius_connector.get_sessions(external_id)
        except Exception:
            return None
        for session in sessions:
            host = self.extract_ip(session, settings.get("session_ip_fields"))
            if host:
                return host
        return None

    async def host_from_radius_snapshot(self, db, phone: str, identity: dict[str, Any]) -> str | None:
        snapshot = identity.get("snapshot")
        external_id = identity.get("external_id")
        if external_id:
            try:
                from radius_service import radius_service
                customer = identity.get("customer")
                snapshot = await radius_service.refresh_snapshot(db, external_id, getattr(customer, "id", None))
            except Exception:
                pass
        if snapshot and snapshot.ip_address:
            return self.clean_ip(snapshot.ip_address)
        return None

    async def host_from_mikrotik(self, identity: dict[str, Any], settings: dict[str, Any]) -> str | None:
        username = identity.get("username") or identity.get("external_id")
        if not username:
            return None
        method = (settings.get("mikrotik_method") or "ssh").lower()
        if method == "rest":
            return await self.host_from_mikrotik_rest(username, settings)
        return self.host_from_mikrotik_ssh(username, settings)

    async def host_from_mikrotik_rest(self, username: str, settings: dict[str, Any]) -> str | None:
        if not settings.get("mikrotik_host") or not settings.get("mikrotik_username"):
            return None
        scheme = "https" if settings.get("mikrotik_use_ssl") else "http"
        url = f"{scheme}://{settings['mikrotik_host']}:{settings.get('mikrotik_port') or 80}/rest/ppp/active"
        try:
            async with httpx.AsyncClient(timeout=float(settings.get("mikrotik_timeout_seconds") or 10), verify=bool(settings.get("mikrotik_verify_ssl"))) as client:
                response = await client.get(url, auth=(settings.get("mikrotik_username"), settings.get("mikrotik_password") or ""))
            if response.status_code >= 400:
                return None
            data = response.json()
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(item.get("name") or item.get("user") or item.get("username") or "") == str(username):
                    return self.extract_ip(item, DEFAULT_SESSION_IP_FIELDS)
        except Exception:
            return None
        return None

    def host_from_mikrotik_ssh(self, username: str, settings: dict[str, Any]) -> str | None:
        try:
            import paramiko
        except Exception:
            return None
        if not settings.get("mikrotik_host") or not settings.get("mikrotik_username"):
            return None
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=settings.get("mikrotik_host"),
                port=int(settings.get("mikrotik_port") or 22),
                username=settings.get("mikrotik_username"),
                password=settings.get("mikrotik_password") or None,
                timeout=float(settings.get("mikrotik_timeout_seconds") or 10),
                look_for_keys=False,
                allow_agent=False,
            )
            safe_username = str(username).replace('"', '\\"')
            command = f'/ppp active print detail without-paging where name="{safe_username}"'
            stdin, stdout, stderr = client.exec_command(command, timeout=20)
            output = stdout.read().decode("utf-8", errors="ignore")
            return self.extract_ip_from_text(output)
        except Exception:
            return None
        finally:
            client.close()

    def build_router(self, settings: dict[str, Any], discovery: dict[str, Any], customer=None):
        return SimpleNamespace(
            id=None,
            dynamic=True,
            enabled=True,
            customer_id=getattr(customer, "id", None),
            customer=customer,
            radius_external_id=discovery.get("external_id"),
            name=settings.get("default_name") or "Auto CPE Router",
            model=settings.get("default_model"),
            protocol=settings.get("default_protocol") or "tplink_web",
            scheme=settings.get("scheme") or "http",
            host=discovery.get("host"),
            host_source=discovery.get("source"),
            port=settings.get("port") or None,
            username=settings.get("username") or None,
            password=settings.get("password") or None,
            ssid=settings.get("ssid") or None,
            wifi_interface=settings.get("wifi_interface") or None,
            wifi_profile=settings.get("wifi_profile") or None,
            http_method=settings.get("http_method") or "POST",
            http_change_password_path=settings.get("http_change_password_path") or None,
            http_payload_template=settings.get("http_payload_template") or None,
            http_status_path=settings.get("http_status_path") or None,
            http_reboot_path=settings.get("http_reboot_path") or None,
            ssh_change_password_command=None,
            ssh_reboot_command=None,
            last_status=f"dynamic:{discovery.get('source')}",
            last_error=None,
            last_seen_at=datetime.now(timezone.utc),
        )

    def get_customer(self, db, phone: str):
        clean_phone = radius_connector.clean_phone(phone)
        return db.query(Customer).filter(Customer.phone == clean_phone).first()

    def extract_ip(self, data: Any, fields: list[str] | None = None) -> str | None:
        fields = fields or DEFAULT_SESSION_IP_FIELDS
        if isinstance(data, dict):
            for field in fields:
                value = self.pick(data, field)
                ip = self.clean_ip(value)
                if ip:
                    return ip
            for value in data.values():
                ip = self.extract_ip(value, fields)
                if ip:
                    return ip
        elif isinstance(data, list):
            for item in data:
                ip = self.extract_ip(item, fields)
                if ip:
                    return ip
        elif isinstance(data, str):
            return self.extract_ip_from_text(data)
        return None

    def extract_ip_from_text(self, text: str) -> str | None:
        if not text:
            return None
        for pattern in (
            r'(?:address|remote-address|framed-ip-address|Framed-IP-Address)="?([0-9]{1,3}(?:\.[0-9]{1,3}){3})"?',
            r'\b([0-9]{1,3}(?:\.[0-9]{1,3}){3})\b',
        ):
            match = re.search(pattern, text)
            if match:
                return self.clean_ip(match.group(1))
        return None

    def clean_ip(self, value: Any) -> str | None:
        if not value:
            return None
        text = str(value).strip().strip('"')
        match = re.match(r"^([0-9]{1,3}(?:\.[0-9]{1,3}){3})$", text)
        if not match:
            return None
        parts = [int(part) for part in match.group(1).split(".")]
        if any(part > 255 for part in parts):
            return None
        return match.group(1)

    def pick(self, data: dict[str, Any], path: str | None) -> Any:
        if not path:
            return None
        current = data
        for part in str(path).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def parse_list(self, value: Any, default: list[str]) -> list[str]:
        if isinstance(value, list):
            result = [str(item).strip() for item in value if str(item).strip()]
            return result or default
        if not value:
            return default
        result = [part.strip() for part in str(value).replace(";", ",").split(",") if part.strip()]
        return result or default

    def form_int(self, form, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(form.get(key) or default)
        except ValueError:
            value = default
        return max(minimum, min(value, maximum))


router_auto_discovery = RouterAutoDiscovery()
