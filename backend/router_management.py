import json
import re
from datetime import datetime, timezone
from string import Template
from typing import Any

import httpx


VENDOR_WEB_PROTOCOLS = {"tplink_web", "huawei_web"}


class RouterConnector:
    def validate_wifi_password(self, password: str) -> tuple[bool, str | None]:
        value = (password or "").strip()
        if len(value) < 8:
            return False, "الباسورد لازم يكون 8 حروف أو أكثر."
        if len(value) > 63:
            return False, "الباسورد لا يجب أن يزيد عن 63 حرف."
        if any(ch.isspace() for ch in value):
            return False, "يفضل بدون مسافات لتجنب مشاكل بعض الراوترات."
        if not re.match(r"^[\w\-@#$%&*!?.+=]+$", value):
            return False, "استخدم حروف وأرقام ورموز بسيطة فقط."
        return True, None

    async def change_wifi_password(self, router, new_password: str) -> dict[str, Any]:
        ok, error = self.validate_wifi_password(new_password)
        if not ok:
            return {"success": False, "message": error}
        if not router or not getattr(router, "enabled", False):
            return {"success": False, "message": "لا يوجد راوتر مفعّل لهذا العميل."}

        protocol = (router.protocol or "manual").lower()
        context = self.context(router, new_password)
        if protocol == "manual":
            return {"success": False, "manual_required": True, "message": "الراوتر مضبوط Manual. تم تحويل الطلب للدعم."}
        if protocol == "http_json":
            return await self.change_with_http(router, context)
        if protocol in VENDOR_WEB_PROTOCOLS:
            if router.http_change_password_path:
                return await self.change_with_http(router, context)
            return {
                "success": False,
                "manual_required": True,
                "message": "TP-Link/Huawei يحتاج endpoint أو ACS خاص بالموديل قبل التنفيذ التلقائي.",
            }
        if protocol in {"ssh", "mikrotik_ssh"}:
            return self.change_with_ssh(router, context)
        if protocol == "tr069":
            return {"success": False, "manual_required": True, "message": "TR-069/ACS hook غير مكوّن بعد لهذا الراوتر."}
        return {"success": False, "message": f"بروتوكول الراوتر غير مدعوم: {protocol}"}

    async def reboot(self, router) -> dict[str, Any]:
        if not router or not getattr(router, "enabled", False):
            return {"success": False, "message": "لا يوجد راوتر مفعّل."}
        context = self.context(router, "")
        protocol = (router.protocol or "manual").lower()
        if protocol == "http_json" and router.http_reboot_path:
            return await self.http_request(router, router.http_method or "POST", router.http_reboot_path, {})
        if protocol in VENDOR_WEB_PROTOCOLS and router.http_reboot_path:
            return await self.http_request(router, router.http_method or "POST", router.http_reboot_path, {})
        if protocol in {"ssh", "mikrotik_ssh"} and router.ssh_reboot_command:
            return self.run_ssh(router, self.render(router.ssh_reboot_command, context))
        return {"success": False, "manual_required": True, "message": "إعادة التشغيل غير مكوّنة لهذا الراوتر."}

    async def status(self, router) -> dict[str, Any]:
        if not router or not getattr(router, "enabled", False):
            return {"success": False, "message": "لا يوجد راوتر مفعّل."}
        protocol = (router.protocol or "").lower()
        if protocol in {"http_json", *VENDOR_WEB_PROTOCOLS} and router.http_status_path:
            return await self.http_request(router, "GET", router.http_status_path, {})
        return {"success": True, "message": "Router link exists", "protocol": router.protocol}

    async def change_with_http(self, router, context: dict[str, Any]) -> dict[str, Any]:
        if not router.http_change_password_path:
            return {"success": False, "message": "HTTP change password path غير مكوّن."}
        payload_template = router.http_payload_template or '{"wifi_password":"${password}","ssid":"${ssid}"}'
        try:
            payload_text = self.render(payload_template, context)
            payload = json.loads(payload_text) if payload_text.strip() else {}
        except Exception as exc:
            return {"success": False, "message": f"HTTP payload template invalid: {exc}"}
        return await self.http_request(router, router.http_method or "POST", router.http_change_password_path, payload)

    async def http_request(self, router, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not router.host:
            return {"success": False, "message": "Router host is missing."}
        scheme = getattr(router, "scheme", None) or ("https" if str(router.port or "").endswith("443") else "http")
        base = f"{scheme}://{router.host}"
        if router.port:
            base += f":{router.port}"
        url = f"{base}/{path.lstrip('/')}"
        auth = (router.username, router.password) if router.username else None
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                response = await client.request(method.upper(), url, json=payload if method.upper() != "GET" else None, auth=auth)
            return {
                "success": response.status_code < 400,
                "message": f"HTTP {response.status_code}",
                "status_code": response.status_code,
                "body": response.text[:500],
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def change_with_ssh(self, router, context: dict[str, Any]) -> dict[str, Any]:
        if not router.ssh_change_password_command:
            return {"success": False, "message": "SSH command template غير مكوّن."}
        command = self.render(router.ssh_change_password_command, context)
        return self.run_ssh(router, command)

    def run_ssh(self, router, command: str) -> dict[str, Any]:
        try:
            import paramiko
        except Exception:
            return {"success": False, "message": "SSH execution requires installing paramiko."}
        if not router.host or not router.username:
            return {"success": False, "message": "Router host/username missing."}
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=router.host,
                port=router.port or 22,
                username=router.username,
                password=router.password or None,
                timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
            stdin, stdout, stderr = client.exec_command(command, timeout=20)
            output = stdout.read().decode("utf-8", errors="ignore")
            error = stderr.read().decode("utf-8", errors="ignore")
            success = not error.strip()
            return {"success": success, "message": (error or output or "SSH command executed")[:500]}
        except Exception as exc:
            return {"success": False, "message": str(exc)}
        finally:
            client.close()

    def context(self, router, password: str) -> dict[str, Any]:
        return {
            "password": password,
            "ssid": router.ssid or "",
            "interface": router.wifi_interface or "",
            "profile": router.wifi_profile or "",
            "host": router.host or "",
            "username": router.username or "",
            "source": getattr(router, "host_source", "") or "",
        }

    def render(self, template: str, context: dict[str, Any]) -> str:
        return Template(template or "").safe_substitute(context)


router_connector = RouterConnector()
