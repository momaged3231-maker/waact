import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from database.db import SessionLocal
from database.models import ExternalWebhook


class IntegrationManager:
    async def emit_event(self, event: str, payload: dict[str, Any]) -> None:
        db = SessionLocal()
        try:
            webhooks = (
                db.query(ExternalWebhook)
                .filter(
                    ExternalWebhook.enabled == True,
                    ExternalWebhook.event.in_([event, "*"]),
                )
                .all()
            )
            for webhook in webhooks:
                await self.send(webhook, event, payload)
                db.commit()
        except Exception as exc:
            print(f"[INTEGRATIONS] emit skipped: {exc}")
        finally:
            db.close()

    async def send(self, webhook: ExternalWebhook, event: str, payload: dict[str, Any]) -> bool:
        body = json.dumps({
            "event": event,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }, ensure_ascii=False).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-WAACT-Event": event,
        }
        if webhook.secret:
            signature = hmac.new(webhook.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-WAACT-Signature"] = f"sha256={signature}"

        webhook.last_sent_at = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(webhook.url, content=body, headers=headers)
            webhook.last_status = str(response.status_code)
            webhook.last_error = None if response.status_code < 400 else response.text[:500]
            return response.status_code < 400
        except Exception as exc:
            webhook.last_status = "error"
            webhook.last_error = str(exc)[:500]
            return False


integration_manager = IntegrationManager()
