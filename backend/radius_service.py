from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from database.models import Customer, CustomerStatus, RadiusEvent, RadiusSnapshot, RadiusSubscriberLink
from radius import format_radius_status_ar, radius_connector


RADIUS_STATUS_COMMANDS = {
    "حالة الاشتراك",
    "حاله الاشتراك",
    "حالة الحساب",
    "حاله الحساب",
    "اشتراكي",
    "اشتراك",
    "موعد التجديد",
    "الباقة",
    "الباقه",
}
RADIUS_PROBLEM_COMMANDS = {
    "النت مش شغال",
    "الانترنت مش شغال",
    "النت واقع",
    "مفيش نت",
    "مش شغال النت",
}
RADIUS_RENEW_COMMANDS = {"جدد", "تجديد", "عايز اجدد", "اريد التجديد"}


class RadiusService:
    async def lookup_by_phone(self, db: Session, phone: str) -> dict[str, Any]:
        clean_phone = radius_connector.clean_phone(phone)
        customer = db.query(Customer).filter(Customer.phone == clean_phone).first()
        if customer:
            link = db.query(RadiusSubscriberLink).filter(RadiusSubscriberLink.customer_id == customer.id).first()
            if link:
                snapshot = await self.refresh_snapshot(db, link.external_id, customer.id)
                return {"linked": True, "customer": customer, "snapshot": snapshot, "candidates": []}

        candidates = await radius_connector.search_subscribers(clean_phone, limit=5)
        exact = [item for item in candidates if item.get("phone") and clean_phone.endswith(item["phone"][-10:])]
        if customer and len(exact) == 1:
            link = self.link_customer(db, customer, exact[0])
            snapshot = self.upsert_snapshot(db, exact[0], customer.id)
            return {"linked": True, "customer": customer, "snapshot": snapshot, "candidates": []}
        return {"linked": False, "customer": customer, "snapshot": None, "candidates": candidates}

    async def lookup_by_query(self, db: Session, query: str) -> list[dict[str, Any]]:
        return await radius_connector.search_subscribers(query, limit=25)

    async def refresh_snapshot(self, db: Session, external_id: str, customer_id: str | None = None) -> RadiusSnapshot:
        subscriber = await radius_connector.get_subscriber(external_id)
        return self.upsert_snapshot(db, subscriber, customer_id)

    def link_customer(self, db: Session, customer: Customer, subscriber: dict[str, Any]) -> RadiusSubscriberLink:
        external_id = subscriber.get("external_id") or subscriber.get("username")
        if not external_id:
            raise RuntimeError("Radius subscriber external_id is missing")
        link = db.query(RadiusSubscriberLink).filter(RadiusSubscriberLink.external_id == str(external_id)).first()
        if not link:
            link = RadiusSubscriberLink(external_id=str(external_id))
            db.add(link)
        link.customer_id = customer.id
        link.username = subscriber.get("username") or str(external_id)
        link.phone = subscriber.get("phone") or customer.phone
        link.source = "manual_or_auto"
        db.commit()
        return link

    def link_customer_by_phone(self, db: Session, phone: str, subscriber: dict[str, Any]) -> RadiusSubscriberLink:
        clean_phone = radius_connector.clean_phone(phone)
        customer = db.query(Customer).filter(Customer.phone == clean_phone).first()
        if not customer:
            customer = Customer(phone=clean_phone, status=CustomerStatus.NEW.value)
            db.add(customer)
            db.commit()
        return self.link_customer(db, customer, subscriber)

    def upsert_snapshot(self, db: Session, subscriber: dict[str, Any], customer_id: str | None = None) -> RadiusSnapshot:
        external_id = str(subscriber.get("external_id") or subscriber.get("username") or "").strip()
        if not external_id:
            raise RuntimeError("Radius subscriber external_id is missing")
        snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.external_id == external_id).first()
        if not snapshot:
            snapshot = RadiusSnapshot(external_id=external_id)
            db.add(snapshot)
        snapshot.customer_id = customer_id or snapshot.customer_id
        snapshot.username = subscriber.get("username") or external_id
        snapshot.phone = subscriber.get("phone") or snapshot.phone
        snapshot.status = subscriber.get("status") or "unknown"
        snapshot.package_name = subscriber.get("package")
        snapshot.expires_at = subscriber.get("expires_at")
        snapshot.online = bool(subscriber.get("online"))
        snapshot.last_seen_at = subscriber.get("last_seen_at")
        snapshot.balance = subscriber.get("balance")
        snapshot.ip_address = subscriber.get("ip_address")
        snapshot.reseller = subscriber.get("reseller")
        snapshot.download_rate = subscriber.get("download_rate")
        snapshot.upload_rate = subscriber.get("upload_rate")
        snapshot.traffic_used = subscriber.get("traffic_used")
        snapshot.raw_json = subscriber.get("raw") or subscriber
        snapshot.synced_at = datetime.now(timezone.utc)
        db.commit()
        return snapshot

    def get_snapshot_for_phone(self, db: Session, phone: str) -> RadiusSnapshot | None:
        clean_phone = radius_connector.clean_phone(phone)
        customer = db.query(Customer).filter(Customer.phone == clean_phone).first()
        if customer:
            snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.customer_id == customer.id).first()
            if snapshot:
                return snapshot
        return db.query(RadiusSnapshot).filter(RadiusSnapshot.phone == clean_phone).first()

    def is_radius_command(self, message: str) -> bool:
        text = self.normalize_message(message)
        return any(cmd in text for cmd in RADIUS_STATUS_COMMANDS | RADIUS_PROBLEM_COMMANDS | RADIUS_RENEW_COMMANDS)

    async def handle_whatsapp_command(self, db: Session, phone: str, message: str) -> dict[str, Any] | None:
        text = self.normalize_message(message)
        if not self.is_radius_command(text):
            return None

        lookup = None
        snapshot = None
        candidates = []
        try:
            lookup = await self.lookup_by_phone(db, phone)
            snapshot = lookup.get("snapshot")
            candidates = lookup.get("candidates", [])
        except Exception as exc:
            return {
                "reply": f"خدمة الاستعلام عن الاشتراك غير متاحة حالياً. سيتم تحويل طلبك للدعم.\nسبب الخطأ: {str(exc)[:120]}",
                "intent": "radius_error",
                "handoff_required": True,
                "handoff_reason": "Radius lookup failed",
            }

        if not snapshot and candidates:
            return {
                "reply": "وجدت أكثر من حساب محتمل. من فضلك ابعت اسم المستخدم أو رقم الاشتراك عشان أربطه بالواتساب.",
                "intent": "radius_needs_identity",
                "handoff_required": False,
            }

        if not snapshot:
            return {
                "reply": "لم أجد اشتراك مربوط برقمك. ابعت اسم المستخدم أو رقم الاشتراك وسنربطه لك.",
                "intent": "radius_not_linked",
                "handoff_required": False,
            }

        if any(cmd in text for cmd in RADIUS_PROBLEM_COMMANDS):
            return self.internet_problem_reply(snapshot)
        if any(cmd in text for cmd in RADIUS_RENEW_COMMANDS):
            return self.renewal_reply(snapshot)
        return self.status_reply(snapshot)

    def status_reply(self, snapshot: RadiusSnapshot) -> dict[str, Any]:
        return {
            "reply": f"بيانات اشتراكك:\n{format_radius_status_ar(snapshot)}\n\nلو عندك مشكلة اكتب: النت مش شغال",
            "intent": "radius_status",
            "handoff_required": False,
        }

    def internet_problem_reply(self, snapshot: RadiusSnapshot) -> dict[str, Any]:
        if snapshot.status == "expired":
            return {
                "reply": f"اشتراكك منتهي.\n{format_radius_status_ar(snapshot)}\n\nللتجديد ابعت: جدد",
                "intent": "radius_expired_support",
                "handoff_required": False,
            }
        if snapshot.status == "disabled":
            return {
                "reply": "حسابك موقوف حالياً. تم تحويل طلبك للدعم لمراجعته.",
                "intent": "radius_disabled_support",
                "handoff_required": True,
                "handoff_reason": "Radius account disabled",
            }
        if not snapshot.online:
            return {
                "reply": "اشتراكك يبدو نشطاً، لكن لا توجد جلسة اتصال حالياً. جرّب فصل الراوتر 30 ثانية وتشغيله. لو المشكلة مستمرة اكتب: الدعم",
                "intent": "radius_offline_support",
                "handoff_required": False,
            }
        return {
            "reply": "اشتراكك نشط ويوجد اتصال حالياً. لو المشكلة مستمرة ابعت تفاصيل المشكلة أو اكتب: الدعم لتحويلك لموظف.",
            "intent": "radius_online_support",
            "handoff_required": False,
        }

    def renewal_reply(self, snapshot: RadiusSnapshot) -> dict[str, Any]:
        expires = snapshot.expires_at.strftime("%Y-%m-%d") if snapshot.expires_at else "غير محدد"
        return {
            "reply": f"طلب التجديد وصل.\nاسم المستخدم: {snapshot.username}\nالباقة: {snapshot.package_name or 'غير محددة'}\nتاريخ الانتهاء: {expires}\nسيتم التواصل معك بخطوات الدفع أو التجديد.",
            "intent": "radius_renewal_request",
            "handoff_required": True,
            "handoff_reason": "Customer requested Radius renewal",
        }

    def normalize_message(self, message: str) -> str:
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

    def due_expiry_snapshots(self, db: Session, days: int) -> list[RadiusSnapshot]:
        start = datetime.now(timezone.utc) + timedelta(days=days)
        end = start + timedelta(days=1)
        return (
            db.query(RadiusSnapshot)
            .filter(
                RadiusSnapshot.expires_at >= start,
                RadiusSnapshot.expires_at < end,
                RadiusSnapshot.phone != None,
            )
            .all()
        )

    def event_exists_today(self, db: Session, external_id: str, event_type: str) -> bool:
        since = datetime.now(timezone.utc) - timedelta(hours=20)
        return db.query(RadiusEvent).filter(
            RadiusEvent.external_id == external_id,
            RadiusEvent.event_type == event_type,
            RadiusEvent.created_at >= since,
        ).first() is not None

    def log_event(self, db: Session, external_id: str, event_type: str, phone: str | None = None, payload: dict | None = None):
        db.add(RadiusEvent(external_id=external_id, event_type=event_type, phone=phone, payload=payload or {}))
        db.commit()


radius_service = RadiusService()
