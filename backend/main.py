import os
import logging
import httpx
import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response, RedirectResponse, HTMLResponse
from contextlib import asynccontextmanager
from database.db import init_db
from config import config
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

scheduler = BackgroundScheduler()


def generate_reports_job():
    from database.db import SessionLocal
    from workflows.reporting import report_manager

    db = SessionLocal()
    try:
        report_manager.generate_daily_report(db)
        report_manager.generate_weekly_report(db)
        report_manager.generate_monthly_report(db)
    except Exception as e:
        print(f"[SCHEDULER] Report error: {e}")
    finally:
        db.close()


async def _radius_reminders_job():
    from database.db import SessionLocal
    from radius import radius_connector
    from radius_service import radius_service
    from whatsapp.connector import whatsapp_connector

    settings = radius_connector.load_settings()
    if not settings.get("enabled") or not settings.get("reminders_enabled"):
        return

    db = SessionLocal()
    try:
        days_before = settings.get("reminder_days_before") or []
        days_after = settings.get("expired_reminder_days_after") or []
        template = settings.get("renewal_message") or "اشتراكك هينتهي يوم {expires_at}. للتجديد ابعت جدد."
        for days in days_before:
            for snapshot in radius_service.due_expiry_snapshots(db, int(days)):
                event_type = f"expiry_before_{days}d"
                if radius_service.event_exists_today(db, snapshot.external_id, event_type):
                    continue
                expires_at = snapshot.expires_at.strftime("%Y-%m-%d") if snapshot.expires_at else "غير محدد"
                message = template.format(
                    username=snapshot.username or snapshot.external_id,
                    package=snapshot.package_name or "",
                    expires_at=expires_at,
                    status=snapshot.status,
                )
                ok = await whatsapp_connector.send_message(phone=snapshot.phone, message=message)
                radius_service.log_event(db, snapshot.external_id, event_type, snapshot.phone, {"sent": ok})

        for days in days_after:
            for snapshot in radius_service.due_expiry_snapshots(db, -int(days)):
                event_type = f"expired_after_{days}d"
                if radius_service.event_exists_today(db, snapshot.external_id, event_type):
                    continue
                message = f"اشتراكك منتهي. للتجديد ابعت جدد أو تواصل معنا.\nUsername: {snapshot.username or snapshot.external_id}"
                ok = await whatsapp_connector.send_message(phone=snapshot.phone, message=message)
                radius_service.log_event(db, snapshot.external_id, event_type, snapshot.phone, {"sent": ok})
    except Exception as e:
        print(f"[SCHEDULER] Radius reminders error: {e}")
    finally:
        db.close()


def radius_reminders_job():
    asyncio.run(_radius_reminders_job())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    scheduler.add_job(generate_reports_job, "interval", hours=6, id="reports_6h")
    scheduler.add_job(radius_reminders_job, "interval", hours=6, id="radius_reminders_6h")
    scheduler.start()

    print(f"[WAACT] System initialized. Dashboard: {config.APP_URL}")
    yield

    scheduler.shutdown(wait=False)


app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    lifespan=lifespan,
)


@app.middleware("http")
async def optional_auth_middleware(request: Request, call_next):
    if not config.AUTH_ENABLED:
        return await call_next(request)

    path = request.url.path
    public_paths = ("/login", "/api/health", "/static")
    if path.startswith(public_paths):
        return await call_next(request)

    from database.db import SessionLocal
    from auth import ensure_default_user, get_current_user

    db = SessionLocal()
    try:
        ensure_default_user(db)
        if get_current_user(request, db):
            return await call_next(request)
    finally:
        db.close()

    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if not config.AUTH_ENABLED:
        return RedirectResponse(url="/", status_code=303)
    return """
    <!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>WAACT Login</title><style>body{margin:0;background:#0f0f1a;color:#fff;font-family:Segoe UI,Tahoma,Arial;display:grid;place-items:center;min-height:100vh}.box{width:min(420px,92vw);background:#1a1a2e;border:1px solid #2a2a4a;border-radius:18px;padding:28px}h1{color:#00d4aa;margin:0 0 8px}p{color:#888}input{width:100%;padding:12px;margin:8px 0 14px;background:#101020;border:1px solid #2a2a4a;border-radius:10px;color:#fff}button{width:100%;padding:12px;border:0;border-radius:10px;background:#00d4aa;color:#06130f;font-weight:700;cursor:pointer}.err{color:#ff7777;margin-top:10px}</style></head>
    <body><form class="box" method="post" action="/login"><h1>WAACT</h1><p>تسجيل الدخول للوحة التحكم</p><input name="username" placeholder="اسم المستخدم" required><input name="password" type="password" placeholder="كلمة المرور" required><button>دخول</button></form></body></html>
    """


