from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, Integer
from datetime import datetime, timedelta, timezone
import os
import json
import csv
import io
import shutil
import sqlite3
import tempfile
from pathlib import Path

from database.db import engine, get_db, init_db
from database.models import (
    Customer,
    Conversation,
    Lead,
    KnowledgeDocument,
    HandoffRequest,
    Report,
    FollowUpTask,
    AIUsageLog,
    Campaign,
    CampaignRecipient,
    OptOut,
    RadiusSubscriberLink,
    RadiusSnapshot,
    RadiusSyncLog,
    RadiusEvent,
    RouterDevice,
    RouterActionLog,
    RouterPendingAction,
    User,
    AuditLog,
    AutomationRule,
    AutomationLog,
    ExternalWebhook,
)
from config import config
from auth import get_current_user, has_role, hash_password, log_audit
from workflows.reporting import report_manager
from workflows.handoff import handoff_manager
from rag.knowledge import knowledge_manager
from whatsapp.connector import whatsapp_connector
from ai.providers import ai_provider_manager
from integrations import integration_manager
from radius import radius_connector
from radius_service import radius_service
from router_discovery import router_auto_discovery
from router_management import router_connector
from router_service import router_service

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["app_version"] = config.APP_VERSION
templates.env.globals["app_release"] = config.APP_RELEASE
templates.env.globals["prd_version"] = config.PRD_VERSION
templates.env.globals["app_mode"] = config.APP_MODE

PIPELINE_STAGES = [
    ("new", "جديد"),
    ("contacted", "تم التواصل"),
    ("qualified", "مؤهل"),
    ("proposal", "عرض سعر"),
    ("negotiation", "تفاوض"),
    ("won", "تم البيع"),
    ("lost", "خسارة"),
]


def parse_datetime(value: str | None):
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_future(value: datetime | None) -> bool:
    if not value:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > datetime.now(timezone.utc)


def customers_for_segment(db: Session, segment: str):
    if segment and segment.startswith("radius_"):
        now = datetime.now(timezone.utc)
        query = db.query(RadiusSnapshot).join(Customer, RadiusSnapshot.customer_id == Customer.id).filter(
            Customer.phone.notin_(db.query(OptOut.phone)),
            RadiusSnapshot.customer_id != None,
        )
        if segment == "radius_expired":
            query = query.filter(RadiusSnapshot.status == "expired")
        elif segment == "radius_expiring_3d":
            query = query.filter(
                RadiusSnapshot.status == "active",
                RadiusSnapshot.expires_at >= now,
                RadiusSnapshot.expires_at <= now + timedelta(days=3),
            )
        elif segment == "radius_active":
            query = query.filter(RadiusSnapshot.status == "active")
        elif segment == "radius_offline":
            query = query.filter(RadiusSnapshot.status == "active", RadiusSnapshot.online == False)
        return [snapshot.customer for snapshot in query.order_by(RadiusSnapshot.expires_at.asc()).limit(500).all() if snapshot.customer]

    query = db.query(Customer).filter(Customer.phone.notin_(db.query(OptOut.phone)))
    if segment and segment != "all":
        query = query.filter(Customer.status == segment)
    return query.order_by(Customer.last_seen_at.desc()).limit(500).all()


def render_campaign_message(campaign: Campaign, recipient: CampaignRecipient) -> str:
    customer = recipient.customer
    replacements = {
        "name": (customer.name if customer and customer.name else "عميلنا"),
        "phone": recipient.phone,
        "status": (customer.status if customer else ""),
        "service": (customer.interested_service if customer and customer.interested_service else ""),
    }
    message = campaign.message or ""
    for key, value in replacements.items():
        message = message.replace("{" + key + "}", str(value or ""))
    return message


def require_min_role(request: Request, db: Session, role: str):
    if not config.AUTH_ENABLED:
        return None
    user = get_current_user(request, db)
    if not has_role(user, role):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


def safe_redirect_url(value: str | None, fallback: str) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


async def extract_upload_text(file: UploadFile) -> str:
    filename = (file.filename or "").lower()
    data = await file.read()

    if filename.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF extraction requires pypdf or readable PDF: {e}")

    if filename.endswith(".docx"):
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"DOCX extraction requires python-docx: {e}")

    raise HTTPException(status_code=400, detail="Supported files: .txt, .md, .csv, .pdf, .docx")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
async def dashboard_index(request: Request, db: Session = Depends(get_db)):
    stats = report_manager.get_dashboard_stats(db)
    recent_convs = (
        db.query(Conversation)
        .order_by(Conversation.created_at.desc())
        .limit(10)
        .all()
    )
    pending_handoffs = handoff_manager.get_pending_handoffs(db)
    latest_report = (
        db.query(Report)
        .filter(Report.report_type == "daily")
        .order_by(Report.created_at.desc())
        .first()
    )
    today_report = latest_report.report_data if latest_report else {}

    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": stats,
        "recent_conversations": recent_convs,
        "pending_handoffs": pending_handoffs,
        "today_report": today_report,
    })


