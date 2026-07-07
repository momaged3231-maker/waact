from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from database.db import SessionLocal
from database.models import Customer, CustomerStatus, Conversation, Direction, OptOut
from workflows.message_flow import message_flow
from workflows.handoff import handoff_manager
from config import config
from automation import automation_engine
from media_intelligence import media_intelligence
from integrations import integration_manager
from radius_service import radius_service
from router_service import router_service

router = APIRouter()


def has_meaningful_text(text: str | None) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    return not (value.startswith("[") and value.endswith("]"))


def get_or_create_customer(db, phone: str) -> Customer:
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer:
        customer = Customer(phone=phone, status=CustomerStatus.NEW.value)
        db.add(customer)
        db.commit()
    customer.last_seen_at = datetime.now(timezone.utc)
    return customer


async def run_inbound_automation(db, phone: str, message_text: str, result: dict, extra: dict | None = None):
    try:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        context = {
            "customer": customer,
            "phone": phone,
            "chat_id": f"{phone}@c.us",
            "message_text": message_text,
            "intent": result.get("intent", "other"),
            "ai_result": result,
        }
        if extra:
            context.update(extra)
        await automation_engine.run(db, "inbound_message", context)
    except Exception as automation_error:
        print(f"[AUTOMATION] skipped: {automation_error}")
    try:
        payload = {
            "phone": phone,
            "chat_id": f"{phone}@c.us",
            "message": message_text,
            "intent": result.get("intent", "other"),
            "handoff_required": result.get("handoff_required", False),
        }
        if extra:
            payload.update({k: v for k, v in extra.items() if k in {"media_type", "media_analysis"}})
        await integration_manager.emit_event("message.inbound", payload)
    except Exception as integration_error:
        print(f"[INTEGRATIONS] skipped: {integration_error}")


def media_fallback_reply(media_type: str | None, analysis: dict) -> str:
    if analysis.get("status") in {"ocr_unavailable", "pdf_unavailable", "transcription_unavailable"}:
        return "وصلتني الوسائط، لكن تحليل هذا النوع غير مفعل حالياً. اكتب طلبك نصياً وسأساعدك فوراً."
    return "وصلتني الوسائط. أرسل لي رسالة نصية توضّح طلبك حتى أقدر أساعدك بدقة."


