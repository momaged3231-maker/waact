from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database.models import Customer, HandoffRequest, HandoffStatus


class HandoffManager:
    def create_handoff_request(
        self,
        db: Session,
        customer: Customer,
        reason: str,
        conversation_summary: str = None,
        pause_auto_reply: bool = True,
    ) -> HandoffRequest:
        if pause_auto_reply:
            customer.is_handover = True

        handoff = HandoffRequest(
            customer_id=customer.id,
            reason=reason,
            status=HandoffStatus.PENDING.value,
            conversation_summary=conversation_summary,
        )
        db.add(handoff)
        db.commit()
        return handoff

    def accept_handoff(self, db: Session, handoff_id: str, assigned_to: str) -> bool:
        handoff = db.query(HandoffRequest).filter(HandoffRequest.id == handoff_id).first()
        if not handoff:
            return False
        handoff.status = HandoffStatus.ACCEPTED.value
        handoff.assigned_to = assigned_to
        db.commit()
        return True

    def resolve_handoff(self, db: Session, handoff_id: str) -> bool:
        handoff = db.query(HandoffRequest).filter(HandoffRequest.id == handoff_id).first()
        if not handoff:
            return False
        handoff.status = HandoffStatus.RESOLVED.value
        handoff.resolved_at = datetime.now(timezone.utc)
        customer = db.query(Customer).filter(Customer.id == handoff.customer_id).first()
        if customer:
            customer.is_handover = False
        db.commit()
        return True

    def get_pending_handoffs(self, db: Session) -> list[HandoffRequest]:
        return (
            db.query(HandoffRequest)
            .filter(HandoffRequest.status == HandoffStatus.PENDING.value)
            .order_by(HandoffRequest.created_at.asc())
            .all()
        )

    def get_customer_handoffs(self, db: Session, customer_id: str) -> list[HandoffRequest]:
        return (
            db.query(HandoffRequest)
            .filter(HandoffRequest.customer_id == customer_id)
            .order_by(HandoffRequest.created_at.desc())
            .all()
        )


handoff_manager = HandoffManager()
