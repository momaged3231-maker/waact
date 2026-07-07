from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database.models import Customer, Conversation, CustomerStatus, Direction
from rag.knowledge import knowledge_manager
from ai.engine import ai_engine
from ai.memory import memory_manager
from workflows.handoff import handoff_manager


EXPLICIT_HANDOFF_WORDS = {
    "موظف",
    "الدعم",
    "دعم",
    "خدمة العملاء",
    "خدمه العملاء",
    "كلموني",
    "اتصلوا",
    "اتواصل معايا",
    "اتواصل معايه",
    "مندوب",
    "انسان",
    "human",
    "agent",
}


class MessageFlow:
    def process_incoming_message(self, db: Session, phone: str, message_text: str, whatsapp_message_id: str = None) -> dict:
        customer = self._get_or_create_customer(db, phone)
        customer.last_seen_at = datetime.now(timezone.utc)

        conversation = Conversation(
            customer_id=customer.id,
            whatsapp_message_id=whatsapp_message_id,
            direction=Direction.INBOUND.value,
            message_text=message_text,
        )
        db.add(conversation)
        db.commit()

        customer_context = memory_manager.build_customer_context(customer, db)

        if customer.is_handover:
            reply = "شكراً لانتظارك. طلبك قيد المراجعة من قبل فريق الدعم. سنتواصل معك قريباً."
            handoff_response = {
                "reply": reply,
                "intent": "handoff",
                "service_interest": None,
                "needs_follow_up": False,
                "handoff_required": False,
                "handoff_reason": None,
                "lead_status": customer.status,
                "confidence": 1.0,
            }
            conversation.ai_response = reply
            conversation.intent = "handoff"
            db.commit()
            return handoff_response

        rag_results = knowledge_manager.search_knowledge(message_text)
        rag_context = knowledge_manager.format_context(rag_results)

        recent_convs = (
            db.query(Conversation)
            .filter(Conversation.customer_id == customer.id)
            .order_by(Conversation.created_at.desc())
            .limit(5)
            .all()
        )
        recent_convs.reverse()
        history = [
            {"direction": c.direction, "message_text": c.message_text, "ai_response": c.ai_response}
            for c in recent_convs
        ]

        ai_response = ai_engine.generate_response(
            message=message_text,
            customer_memory=customer_context,
            rag_context=rag_context,
            conversation_history=history,
        )

        reply_text = ai_response.get("reply", "")
        conversation.ai_response = reply_text
        conversation.intent = ai_response.get("intent", "other")
        conversation.service_interest = ai_response.get("service_interest")
        conversation.confidence = ai_response.get("confidence", 0.5)
        conversation.handoff_required = ai_response.get("handoff_required", False)
        conversation.needs_follow_up = ai_response.get("needs_follow_up", False)
        db.commit()

        memory_manager.update_memory(db, customer, conversation, ai_response)

        if ai_response.get("handoff_required", False):
            handoff_manager.create_handoff_request(
                db=db,
                customer=customer,
                reason=ai_response.get("handoff_reason", "طلب العميل التحدث مع موظف"),
                conversation_summary=customer.memory_summary,
                pause_auto_reply=self._should_pause_auto_reply(message_text, ai_response),
            )

        return ai_response

    def _should_pause_auto_reply(self, message_text: str, ai_response: dict) -> bool:
        if ai_response.get("pause_auto_reply") is True:
            return True
        text = (
            (message_text or "")
            .strip()
            .casefold()
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا")
            .replace("ى", "ي")
            .replace("ة", "ه")
        )
        return any(word in text for word in EXPLICIT_HANDOFF_WORDS)

    def send_outbound_message(self, db: Session, customer_id: str, message_text: str, intent: str = None) -> Conversation:
        conversation = Conversation(
            customer_id=customer_id,
            direction=Direction.OUTBOUND.value,
            message_text=message_text,
            intent=intent or "follow_up",
        )
        db.add(conversation)
        db.commit()
        return conversation

    def _get_or_create_customer(self, db: Session, phone: str) -> Customer:
        from database.models import Customer
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            customer = Customer(
                phone=phone,
                status=CustomerStatus.NEW.value,
            )
            db.add(customer)
            db.commit()
        return customer


message_flow = MessageFlow()
