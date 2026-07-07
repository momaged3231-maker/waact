# WAACT PRD v4 - MVP V1.1

Product: WAACT
Release: MVP V1.1
PRD Version: v4
Primary market: Arabic ISP/customer support teams using WhatsApp

## Objective

MVP V1.1 turns WAACT into an operational Arabic WhatsApp CRM and ISP automation platform. The release combines live WhatsApp inbox, CRM workflows, AI assist, Radius Manager integration, campaigns, analytics, and controlled router/WiFi self-service.

The release must help support agents answer faster, reduce repetitive renewal/status requests, and safely automate WiFi password changes when router remote management is configured.

## Users

- Support agent: handles WhatsApp chats, sees customer/Radius/router context, changes WiFi password, creates handoff when automation fails.
- Sales agent: manages leads, pipeline, tasks, and campaigns.
- Manager/admin: reviews analytics, exports, users, audit logs, integrations, and maintenance.
- End customer: uses WhatsApp to ask about subscription status, renewal, package, connectivity, and WiFi password change.

## In Scope

- Arabic RTL dashboard.
- WhatsApp live inbox via whatsapp-web.js sidecar.
- CRM customers, conversations, leads, pipeline, follow-up tasks, handoffs, assignment, tags, and notes.
- AI Assist for suggested reply, summary, lead extraction, RAG answers, feedback, usage, and provider fallback.
- Knowledge base upload/versioning/re-indexing.
- Campaigns with variables, scheduling, opt-out, and Radius segments.
- Radius Manager configurable integration with lookup/link/snapshots/actions/logs/reminders.
- Router/WiFi management with dashboard, API, inbox card, WhatsApp self-service flow, and action logs.
- TP-Link/Huawei support through configurable Web/API endpoints or safe handoff.
- Optional authentication and audit logging.
- CSV exports, integrations/webhooks, analytics, and SQLite backup/restore.

## Out Of Scope

- Full payment gateway auto-renewal.
- Full TR-069/ACS implementation without ACS/vendor details.
- AI executing raw router commands.
- Multi-tenant SaaS isolation.
- Native mobile app.
- Full billing/accounting module.
- Guaranteed model-specific TP-Link/Huawei adapters without exact model/API details.

## Core Features

### WhatsApp Inbox

- Display live chats, messages, media, and unread counters from the WhatsApp connector.
- Send outbound WhatsApp messages from the dashboard.
- Show AI Assist actions: suggested reply, summary, lead extraction.
- Show chat meta panel: status, priority, assigned user, tags, internal notes.
- Show Radius Card for linked subscriber status and renewal actions.
- Show Router Card for linked router status and WiFi password change.

### CRM

- Store customers, conversations, leads, follow-up tasks, handoff requests, and internal notes.
- Use `users` table for inbox assignment.
- Keep auth optional for local MVP with `AUTH_ENABLED=false` by default.
- Support audit logs for sensitive admin/user actions.

### AI

- Use central multi-provider fallback for all AI calls.
- Track usage, estimated cost, latency, feedback, and provider health.
- Use RAG knowledge base for grounded Arabic answers.
- Never allow AI to execute raw router commands.

### Radius Manager

- Provide `/radius` settings/search/link/snapshots/logs UI.
- Support configurable base URL, auth, endpoints, field mapping, and actions.
- Support customer WhatsApp commands:
  - `حالة الاشتراك`
  - `موعد التجديد`
  - `الباقة`
  - `النت مش شغال`
  - `جدد`
- Support campaign segments:
  - `radius_expiring_3d`
  - `radius_expired`
  - `radius_active`
  - `radius_offline`
- Export Radius snapshots through `/export/radius.csv`.

### Router/WiFi Management

- Provide `/routers` dashboard for router linking, protocol settings, WiFi password changes, reboot/test, pending requests, and action logs.
- Link router by customer or Radius external ID.
- Support Dynamic Router Discovery so the operator does not need to add every customer router manually.
- Discover the current customer CPE/router IP at execution time from DMA/Radius sessions, Radius snapshots, or MikroTik PPP active sessions.
- Use a default CPE template for protocol, remote-management port, credentials, and HTTP payload when no static router exists.
- Supported protocols:
  - `manual`
  - `http_json`
  - `tplink_web`
  - `huawei_web`
  - `ssh`
  - `mikrotik_ssh`
  - `tr069` placeholder
