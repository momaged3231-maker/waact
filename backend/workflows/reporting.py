from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.models import Customer, Conversation, Lead, HandoffRequest, Report
from config import config


class ReportManager:
    def generate_daily_report(self, db: Session) -> dict:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._generate_report(db, start, now, "daily")

    def generate_weekly_report(self, db: Session) -> dict:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._generate_report(db, start, now, "weekly")

    def generate_monthly_report(self, db: Session) -> dict:
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self._generate_report(db, start, now, "monthly")

    def _generate_report(self, db: Session, start: datetime, end: datetime, report_type: str) -> dict:
        total_messages = (
            db.query(func.count(Conversation.id))
            .filter(Conversation.created_at >= start, Conversation.created_at <= end)
            .scalar()
            or 0
        )

        inbound_messages = (
            db.query(func.count(Conversation.id))
            .filter(
                Conversation.created_at >= start,
                Conversation.created_at <= end,
                Conversation.direction == "inbound",
            )
            .scalar()
            or 0
        )

        outbound_messages = total_messages - inbound_messages

        new_customers = (
            db.query(func.count(Customer.id))
            .filter(Customer.first_seen_at >= start, Customer.first_seen_at <= end)
            .scalar()
            or 0
        )

        total_customers = db.query(func.count(Customer.id)).scalar() or 0

        returning_customers = (
            db.query(func.count(Customer.id))
            .filter(Customer.total_messages >= 2)
            .scalar()
            or 0
        )

        interested_customers = (
            db.query(func.count(Customer.id))
            .filter(Customer.status.in_(["interested", "needs_follow_up"]))
            .scalar()
            or 0
        )

        handoff_requests = (
            db.query(func.count(HandoffRequest.id))
            .filter(HandoffRequest.created_at >= start, HandoffRequest.created_at <= end)
            .scalar()
            or 0
        )

        top_services = (
            db.query(Conversation.service_interest, func.count(Conversation.id).label("count"))
            .filter(
                Conversation.created_at >= start,
                Conversation.created_at <= end,
                Conversation.service_interest.isnot(None),
            )
            .group_by(Conversation.service_interest)
            .order_by(func.count(Conversation.id).desc())
            .limit(5)
            .all()
        )

        top_intents = (
            db.query(Conversation.intent, func.count(Conversation.id).label("count"))
            .filter(
                Conversation.created_at >= start,
                Conversation.created_at <= end,
                Conversation.intent.isnot(None),
            )
            .group_by(Conversation.intent)
            .order_by(func.count(Conversation.id).desc())
            .limit(5)
            .all()
        )

        total_leads = (
            db.query(func.count(Lead.id))
            .filter(Lead.created_at >= start, Lead.created_at <= end)
            .scalar()
            or 0
        )

        won_leads = (
            db.query(func.count(Lead.id))
            .filter(
                Lead.lead_status == "won",
                Lead.updated_at >= start,
                Lead.updated_at <= end,
            )
            .scalar()
            or 0
        )

        open_handoffs = (
            db.query(func.count(HandoffRequest.id))
            .filter(HandoffRequest.status == "pending")
            .scalar()
            or 0
        )

        auto_reply_rate = (outbound_messages / inbound_messages * 100) if inbound_messages > 0 else 0
        auto_reply_rate = round(auto_reply_rate, 1)

        report_data = {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "report_type": report_type,
            "total_messages": total_messages,
            "inbound_messages": inbound_messages,
            "outbound_messages": outbound_messages,
            "new_customers": new_customers,
            "total_customers": total_customers,
            "returning_customers": returning_customers,
            "interested_customers": interested_customers,
            "handoff_requests": handoff_requests,
            "top_services": [{"service": s[0], "count": s[1]} for s in top_services],
            "top_intents": [{"intent": i[0], "count": i[1]} for i in top_intents],
            "total_leads": total_leads,
            "won_leads": won_leads,
            "open_handoffs": open_handoffs,
            "auto_reply_rate": auto_reply_rate,
        }

        report = Report(
            report_type=report_type,
            report_data=report_data,
            period_start=start,
            period_end=end,
        )
        db.add(report)
        db.commit()

        return report_data

    def get_recent_reports(self, db: Session, limit: int = 10) -> list[Report]:
        return (
            db.query(Report)
            .order_by(Report.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_dashboard_stats(self, db: Session) -> dict:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        messages_today = (
            db.query(func.count(Conversation.id))
            .filter(Conversation.created_at >= today_start)
            .scalar()
            or 0
        )

        new_customers_today = (
            db.query(func.count(Customer.id))
            .filter(Customer.first_seen_at >= today_start)
            .scalar()
            or 0
        )

        active_customers = (
            db.query(func.count(Customer.id))
            .filter(Customer.last_seen_at >= today_start)
            .scalar()
            or 0
        )

        pending_handoffs = (
            db.query(func.count(HandoffRequest.id))
            .filter(HandoffRequest.status == "pending")
            .scalar()
            or 0
        )

        follow_up_needed = (
            db.query(func.count(Customer.id))
            .filter(Customer.status == "needs_follow_up")
            .scalar()
            or 0
        )

        interested = (
            db.query(func.count(Customer.id))
            .filter(Customer.status == "interested")
            .scalar()
            or 0
        )

        return {
            "messages_today": messages_today,
            "new_customers_today": new_customers_today,
            "active_customers": active_customers,
            "pending_handoffs": pending_handoffs,
            "follow_up_needed": follow_up_needed,
            "interested_customers": interested,
            "total_customers": db.query(func.count(Customer.id)).scalar() or 0,
        }


report_manager = ReportManager()
