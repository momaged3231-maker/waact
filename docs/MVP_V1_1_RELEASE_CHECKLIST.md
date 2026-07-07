# MVP V1.1 Release Checklist

Use this checklist before presenting WAACT MVP V1.1 as ready for operational testing.

## Backend

- [ ] `python check_mvp_v1_1.py` from `backend/` passes for local MVP verification.
- [ ] `python -m py_compile main.py dashboard\routes.py database\models.py database\db.py whatsapp\webhook.py router_management.py router_service.py radius.py radius_service.py`
- [ ] `python -c "from database.db import init_db; init_db(); print('db init ok')"`
- [ ] `/api/health` returns `200` with `version=1.1.0` and `release=MVP V1.1`.
- [ ] `/api/status` returns database connectivity.

## Pages

- [ ] `/` dashboard loads.
- [ ] `/whatsapp-chats` loads.
- [ ] `/radius` loads.
- [ ] `/routers` loads.
- [ ] `/analytics` loads.
- [ ] `/integrations` loads.
- [ ] `/maintenance` loads.

## Radius

- [ ] Radius settings saved from `/radius`.
- [ ] `/radius/test` returns expected result for current environment.
- [ ] `/api/radius/lookup?phone=...` returns linked snapshot/candidates or safe error.
- [ ] `/export/radius.csv` downloads.

## Routers

- [ ] Router can be added from `/routers` with blank optional port.
- [ ] `/api/routers/lookup?phone=...` returns linked router or `null`.
- [ ] Auto Discovery can be configured from `/routers`.
- [ ] `/api/routers/discover?phone=...` returns current CPE IP when DMA/Radius session or MikroTik PPP active data exists.
- [ ] Dynamic discovery re-checks IP at execution time, not only when request starts.
- [ ] `manual` router protocol creates handoff/manual result instead of unsafe execution.
- [ ] `tplink_web` and `huawei_web` require configured HTTP endpoint before automatic execution.
- [ ] Manual/unconfigured WiFi requests can be marked completed or closed from `/routers`.
- [ ] Router action appears in `RouterActionLog`.
- [ ] `/export/routers.csv` downloads.

## WhatsApp

- [ ] WhatsApp connector starts on `http://localhost:3001`.
- [ ] QR login succeeds.
- [ ] `/api/whatsapp/chats` returns chats when connected.
- [ ] Sending from inbox works.
- [ ] Incoming webhook respects `X-Webhook-Secret` when configured.

## WiFi Password Self-Service

- [ ] Customer sends `تغيير باسورد الواي فاي`.
- [ ] Bot asks for the new password.
- [ ] Invalid password is rejected.
- [ ] `إلغاء` cancels the router flow and does not create opt-out.
- [ ] `تأكيد` executes only configured backend protocol/template/API.
- [ ] Failed or unconfigured router creates handoff.

## Security

- [ ] `AUTH_ENABLED=false` is intentional for local MVP, or `AUTH_ENABLED=true` is configured for production testing.
- [ ] `SECRET_KEY` changed if auth is enabled.
- [ ] Router remote management is limited by VPN/IP whitelist/internal network where possible.
- [ ] Router credentials are not returned by API responses.
- [ ] AI provider keys and Radius/router settings are not committed.

## Known Non-Blocking Warnings

- Chroma telemetry warning `capture() takes 1 positional argument but 3 were given` is harmless for MVP operation.
