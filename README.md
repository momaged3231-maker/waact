# WAACT - WhatsApp Automation System (نظام أتمتة الواتساب الذكي)

Current release: MVP V1.3
PRD: `docs/PRD_V5_MVP_V1_3.md`
Release checklist: `docs/MVP_V1_3_RELEASE_CHECKLIST.md`

نظام عربي لإدارة واتساب وCRM وأتمتة شركات الإنترنت، يشمل Inbox مباشر، AI Assist، RAG، Radius Manager، حملات، وتحكم آمن في راوترات العملاء وتغيير باسورد الواي فاي عند تفعيل remote management.

MVP V1.1 يدعم Dynamic Router Discovery: يمكن قراءة IP الراوتر الحالي من DMA/Radius sessions أو MikroTik PPP active بدل إضافة IP ثابت لكل عميل.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  WhatsApp Client (whatsapp-web.js)                          │
│  QR Code Authentication → Message Listener → HTTP Webhook  │
└───────────────────┬─────────────────────────────────────────┘
                    │ POST /api/whatsapp/webhook
                    ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend (Python)                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐│
│  │ Message  │  │   AI     │  │   RAG    │  │   Database   ││
│  │ Pipeline │→│  Engine  │→│  Search  │→│  (SQLAlchemy) ││
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘│
│         │            │            │              │          │
│         ▼            ▼            ▼              ▼          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐│
│  │  Memory  │  │ Prompts  │  │ChromaDB  │  │  Customers   ││
│  │ Manager  │  │ (Arabic) │  │(Vectors) │  │ Conversations ││
│  └──────────┘  └──────────┘  └──────────┘  │  Leads        ││
│         │                                   │  Reports      ││
│         ▼                                   └──────────────┘│
│  ┌─────────────────┐                                       │
│  │   Dashboard      │ ← HTML + Chart.js                     │
│  │   / (Overview)   │                                       │
│  │   /customers     │                                       │
│  │   /conversations │                                       │
│  │   /leads         │                                       │
│  │   /reports       │                                       │
│  │   /knowledge     │                                       │
│  │   /handoffs      │                                       │
│  └─────────────────┘                                       │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | Python FastAPI |
| **Database** | SQLAlchemy + SQLite (PostgreSQL-ready) |
| **Vector DB** | ChromaDB |
| **AI/LLM** | OpenAI (GPT-4o-mini, text-embedding-3-small) |
| **WhatsApp** | whatsapp-web.js (Node.js sidecar) |
| **Dashboard** | Jinja2 Templates + Chart.js |
| **Scheduling** | APScheduler |

## Database Schema

### customers
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| phone | String (unique) | Phone number |
| name | String? | Customer name |
| status | Enum | new, interested, needs_follow_up, sold, not_interested |
| memory_summary | Text? | Conversation memory |
| interested_service | String? | Service they asked about |
| last_intent | String? | Last detected intent |
| is_handover | Boolean | Handed to human? |

### conversations
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| customer_id | FK | References customers |
| direction | Enum | inbound/outbound |
| message_text | Text | Message content |
| ai_response | Text? | AI generated reply |
| intent | String? | Detected intent |
| confidence | Float? | AI confidence |

### leads
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| customer_id | FK (unique) | References customers |
| service_interest | String? | Service interested in |
| lead_status | Enum | new, contacted, qualified, proposal, negotiation, won, lost |
| priority | Enum | low, medium, high |

### knowledge_documents
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| title | String | Document title |
| category | String | services, pricing, faq, etc. |
| content | Text | Full content |
| chunk_count | Integer | Number of chunks in vector DB |

### handoff_requests
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| customer_id | FK | References customers |
| reason | Text | Why handoff needed |
| status | Enum | pending, accepted, resolved, rejected |

### reports
| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary Key |
| report_type | String | daily, weekly, monthly |
| report_data | JSON | Full report data |

## Workflows

### 1. Message Processing
```
WhatsApp Message → Get/Create Customer → Store Message
  → Search RAG (Vector DB) → Build Context
  → AI Engine (System Prompt + RAG + Memory) → Generate Reply
  → Update Memory (Intent, Status, Lead) → Send Reply → Store Reply
```

### 2. Knowledge Ingestion
```
Add Document → Clean Text → Chunk (500 tokens, 50 overlap)
  → Generate Embeddings → Store in ChromaDB → Record in DB
```

### 3. Memory Update (after each conversation)
```
Analyze Conversation → Extract Intent → Extract Service Interest
  → Update Memory Summary → Update Lead Status → Set Follow-up
```

### 4. Human Handoff
```
Customer Asks → Create Handoff Request → Notify Dashboard
  → Pause Auto-Reply → Agent Accepts → Agent Resolves
```

### 5. Reports Generation (daily/weekly/monthly)
```
Count Messages → Count New Customers → Count Leads
  → Top Services → Top Intents → Handoff Stats
  → Auto-Reply Rate → Store Report → (Future: Email/Telegram)
```

## Prompts

### AI System Prompt
يقوم البوت بالرد على استفسارات العملاء بناءً على:

