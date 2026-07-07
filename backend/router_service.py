from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from database.models import Customer, CustomerStatus, RadiusSnapshot, RadiusSubscriberLink, RouterActionLog, RouterDevice, RouterPendingAction
from radius import radius_connector
from router_discovery import router_auto_discovery
from router_management import router_connector


WIFI_COMMANDS = {
    "غير باسورد الواي فاي",
    "تغيير باسورد الواي فاي",
    "غير كلمة سر الواي فاي",
    "تغيير كلمة سر الواي فاي",
    "عايز اغير باسورد الواي فاي",
    "باسورد الواي فاي",
    "كلمة سر الواي فاي",
    "wifi password",
}
CONFIRM_WORDS = {"تأكيد", "تاكيد", "أكد", "اكد", "confirm", "yes", "تمام"}
CANCEL_WORDS = {"الغاء", "إلغاء", "cancel", "لا"}


class RouterService:
    def get_or_create_customer(self, db: Session, phone: str) -> Customer:
        clean_phone = radius_connector.clean_phone(phone)
        customer = db.query(Customer).filter(Customer.phone == clean_phone).first()
        if not customer:
            customer = Customer(phone=clean_phone, status=CustomerStatus.NEW.value)
            db.add(customer)
            db.commit()
        return customer

    def get_customer_router(self, db: Session, phone: str) -> RouterDevice | None:
        clean_phone = radius_connector.clean_phone(phone)
        customer = db.query(Customer).filter(Customer.phone == clean_phone).first()
        if customer:
            router = (
                db.query(RouterDevice)
                .filter(RouterDevice.customer_id == customer.id, RouterDevice.enabled == True)
                .order_by(RouterDevice.updated_at.desc())
                .first()
            )
            if router:
                return router

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
        if link:
            router = (
                db.query(RouterDevice)
                .filter(RouterDevice.radius_external_id == link.external_id, RouterDevice.enabled == True)
                .order_by(RouterDevice.updated_at.desc())
                .first()
            )
            if router:
                return router

        snapshot = (
            db.query(RadiusSnapshot)
            .filter(RadiusSnapshot.phone == clean_phone)
            .order_by(RadiusSnapshot.synced_at.desc())
            .first()
        )
        if snapshot:
            return (
                db.query(RouterDevice)
                .filter(RouterDevice.radius_external_id == snapshot.external_id, RouterDevice.enabled == True)
                .order_by(RouterDevice.updated_at.desc())
                .first()
            )
        return None

    async def get_router_for_phone(self, db: Session, phone: str):
        router = self.get_customer_router(db, phone)
        if router:
            return router
        return await router_auto_discovery.discover_router(db, phone)

    def active_pending(self, db: Session, phone: str) -> RouterPendingAction | None:
        now = datetime.now(timezone.utc)
        return (
            db.query(RouterPendingAction)
            .filter(
                RouterPendingAction.phone == radius_connector.clean_phone(phone),
                RouterPendingAction.status.in_(["awaiting_password", "awaiting_confirm"]),
                RouterPendingAction.expires_at > now,
            )
            .order_by(RouterPendingAction.created_at.desc())
            .first()
        )

    def is_wifi_command(self, message: str) -> bool:
        text = self.normalize(message)
        if any(self.normalize(cmd) in text for cmd in WIFI_COMMANDS):
            return True
        has_wifi = any(word in text for word in {"واي فاي", "وايفاي", "wifi", "wi-fi"})
        has_password = any(word in text for word in {"باسورد", "كلمة سر", "كلمه سر", "password"})
        has_change = any(word in text for word in {"غير", "تغيير", "اغير", "تغير", "محتاج", "عايز", "اريد"})
        return has_wifi and has_password and has_change

    async def handle_whatsapp_command(self, db: Session, phone: str, message: str) -> dict[str, Any] | None:
        text = self.normalize(message)
        pending = self.active_pending(db, phone)
        if pending:
            return await self.handle_pending(db, pending, message)
        if not self.is_wifi_command(text):
            return None

        customer = self.get_or_create_customer(db, phone)
        router = await self.get_router_for_phone(db, phone)
        if not router:
            self.log(db, None, customer.id, phone, "change_wifi_password", False, "No router linked")
            return {
                "reply": "لم أتمكن من معرفة راوتر حسابك أو IP الراوتر الحالي تلقائياً. تم تحويل طلب تغيير باسورد الواي فاي للدعم.",
                "intent": "router_not_discovered",
                "handoff_required": True,
                "handoff_reason": "Customer requested WiFi password change but router was not discovered",
            }

        db.query(RouterPendingAction).filter(
            RouterPendingAction.phone == customer.phone,
            RouterPendingAction.status.in_(["awaiting_password", "awaiting_confirm"]),
        ).update({"status": "cancelled"})
        pending = RouterPendingAction(
            customer_id=customer.id,
            router_id=getattr(router, "id", None),
            phone=customer.phone,
            action_type="change_wifi_password",
            status="awaiting_password",
            payload_json={
                "dynamic_router": bool(getattr(router, "dynamic", False)),
                "discovered_host": getattr(router, "host", None),
                "host_source": getattr(router, "host_source", None),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        db.add(pending)
        db.commit()
        return {
            "reply": "تمام. اكتب الباسورد الجديد للواي فاي. لازم يكون 8 حروف أو أكثر وبدون مسافات.\nلو غيرت رأيك اكتب: إلغاء",
            "intent": "router_wifi_password_start",
            "handoff_required": False,
        }

    async def handle_pending(self, db: Session, pending: RouterPendingAction, message: str) -> dict[str, Any]:
        text = self.normalize(message)
        if text in {self.normalize(word) for word in CANCEL_WORDS}:
            pending.status = "cancelled"
            db.commit()
            return {"reply": "تم إلغاء طلب تغيير باسورد الواي فاي.", "intent": "router_wifi_cancelled", "handoff_required": False}

        if pending.status == "awaiting_password":
            new_password = (message or "").strip()
            ok, error = router_connector.validate_wifi_password(new_password)
            if not ok:
                return {"reply": f"{error}\nاكتب باسورد جديد أو اكتب إلغاء.", "intent": "router_wifi_invalid_password", "handoff_required": False}
            payload = pending.payload_json or {}
            payload["new_password"] = new_password
            pending.payload_json = payload
            pending.status = "awaiting_confirm"
            pending.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            db.commit()
            return {
                "reply": "للتأكيد: سيتم تغيير باسورد الواي فاي وقد تحتاج تعيد اتصال كل الأجهزة.\nاكتب: تأكيد\nأو اكتب: إلغاء",
                "intent": "router_wifi_awaiting_confirm",
                "handoff_required": False,
            }

        if pending.status == "awaiting_confirm":
            if text not in {self.normalize(word) for word in CONFIRM_WORDS}:
                return {"reply": "اكتب تأكيد لتنفيذ تغيير الباسورد، أو إلغاء لإلغاء الطلب.", "intent": "router_wifi_confirm_needed", "handoff_required": False}
            router = db.query(RouterDevice).filter(RouterDevice.id == pending.router_id).first() if pending.router_id else None
            if not router:
                router = await self.get_router_for_phone(db, pending.phone)
            new_password = (pending.payload_json or {}).get("new_password")
            result = await router_connector.change_wifi_password(router, new_password)
            if result.get("success"):
                pending.status = "completed"
            elif result.get("manual_required"):
                pending.status = "manual_required"
            else:
                pending.status = "failed"
            if pending.payload_json:
                pending.payload_json = {"password_length": len(new_password or "")}
            if router:
                router.last_status = "ok" if result.get("success") else "error"
                router.last_error = None if result.get("success") else result.get("message")
                router.last_seen_at = datetime.now(timezone.utc) if result.get("success") else router.last_seen_at
            self.log(
                db,
                getattr(router, "id", None) if router else None,
                pending.customer_id,
                pending.phone,
                "change_wifi_password",
                bool(result.get("success")),
                result.get("message"),
                {
                    "manual_required": result.get("manual_required", False),
                    "dynamic_router": bool(getattr(router, "dynamic", False)) if router else False,
                    "host_source": getattr(router, "host_source", None) if router else None,
                },
            )
            db.commit()
            if result.get("success"):
                return {
                    "reply": "تم تغيير باسورد الواي فاي بنجاح. لو الأجهزة فصلت، أعد الاتصال بالباسورد الجديد.",
                    "intent": "router_wifi_changed",
                    "handoff_required": False,
                }
            return {
                "reply": f"لم أتمكن من تغيير الباسورد تلقائياً. تم تحويل الطلب للدعم.\nالسبب: {result.get('message', 'غير معروف')}",
                "intent": "router_wifi_change_failed",
                "handoff_required": True,
                "handoff_reason": "WiFi password change failed or requires manual action",
            }

        return None

    def log(self, db: Session, router_id: str | None, customer_id: str | None, phone: str | None, action: str, success: bool, message: str | None, payload: dict | None = None):
        db.add(RouterActionLog(
            router_id=router_id,
            customer_id=customer_id,
            phone=radius_connector.clean_phone(phone),
            action=action,
            success=success,
            message=message,
            payload=payload or {},
        ))

    def normalize(self, message: str) -> str:
        return (
            (message or "")
            .strip()
            .casefold()
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
            .replace("ى", "ي")
            .replace("ة", "ه")
        )


router_service = RouterService()
