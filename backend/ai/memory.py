import json
import re
from datetime import datetime
from sqlalchemy.orm import Session
from openai import OpenAI
from config import config
from ai.prompts import MEMORY_UPDATE_PROMPT
from database.models import Customer, Lead, Conversation


class MemoryManager:
    def __init__(self):
        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL

    def build_customer_context(self, customer: Customer, db: Session) -> dict:
        if not customer:
            return {
                "name": None,
                "status": "new",
                "interested_service": None,
                "last_intent": None,
                "memory_summary": None,
                "is_handover": False,
                "message_count": 0,
                "last_seen_at": None,
            }

        msg_count = (
            db.query(Conversation)
            .filter(Conversation.customer_id == customer.id)
            .count()
        )

        return {
            "name": customer.name,
            "status": customer.status,
            "interested_service": customer.interested_service,
            "last_intent": customer.last_intent,
            "memory_summary": customer.memory_summary,
            "is_handover": customer.is_handover,
            "message_count": msg_count,
            "last_seen_at": customer.last_seen_at.isoformat() if customer.last_seen_at else None,
        }

    def update_memory(
        self,
        db: Session,
        customer: Customer,
        conversation: Conversation,
        ai_response: dict,
    ) -> dict:
        recent_convs = (
            db.query(Conversation)
            .filter(Conversation.customer_id == customer.id)
            .order_by(Conversation.created_at.desc())
            .limit(5)
            .all()
        )
        recent_convs.reverse()

        conversation_text = ""
        for conv in recent_convs:
            direction = "العميل" if conv.direction == "inbound" else "البوت"
            text = conv.message_text if conv.direction == "inbound" else (conv.ai_response or "")
            conversation_text += f"{direction}: {text}\n"

        prompt = MEMORY_UPDATE_PROMPT.format(conversation_text=conversation_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.1,
                max_tokens=400,
            )
            content = response.choices[0].message.content
            analysis = self._parse_memory_update(content)
        except Exception:
            analysis = {
                "memory_summary": conversation.message_text[:200] if conversation.message_text else "",
                "intent": ai_response.get("intent", "other"),
                "service_interest": ai_response.get("service_interest"),
                "customer_status": ai_response.get("lead_status", "new"),
                "needs_follow_up": ai_response.get("needs_follow_up", False),
                "handoff_required": ai_response.get("handoff_required", False),
                "handoff_reason": ai_response.get("handoff_reason"),
                "extracted_name": None,
                "lead_status": "new",
                "priority": "medium",
                "follow_up_reason": None,
                "important_notes": None,
            }

        customer.memory_summary = analysis.get("memory_summary", customer.memory_summary)
        customer.last_intent = analysis.get("intent", ai_response.get("intent", "other"))
        customer.status = analysis.get("customer_status", customer.status)

        if analysis.get("service_interest"):
            customer.interested_service = analysis["service_interest"]

        if analysis.get("extracted_name") and not customer.name:
            customer.name = analysis["extracted_name"]

        customer.total_messages = (customer.total_messages or 0) + 1

        lead = db.query(Lead).filter(Lead.customer_id == customer.id).first()
        if not lead and analysis.get("lead_status"):
            lead = Lead(
                customer_id=customer.id,
                service_interest=analysis.get("service_interest", ai_response.get("service_interest")),
                lead_status=analysis.get("lead_status", "new"),
                priority=analysis.get("priority", "medium"),
            )
            db.add(lead)
        elif lead:
            if analysis.get("lead_status"):
                lead.lead_status = analysis["lead_status"]
            if analysis.get("service_interest"):
                lead.service_interest = analysis["service_interest"]
            if analysis.get("priority"):
                lead.priority = analysis["priority"]

        db.commit()
        return analysis

    def _parse_memory_update(self, content: str) -> dict:
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {
            "memory_summary": content[:200],
            "intent": "other",
            "service_interest": None,
            "customer_status": "new",
            "needs_follow_up": False,
            "handoff_required": False,
            "handoff_reason": None,
            "extracted_name": None,
            "lead_status": "new",
            "priority": "medium",
            "follow_up_reason": None,
            "important_notes": None,
        }


memory_manager = MemoryManager()
