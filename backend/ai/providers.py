import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from config import config


SETTINGS_PATH = Path(__file__).resolve().parent.parent / "ai_settings.json"


PROVIDER_DEFINITIONS = [
    {
        "id": "openai",
        "name": "OpenAI",
        "category": "OpenAI-compatible",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "site": "https://platform.openai.com/api-keys",
        "notes": "أفضل خيار عام للردود والـ RAG.",
        "type": "openai_compatible",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "category": "Aggregator",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
        "env_key": "OPENROUTER_API_KEY",
        "site": "https://openrouter.ai/keys",
        "notes": "مفيد كاحتياطي لأنه يفتح نماذج كثيرة من مكان واحد.",
        "type": "openai_compatible",
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude",
        "category": "Claude API",
        "base_url": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-3-5-haiku-latest",
        "env_key": "ANTHROPIC_API_KEY",
        "site": "https://console.anthropic.com/settings/keys",
        "notes": "قوي في المحادثات الطويلة واللغة العربية.",
        "type": "anthropic",
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "category": "Google AI",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-flash",
        "env_key": "GOOGLE_API_KEY",
        "site": "https://aistudio.google.com/app/apikey",
        "notes": "سريع ورخيص ومناسب كاحتياطي.",
        "type": "gemini",
    },
    {
        "id": "groq",
        "name": "Groq",
        "category": "OpenAI-compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-8b-instant",
        "env_key": "GROQ_API_KEY",
        "site": "https://console.groq.com/keys",
        "notes": "سريع جداً، ممتاز كfallback للردود القصيرة.",
        "type": "openai_compatible",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "category": "OpenAI-compatible",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "site": "https://platform.deepseek.com/api_keys",
        "notes": "تكلفة منخفضة وجودة جيدة.",
        "type": "openai_compatible",
    },
    {
        "id": "mistral",
        "name": "Mistral AI",
        "category": "OpenAI-compatible",
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-small-latest",
        "env_key": "MISTRAL_API_KEY",
        "site": "https://console.mistral.ai/api-keys",
        "notes": "نماذج أوروبية قوية وسريعة.",
        "type": "openai_compatible",
    },
    {
        "id": "together",
        "name": "Together AI",
        "category": "OpenAI-compatible",
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
        "env_key": "TOGETHER_API_KEY",
        "site": "https://api.together.xyz/settings/api-keys",
        "notes": "يقدم نماذج open-source كثيرة.",
        "type": "openai_compatible",
    },
    {
        "id": "fireworks",
        "name": "Fireworks AI",
        "category": "OpenAI-compatible",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "default_model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
        "env_key": "FIREWORKS_API_KEY",
        "site": "https://fireworks.ai/account/api-keys",
        "notes": "استضافة سريعة لنماذج Llama وغيرها.",
        "type": "openai_compatible",
    },
    {
        "id": "perplexity",
        "name": "Perplexity",
        "category": "OpenAI-compatible",
        "base_url": "https://api.perplexity.ai",
        "default_model": "sonar",
        "env_key": "PERPLEXITY_API_KEY",
        "site": "https://www.perplexity.ai/settings/api",
        "notes": "مفيد لو احتجت إجابات مدعومة بالبحث.",
        "type": "openai_compatible",
    },
    {
        "id": "xai",
        "name": "xAI Grok",
        "category": "OpenAI-compatible",
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-2-latest",
        "env_key": "XAI_API_KEY",
        "site": "https://console.x.ai/",
        "notes": "اختياري كاحتياطي إضافي.",
        "type": "openai_compatible",
    },
    {
        "id": "cohere",
        "name": "Cohere",
        "category": "Cohere Chat v2",
        "base_url": "https://api.cohere.com/v2/chat",
        "default_model": "command-r-plus",
        "env_key": "COHERE_API_KEY",
        "site": "https://dashboard.cohere.com/api-keys",
        "notes": "جيد للردود التجارية والـ RAG.",
        "type": "cohere",
    },
]


PLACEHOLDER_KEYS = {
    "",
    "sk-your-openai-key-here",
    "sk-your-key-here",
    "sk-xxxxxxxxxx",
    "your-api-key",
}

DEFAULT_GOVERNANCE = {
    "auto_disable_enabled": True,
    "failure_threshold": 3,
    "cooldown_minutes": 30,
}