@router.get("/conversations", response_class=HTMLResponse)
async def conversations_page(
    request: Request,
    page: int = 1,
    customer_id: str = None,
    db: Session = Depends(get_db),
):
    per_page = 50
    query = db.query(Conversation).order_by(Conversation.created_at.desc())
    if customer_id:
        query = query.filter(Conversation.customer_id == customer_id)

    total = query.count()
    offset = (page - 1) * per_page
    conversations = query.offset(offset).limit(per_page).all()

    customers = db.query(Customer).order_by(Customer.last_seen_at.desc()).limit(100).all()

    return templates.TemplateResponse("conversations.html", {
        "request": request,
        "conversations": conversations,
        "customers": customers,
        "selected_customer_id": customer_id,
        "page": page,
        "total_pages": (total // per_page) + 1,
        "total": total,
    })


@router.get("/customers", response_class=HTMLResponse)
async def customers_page(
    request: Request,
    status: str = None,
    search: str = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    per_page = 50
    query = db.query(Customer).order_by(Customer.last_seen_at.desc())

    if status:
        query = query.filter(Customer.status == status)
    if search:
        query = query.filter(
            Customer.phone.contains(search) | Customer.name.contains(search)
        )

    total = query.count()
    offset = (page - 1) * per_page
    customers = query.offset(offset).limit(per_page).all()

    status_counts = (
        db.query(Customer.status, func.count(Customer.id))
        .group_by(Customer.status)
        .all()
    )

    return templates.TemplateResponse("customers.html", {
        "request": request,
        "customers": customers,
        "status_counts": dict(status_counts),
        "current_status": status,
        "search": search,
        "page": page,
        "total_pages": (total // per_page) + 1,
        "total": total,
    })


@router.get("/customer/{customer_id}", response_class=HTMLResponse)
async def customer_detail(request: Request, customer_id: str, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.customer_id == customer_id)
        .order_by(Conversation.created_at.desc())
        .limit(100)
        .all()
    )
    lead = db.query(Lead).filter(Lead.customer_id == customer_id).first()
    handoffs = handoff_manager.get_customer_handoffs(db, customer_id)

    return templates.TemplateResponse("customer_detail.html", {
        "request": request,
        "customer": customer,
        "conversations": conversations,
        "lead": lead,
        "handoffs": handoffs,
    })


@router.post("/customer/{customer_id}/handover/clear")
async def clear_customer_handover(customer_id: str, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.is_handover = False
    db.commit()
    return RedirectResponse(url=f"/customer/{customer_id}", status_code=303)


@router.post("/customer/{customer_id}/handover/pause")
async def pause_customer_handover(customer_id: str, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    customer.is_handover = True
    db.commit()
    return RedirectResponse(url=f"/customer/{customer_id}", status_code=303)


@router.get("/leads", response_class=HTMLResponse)
async def leads_page(
    request: Request,
    status: str = None,
    priority: str = None,
    db: Session = Depends(get_db),
):
    query = db.query(Lead).order_by(Lead.updated_at.desc())
    if status:
        query = query.filter(Lead.lead_status == status)
    if priority:
        query = query.filter(Lead.priority == priority)

    leads = query.all()

    status_counts = (
        db.query(Lead.lead_status, func.count(Lead.id))
        .group_by(Lead.lead_status)
        .all()
    )

    return templates.TemplateResponse("leads.html", {
        "request": request,
        "leads": leads,
        "status_counts": dict(status_counts),
        "current_status": status,
        "current_priority": priority,
    })


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_page(request: Request, db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.updated_at.desc()).all()
    grouped = {stage: [] for stage, _ in PIPELINE_STAGES}
    for lead in leads:
        grouped.setdefault(lead.lead_status or "new", []).append(lead)

    return templates.TemplateResponse("pipeline.html", {
        "request": request,
        "stages": PIPELINE_STAGES,
        "grouped": grouped,
        "total_value": sum(float(lead.estimated_value or 0) for lead in leads),
        "total_leads": len(leads),
    })


@router.post("/pipeline/leads/{lead_id}/status")
async def update_lead_status(lead_id: str, status: str = Form(...), db: Session = Depends(get_db)):
    allowed = {stage for stage, _ in PIPELINE_STAGES}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.lead_status = status
    if lead.customer:
        if status == "won":
            lead.customer.status = "sold"
        elif status == "lost":
            lead.customer.status = "not_interested"
        elif status in {"qualified", "proposal", "negotiation"}:
            lead.customer.status = "interested"
    db.commit()
    return {"success": True, "lead_id": lead_id, "status": status}


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    status: str = "pending",
    db: Session = Depends(get_db),
):
    query = db.query(FollowUpTask).order_by(
        FollowUpTask.due_at.is_(None),
        FollowUpTask.due_at.asc(),
        FollowUpTask.created_at.desc(),
    )
    if status:
        query = query.filter(FollowUpTask.status == status)
    tasks = query.all()
    customers = db.query(Customer).order_by(Customer.last_seen_at.desc()).limit(200).all()
    leads = db.query(Lead).order_by(Lead.updated_at.desc()).limit(200).all()

    counts = dict(db.query(FollowUpTask.status, func.count(FollowUpTask.id)).group_by(FollowUpTask.status).all())
    today = datetime.now(timezone.utc).date()
    overdue_count = sum(1 for task in tasks if task.due_at and task.due_at.date() < today and task.status == "pending")

    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "tasks": tasks,
        "customers": customers,
        "leads": leads,
        "counts": counts,
        "current_status": status,
        "overdue_count": overdue_count,
    })


@router.post("/tasks/create")
async def create_task(
    customer_id: str = Form(...),
    lead_id: str = Form(None),
    title: str = Form(...),
    description: str = Form(None),
    due_at: str = Form(None),
    assigned_to: str = Form(None),
    priority: str = Form("medium"),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    task = FollowUpTask(
        customer_id=customer_id,
        lead_id=lead_id or None,
        title=title.strip(),
        description=(description or "").strip() or None,
        due_at=parse_datetime(due_at),
        assigned_to=(assigned_to or "").strip() or None,
        priority=priority,
    )
    db.add(task)

    lead = db.query(Lead).filter(Lead.id == lead_id).first() if lead_id else None
    if lead and task.due_at:
        lead.next_follow_up_at = task.due_at
    customer.status = "needs_follow_up"
    db.commit()
    return RedirectResponse(url="/tasks", status_code=303)


@router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, return_to: str = Form(None), db: Session = Depends(get_db)):
    task = db.query(FollowUpTask).filter(FollowUpTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse(url=safe_redirect_url(return_to, "/tasks"), status_code=303)


@router.post("/tasks/{task_id}/snooze")
async def snooze_task(task_id: str, days: int = Form(1), db: Session = Depends(get_db)):
    task = db.query(FollowUpTask).filter(FollowUpTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    base = task.due_at or datetime.now(timezone.utc)
    task.due_at = base + timedelta(days=days)
    task.status = "pending"
    if task.lead:
        task.lead.next_follow_up_at = task.due_at
    db.commit()
    return RedirectResponse(url="/tasks", status_code=303)


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request, db: Session = Depends(get_db)):
    campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
    active_customers = db.query(Customer).filter(Customer.phone.notin_(db.query(OptOut.phone)))
    now = datetime.now(timezone.utc)
    segments = {
        "all": active_customers.count(),
        "new": active_customers.filter(Customer.status == "new").count(),
        "interested": active_customers.filter(Customer.status == "interested").count(),
        "needs_follow_up": active_customers.filter(Customer.status == "needs_follow_up").count(),
        "sold": active_customers.filter(Customer.status == "sold").count(),
        "radius_expired": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "expired", RadiusSnapshot.customer_id != None).count(),
        "radius_expiring_3d": db.query(RadiusSnapshot).filter(
            RadiusSnapshot.status == "active",
            RadiusSnapshot.expires_at >= now,
            RadiusSnapshot.expires_at <= now + timedelta(days=3),
            RadiusSnapshot.customer_id != None,
        ).count(),
        "radius_active": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "active", RadiusSnapshot.customer_id != None).count(),
        "radius_offline": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "active", RadiusSnapshot.online == False, RadiusSnapshot.customer_id != None).count(),
    }
    return templates.TemplateResponse("campaigns.html", {
        "request": request,
        "campaigns": campaigns,
        "segments": segments,
        "opt_out_count": db.query(OptOut).count(),
        "due_campaign_ids": {campaign.id for campaign in campaigns if not is_future(campaign.scheduled_at)},
    })


