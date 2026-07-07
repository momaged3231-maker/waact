# WAACT PRD v5 - MVP V1.3

Product: WAACT
Release: MVP V1.3
PRD Version: v5

## Objective

MVP V1.3 stabilizes the live WhatsApp automation flow for ISP usage. It focuses on reliable auto replies, safer handoff behavior, better Arabic intent matching, and operational readiness for dynamic router discovery through DMA/Radius or MikroTik.

## Delta From MVP V1.1

- Auto replies continue after Radius/Router errors instead of getting stuck in handover mode.
- Handover now pauses auto replies only when the customer explicitly asks for a human agent or an agent pauses the customer manually.
- Customer detail page includes controls to pause or resume automatic replies for one customer.
- WhatsApp connector tries to resolve real phone numbers from WhatsApp contacts instead of storing `@lid` identifiers when possible.
- WiFi password intent normalization supports Arabic variants like `واى فاى`, `واي فاي`, `كلمة سر`, `باسورد`, and English `wifi password`.
- Router Auto Discovery remains available for current CPE IP lookup from DMA/Radius sessions, Radius snapshots, or MikroTik PPP active sessions.

## Core Acceptance Criteria

- `/api/health` returns `version=1.3.0`, `release=MVP V1.3`, and `prd_version=v5`.
- Backend pages render: dashboard, live inbox, Radius, Routers, Analytics, Integrations, Maintenance.
- WhatsApp connector can connect and send incoming webhook calls using the configured secret.
- A Radius error can create a support ticket without setting `Customer.is_handover=True`.
- A customer asking clearly for a human agent can still pause auto replies.
- `/customer/{id}` can manually resume or pause automatic replies.
- WiFi password phrases using `واى فاى` trigger Router flow.
- `/api/routers/discover?phone=...` returns a safe response even when no current IP is found.
- Manual router requests can be completed or closed from `/routers`.

## Operational Notes

- If OpenAI quota is exhausted, RAG embedding search may log an error; configured AI fallback providers should still handle chat replies.
- DMA/Radius integration must be enabled and configured before subscription status replies become real customer data.
- TP-Link/Huawei password changes still require a known web/API endpoint or ACS/TR-069 flow for the exact model.
- Restart backend and connector after changing `.env`, connector `.env`, or Python/Node code.

## Demo Script

1. Show `/api/health` and `/settings` to confirm backend and WhatsApp connector.
2. Open `/whatsapp-chats` and send a message from a second phone.
3. Send `حالة الاشتراك`; if Radius is not configured, explain it creates support context without freezing AI.
4. Send `محتاج اغير باسورد الواى فاى`; show Router flow starts instead of generic AI fallback.
5. Open `/routers` and show Auto Discovery settings.
6. Open `/customers`, choose the test customer, and show pause/resume auto reply.
