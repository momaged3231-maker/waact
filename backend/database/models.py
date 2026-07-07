import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey, JSON, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.sqlite import TEXT as SQLITE_TEXT
from database.db import Base
import enum


def gen_uuid():
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class CustomerStatus(str, enum.Enum):
    NEW = "new"
    INTERESTED = "interested"
    NEEDS_FOLLOW_UP = "needs_follow_up"
    SOLD = "sold"
    NOT_INTERESTED = "not_interested"
    BLOCKED = "blocked"


class LeadStatus(str, enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Direction(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class HandoffStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(String, primary_key=True, default=gen_uuid)
    phone = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    status = Column(String, default=CustomerStatus.NEW.value)
    source = Column(String, default="whatsapp")
    first_seen_at = Column(DateTime, default=utcnow)
    last_seen_at = Column(DateTime, default=utcnow)
    notes = Column(Text, nullable=True)
    memory_summary = Column(Text, nullable=True)
    last_intent = Column(String, nullable=True)
    interested_service = Column(String, nullable=True)
    is_handover = Column(Boolean, default=False)
    total_messages = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    conversations = relationship("Conversation", back_populates="customer", cascade="all, delete-orphan")
    lead = relationship("Lead", back_populates="customer", uselist=False, cascade="all, delete-orphan")
    handoff_requests = relationship("HandoffRequest", back_populates="customer", cascade="all, delete-orphan")
    follow_up_tasks = relationship("FollowUpTask", back_populates="customer", cascade="all, delete-orphan")
    radius_links = relationship("RadiusSubscriberLink", back_populates="customer", cascade="all, delete-orphan")
    radius_snapshots = relationship("RadiusSnapshot", back_populates="customer")
    router_devices = relationship("RouterDevice", back_populates="customer", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    whatsapp_message_id = Column(String, nullable=True)
    direction = Column(String, nullable=False)
    message_text = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=True)
    intent = Column(String, nullable=True)
    service_interest = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    handoff_required = Column(Boolean, default=False)
    needs_follow_up = Column(Boolean, default=False)
    context = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    customer = relationship("Customer", back_populates="conversations")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), unique=True, nullable=False)
    service_interest = Column(String, nullable=True)
    lead_status = Column(String, default=LeadStatus.NEW.value)
    priority = Column(String, default=Priority.MEDIUM.value)
    assigned_to = Column(String, nullable=True)
    next_follow_up_at = Column(DateTime, nullable=True)
    estimated_value = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer", back_populates="lead")
    follow_up_tasks = relationship("FollowUpTask", back_populates="lead", cascade="all, delete-orphan")


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    lead_id = Column(String, ForeignKey("leads.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending", index=True)
    priority = Column(String, default=Priority.MEDIUM.value)
    assigned_to = Column(String, nullable=True)
    due_at = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer", back_populates="follow_up_tasks")
    lead = relationship("Lead", back_populates="follow_up_tasks")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)
    source = Column(String, nullable=True)
    version = Column(Integer, default=1)
    content_hash = Column(String, nullable=True, index=True)
    chunk_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=gen_uuid)
    report_type = Column(String, nullable=False, index=True)
    report_data = Column(JSON, nullable=False)
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class HandoffRequest(Base):
    __tablename__ = "handoff_requests"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(String, default=HandoffStatus.PENDING.value)
    assigned_to = Column(String, nullable=True)
    conversation_summary = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    customer = relationship("Customer", back_populates="handoff_requests")


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=True)
    task_type = Column(String, default="chat", index=True)
    success = Column(Boolean, default=False, index=True)
    latency_ms = Column(Integer, nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    feedback = Column(String, nullable=True)
    feedback_note = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    segment = Column(String, default="all")
    status = Column(String, default="draft", index=True)
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(String, primary_key=True, default=gen_uuid)
    campaign_id = Column(String, ForeignKey("campaigns.id"), nullable=False, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)
    phone = Column(String, nullable=False, index=True)
    status = Column(String, default="pending", index=True)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    campaign = relationship("Campaign", back_populates="recipients")
    customer = relationship("Customer")


class OptOut(Base):
    __tablename__ = "opt_outs"

    id = Column(String, primary_key=True, default=gen_uuid)
    phone = Column(String, unique=True, nullable=False, index=True)
    reason = Column(String, default="campaign_opt_out")
    created_at = Column(DateTime, default=utcnow, index=True)


class RadiusSubscriberLink(Base):
    __tablename__ = "radius_subscriber_links"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False, index=True)
    external_id = Column(String, nullable=False, unique=True, index=True)
    username = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    source = Column(String, default="manual")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer", back_populates="radius_links")


