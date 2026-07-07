from datetime import datetime, timedelta, timezone

from database.models import AutomationRule, AutomationLog, FollowUpTask, ChatMeta, HandoffRequest
from whatsapp.connector import whatsapp_connector


class AutomationEngine:
    async def run(self, db, trigger: str, context: dict):
        rules = (
            db.query(AutomationRule)
            .filter(AutomationRule.enabled == True, AutomationRule.trigger == trigger)
            .order_by(AutomationRule.priority.asc(), AutomationRule.created_at.asc())
            .all()
        )
        for rule in rules:
            if self.in_cooldown(rule):
                self.log(db, rule, trigger, False, True, context, "cooldown")
                continue
            if not self.matches(rule, context):
                self.log(db, rule, trigger, False, True, context, "condition_not_matched")
                continue
            try:
                await self.execute(db, rule, context)
                rule.last_run_at = datetime.now(timezone.utc)
                self.log(db, rule, trigger, True, False, context, "executed")
            except Exception as exc:
                self.log(db, rule, trigger, False, False, context, str(exc)[:500])
            db.commit()

    def in_cooldown(self, rule: AutomationRule) -> bool:
        if not rule.last_run_at or not rule.cooldown_minutes:
            return False
        last_run_at = rule.last_run_at
        if last_run_at.tzinfo is None:
            last_run_at = last_run_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_run_at < timedelta(minutes=rule.cooldown_minutes)

    def matches(self, rule: AutomationRule, context: dict) -> bool:
        value = (rule.condition_value or "").strip().lower()
        if rule.condition_type == "always":
            return True
        if rule.condition_type == "message_contains":
            return value and value in (context.get("message_text") or "").lower()
        if rule.condition_type == "customer_status":
            customer = context.get("customer")
            return bool(customer and customer.status == value)
        if rule.condition_type == "intent":
            return (context.get("intent") or "").lower() == value
        return False

    async def execute(self, db, rule: AutomationRule, context: dict):
        payload = rule.action_payload or {}
        customer = context.get("customer")
        chat_id = context.get("chat_id")

        if rule.action_type == "send_message":
            if not customer:
                raise RuntimeError("customer required for send_message")
            message = payload.get("message") or ""
            if not message.strip():
                raise RuntimeError("message is empty")
            ok = await whatsapp_connector.send_message(phone=customer.phone, message=message)
            if not ok:
                raise RuntimeError("send failed")
            return

        if rule.action_type == "create_task":
            if not customer:
                raise RuntimeError("customer required for create_task")
            db.add(FollowUpTask(
                customer_id=customer.id,
                lead_id=getattr(customer.lead, "id", None),
                title=payload.get("title") or "متابعة تلقائية",
                description=payload.get("description"),
                priority=payload.get("priority") or "medium",
                assigned_to=payload.get("assigned_to"),
                due_at=datetime.now(timezone.utc) + timedelta(minutes=int(payload.get("due_in_minutes", 1440))),
            ))
            return

        if rule.action_type == "set_customer_status":
            if not customer:
                raise RuntimeError("customer required for set_customer_status")
            customer.status = payload.get("status") or customer.status
            return

        if rule.action_type == "add_tag":
            tag = (payload.get("tag") or "").strip()
            if not chat_id or not tag:
                raise RuntimeError("chat_id and tag required")
            meta = db.query(ChatMeta).filter(ChatMeta.chat_id == chat_id).first()
            if not meta:
                meta = ChatMeta(chat_id=chat_id)
                db.add(meta)
            tags = [t.strip() for t in (meta.tags or "").split(",") if t.strip()]
            if tag not in tags:
                tags.append(tag)
            meta.tags = ", ".join(tags)
            return

        if rule.action_type == "handoff":
            if not customer:
                raise RuntimeError("customer required for handoff")
            customer.is_handover = True
            db.add(HandoffRequest(
                customer_id=customer.id,
                reason=payload.get("reason") or "Automation handoff",
                conversation_summary=payload.get("summary"),
            ))
            return

        raise RuntimeError(f"unknown action: {rule.action_type}")

    def log(self, db, rule, trigger, success, skipped, context, message):
        db.add(AutomationLog(
            rule_id=rule.id,
            trigger=trigger,
            success=success,
            skipped=skipped,
            entity_type="customer" if context.get("customer") else "chat",
            entity_id=getattr(context.get("customer"), "id", None) or context.get("chat_id"),
            message=message,
        ))


automation_engine = AutomationEngine()