@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if not config.AUTH_ENABLED:
        return RedirectResponse(url="/", status_code=303)
    from database.db import SessionLocal
    from database.models import User
    from auth import ensure_default_user, verify_password, make_session_token, log_audit

    db = SessionLocal()
    try:
        ensure_default_user(db)
        user = db.query(User).filter(User.username == username, User.is_active == True).first()
        if user and verify_password(password, user.password_hash):
            user.last_login_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            db.commit()
            log_audit("login", user=user)
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie("waact_auth", make_session_token(user.id), httponly=True, samesite="lax")
            return response
    finally:
        db.close()

    return HTMLResponse("<h3 style='font-family:Arial;color:#c00'>بيانات الدخول غير صحيحة</h3><a href='/login'>رجوع</a>", status_code=401)


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("waact_auth")
    return response

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if config.DEBUG:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "traceback": traceback.format_exc()},
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


from whatsapp.webhook import router as whatsapp_router
from dashboard.routes import router as dashboard_router

app.include_router(whatsapp_router)
app.include_router(dashboard_router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "release": config.APP_RELEASE,
        "prd_version": config.PRD_VERSION,
    }


@app.get("/api/status")
async def system_status():
    from database.db import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"
    finally:
        db.close()

    try:
        from rag.vector_store import vector_store
        kb_count = vector_store.count()
    except Exception:
        kb_count = 0

    return {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "release": config.APP_RELEASE,
        "database": db_status,
        "knowledge_base_chunks": kb_count,
        "openai_configured": bool(config.OPENAI_API_KEY),
        "whatsapp_connector": config.WHATSAPP_CONNECTOR_URL,
        "scheduler_running": scheduler.running,
    }


@app.get("/api/whatsapp/qr")
async def get_whatsapp_qr():
    from whatsapp.connector import whatsapp_connector
    qr = await whatsapp_connector.get_qr()
    return {"qr": qr}


@app.get("/api/whatsapp/chats")
async def get_whatsapp_chats():
    from whatsapp.connector import whatsapp_connector
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(f"{config.WHATSAPP_CONNECTOR_URL}/api/chats", headers=whatsapp_connector.headers())
            if resp.status_code == 200:
                return resp.json()
            return {"chats": [], "error": "Connector error"}
    except Exception as e:
        return {"chats": [], "error": str(e)}


@app.get("/api/whatsapp/chats/{chat_id}/messages")
async def get_whatsapp_chat_messages(chat_id: str, limit: int = 50):
    from urllib.parse import quote
    from whatsapp.connector import whatsapp_connector
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{config.WHATSAPP_CONNECTOR_URL}/api/chats/{quote(chat_id)}/messages?limit={limit}",
                headers=whatsapp_connector.headers(),
            )
            if resp.status_code == 200:
                return resp.json()
            return {"messages": [], "error": "Connector error"}
    except Exception as e:
        return {"messages": [], "error": str(e)}


@app.get("/api/whatsapp/media/{message_id}")
async def get_whatsapp_media(message_id: str):
    from urllib.parse import quote
    from whatsapp.connector import whatsapp_connector
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                f"{config.WHATSAPP_CONNECTOR_URL}/api/messages/{quote(message_id, safe='')}/media",
                headers=whatsapp_connector.headers(),
            )
            if resp.status_code != 200:
                return Response(content=resp.content, status_code=resp.status_code)

            headers = {"Cache-Control": resp.headers.get("cache-control", "private, max-age=3600")}
            disposition = resp.headers.get("content-disposition")
            if disposition:
                headers["Content-Disposition"] = disposition

            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "application/octet-stream"),
                headers=headers,
            )
    except Exception as e:
        return Response(content=str(e), status_code=502)


