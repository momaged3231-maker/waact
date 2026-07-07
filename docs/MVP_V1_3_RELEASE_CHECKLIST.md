# MVP V1.3 Release Checklist

## Required Checks

- [ ] `python check_mvp_v1_3.py` passes from `backend/`.
- [ ] `python -m py_compile main.py dashboard\routes.py database\models.py database\db.py whatsapp\webhook.py router_management.py router_service.py router_discovery.py radius.py radius_service.py workflows\message_flow.py workflows\handoff.py ai\memory.py` passes.
- [ ] `node --check index.js` passes from `whatsapp-connector/`.
- [ ] `/api/health` returns `1.3.0`, `MVP V1.3`, `v5`.
- [ ] `/api/status` reports database connected.
- [ ] `http://localhost:3001/api/status` reports `connected=true` after WhatsApp is ready.

## WhatsApp Auto Reply

- [ ] Incoming messages show `[INCOMING]` in connector logs.
- [ ] Successful replies show `[REPLIED]` in connector logs.
- [ ] `حالة الاشتراك` does not permanently pause automatic replies if Radius is disabled or errors.
- [ ] `محتاج اغير باسورد الواى فاى` enters Router WiFi password flow.
- [ ] Human phrases like `عايز موظف` can pause auto replies.

## Router/DMA/MikroTik

- [ ] `/routers` renders Auto Discovery settings.
- [ ] `/api/routers/discover?phone=...` returns a safe JSON response.
- [ ] DMA/Radius session IP field mapping is configured when available.
- [ ] MikroTik PPP active lookup is configured if used.
- [ ] Manual router requests can be completed/closed from `/routers`.

## Known Environment Issues

- [ ] OpenAI billing/quota is valid if OpenAI embeddings/RAG are required.
- [ ] AI fallback providers are configured in `/settings` if OpenAI quota is exhausted.
- [ ] Radius/DMA settings are configured before real subscription status answers are expected.