| Element | Description |
|---------|-------------|
| **Role** | مساعد خدمة عملاء ذكي ومحترف |
| **Language** | عربية فصيحة مفهومة |
| **Rules** | ردود قصيرة (2-4 جمل)، لا يخترع معلومات، يعتمد على RAG |
| **Format** | Reply + JSON with intent, service_interest, handoff flags |

### RAG Context Prompt
```
استخدم ONLY المعلومات المقدمة في [المعرفة المتاحة] للإجابة.
إذا لم تحتوِ المعرفة على الإجابة، اعرض تحويل الطلب للدعم.
```

### Memory Update Prompt
```
تحليل المحادثة واستخراج:
- memory_summary (ملخص المحادثة)
- intent (النية النهائية)
- service_interest (الخدمة المهتم بها)
- customer_status (تحديث حالة العميل)
- lead_status (تحديث حالة الفرصة)
- needs_follow_up (هل يحتاج متابعة)
```

## Dashboard Features

| Page | Content |
|------|---------|
| **/ (Overview)** | Key metrics, message chart, customer status chart, recent conversations, pending handoffs |
| **/conversations** | All messages with filters, search by customer |
| **/customers** | Customer list with status, detail view with chat history |
| **/leads** | Lead pipeline with status and priority filters |
| **/reports** | Daily/Weekly/Monthly reports with charts and KPIs |
| **/knowledge** | Add/delete knowledge documents, browse by category |
| **/handoffs** | Pending/accepted/resolved handoff requests with actions |
| **/settings** | System status, connection info, instructions |

## Setup & Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- OpenAI API Key

### Quick Start
```bash
# 1. Install Python dependencies
cd backend
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY

# 3. Initialize database & seed knowledge
python seed_knowledge.py

# 4. Start backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 5. (In another terminal) Start WhatsApp connector
cd whatsapp-connector
npm install
npm start
# Scan QR code with WhatsApp
```

### Using start.bat (Windows)
```bash
.\start.bat
```

### Access Dashboard
- Dashboard: http://localhost:8000
- API Health: http://localhost:8000/api/health

### MVP V1.3 Verification
```bash
cd backend
python check_mvp_v1_3.py
```

### Router Auto Discovery
- افتح `/routers`.
- فعّل Auto Discovery.
- استخدم `radius_sessions,radius_snapshot,mikrotik_ppp` حسب المتاح عندك.
- DMA/Radius يحتاج `sessions_path` وحقول IP صحيحة في `/radius`.
- MikroTik يحتاج SSH أو RouterOS REST للوصول إلى PPP active sessions.
- بعد معرفة IP الحالي، يستخدم النظام template افتراضي لبروتوكول CPE مثل `tplink_web` أو `huawei_web`.

## Project Structure
```
waact/
├── backend/                    # Python FastAPI Backend
│   ├── main.py                # Main app entry
│   ├── config.py              # Configuration
│   ├── seed_knowledge.py      # Knowledge ingestion script
│   ├── .env.example           # Environment variables template
│   ├── database/
│   │   ├── db.py              # Database connection
│   │   └── models.py          # SQLAlchemy models
│   ├── ai/
│   │   ├── engine.py          # AI response generation
│   │   ├── prompts.py         # System prompts (Arabic)
│   │   └── memory.py          # Memory management
│   ├── rag/
│   │   ├── vector_store.py    # ChromaDB wrapper
│   │   ├── embeddings.py      # OpenAI embeddings
│   │   └── knowledge.py       # Knowledge ingestion
│   ├── workflows/
│   │   ├── message_flow.py    # Message processing pipeline
│   │   ├── handoff.py         # Human handoff workflow
│   │   └── reporting.py       # Reports generation
│   ├── dashboard/
│   │   ├── routes.py          # Dashboard endpoints
│   │   └── templates/         # HTML templates (RTL)
│   └── whatsapp/
│       ├── connector.py       # WhatsApp connector client
│       └── webhook.py         # Webhook receiver
├── whatsapp-connector/        # Node.js WhatsApp bridge
│   ├── index.js               # WhatsApp Web JS client
│   └── package.json
├── knowledge/                 # Knowledge base (Markdown)
│   ├── services.md
│   ├── pricing.md
│   ├── faq.md
│   ├── policies.md
│   ├── objections.md
│   └── scripts.md
├── chroma_db/                 # Vector DB persistence
├── run.py                     # Alternative start script
├── start.bat                  # Windows start script
└── README.md
```

## Future Improvements (V2)

- [ ] **PostgreSQL Support** - Replace SQLite for production
- [ ] **Multi-Language** - Support English and other languages
- [ ] **Real-time Dashboard** via WebSockets
- [ ] **Email/Telegram Reports** - Automated report delivery
- [ ] **Sentiment Analysis** - Detect customer mood
- [ ] **A/B Testing** - Compare different response strategies
- [ ] **Analytics Export** - CSV/PDF report export
- [ ] **Team Management** - Multiple agents with roles
- [ ] **Webhooks Out** - Send events to external systems
- [ ] **IVR Integration** - Voice call automation
- [ ] **Campaign Management** - Bulk messaging with templates
- [ ] **Custom AI Models** - Fine-tune on your data
- [ ] **Audit Log** - Full system audit trail
- [ ] **Rate Limiting** - Anti-spam protection
- [ ] **Message Templates** - Pre-approved WhatsApp templates