@app.post("/api/whatsapp/send")
async def send_whatsapp_message(request: Request):
    body = await request.json()
    chat_id = (body.get("chat_id") or body.get("chatId") or "").strip()
    phone = (body.get("phone") or "").strip()
    message = (body.get("message") or "").strip()

    if not message or not (chat_id or phone):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "chat_id/phone and message are required"},
        )

    payload = {"message": message}
    if chat_id:
        payload["chatId"] = chat_id
    else:
        payload["phone"] = phone

    try:
        from whatsapp.connector import whatsapp_connector
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{config.WHATSAPP_CONNECTOR_URL}/api/send",
                json=payload,
                headers=whatsapp_connector.headers(),
            )
        if resp.status_code != 200:
            return JSONResponse(status_code=resp.status_code, content={"success": False, "error": resp.text})

        result = resp.json()
        direct_phone = phone or (chat_id.split("@", 1)[0] if chat_id.endswith("@c.us") else None)
        actor = None
        if direct_phone:
            from database.db import SessionLocal
            from database.models import Customer, Conversation, Direction, CustomerStatus
            from auth import get_current_user, log_audit

            db = SessionLocal()
            try:
                actor = get_current_user(request, db)
                customer = db.query(Customer).filter(Customer.phone == direct_phone).first()
                if not customer:
                    customer = Customer(phone=direct_phone, status=CustomerStatus.NEW.value)
                    db.add(customer)
                    db.commit()

                conv = Conversation(
                    customer_id=customer.id,
                    whatsapp_message_id=result.get("message_id"),
                    direction=Direction.OUTBOUND.value,
                    message_text=message,
                    intent="agent_reply",
                    metadata_json={"source": "dashboard_live_inbox", "chat_id": chat_id or f"{phone}@c.us"},
                )
                db.add(conv)
                db.commit()
                log_audit("message.send", user=actor, entity_type="conversation", entity_id=conv.id, details={"phone": direct_phone, "chat_id": chat_id}, request=request)
            finally:
                db.close()

        try:
            from integrations import integration_manager
            await integration_manager.emit_event("message.outbound", {
                "phone": direct_phone or phone,
                "chat_id": chat_id or (f"{phone}@c.us" if phone else None),
                "message": message,
                "message_id": result.get("message_id"),
                "source": "dashboard_live_inbox",
            })
        except Exception as integration_error:
            print(f"[INTEGRATIONS] skipped: {integration_error}")

        return result
    except Exception as e:
        return JSONResponse(status_code=502, content={"success": False, "error": str(e)})


def compact_thread(messages: list[dict], limit: int = 30) -> str:
    lines = []
    for msg in messages[-limit:]:
        sender = "الموظف" if msg.get("fromMe") else "العميل"
        body = (msg.get("body") or "").strip()
        if not body and msg.get("hasMedia"):
            body = f"[{msg.get('type', 'media')}]"
        if body:
            lines.append(f"{sender}: {body}")
    return "\n".join(lines) or "لا توجد رسائل نصية كافية."


@app.post("/api/ai/assist")
async def ai_assist(request: Request):
    from ai.providers import ai_provider_manager

    body = await request.json()
    task = body.get("task", "suggest_reply")
    messages = body.get("messages") or []
    customer_name = body.get("customer_name") or "العميل"
    thread = compact_thread(messages)

    prompts = {
        "suggest_reply": (
            "أنت مساعد مبيعات واتساب محترف. اقترح رد عربي قصير وطبيعي للموظف فقط، "
            "بدون JSON وبدون شرح. لا تعد العميل بشيء غير موجود في المحادثة."
        ),
        "summary": (
            "لخص محادثة واتساب في نقاط قصيرة: احتياج العميل، الخدمة المطلوبة، آخر موقف، "
            "المتابعة المطلوبة. اكتب بالعربية."
        ),
        "extract_lead": (
            "استخرج بيانات فرصة البيع من المحادثة بصيغة JSON فقط بالمفاتيح: "
            "service_interest, lead_status, priority, estimated_value, next_action, notes."
        ),
    }
    system = prompts.get(task, prompts["suggest_reply"])

    try:
        result = ai_provider_manager.call_with_fallback(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"اسم العميل: {customer_name}\n\nالمحادثة:\n{thread}"},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return {
            "success": True,
            "task": task,
            "content": result["content"].strip(),
            "provider": result["provider_name"],
            "model": result["model"],
            "usage_log_id": result.get("usage_log_id"),
        }
    except Exception as e:
        return JSONResponse(status_code=502, content={"success": False, "error": str(e)})