TOKEN_COST_PER_1M = {
    "openai": {"input": 0.15, "output": 0.60},
    "openrouter": {"input": 0.20, "output": 0.80},
    "anthropic": {"input": 0.80, "output": 4.00},
    "gemini": {"input": 0.10, "output": 0.40},
    "groq": {"input": 0.05, "output": 0.08},
    "deepseek": {"input": 0.14, "output": 0.28},
    "mistral": {"input": 0.20, "output": 0.60},
    "together": {"input": 0.20, "output": 0.20},
    "fireworks": {"input": 0.20, "output": 0.20},
    "perplexity": {"input": 1.00, "output": 1.00},
    "xai": {"input": 2.00, "output": 10.00},
    "cohere": {"input": 2.50, "output": 10.00},
}


class AIProviderManager:
    def __init__(self):
        self.definitions = PROVIDER_DEFINITIONS

    def load_settings(self) -> dict[str, Any]:
        data = {"fallback_enabled": True, "governance": DEFAULT_GOVERNANCE.copy(), "providers": {}}
        if SETTINGS_PATH.exists():
            try:
                data.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
            except Exception:
                pass

        governance = data.setdefault("governance", {})
        for key, value in DEFAULT_GOVERNANCE.items():
            governance.setdefault(key, value)

        providers = data.setdefault("providers", {})
        for index, definition in enumerate(self.definitions, start=1):
            provider_id = definition["id"]
            env_key = os.getenv(definition["env_key"], "")
            existing = providers.get(provider_id, {})
            api_key = existing.get("api_key") or env_key
            providers[provider_id] = {
                "enabled": bool(existing.get("enabled", provider_id == "openai" and self.has_real_key(api_key))),
                "priority": int(existing.get("priority", index)),
                "model": existing.get("model") or definition["default_model"],
                "base_url": existing.get("base_url") or definition["base_url"],
                "api_key": api_key,
                "failure_count": int(existing.get("failure_count") or 0),
                "disabled_until": existing.get("disabled_until"),
                "last_error": existing.get("last_error"),
            }
        return data

    def save_from_form(self, form) -> None:
        current = self.load_settings()
        updated = {
            "fallback_enabled": form.get("fallback_enabled") == "on",
            "governance": {
                "auto_disable_enabled": form.get("auto_disable_enabled") == "on",
                "failure_threshold": self.form_int(form, "failure_threshold", DEFAULT_GOVERNANCE["failure_threshold"], 1, 20),
                "cooldown_minutes": self.form_int(form, "cooldown_minutes", DEFAULT_GOVERNANCE["cooldown_minutes"], 1, 1440),
            },
            "providers": {},
        }

        for definition in self.definitions:
            provider_id = definition["id"]
            existing = current["providers"].get(provider_id, {})
            new_key = (form.get(f"{provider_id}_api_key") or "").strip()
            api_key = new_key or existing.get("api_key", "")
            try:
                priority = int(form.get(f"{provider_id}_priority") or existing.get("priority", 99))
            except ValueError:
                priority = 99

            updated["providers"][provider_id] = {
                "enabled": form.get(f"{provider_id}_enabled") == "on",
                "priority": priority,
                "model": (form.get(f"{provider_id}_model") or definition["default_model"]).strip(),
                "base_url": (form.get(f"{provider_id}_base_url") or definition["base_url"]).strip().rstrip("/"),
                "api_key": api_key,
                "failure_count": 0,
                "disabled_until": None,
                "last_error": None,
            }

        self.write_settings(updated)

    def status_for_ui(self) -> dict[str, Any]:
        settings = self.load_settings()
        cards = []
        for definition in self.definitions:
            provider_id = definition["id"]
            provider = settings["providers"][provider_id]
            has_key = self.has_real_key(provider.get("api_key", ""))
            temporarily_disabled = self.is_provider_temporarily_disabled(provider)
            cards.append({
                **definition,
                **provider,
                "has_key": has_key,
                "masked_key": self.mask_key(provider.get("api_key", "")),
                "temporarily_disabled": temporarily_disabled,
                "ready": provider.get("enabled") and has_key and not temporarily_disabled,
            })

        cards.sort(key=lambda item: item.get("priority", 99))
        return {
            "fallback_enabled": settings.get("fallback_enabled", True),
            "governance": settings.get("governance", DEFAULT_GOVERNANCE),
            "providers": cards,
            "ready_count": sum(1 for card in cards if card["ready"]),
        }

    def call_with_fallback(self, messages: list[dict], temperature: float, max_tokens: int) -> dict[str, Any]:
        settings = self.load_settings()
        providers = []
        skipped_disabled = []
        for definition in self.definitions:
            provider = settings["providers"].get(definition["id"], {})
            if provider.get("enabled") and self.has_real_key(provider.get("api_key", "")):
                merged = {**definition, **provider}
                if self.is_provider_temporarily_disabled(merged):
                    skipped_disabled.append({"provider": definition["id"], "error": "temporarily disabled"})
                    continue
                providers.append(merged)

        providers.sort(key=lambda item: item.get("priority", 99))
        if not providers:
            if skipped_disabled:
                raise RuntimeError("All configured AI providers are temporarily disabled by governance rules.")
            raise RuntimeError("No AI provider configured. Add an API key in Settings > AI Providers.")

        errors = skipped_disabled[:]
        for provider in providers:
            started = time.perf_counter()
            try:
                content = self.call_provider(provider, messages, temperature, max_tokens)
                prompt_tokens = self.estimate_message_tokens(messages)
                completion_tokens = self.estimate_text_tokens(content)
                usage_log_id = self.log_usage(
                    provider=provider,
                    task_type="chat",
                    success=True,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost_usd=self.estimate_cost(provider, prompt_tokens, completion_tokens),
                )
                self.update_provider_health(provider["id"], success=True)
                return {
                    "content": content,
                    "provider": provider["id"],
                    "provider_name": provider["name"],
                    "model": provider["model"],
                    "fallback_errors": errors,
                    "usage_log_id": usage_log_id,
                }
            except Exception as exc:
                self.update_provider_health(provider["id"], success=False, error=str(exc))
                self.log_usage(
                    provider=provider,
                    task_type="chat",
                    success=False,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error=str(exc)[:1000],
                )
                errors.append({
                    "provider": provider["id"],
                    "model": provider.get("model"),
                    "error": str(exc)[:500],
                })
                if not settings.get("fallback_enabled", True):
                    break

        summary = " | ".join(f"{e['provider']}: {e['error']}" for e in errors)
        raise RuntimeError(f"All AI providers failed. {summary}")

    def log_usage(
        self,
        provider: dict[str, Any],
        task_type: str,
        success: bool,
        latency_ms: int | None = None,
        error: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
    ) -> str | None:
        try:
            from database.db import SessionLocal
            from database.models import AIUsageLog

            db = SessionLocal()
            try:
                log = AIUsageLog(
                    provider=provider.get("id") or provider.get("name", "unknown"),
                    model=provider.get("model"),
                    task_type=task_type,
                    success=success,
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost_usd=estimated_cost_usd,
                    error=error,
                )
                db.add(log)
                db.commit()
                return log.id
            finally:
                db.close()
        except Exception:
            return None

    def test_provider(self, provider_id: str) -> dict[str, Any]:
        settings = self.load_settings()
        definition = next((item for item in self.definitions if item["id"] == provider_id), None)
        if not definition:
            return {"ok": False, "error": "Unknown provider"}

        provider = {**definition, **settings["providers"].get(provider_id, {})}
        if not self.has_real_key(provider.get("api_key", "")):
            return {"ok": False, "error": "API key is missing"}

        try:
            content = self.call_provider(
                provider,
                [
                    {"role": "system", "content": "Reply with OK only."},
                    {"role": "user", "content": "test"},
                ],
                temperature=0,
                max_tokens=20,
            )
            self.update_provider_health(provider_id, success=True)
            return {
                "ok": True,
                "provider": definition["name"],
                "model": provider["model"],
                "reply": content.strip()[:100],
            }
        except Exception as exc:
            self.update_provider_health(provider_id, success=False, error=str(exc))
            return {"ok": False, "error": str(exc)[:500]}

    def update_provider_health(self, provider_id: str, success: bool, error: str | None = None) -> None:
        settings = self.load_settings()
        provider = settings.get("providers", {}).get(provider_id)
        if not provider:
            return

        if success:
            provider["failure_count"] = 0
            provider["disabled_until"] = None
            provider["last_error"] = None
        else:
            governance = settings.get("governance", DEFAULT_GOVERNANCE)
            provider["failure_count"] = int(provider.get("failure_count") or 0) + 1
            provider["last_error"] = (error or "")[:500]
            if governance.get("auto_disable_enabled", True) and provider["failure_count"] >= int(governance.get("failure_threshold") or 3):
                cooldown = int(governance.get("cooldown_minutes") or 30)
                provider["disabled_until"] = (datetime.now(timezone.utc) + timedelta(minutes=cooldown)).isoformat()

        self.write_settings(settings)

    def is_provider_temporarily_disabled(self, provider: dict[str, Any]) -> bool:
        disabled_until = self.parse_datetime(provider.get("disabled_until"))
        return bool(disabled_until and disabled_until > datetime.now(timezone.utc))

    def parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            return None

    def estimate_message_tokens(self, messages: list[dict]) -> int:
        return sum(self.estimate_text_tokens(message.get("content", "")) for message in messages)

    def estimate_text_tokens(self, text: str) -> int:
        return max(1, len(text or "") // 4)

    def estimate_cost(self, provider: dict[str, Any], prompt_tokens: int, completion_tokens: int) -> float:
        rates = TOKEN_COST_PER_1M.get(provider.get("id"), {"input": 0, "output": 0})
        cost = (prompt_tokens * rates["input"] + completion_tokens * rates["output"]) / 1_000_000
        return round(cost, 6)

    def form_int(self, form, key: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(form.get(key) or default)
        except ValueError:
            value = default
        return max(minimum, min(value, maximum))

    def write_settings(self, settings: dict[str, Any]) -> None:
        SETTINGS_PATH.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def call_provider(self, provider: dict[str, Any], messages: list[dict], temperature: float, max_tokens: int) -> str:
        provider_type = provider["type"]
        if provider_type == "anthropic":
            return self.call_anthropic(provider, messages, temperature, max_tokens)
        if provider_type == "gemini":
            return self.call_gemini(provider, messages, temperature, max_tokens)
        if provider_type == "cohere":
            return self.call_cohere(provider, messages, temperature, max_tokens)
        return self.call_openai_compatible(provider, messages, temperature, max_tokens)

    def call_openai_compatible(self, provider: dict[str, Any], messages: list[dict], temperature: float, max_tokens: int) -> str:
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        if provider["id"] == "openrouter":
            headers["HTTP-Referer"] = config.APP_URL
            headers["X-Title"] = "WAACT"

        payload = {
            "model": provider["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self.post_json(f"{provider['base_url'].rstrip('/')}/chat/completions", headers, payload)
        return data["choices"][0]["message"]["content"]

    def call_anthropic(self, provider: dict[str, Any], messages: list[dict], temperature: float, max_tokens: int) -> str:
        system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
        chat_messages = [
            {"role": m.get("role"), "content": m.get("content", "")}
            for m in messages
            if m.get("role") in {"user", "assistant"}
        ]
        payload = {
            "model": provider["model"],
            "system": "\n\n".join(system_parts),
            "messages": chat_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = self.post_json(
            provider["base_url"],
            {
                "x-api-key": provider["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload,
        )
        return "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")

    def call_gemini(self, provider: dict[str, Any], messages: list[dict], temperature: float, max_tokens: int) -> str:
        system_text = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
        contents = []
        injected_system = False
        for message in messages:
            role = message.get("role")
            if role == "system":
                continue
            gemini_role = "model" if role == "assistant" else "user"
            text = message.get("content", "")
            if gemini_role == "user" and system_text and not injected_system:
                text = f"{system_text}\n\n{text}"
                injected_system = True
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

        if not contents and system_text:
            contents.append({"role": "user", "parts": [{"text": system_text}]})

        url = f"{provider['base_url'].rstrip('/')}/models/{provider['model']}:generateContent?key={provider['api_key']}"
        data = self.post_json(url, {"Content-Type": "application/json"}, {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        })
        parts = data["candidates"][0]["content"].get("parts", [])
        return "".join(part.get("text", "") for part in parts)

    def call_cohere(self, provider: dict[str, Any], messages: list[dict], temperature: float, max_tokens: int) -> str:
        data = self.post_json(
            provider["base_url"],
            {
                "Authorization": f"Bearer {provider['api_key']}",
                "Content-Type": "application/json",
            },
            {
                "model": provider["model"],
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        content = data.get("message", {}).get("content", [])
        return "".join(part.get("text", "") for part in content)

    def post_json(self, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def has_real_key(self, api_key: str) -> bool:
        key = (api_key or "").strip()
        if not key:
            return False
        if key.lower() in PLACEHOLDER_KEYS:
            return False
        return "your" not in key.lower() and "xxxx" not in key.lower()

    def mask_key(self, api_key: str) -> str:
        if not self.has_real_key(api_key):
            return "غير مضاف"
        if len(api_key) <= 12:
            return "***"
        return f"{api_key[:6]}...{api_key[-4:]}"


ai_provider_manager = AIProviderManager()