- WhatsApp WiFi password flow:
  - Customer requests WiFi password change.
  - Bot asks for new password.
  - Bot validates length and simple characters.
  - Bot requests explicit confirmation.
  - Backend executes only configured protocol/template/API.
  - If router is missing, manual, unconfigured, or fails, create handoff instead of unsafe execution.
- Every router action must be logged in `RouterActionLog`.
- `إلغاء` must cancel a pending router flow without creating marketing opt-out.
- Manual/unconfigured TP-Link/Huawei requests must be visible in `/routers` and support can mark them completed or closed, with optional WhatsApp notification to the customer.

### Dynamic Router Discovery

- `/routers` includes Auto Discovery settings.
- Source order is configurable, for example `radius_sessions,radius_snapshot,mikrotik_ppp`.
- DMA/Radius mode reads the active session IP using configured `sessions_path` and session IP field names.
- Radius snapshot mode uses the mapped `ip_address` field from subscriber detail/snapshot.
- MikroTik mode can read `/ppp active` by subscriber username through SSH or RouterOS REST.
- The discovered IP is used only at execution time, so reconnects and changed IPs are handled by re-discovery.
- If no current IP is found, the request must be handed off safely.

## TP-Link/Huawei Strategy

Most TP-Link and Huawei CPE devices do not share one stable public API. MVP V1.1 therefore supports them safely through configurable protocol entries:

- Use `tplink_web` or `huawei_web` only when the endpoint/API for the exact model is known.
- Use HTTP path and payload template fields for known model endpoints.
- Use `manual` when remote management is unavailable or unknown.
- Prefer VPN/IP whitelist/internal network access over exposing router management to the public internet.
- Prefer future ACS/TR-069 integration when the operator has ACS details.
- Dynamic Discovery solves changing WAN IPs, but TP-Link/Huawei password execution still needs a known endpoint/session flow for the exact CPE model.

## Security Requirements

- Router credentials must not be returned in API responses.
- WiFi password changes require customer confirmation.
- AI is not allowed to run raw router commands.
- Router protocols execute only configured backend templates/endpoints.
- Optional auth is available through signed cookies.
- Admin-sensitive pages require role checks when auth is enabled.
- Webhook secret is supported.
- CSV/backup/restore are admin operational tools.

## Acceptance Criteria

- `/api/health` returns `200` and reports `version=1.1.0` and `release=MVP V1.1`.
- `/whatsapp-chats` renders and can show inbox when connector is connected.
- `/radius` renders and accepts configurable integration settings.
- `/routers` renders and accepts adding a router with blank optional port.
- `/api/routers/lookup?phone=...` returns linked router or `null` safely.
- `/api/routers/discover?phone=...` returns the current discovered host/source when DMA/Radius or MikroTik data is available.
- WhatsApp router flow starts, validates password, confirms, and can cancel with `إلغاء`.
- Router manual/unconfigured protocols create handoff instead of unsafe execution.
- Router manual/unconfigured requests can be completed/closed by support from `/routers`.
- `/analytics` shows Radius and Router metrics.
- `/export/radius.csv` and `/export/routers.csv` work.
- `init_db()` creates/migrates required SQLite tables.
- Python compile check passes for the main backend modules.

## Operational Configuration Needed Before Production

- Real Radius Manager endpoints, auth, field mappings, and actions.
- Most common TP-Link/Huawei models and their remote-management method.
- Network path to routers: VPN, internal server, public IP with whitelist, or ACS/TR-069.
- Router credential policy and access restrictions.
- Final Arabic WhatsApp message templates.
- User roles and admin credentials if `AUTH_ENABLED=true`.

## V1.2 Candidates

- Payment workflow and payment webhook.
- Radius activate/renew automation after verified payment.
- Real ACS/TR-069 integration.
- Model-specific TP-Link/Huawei adapters.
- Router credential encryption at rest.
- PostgreSQL migration and Docker deployment.
- Advanced SLA and team dashboards.
