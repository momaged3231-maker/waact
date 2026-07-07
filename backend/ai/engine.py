import json
import re
from config import config
from ai.prompts import SYSTEM_PROMPT, RAG_CONTEXT_PROMPT, CUSTOMER_MEMORY_PROMPT
from ai.providers import ai_provider_manager


class AIEngine:
    def __init__(self):
        pass

    def generate_response(
        self,
        message: str,
        customer_memory: dict = None,
        rag_context: str = None,
        conversation_history: list[dict] = None,
    ) -> dict:
        company_name = config.APP_NAME
        assistant_name = "مساعد واتساب"

        system = SYSTEM_PROMPT.format(
            company_name=company_name,
            assistant_name=assistant_name,
        )

        if rag_context:
            system += RAG_CONTEXT_PROMPT.format(rag_context=rag_context)

        if customer_memory:
            system += CUSTOMER_MEMORY_PROMPT.format(
                customer_name=customer_memory.get("name", "غير معروف"),
                last_seen_at=customer_memory.get("last_seen_at", "غير معروف"),
                message_count=customer_memory.get("message_count", 0),
                customer_status=customer_memory.get("status", "new"),
                interested_service=customer_memory.get("interested_service", "غير محدد"),
                last_intent=customer_memory.get("last_intent", "لا يوجد"),
                memory_summary=customer_memory.get("memory_summary", "لا يوجد"),
                is_handover=customer_memory.get("is_handover", False),
            )

        messages = [{"role": "system", "content": system}]

        if conversation_history:
            for msg in conversation_history[-5:]:
                role = "user" if msg.get("direction") == "inbound" else "assistant"
                text = msg.get("message_text", "")
                if role == "assistant":
                    text = msg.get("ai_response", msg.get("message_text", ""))
                if text:
                    messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": message})

        try:
            result = ai_provider_manager.call_with_fallback(
                messages=messages,
                temperature=config.TEMPERATURE,
                max_tokens=config.MAX_RESPONSE_TOKENS,
            )
            parsed = self._parse_response(result["content"])
            parsed["provider"] = result["provider"]
            parsed["provider_name"] = result["provider_name"]
            parsed["model"] = result["model"]
            parsed["fallback_errors"] = result["fallback_errors"]
            return parsed
        except Exception as e:
            return {
                "reply": "عذراً، حدث خطأ في النظام. سيتم تحويلك للدعم الفني.",
                "intent": "error",
                "service_interest": None,
                "needs_follow_up": False,
                "handoff_required": True,
                "handoff_reason": f"خطأ في النظام: {str(e)}",
                "lead_status": "needs_follow_up",
                "confidence": 0.0,
            }

    def _parse_response(self, content: str) -> dict:
        json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                reply = content[: json_match.start()].strip()
                if not reply:
                    reply = parsed.get("reply", "")
                return {
                    "reply": reply or parsed.get("reply", ""),
                    "intent": parsed.get("intent", "other"),
                    "service_interest": parsed.get("service_interest"),
                    "needs_follow_up": parsed.get("needs_follow_up", False),
                    "handoff_required": parsed.get("handoff_required", False),
                    "handoff_reason": parsed.get("handoff_reason"),
                    "lead_status": parsed.get("lead_status", "new"),
                    "confidence": parsed.get("confidence", 0.5),
                }
            except json.JSONDecodeError:
                pass

        lines = content.strip().split("\n")
        reply = ""
        intent = "other"
        service_interest = None
        needs_follow_up = False
        handoff_required = False
        handoff_reason = None
        lead_status = "new"
        confidence = 0.5

        for line in lines:
            line = line.strip()
            if line.upper().startswith("INTENT:") or line.upper().startswith("INTENTION:"):
                intent = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("SERVICE_INTEREST:"):
                val = line.split(":", 1)[1].strip()
                service_interest = val if val and val != "null" else None
            elif line.upper().startswith("NEED_FOLLOW_UP:"):
                needs_follow_up = line.split(":", 1)[1].strip().lower() == "true"
            elif line.upper().startswith("HANDOFF_REQUIRED:"):
                handoff_required = line.split(":", 1)[1].strip().lower() == "true"
            elif line.upper().startswith("HANDOFF_REASON:"):
                handoff_reason = line.split(":", 1)[1].strip()
            elif line.upper().startswith("LEAD_STATUS:"):
                lead_status = line.split(":", 1)[1].strip().lower()
            elif line.upper().startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.split(":", 1)[1].strip())
                except ValueError:
                    confidence = 0.5
            else:
                if not reply and line and not line.startswith("{"):
                    reply = line

        return {
            "reply": reply or "شكراً لتواصلك. سنعود إليك قريباً.",
            "intent": intent,
            "service_interest": service_interest,
            "needs_follow_up": needs_follow_up,
            "handoff_required": handoff_required,
            "handoff_reason": handoff_reason,
            "lead_status": lead_status,
            "confidence": confidence,
        }


ai_engine = AIEngine()