@router.post("/campaigns/create")
async def create_campaign(
    name: str = Form(...),
    segment: str = Form("all"),
    message: str = Form(...),
    scheduled_at: str = Form(None),
    db: Session = Depends(get_db),
):
    customers = customers_for_segment(db, segment)
    scheduled = parse_datetime(scheduled_at)
    campaign = Campaign(
        name=name.strip(),
        segment=segment,
        message=message.strip(),
        total_recipients=len(customers),
        scheduled_at=scheduled,
        status="scheduled" if is_future(scheduled) else "draft",
    )
    db.add(campaign)
    db.commit()

    for customer in customers:
        db.add(CampaignRecipient(
            campaign_id=campaign.id,
            customer_id=customer.id,
            phone=customer.phone,
        ))
    db.commit()
    return RedirectResponse(url="/campaigns", status_code=303)


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    batch_size: int = Form(50),
    db: Session = Depends(get_db),
):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if is_future(campaign.scheduled_at):
        campaign.status = "scheduled"
        db.commit()
        return RedirectResponse(url="/campaigns", status_code=303)

    batch_size = max(1, min(batch_size, 100))

    recipients = (
        db.query(CampaignRecipient)
        .filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.status == "pending",
        )
        .limit(batch_size)
        .all()
    )

    campaign.status = "sending"
    campaign.started_at = campaign.started_at or datetime.now(timezone.utc)
    db.commit()

    for recipient in recipients:
        if db.query(OptOut).filter(OptOut.phone == recipient.phone).first():
            recipient.status = "opted_out"
            recipient.error = "Customer opted out"
            db.commit()
            continue

        ok = await whatsapp_connector.send_message(
            phone=recipient.phone,
            message=render_campaign_message(campaign, recipient),
        )
        if ok:
            recipient.status = "sent"
            recipient.sent_at = datetime.now(timezone.utc)
            campaign.sent_count = (campaign.sent_count or 0) + 1
        else:
            recipient.status = "failed"
            recipient.error = "WhatsApp connector send failed"
            campaign.failed_count = (campaign.failed_count or 0) + 1
        db.commit()

    remaining = db.query(CampaignRecipient).filter(
        CampaignRecipient.campaign_id == campaign_id,
        CampaignRecipient.status == "pending",
    ).count()
    if remaining == 0:
        campaign.status = "completed"
        campaign.completed_at = datetime.now(timezone.utc)
    else:
        campaign.status = "paused"
    db.commit()
    return RedirectResponse(url="/campaigns", status_code=303)


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, db: Session = Depends(get_db)):
    reports = report_manager.get_recent_reports(db, 30)

    today = db.query(Report).filter(Report.report_type == "daily").order_by(Report.created_at.desc()).first()
    weekly = db.query(Report).filter(Report.report_type == "weekly").order_by(Report.created_at.desc()).first()
    monthly = db.query(Report).filter(Report.report_type == "monthly").order_by(Report.created_at.desc()).first()

    get_data = lambda r: r.report_data if r else {}
    today = get_data(today)
    weekly = get_data(weekly)
    monthly = get_data(monthly)

    return templates.TemplateResponse("reports.html", {
        "request": request,
        "reports": reports,
        "today": today,
        "weekly": weekly,
        "monthly": monthly,
    })


@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(
    request: Request,
    category: str = None,
    show_inactive: bool = False,
    db: Session = Depends(get_db),
):
    categories = knowledge_manager.get_categories(db)
    query = db.query(KnowledgeDocument)
    if category:
        query = query.filter(KnowledgeDocument.category == category)
    if not show_inactive:
        query = query.filter(KnowledgeDocument.is_active == True)
    documents = query.order_by(KnowledgeDocument.source.asc(), KnowledgeDocument.version.desc()).all()

    return templates.TemplateResponse("knowledge.html", {
        "request": request,
        "documents": documents,
        "categories": categories,
        "current_category": category,
        "show_inactive": show_inactive,
    })


@router.post("/knowledge/ingest", response_class=HTMLResponse)
async def ingest_knowledge(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    content: str = Form(...),
    source: str = Form(None),
    db: Session = Depends(get_db),
):
    try:
        doc = knowledge_manager.ingest_document(
            db=db,
            title=title,
            category=category,
            content=content,
            source=source,
        )
        return RedirectResponse(url="/knowledge", status_code=303)
    except Exception as e:
        return templates.TemplateResponse("knowledge.html", {
            "request": request,
            "documents": [],
            "categories": [],
            "error": f"فشل الإضافة: {str(e)}",
        })


@router.post("/knowledge/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    title: str = Form(None),
    category: str = Form("general"),
    db: Session = Depends(get_db),
):
    content = (await extract_upload_text(file)).strip()
    if not content:
        raise HTTPException(status_code=400, detail="File has no extractable text")

    knowledge_manager.ingest_document(
        db=db,
        title=title or file.filename,
        category=category,
        content=content,
        source=f"upload/{file.filename}",
    )
    return RedirectResponse(url="/knowledge", status_code=303)


@router.post("/knowledge/delete/{doc_id}")
async def delete_knowledge(doc_id: str, db: Session = Depends(get_db)):
    knowledge_manager.delete_document(db, doc_id)
    return RedirectResponse(url="/knowledge", status_code=303)


@router.post("/knowledge/reindex/{doc_id}")
async def reindex_knowledge(doc_id: str, db: Session = Depends(get_db)):
    knowledge_manager.reindex_document(db, doc_id)
    return RedirectResponse(url="/knowledge?show_inactive=true", status_code=303)


@router.post("/knowledge/toggle/{doc_id}")
async def toggle_knowledge(doc_id: str, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Knowledge document not found")
    knowledge_manager.set_document_active(db, doc_id, not doc.is_active)
    return RedirectResponse(url="/knowledge?show_inactive=true", status_code=303)


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    last_14_days = [(now - timedelta(days=i)).date() for i in reversed(range(14))]

    daily_rows = (
        db.query(func.date(Conversation.created_at).label("day"), func.count(Conversation.id).label("total"))
        .filter(Conversation.created_at >= since)
        .group_by("day")
        .all()
    )
    daily_map = {row.day: row.total for row in daily_rows}

    lead_stage_counts = {
        stage: db.query(Lead).filter(Lead.lead_status == stage).count()
        for stage, _ in PIPELINE_STAGES
    }
    automation_total = db.query(AutomationLog).filter(AutomationLog.created_at >= since).count()
    automation_success = db.query(AutomationLog).filter(AutomationLog.created_at >= since, AutomationLog.success == True).count()
    automation_skipped = db.query(AutomationLog).filter(AutomationLog.created_at >= since, AutomationLog.skipped == True).count()

    metrics = {
        "customers": db.query(Customer).count(),
        "new_customers_30d": db.query(Customer).filter(Customer.created_at >= since).count(),
        "conversations_30d": db.query(Conversation).filter(Conversation.created_at >= since).count(),
        "inbound_30d": db.query(Conversation).filter(Conversation.created_at >= since, Conversation.direction == "inbound").count(),
        "outbound_30d": db.query(Conversation).filter(Conversation.created_at >= since, Conversation.direction == "outbound").count(),
        "open_leads": db.query(Lead).filter(Lead.lead_status.notin_(["won", "lost"])).count(),
        "won_leads": db.query(Lead).filter(Lead.lead_status == "won").count(),
        "pending_tasks": db.query(FollowUpTask).filter(FollowUpTask.status == "pending").count(),
        "overdue_tasks": db.query(FollowUpTask).filter(FollowUpTask.status == "pending", FollowUpTask.due_at < now).count(),
        "campaigns_30d": db.query(Campaign).filter(Campaign.created_at >= since).count(),
        "campaign_sent": db.query(func.sum(Campaign.sent_count)).scalar() or 0,
        "campaign_failed": db.query(func.sum(Campaign.failed_count)).scalar() or 0,
        "opt_outs": db.query(OptOut).count(),
        "ai_calls_30d": db.query(AIUsageLog).filter(AIUsageLog.created_at >= since).count(),
        "ai_cost_30d": db.query(func.sum(AIUsageLog.estimated_cost_usd)).filter(AIUsageLog.created_at >= since).scalar() or 0,
        "ai_feedback_up": db.query(AIUsageLog).filter(AIUsageLog.feedback == "up").count(),
        "ai_feedback_down": db.query(AIUsageLog).filter(AIUsageLog.feedback == "down").count(),
        "automation_total_30d": automation_total,
        "automation_success_30d": automation_success,
        "automation_skipped_30d": automation_skipped,
        "radius_subscribers": db.query(RadiusSnapshot).count(),
        "radius_active": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "active").count(),
        "radius_expired": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "expired").count(),
        "radius_online": db.query(RadiusSnapshot).filter(RadiusSnapshot.online == True).count(),
        "routers": db.query(RouterDevice).count(),
        "routers_enabled": db.query(RouterDevice).filter(RouterDevice.enabled == True).count(),
        "router_actions_30d": db.query(RouterActionLog).filter(RouterActionLog.created_at >= since).count(),
    }

    charts = {
        "daily_conversations": {
            "labels": [day.strftime("%m-%d") for day in last_14_days],
            "values": [daily_map.get(day.isoformat(), 0) for day in last_14_days],
        },
        "pipeline": {
            "labels": [label for _, label in PIPELINE_STAGES],
            "values": [lead_stage_counts[stage] for stage, _ in PIPELINE_STAGES],
        },
        "automation": {
            "labels": ["success", "skipped", "failed"],
            "values": [automation_success, automation_skipped, max(automation_total - automation_success - automation_skipped, 0)],
        },
    }

    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "metrics": metrics,
        "charts": charts,
    })