class RadiusSnapshot(Base):
    __tablename__ = "radius_snapshots"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)
    external_id = Column(String, nullable=False, unique=True, index=True)
    username = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    status = Column(String, default="unknown", index=True)
    package_name = Column(String, nullable=True, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    online = Column(Boolean, default=False, index=True)
    last_seen_at = Column(DateTime, nullable=True)
    balance = Column(Float, nullable=True)
    ip_address = Column(String, nullable=True)
    reseller = Column(String, nullable=True, index=True)
    download_rate = Column(String, nullable=True)
    upload_rate = Column(String, nullable=True)
    traffic_used = Column(String, nullable=True)
    raw_json = Column(JSON, nullable=True)
    synced_at = Column(DateTime, default=utcnow, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer", back_populates="radius_snapshots")


class RadiusSyncLog(Base):
    __tablename__ = "radius_sync_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    action = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=True, index=True)
    success = Column(Boolean, default=False, index=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class RadiusEvent(Base):
    __tablename__ = "radius_events"

    id = Column(String, primary_key=True, default=gen_uuid)
    external_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)


class RouterDevice(Base):
    __tablename__ = "router_devices"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)
    radius_external_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=False)
    model = Column(String, nullable=True)
    protocol = Column(String, default="manual", index=True)
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    ssid = Column(String, nullable=True)
    wifi_interface = Column(String, nullable=True)
    wifi_profile = Column(String, nullable=True)
    http_method = Column(String, default="POST")
    http_change_password_path = Column(Text, nullable=True)
    http_payload_template = Column(Text, nullable=True)
    http_status_path = Column(Text, nullable=True)
    http_reboot_path = Column(Text, nullable=True)
    ssh_change_password_command = Column(Text, nullable=True)
    ssh_reboot_command = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    last_status = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer", back_populates="router_devices")


class RouterActionLog(Base):
    __tablename__ = "router_action_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    router_id = Column(String, ForeignKey("router_devices.id"), nullable=True, index=True)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)
    phone = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    success = Column(Boolean, default=False, index=True)
    message = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    router = relationship("RouterDevice")
    customer = relationship("Customer")


class RouterPendingAction(Base):
    __tablename__ = "router_pending_actions"

    id = Column(String, primary_key=True, default=gen_uuid)
    customer_id = Column(String, ForeignKey("customers.id"), nullable=True, index=True)
    router_id = Column(String, ForeignKey("router_devices.id"), nullable=True, index=True)
    phone = Column(String, nullable=False, index=True)
    action_type = Column(String, default="change_wifi_password", index=True)
    status = Column(String, default="awaiting_password", index=True)
    payload_json = Column(JSON, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    customer = relationship("Customer")
    router = relationship("RouterDevice")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="agent", index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    last_login_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    username = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    entity_type = Column(String, nullable=True, index=True)
    entity_id = Column(String, nullable=True, index=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    user = relationship("User")


class ChatMeta(Base):
    __tablename__ = "chat_meta"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="open", index=True)
    assigned_user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    tags = Column(Text, nullable=True)
    priority = Column(String, default=Priority.MEDIUM.value)
    last_read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    assigned_user = relationship("User")
    notes = relationship("InternalNote", back_populates="chat", cascade="all, delete-orphan")


class InternalNote(Base):
    __tablename__ = "internal_notes"

    id = Column(String, primary_key=True, default=gen_uuid)
    chat_id = Column(String, ForeignKey("chat_meta.chat_id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    username = Column(String, nullable=True)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)

    chat = relationship("ChatMeta", back_populates="notes")
    user = relationship("User")


class AutomationRule(Base):
    __tablename__ = "automation_rules"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    trigger = Column(String, default="inbound_message", index=True)
    condition_type = Column(String, default="always")
    condition_value = Column(Text, nullable=True)
    action_type = Column(String, nullable=False)
    action_payload = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=False, index=True)
    priority = Column(Integer, default=100)
    cooldown_minutes = Column(Integer, default=60)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    rule_id = Column(String, ForeignKey("automation_rules.id"), nullable=False, index=True)
    trigger = Column(String, nullable=False, index=True)
    success = Column(Boolean, default=False, index=True)
    skipped = Column(Boolean, default=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True)

    rule = relationship("AutomationRule")


class ExternalWebhook(Base):
    __tablename__ = "external_webhooks"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    event = Column(String, default="message.inbound", index=True)
    url = Column(Text, nullable=False)
    secret = Column(String, nullable=True)
    enabled = Column(Boolean, default=True, index=True)
    last_status = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    last_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