@app.post("/api/ai/feedback")
async def ai_feedback(request: Request):
    from database.db import SessionLocal
    from database.models import AIUsageLog

    body = await request.json()
    usage_log_id = body.get("usage_log_id")
    feedback = body.get("feedback")
    note = (body.get("note") or "").strip()[:1000]
    if not usage_log_id or feedback not in {"up", "down"}:
        return JSONResponse(status_code=400, content={"success": False, "error": "Invalid feedback payload"})

    db = SessionLocal()
    try:
        log = db.query(AIUsageLog).filter(AIUsageLog.id == usage_log_id).first()
        if not log:
            return JSONResponse(status_code=404, content={"success": False, "error": "AI usage log not found"})
        log.feedback = feedback
        log.feedback_note = note or None
        db.commit()
        return {"success": True}
    finally:
        db.close()


@app.get("/api/inbox/meta/{chat_id}")
async def get_inbox_meta(chat_id: str):
    from database.db import SessionLocal
    from database.models import ChatMeta, InternalNote, User

    db = SessionLocal()
    try:
        meta = db.query(ChatMeta).filter(ChatMeta.chat_id == chat_id).first()
        notes = db.query(InternalNote).filter(InternalNote.chat_id == chat_id).order_by(InternalNote.created_at.desc()).limit(20).all()
        users = db.query(User).filter(User.is_active == True).order_by(User.username.asc()).all()
        return {
            "meta": {
                "chat_id": chat_id,
                "status": meta.status if meta else "open",
                "assigned_user_id": meta.assigned_user_id if meta else None,
                "assigned_username": meta.assigned_user.username if meta and meta.assigned_user else None,
                "tags": meta.tags if meta else "",
                "priority": meta.priority if meta else "medium",
            },
            "notes": [
                {
                    "id": n.id,
                    "note": n.note,
                    "username": n.username,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in notes
            ],
            "users": [{"id": u.id, "username": u.username, "role": u.role} for u in users],
        }
    finally:
        db.close()


@app.post("/api/inbox/meta")
async def save_inbox_meta(request: Request):
    from database.db import SessionLocal
    from database.models import ChatMeta
    from auth import get_current_user, log_audit

    body = await request.json()
    chat_id = (body.get("chat_id") or "").strip()
    if not chat_id:
        return JSONResponse(status_code=400, content={"success": False, "error": "chat_id is required"})

    db = SessionLocal()
    try:
        actor = get_current_user(request, db)
        meta = db.query(ChatMeta).filter(ChatMeta.chat_id == chat_id).first()
        if not meta:
            meta = ChatMeta(chat_id=chat_id)
            db.add(meta)
        meta.status = body.get("status") or meta.status or "open"
        meta.assigned_user_id = body.get("assigned_user_id") or None
        meta.tags = (body.get("tags") or "").strip()
        meta.priority = body.get("priority") or meta.priority or "medium"
        db.commit()
        log_audit("inbox.meta.update", user=actor, entity_type="chat", entity_id=chat_id, details={"status": meta.status, "assigned_user_id": meta.assigned_user_id}, request=request)
        return {"success": True}
    finally:
        db.close()


@app.post("/api/inbox/notes")
async def add_inbox_note(request: Request):
    from database.db import SessionLocal
    from database.models import ChatMeta, InternalNote
    from auth import get_current_user, log_audit

    body = await request.json()
    chat_id = (body.get("chat_id") or "").strip()
    note_text = (body.get("note") or "").strip()
    if not chat_id or not note_text:
        return JSONResponse(status_code=400, content={"success": False, "error": "chat_id and note are required"})

    db = SessionLocal()
    try:
        actor = get_current_user(request, db)
        meta = db.query(ChatMeta).filter(ChatMeta.chat_id == chat_id).first()
        if not meta:
            meta = ChatMeta(chat_id=chat_id)
            db.add(meta)
            db.commit()
        note = InternalNote(
            chat_id=chat_id,
            user_id=getattr(actor, "id", None),
            username=getattr(actor, "username", "local") if actor else "local",
            note=note_text,
        )
        db.add(note)
        db.commit()
        log_audit("inbox.note.create", user=actor, entity_type="chat", entity_id=chat_id, request=request)
        return {"success": True, "note_id": note.id}
    finally:
        db.close()


@app.post("/api/reports/generate")
async def trigger_reports():
    generate_reports_job()
    return {"status": "reports generated"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.DEBUG,
        log_level="info",
    )