@router.get("/support", response_class=HTMLResponse)
async def support_center_page(request: Request, db: Session = Depends(get_db)):
    handoffs = (
        db.query(HandoffRequest)
        .filter(HandoffRequest.status.in_(["pending", "accepted"]))
        .order_by(HandoffRequest.created_at.desc())
        .limit(50)
        .all()
    )
    wifi_requests = (
        db.query(RouterPendingAction)
        .filter(RouterPendingAction.status.in_(["manual_required", "failed", "awaiting_password", "awaiting_confirm"]))
        .order_by(RouterPendingAction.created_at.desc())
        .limit(50)
        .all()
    )
    tasks = (
        db.query(FollowUpTask)
        .filter(FollowUpTask.status == "pending")
        .order_by(FollowUpTask.due_at.is_(None), FollowUpTask.due_at.asc(), FollowUpTask.created_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse("support_center.html", {
        "request": request,
        "handoffs": handoffs,
        "wifi_requests": wifi_requests,
        "tasks": tasks,
    })


@router.get("/isp", response_class=HTMLResponse)
async def isp_operations_page(request: Request, q: str = None, db: Session = Depends(get_db)):
    radius_lookup = None
    radius_error = None
    router_lookup = None
    discovery = None
    if q:
        try:
            radius_lookup = await radius_service.lookup_by_phone(db, q)
        except Exception as exc:
            radius_error = str(exc)
            snapshot = radius_service.get_snapshot_for_phone(db, q)
            radius_lookup = {"linked": bool(snapshot), "snapshot": snapshot, "candidates": []}
        try:
            discovery = await router_auto_discovery.discover_host(db, q)
            router_lookup = await router_service.get_router_for_phone(db, q)
        except Exception as exc:
            discovery = {"host": None, "source": None, "error": str(exc)}

    stats = {
        "radius_total": db.query(RadiusSnapshot).count(),
        "radius_active": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "active").count(),
        "radius_expired": db.query(RadiusSnapshot).filter(RadiusSnapshot.status == "expired").count(),
        "radius_online": db.query(RadiusSnapshot).filter(RadiusSnapshot.online == True).count(),
        "routers_static": db.query(RouterDevice).count(),
        "wifi_pending": db.query(RouterPendingAction).filter(RouterPendingAction.status.in_(["manual_required", "failed", "awaiting_password", "awaiting_confirm"])).count(),
    }
    return templates.TemplateResponse("isp_operations.html", {
        "request": request,
        "query": q or "",
        "stats": stats,
        "radius_lookup": radius_lookup,
        "radius_error": radius_error,
        "router_lookup": router_device_dict(router_lookup),
        "discovery": discovery,
        "auto_settings": router_auto_discovery.status_for_ui(),
    })


def make_csv_response(filename: str, headers: list[str], rows: list[list]) -> StreamingResponse:
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def sqlite_database_path() -> Path | None:
    if not config.DATABASE_URL.startswith("sqlite:///"):
        return None
    raw_path = config.DATABASE_URL.replace("sqlite:///", "", 1)
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path.resolve()


def radius_snapshot_dict(snapshot: RadiusSnapshot | None) -> dict | None:
    if not snapshot:
        return None
    return {
        "id": snapshot.id,
        "customer_id": snapshot.customer_id,
        "external_id": snapshot.external_id,
        "username": snapshot.username,
        "phone": snapshot.phone,
        "status": snapshot.status,
        "package": snapshot.package_name,
        "expires_at": snapshot.expires_at.isoformat() if snapshot.expires_at else None,
        "online": snapshot.online,
        "last_seen_at": snapshot.last_seen_at.isoformat() if snapshot.last_seen_at else None,
        "balance": snapshot.balance,
        "ip_address": snapshot.ip_address,
        "reseller": snapshot.reseller,
        "download_rate": snapshot.download_rate,
        "upload_rate": snapshot.upload_rate,
        "traffic_used": snapshot.traffic_used,
        "synced_at": snapshot.synced_at.isoformat() if snapshot.synced_at else None,
    }


def router_device_dict(router: RouterDevice | None) -> dict | None:
    if not router:
        return None
    return {
        "id": getattr(router, "id", None),
        "dynamic": bool(getattr(router, "dynamic", False)),
        "host_source": getattr(router, "host_source", None),
        "customer_id": getattr(router, "customer_id", None),
        "customer_phone": router.customer.phone if getattr(router, "customer", None) else None,
        "radius_external_id": getattr(router, "radius_external_id", None),
        "name": getattr(router, "name", None),
        "model": getattr(router, "model", None),
        "protocol": getattr(router, "protocol", None),
        "host": getattr(router, "host", None),
        "port": getattr(router, "port", None),
        "ssid": getattr(router, "ssid", None),
        "wifi_interface": getattr(router, "wifi_interface", None),
        "wifi_profile": getattr(router, "wifi_profile", None),
        "enabled": getattr(router, "enabled", False),
        "last_status": getattr(router, "last_status", None),
        "last_error": getattr(router, "last_error", None),
        "last_seen_at": router.last_seen_at.isoformat() if getattr(router, "last_seen_at", None) else None,
    }


@router.get("/radius", response_class=HTMLResponse)
async def radius_page(request: Request, q: str = None, db: Session = Depends(get_db)):
    results = []
    search_error = None
    if q:
        try:
            results = await radius_service.lookup_by_query(db, q)
        except Exception as exc:
            search_error = str(exc)

    links = db.query(RadiusSubscriberLink).order_by(RadiusSubscriberLink.updated_at.desc()).limit(100).all()
    snapshots = db.query(RadiusSnapshot).order_by(RadiusSnapshot.synced_at.desc()).limit(100).all()
    logs = db.query(RadiusSyncLog).order_by(RadiusSyncLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("radius.html", {
        "request": request,
        "settings": radius_connector.status_for_ui(),
        "query": q or "",
        "results": results,
        "search_error": search_error,
        "links": links,
        "snapshots": snapshots,
        "logs": logs,
    })


@router.post("/radius/settings")
async def save_radius_settings(request: Request):
    form = await request.form()
    radius_connector.save_from_form(form)
    return RedirectResponse(url="/radius?saved=true", status_code=303)


@router.post("/radius/test")
async def test_radius_connection():
    return await radius_connector.test_connection()


@router.post("/radius/link")
async def link_radius_subscriber(
    phone: str = Form(...),
    external_id: str = Form(...),
    username: str = Form(None),
    package_name: str = Form(None),
    status: str = Form("unknown"),
    db: Session = Depends(get_db),
):
    subscriber = {
        "external_id": external_id,
        "username": username or external_id,
        "phone": phone,
        "package": package_name,
        "status": status,
    }
    link = radius_service.link_customer_by_phone(db, phone, subscriber)
    radius_service.upsert_snapshot(db, subscriber, link.customer_id)
    db.add(RadiusSyncLog(action="link", external_id=external_id, success=True, message=f"Linked to {phone}"))
    db.commit()
    return RedirectResponse(url="/radius", status_code=303)


@router.post("/radius/{external_id}/refresh")
async def refresh_radius_subscriber(external_id: str, db: Session = Depends(get_db)):
    try:
        link = db.query(RadiusSubscriberLink).filter(RadiusSubscriberLink.external_id == external_id).first()
        snapshot = await radius_service.refresh_snapshot(db, external_id, getattr(link, "customer_id", None))
        db.add(RadiusSyncLog(action="refresh", external_id=external_id, success=True, message=snapshot.status))
        db.commit()
    except Exception as exc:
        db.add(RadiusSyncLog(action="refresh", external_id=external_id, success=False, message=str(exc)[:500]))
        db.commit()
    return RedirectResponse(url="/radius", status_code=303)


@router.post("/radius/{external_id}/action")
async def radius_action(external_id: str, action: str = Form(...), payload: str = Form("{}"), db: Session = Depends(get_db)):
    try:
        parsed_payload = json.loads(payload or "{}")
        result = await radius_connector.execute_action(external_id, action, parsed_payload)
        db.add(RadiusSyncLog(action=action, external_id=external_id, success=True, message=json.dumps(result, ensure_ascii=False)[:500]))
    except Exception as exc:
        db.add(RadiusSyncLog(action=action, external_id=external_id, success=False, message=str(exc)[:500]))
    db.commit()
    return RedirectResponse(url="/radius", status_code=303)


@router.get("/api/radius/lookup")
async def api_radius_lookup(phone: str, db: Session = Depends(get_db)):
    try:
        lookup = await radius_service.lookup_by_phone(db, phone)
        return {
            "success": True,
            "linked": lookup.get("linked", False),
            "snapshot": radius_snapshot_dict(lookup.get("snapshot")),
            "candidates": lookup.get("candidates", []),
        }
    except Exception as exc:
        snapshot = radius_service.get_snapshot_for_phone(db, phone)
        return {
            "success": False,
            "error": str(exc),
            "snapshot": radius_snapshot_dict(snapshot),
            "candidates": [],
        }


@router.get("/api/radius/subscribers/search")
async def api_radius_search(q: str, db: Session = Depends(get_db)):
    try:
        return {"success": True, "results": await radius_service.lookup_by_query(db, q)}
    except Exception as exc:
        return {"success": False, "error": str(exc), "results": []}


@router.get("/api/radius/subscribers/{external_id}")
async def api_radius_detail(external_id: str, db: Session = Depends(get_db)):
    try:
        link = db.query(RadiusSubscriberLink).filter(RadiusSubscriberLink.external_id == external_id).first()
        snapshot = await radius_service.refresh_snapshot(db, external_id, getattr(link, "customer_id", None))
        return {"success": True, "snapshot": radius_snapshot_dict(snapshot)}
    except Exception as exc:
        snapshot = db.query(RadiusSnapshot).filter(RadiusSnapshot.external_id == external_id).first()
        return {"success": False, "error": str(exc), "snapshot": radius_snapshot_dict(snapshot)}


@router.get("/api/radius/subscribers/{external_id}/sessions")
async def api_radius_sessions(external_id: str):
    try:
        return {"success": True, "sessions": await radius_connector.get_sessions(external_id)}
    except Exception as exc:
        return {"success": False, "error": str(exc), "sessions": []}


@router.post("/api/radius/subscribers/{external_id}/action")
async def api_radius_action(external_id: str, request: Request):
    body = await request.json()
    action = body.get("action")
    payload = body.get("payload") or {}
    if not action:
        return {"success": False, "error": "action is required"}
    try:
        return {"success": True, "result": await radius_connector.execute_action(external_id, action, payload)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.post("/api/radius/link")
async def api_radius_link(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    phone = body.get("phone")
    subscriber = body.get("subscriber") or {}
    if not phone or not subscriber.get("external_id"):
        return {"success": False, "error": "phone and subscriber.external_id are required"}
    link = radius_service.link_customer_by_phone(db, phone, subscriber)
    snapshot = radius_service.upsert_snapshot(db, subscriber, link.customer_id)
    return {"success": True, "snapshot": radius_snapshot_dict(snapshot)}


@router.post("/api/radius/send-renewal")
async def api_send_radius_renewal(request: Request):
    body = await request.json()
    phone = (body.get("phone") or "").strip()
    message = (body.get("message") or radius_connector.load_settings().get("renewal_message") or "").strip()
    if not phone or not message:
        return {"success": False, "error": "phone and message are required"}
    ok = await whatsapp_connector.send_message(phone=phone, message=message)
    return {"success": ok}


@router.get("/routers", response_class=HTMLResponse)
async def routers_page(request: Request, db: Session = Depends(get_db)):
    routers = db.query(RouterDevice).order_by(RouterDevice.updated_at.desc()).limit(200).all()
    logs = db.query(RouterActionLog).order_by(RouterActionLog.created_at.desc()).limit(100).all()
    pending = db.query(RouterPendingAction).order_by(RouterPendingAction.created_at.desc()).limit(50).all()
    customers = db.query(Customer).order_by(Customer.last_seen_at.desc()).limit(200).all()
    return templates.TemplateResponse("routers.html", {
        "request": request,
        "routers": routers,
        "logs": logs,
        "pending": pending,
        "customers": customers,
        "auto_settings": router_auto_discovery.status_for_ui(),
    })


@router.post("/routers/auto-settings")
async def save_router_auto_settings(request: Request):
    form = await request.form()
    router_auto_discovery.save_from_form(form)
    return RedirectResponse(url="/routers?auto_saved=true", status_code=303)


@router.post("/routers/create")
async def create_router(
    customer_id: str = Form(None),
    customer_phone: str = Form(None),
    radius_external_id: str = Form(None),
    name: str = Form(...),
    model: str = Form(None),
    protocol: str = Form("manual"),
    host: str = Form(None),
    port: str = Form(None),
    username: str = Form(None),
    password: str = Form(None),
    ssid: str = Form(None),
    wifi_interface: str = Form(None),
    wifi_profile: str = Form(None),
    http_method: str = Form("POST"),
    http_change_password_path: str = Form(None),
    http_payload_template: str = Form(None),
    http_status_path: str = Form(None),
    http_reboot_path: str = Form(None),
    ssh_change_password_command: str = Form(None),
    ssh_reboot_command: str = Form(None),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
):
    if not customer_id and customer_phone:
        customer = router_service.get_or_create_customer(db, customer_phone)
        customer_id = customer.id
    router_port = int(port) if str(port or "").strip() else None
    router = RouterDevice(
        customer_id=customer_id or None,
        radius_external_id=(radius_external_id or "").strip() or None,
        name=name.strip(),
        model=(model or "").strip() or None,
        protocol=protocol,
        host=(host or "").strip() or None,
        port=router_port,
        username=(username or "").strip() or None,
        password=(password or "").strip() or None,
        ssid=(ssid or "").strip() or None,
        wifi_interface=(wifi_interface or "").strip() or None,
        wifi_profile=(wifi_profile or "").strip() or None,
        http_method=http_method or "POST",
        http_change_password_path=(http_change_password_path or "").strip() or None,
        http_payload_template=(http_payload_template or "").strip() or None,
        http_status_path=(http_status_path or "").strip() or None,
        http_reboot_path=(http_reboot_path or "").strip() or None,
        ssh_change_password_command=(ssh_change_password_command or "").strip() or None,
        ssh_reboot_command=(ssh_reboot_command or "").strip() or None,
        enabled=enabled == "on",
    )
    db.add(router)
    db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/{router_id}/toggle")
async def toggle_router(router_id: str, db: Session = Depends(get_db)):
    router = db.query(RouterDevice).filter(RouterDevice.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    router.enabled = not router.enabled
    db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/{router_id}/delete")
async def delete_router(router_id: str, db: Session = Depends(get_db)):
    router = db.query(RouterDevice).filter(RouterDevice.id == router_id).first()
    if router:
        db.delete(router)
        db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/{router_id}/change-wifi")
async def change_router_wifi(router_id: str, new_password: str = Form(...), db: Session = Depends(get_db)):
    router = db.query(RouterDevice).filter(RouterDevice.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    result = await router_connector.change_wifi_password(router, new_password)
    router.last_status = "ok" if result.get("success") else "error"
    router.last_error = None if result.get("success") else result.get("message")
    router.last_seen_at = datetime.now(timezone.utc) if result.get("success") else router.last_seen_at
    router_service.log(db, router.id, router.customer_id, router.customer.phone if router.customer else None, "change_wifi_password_dashboard", bool(result.get("success")), result.get("message"))
    db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/{router_id}/reboot")
async def reboot_router(router_id: str, db: Session = Depends(get_db)):
    router = db.query(RouterDevice).filter(RouterDevice.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    result = await router_connector.reboot(router)
    router_service.log(db, router.id, router.customer_id, router.customer.phone if router.customer else None, "reboot", bool(result.get("success")), result.get("message"))
    db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/{router_id}/test")
async def test_router(router_id: str, db: Session = Depends(get_db)):
    router = db.query(RouterDevice).filter(RouterDevice.id == router_id).first()
    if not router:
        raise HTTPException(status_code=404, detail="Router not found")
    result = await router_connector.status(router)
    router.last_status = "ok" if result.get("success") else "error"
    router.last_error = None if result.get("success") else result.get("message")
    router.last_seen_at = datetime.now(timezone.utc) if result.get("success") else router.last_seen_at
    router_service.log(db, router.id, router.customer_id, router.customer.phone if router.customer else None, "status", bool(result.get("success")), result.get("message"))
    db.commit()
    return RedirectResponse(url="/routers", status_code=303)


@router.post("/routers/pending/{pending_id}/complete")
async def complete_router_pending(
    pending_id: str,
    notify: str = Form(None),
    message: str = Form(None),
    return_to: str = Form(None),
    db: Session = Depends(get_db),
):
    pending = db.query(RouterPendingAction).filter(RouterPendingAction.id == pending_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Router pending request not found")
    pending.status = "completed_manual"
    pending.expires_at = datetime.now(timezone.utc)
    router_service.log(
        db,
        pending.router_id,
        pending.customer_id,
        pending.phone,
        "change_wifi_password_manual_complete",
        True,
        "Completed manually by support",
        {"pending_id": pending.id},
    )
    if notify == "on" and pending.phone:
        text = (message or "تم تنفيذ طلب تغيير باسورد الواي فاي من الدعم. لو الأجهزة فصلت، أعد الاتصال بالباسورد الجديد الذي طلبته.").strip()
        ok = await whatsapp_connector.send_message(phone=pending.phone, message=text)
        router_service.log(
            db,
            pending.router_id,
            pending.customer_id,
            pending.phone,
            "notify_wifi_password_manual_complete",
            ok,
            "Notification sent" if ok else "Notification failed",
            {"pending_id": pending.id},
        )
    db.commit()
    return RedirectResponse(url=safe_redirect_url(return_to, "/routers"), status_code=303)


@router.post("/routers/pending/{pending_id}/close")
async def close_router_pending(
    pending_id: str,
    notify: str = Form(None),
    message: str = Form(None),
    return_to: str = Form(None),
    db: Session = Depends(get_db),
):
    pending = db.query(RouterPendingAction).filter(RouterPendingAction.id == pending_id).first()
    if not pending:
        raise HTTPException(status_code=404, detail="Router pending request not found")
    pending.status = "closed"
    pending.expires_at = datetime.now(timezone.utc)
    router_service.log(
        db,
        pending.router_id,
        pending.customer_id,
        pending.phone,
        "change_wifi_password_manual_close",
        False,
        "Closed by support",
        {"pending_id": pending.id},
    )
    if notify == "on" and pending.phone:
        text = (message or "تم إغلاق طلب تغيير باسورد الواي فاي. لو ما زلت تحتاج مساعدة، ابعت لنا رسالة وسيتابع معك الدعم.").strip()
        ok = await whatsapp_connector.send_message(phone=pending.phone, message=text)
        router_service.log(
            db,
            pending.router_id,
            pending.customer_id,
            pending.phone,
            "notify_wifi_password_manual_close",
            ok,
            "Notification sent" if ok else "Notification failed",
            {"pending_id": pending.id},
        )
    db.commit()
    return RedirectResponse(url=safe_redirect_url(return_to, "/routers"), status_code=303)


@router.get("/api/routers/lookup")
async def api_router_lookup(phone: str, db: Session = Depends(get_db)):
    router = await router_service.get_router_for_phone(db, phone)
    return {"success": True, "router": router_device_dict(router)}


@router.get("/api/routers/discover")
async def api_router_discover(phone: str, db: Session = Depends(get_db)):
    discovery = await router_auto_discovery.discover_host(db, phone)
    router = await router_auto_discovery.discover_router(db, phone)
    return {
        "success": bool(discovery.get("host")),
        "discovery": {
            "host": discovery.get("host"),
            "source": discovery.get("source"),
            "external_id": discovery.get("external_id"),
            "username": discovery.get("username"),
        },
        "router": router_device_dict(router),
    }


@router.post("/api/routers/change-wifi")
async def api_router_change_wifi(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    phone = body.get("phone")
    new_password = body.get("new_password")
    router = await router_service.get_router_for_phone(db, phone)
    if not router:
        return {"success": False, "error": "No linked or auto-discovered router for this phone"}
    result = await router_connector.change_wifi_password(router, new_password)
    router.last_status = "ok" if result.get("success") else "error"
    router.last_error = None if result.get("success") else result.get("message")
    router.last_seen_at = datetime.now(timezone.utc) if result.get("success") else router.last_seen_at
    router_service.log(
        db,
        getattr(router, "id", None),
        getattr(router, "customer_id", None),
        phone,
        "change_wifi_password_api",
        bool(result.get("success")),
        result.get("message"),
        {"dynamic_router": bool(getattr(router, "dynamic", False)), "host_source": getattr(router, "host_source", None)},
    )
    db.commit()
    return result


@router.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, db: Session = Depends(get_db)):
    webhooks = db.query(ExternalWebhook).order_by(ExternalWebhook.created_at.desc()).all()
    return templates.TemplateResponse("integrations.html", {"request": request, "webhooks": webhooks})


@router.post("/integrations/webhooks/create")
async def create_webhook(
    name: str = Form(...),
    event: str = Form("message.inbound"),
    url: str = Form(...),
    secret: str = Form(None),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
):
    db.add(ExternalWebhook(
        name=name.strip(),
        event=event.strip(),
        url=url.strip(),
        secret=(secret or "").strip() or None,
        enabled=enabled == "on",
    ))
    db.commit()
    return RedirectResponse(url="/integrations", status_code=303)


@router.post("/integrations/webhooks/{webhook_id}/toggle")
async def toggle_webhook(webhook_id: str, db: Session = Depends(get_db)):
    webhook = db.query(ExternalWebhook).filter(ExternalWebhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    webhook.enabled = not webhook.enabled
    db.commit()
    return RedirectResponse(url="/integrations", status_code=303)


@router.post("/integrations/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str, db: Session = Depends(get_db)):
    webhook = db.query(ExternalWebhook).filter(ExternalWebhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    await integration_manager.send(webhook, "webhook.test", {"message": "WAACT test event"})
    db.commit()
    return RedirectResponse(url="/integrations", status_code=303)


@router.post("/integrations/webhooks/{webhook_id}/delete")
async def delete_webhook(webhook_id: str, db: Session = Depends(get_db)):
    webhook = db.query(ExternalWebhook).filter(ExternalWebhook.id == webhook_id).first()
    if webhook:
        db.delete(webhook)
        db.commit()
    return RedirectResponse(url="/integrations", status_code=303)


@router.get("/export/{entity}.csv")
async def export_csv(entity: str, db: Session = Depends(get_db)):
    if entity == "customers":
        rows = db.query(Customer).order_by(Customer.created_at.desc()).all()
        return make_csv_response("customers.csv", ["id", "phone", "name", "status", "source", "created_at", "last_seen_at"], [
            [c.id, c.phone, c.name or "", c.status, c.source, c.created_at, c.last_seen_at]
            for c in rows
        ])
    if entity == "leads":
        rows = db.query(Lead).order_by(Lead.created_at.desc()).all()
        return make_csv_response("leads.csv", ["id", "customer_phone", "status", "priority", "service_interest", "estimated_value", "assigned_to", "created_at"], [
            [lead.id, lead.customer.phone if lead.customer else "", lead.lead_status, lead.priority, lead.service_interest or "", lead.estimated_value or "", lead.assigned_to or "", lead.created_at]
            for lead in rows
        ])
    if entity == "conversations":
        rows = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(10000).all()
        return make_csv_response("conversations.csv", ["id", "customer_phone", "direction", "intent", "message_text", "ai_response", "created_at"], [
            [conv.id, conv.customer.phone if conv.customer else "", conv.direction, conv.intent or "", conv.message_text, conv.ai_response or "", conv.created_at]
            for conv in rows
        ])
    if entity == "radius":
        rows = db.query(RadiusSnapshot).order_by(RadiusSnapshot.synced_at.desc()).all()
        return make_csv_response("radius-subscribers.csv", ["external_id", "username", "phone", "status", "package", "expires_at", "online", "ip_address", "reseller", "synced_at"], [
            [row.external_id, row.username or "", row.phone or "", row.status, row.package_name or "", row.expires_at or "", row.online, row.ip_address or "", row.reseller or "", row.synced_at]
            for row in rows
        ])
    if entity == "routers":
        rows = db.query(RouterDevice).order_by(RouterDevice.updated_at.desc()).all()
        return make_csv_response("routers.csv", ["id", "customer_phone", "name", "model", "protocol", "host", "ssid", "enabled", "last_status", "updated_at"], [
            [row.id, row.customer.phone if row.customer else "", row.name, row.model or "", row.protocol, row.host or "", row.ssid or "", row.enabled, row.last_status or "", row.updated_at]
            for row in rows
        ])
    raise HTTPException(status_code=404, detail="Unknown export entity")


@router.get("/maintenance", response_class=HTMLResponse)
async def maintenance_page(request: Request, db: Session = Depends(get_db)):
    require_min_role(request, db, "admin")
    db_path = sqlite_database_path()
    db_size = db_path.stat().st_size if db_path and db_path.exists() else 0
    warnings = []
    if config.DEBUG:
        warnings.append("DEBUG=true")
    if config.SECRET_KEY == "change-this-in-production":
        warnings.append("SECRET_KEY default")
    if not config.AUTH_ENABLED:
        warnings.append("AUTH_ENABLED=false")
    return templates.TemplateResponse("maintenance.html", {
        "request": request,
        "db_path": str(db_path) if db_path else "غير مدعوم",
        "db_size": db_size,
        "warnings": warnings,
        "is_sqlite": db_path is not None,
    })


@router.get("/maintenance/backup")
async def download_backup(request: Request, db: Session = Depends(get_db)):
    require_min_role(request, db, "admin")
    db_path = sqlite_database_path()
    if not db_path or not db_path.exists():
        raise HTTPException(status_code=400, detail="SQLite database not found")

    fd, temp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        source = sqlite3.connect(db_path)
        backup = sqlite3.connect(temp_path)
        try:
            source.backup(backup)
        finally:
            backup.close()
            source.close()
        data = temp_path.read_bytes()
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except TypeError:
            if temp_path.exists():
                temp_path.unlink()

    filename = f"waact-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/maintenance/restore")
async def restore_backup(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_min_role(request, db, "admin")
    db.close()
    db_path = sqlite_database_path()
    if not db_path:
        raise HTTPException(status_code=400, detail="Restore is only supported for SQLite")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Backup file is empty")

    fd, temp_name = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    temp_path = Path(temp_name)
    temp_path.write_bytes(data)
    try:
        restored = sqlite3.connect(temp_path)
        try:
            result = restored.execute("PRAGMA integrity_check").fetchone()
        finally:
            restored.close()
        if not result or result[0] != "ok":
            raise HTTPException(status_code=400, detail="SQLite integrity_check failed")

        engine.dispose()
        if db_path.exists():
            safety_copy = db_path.with_name(f"{db_path.stem}.before-restore-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}{db_path.suffix}")
            shutil.copy2(db_path, safety_copy)
        shutil.copy2(temp_path, db_path)
        init_db()
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except TypeError:
            if temp_path.exists():
                temp_path.unlink()

    return RedirectResponse(url="/maintenance?restored=true", status_code=303)


@router.get("/handoffs", response_class=HTMLResponse)
async def handoffs_page(
    request: Request,
    status: str = "pending",
    db: Session = Depends(get_db),
):
    query = db.query(HandoffRequest).order_by(HandoffRequest.created_at.desc())
    if status:
        query = query.filter(HandoffRequest.status == status)

    handoffs = query.all()

    return templates.TemplateResponse("handoffs.html", {
        "request": request,
        "handoffs": handoffs,
        "current_status": status,
    })


@router.post("/handoffs/accept/{handoff_id}")
async def accept_handoff(
    handoff_id: str,
    assigned_to: str = Form("agent"),
    return_to: str = Form(None),
    db: Session = Depends(get_db),
):
    handoff_manager.accept_handoff(db, handoff_id, assigned_to)
    return RedirectResponse(url=safe_redirect_url(return_to, "/handoffs"), status_code=303)


@router.post("/handoffs/resolve/{handoff_id}")
async def resolve_handoff(handoff_id: str, return_to: str = Form(None), db: Session = Depends(get_db)):
    handoff_manager.resolve_handoff(db, handoff_id)
    return RedirectResponse(url=safe_redirect_url(return_to, "/handoffs"), status_code=303)


@router.get("/whatsapp-chats", response_class=HTMLResponse)
async def whatsapp_chats_page(request: Request):
    return templates.TemplateResponse("whatsapp_chats.html", {"request": request})


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    import asyncio
    status_task = asyncio.create_task(whatsapp_connector.get_status())
    qr_task = asyncio.create_task(whatsapp_connector.get_qr())
    connector_status, qr_code = await asyncio.gather(status_task, qr_task)
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "connector_status": connector_status,
        "qr_code": qr_code,
        "ai_settings": ai_provider_manager.status_for_ui(),
    })


@router.post("/settings/ai")
async def save_ai_settings(request: Request):
    form = await request.form()
    ai_provider_manager.save_from_form(form)
    return RedirectResponse(url="/settings?saved=ai", status_code=303)


@router.post("/settings/ai/test/{provider_id}")
async def test_ai_provider(provider_id: str):
    return ai_provider_manager.test_provider(provider_id)


@router.get("/ai-usage", response_class=HTMLResponse)
async def ai_usage_page(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(
            AIUsageLog.provider,
            AIUsageLog.model,
            func.count(AIUsageLog.id).label("total"),
            func.sum(func.cast(AIUsageLog.success, Integer)).label("successes"),
            func.avg(AIUsageLog.latency_ms).label("avg_latency"),
            func.sum(AIUsageLog.prompt_tokens).label("prompt_tokens"),
            func.sum(AIUsageLog.completion_tokens).label("completion_tokens"),
            func.sum(AIUsageLog.estimated_cost_usd).label("estimated_cost_usd"),
        )
        .group_by(AIUsageLog.provider, AIUsageLog.model)
        .order_by(desc("total"))
        .all()
    )
    recent_errors = (
        db.query(AIUsageLog)
        .filter(AIUsageLog.success == False)
        .order_by(AIUsageLog.created_at.desc())
        .limit(25)
        .all()
    )
    recent_calls = db.query(AIUsageLog).order_by(AIUsageLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("ai_usage.html", {
        "request": request,
        "rows": rows,
        "recent_errors": recent_errors,
        "recent_calls": recent_calls,
    })


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: Session = Depends(get_db)):
    require_min_role(request, db, "admin")
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse("users.html", {
        "request": request,
        "users": users,
        "auth_enabled": config.AUTH_ENABLED,
    })


@router.post("/users/create")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("agent"),
    db: Session = Depends(get_db),
):
    actor = require_min_role(request, db, "admin")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    user = User(username=username.strip(), password_hash=hash_password(password), role=role, is_active=True)
    db.add(user)
    db.commit()
    log_audit("user.create", user=actor, entity_type="user", entity_id=user.id, details={"username": user.username, "role": role}, request=request)
    return RedirectResponse(url="/users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(request: Request, user_id: str, db: Session = Depends(get_db)):
    actor = require_min_role(request, db, "admin")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    db.commit()
    log_audit("user.toggle", user=actor, entity_type="user", entity_id=user.id, details={"is_active": user.is_active}, request=request)
    return RedirectResponse(url="/users", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, db: Session = Depends(get_db)):
    require_min_role(request, db, "admin")
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
    return templates.TemplateResponse("audit.html", {"request": request, "logs": logs})


@router.get("/automation", response_class=HTMLResponse)
async def automation_page(request: Request, db: Session = Depends(get_db)):
    rules = db.query(AutomationRule).order_by(AutomationRule.priority.asc(), AutomationRule.created_at.desc()).all()
    logs = db.query(AutomationLog).order_by(AutomationLog.created_at.desc()).limit(100).all()
    return templates.TemplateResponse("automation.html", {"request": request, "rules": rules, "logs": logs})


@router.post("/automation/create")
async def create_automation_rule(
    request: Request,
    name: str = Form(...),
    trigger: str = Form("inbound_message"),
    condition_type: str = Form("always"),
    condition_value: str = Form(None),
    action_type: str = Form(...),
    action_payload: str = Form("{}"),
    priority: int = Form(100),
    cooldown_minutes: int = Form(60),
    enabled: str = Form(None),
    db: Session = Depends(get_db),
):
    actor = get_current_user(request, db) if config.AUTH_ENABLED else None
    try:
        payload = json.loads(action_payload or "{}")
        if not isinstance(payload, dict):
            raise ValueError("payload must be object")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}")

    rule = AutomationRule(
        name=name.strip(),
        trigger=trigger,
        condition_type=condition_type,
        condition_value=(condition_value or "").strip() or None,
        action_type=action_type,
        action_payload=payload,
        priority=priority,
        cooldown_minutes=cooldown_minutes,
        enabled=enabled == "on",
    )
    db.add(rule)
    db.commit()
    log_audit("automation.create", user=actor, entity_type="automation_rule", entity_id=rule.id, details={"name": rule.name}, request=request)
    return RedirectResponse(url="/automation", status_code=303)


@router.post("/automation/{rule_id}/toggle")
async def toggle_automation_rule(request: Request, rule_id: str, db: Session = Depends(get_db)):
    actor = get_current_user(request, db) if config.AUTH_ENABLED else None
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    rule.enabled = not rule.enabled
    db.commit()
    log_audit("automation.toggle", user=actor, entity_type="automation_rule", entity_id=rule.id, details={"enabled": rule.enabled}, request=request)
    return RedirectResponse(url="/automation", status_code=303)


@router.get("/api/stats", response_class=HTMLResponse)
async def api_stats(db: Session = Depends(get_db)):
    stats = report_manager.get_dashboard_stats(db)
    return stats