@router.post("/api/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    secret = request.headers.get("X-Webhook-Secret", "")
    if config.WHATSAPP_WEBHOOK_SECRET and secret != config.WHATSAPP_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    body = await request.json()
    phone = body.get("phone")
    message_text = body.get("message")
    message_id = body.get("message_id")
    media_type = body.get("media_type")

    if not phone or not message_text:
        raise HTTPException(status_code=400, detail="Phone and message are required")

    db = SessionLocal()
    try:
        if message_text.strip().casefold() in {"إلغاء", "الغاء"} and not router_service.active_pending(db, phone):
            opt_out = db.query(OptOut).filter(OptOut.phone == phone).first()
            if not opt_out:
                db.add(OptOut(phone=phone, reason="campaign_keyword"))
                db.commit()
            return {
                "reply": "تم إلغاء اشتراكك في الرسائل التسويقية. يمكنك مراسلتنا في أي وقت عند الحاجة.",
                "intent": "opt_out",
                "handoff_required": False,
            }

        if not media_type or media_type == "text":
            router_result = await router_service.handle_whatsapp_command(db, phone, message_text)
            if router_result:
                customer = get_or_create_customer(db, phone)
                conversation = Conversation(
                    customer_id=customer.id,
                    whatsapp_message_id=message_id,
                    direction=Direction.INBOUND.value,
                    message_text=message_text,
                    ai_response=router_result.get("reply"),
                    intent=router_result.get("intent", "router_command"),
                    handoff_required=router_result.get("handoff_required", False),
                    metadata_json={"source": "router_command"},
                )
                db.add(conversation)
                if router_result.get("handoff_required"):
                    handoff_manager.create_handoff_request(
                        db=db,
                        customer=customer,
                        reason=router_result.get("handoff_reason") or "Router command handoff",
                        conversation_summary=customer.memory_summary,
                        pause_auto_reply=router_result.get("pause_auto_reply", False),
                    )
                else:
                    db.commit()
                await run_inbound_automation(db, phone, message_text, router_result, {"source": "router_command"})
                return {
                    "reply": router_result.get("reply", ""),
                    "intent": router_result.get("intent", "router_command"),
                    "handoff_required": router_result.get("handoff_required", False),
                }

            radius_result = await radius_service.handle_whatsapp_command(db, phone, message_text)
            if radius_result:
                customer = get_or_create_customer(db, phone)
                conversation = Conversation(
                    customer_id=customer.id,
                    whatsapp_message_id=message_id,
                    direction=Direction.INBOUND.value,
                    message_text=message_text,
                    ai_response=radius_result.get("reply"),
                    intent=radius_result.get("intent", "radius_command"),
                    handoff_required=radius_result.get("handoff_required", False),
                    metadata_json={"source": "radius_command"},
                )
                db.add(conversation)
                if radius_result.get("handoff_required"):
                    handoff_manager.create_handoff_request(
                        db=db,
                        customer=customer,
                        reason=radius_result.get("handoff_reason") or "Radius command handoff",
                        conversation_summary=customer.memory_summary,
                        pause_auto_reply=radius_result.get("pause_auto_reply", False),
                    )
                else:
                    db.commit()
                await run_inbound_automation(db, phone, message_text, radius_result, {"source": "radius_command"})
                return {
                    "reply": radius_result.get("reply", ""),
                    "intent": radius_result.get("intent", "radius_command"),
                    "handoff_required": radius_result.get("handoff_required", False),
                }

        if media_type and media_type != "text":
            analysis = await media_intelligence.analyze_whatsapp_media(message_id, media_type)
            extracted_text = (analysis.get("text") or "").strip()
            message_parts = []
            if has_meaningful_text(message_text):
                message_parts.append(message_text.strip())
            if extracted_text:
                message_parts.append(f"نص مستخرج من الوسائط:\n{extracted_text}")

            if message_parts:
                enriched_text = "\n\n".join(message_parts)
                result = message_flow.process_incoming_message(
                    db=db,
                    phone=phone,
                    message_text=enriched_text,
                    whatsapp_message_id=message_id,
                )
                conversation = (
                    db.query(Conversation)
                    .filter(Conversation.whatsapp_message_id == message_id)
                    .order_by(Conversation.created_at.desc())
                    .first()
                )
                if conversation:
                    conversation.metadata_json = {"media_type": media_type, "media_analysis": analysis}
                    db.commit()
                await run_inbound_automation(db, phone, enriched_text, result, {"media_type": media_type, "media_analysis": analysis})
                return {
                    "reply": result.get("reply", ""),
                    "intent": result.get("intent", "other"),
                    "handoff_required": result.get("handoff_required", False),
                }

            customer = get_or_create_customer(db, phone)
            conversation = Conversation(
                customer_id=customer.id,
                whatsapp_message_id=message_id,
                direction=Direction.INBOUND.value,
                message_text=message_text or f"[{media_type}]",
                intent="media_received",
                metadata_json={"media_type": media_type, "media_analysis": analysis},
            )
            db.add(conversation)
            db.commit()
            result = {
                "reply": media_fallback_reply(media_type, analysis),
                "intent": "media_received",
                "handoff_required": False,
            }
            await run_inbound_automation(db, phone, conversation.message_text, result, {"media_type": media_type, "media_analysis": analysis})
            return result

        result = message_flow.process_incoming_message(
            db=db,
            phone=phone,
            message_text=message_text,
            whatsapp_message_id=message_id,
        )
        await run_inbound_automation(db, phone, message_text, result)
        return {
            "reply": result.get("reply", ""),
            "intent": result.get("intent", "other"),
            "handoff_required": result.get("handoff_required", False),
        }
    except Exception as e:
        return {
            "reply": "عذراً، حدث خطأ في معالجة رسالتك. سيتم التواصل معك قريباً.",
            "intent": "error",
            "handoff_required": True,
        }
    finally:
        db.close()
