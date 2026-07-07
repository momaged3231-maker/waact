from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import config

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in config.DATABASE_URL else {},
    echo=config.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from database.models import (
        Customer,
        Conversation,
        Lead,
        KnowledgeDocument,
        Report,
        HandoffRequest,
        FollowUpTask,
        AIUsageLog,
        Campaign,
        CampaignRecipient,
        OptOut,
        RadiusSubscriberLink,
        RadiusSnapshot,
        RadiusSyncLog,
        RadiusEvent,
        RouterDevice,
        RouterActionLog,
        RouterPendingAction,
        User,
        AuditLog,
        ChatMeta,
        InternalNote,
        AutomationRule,
        AutomationLog,
        ExternalWebhook,
    )

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_columns()


def ensure_sqlite_columns():
    if "sqlite" not in config.DATABASE_URL:
        return

    with engine.begin() as conn:
        ai_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(ai_usage_logs)")}
        for name, column_type in {
            "prompt_tokens": "INTEGER",
            "completion_tokens": "INTEGER",
            "estimated_cost_usd": "FLOAT",
            "feedback": "VARCHAR",
            "feedback_note": "TEXT",
        }.items():
            if name not in ai_columns:
                conn.exec_driver_sql(f"ALTER TABLE ai_usage_logs ADD COLUMN {name} {column_type}")

        knowledge_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(knowledge_documents)")}
        for name, column_type in {
            "version": "INTEGER DEFAULT 1",
            "content_hash": "VARCHAR",
            "last_indexed_at": "DATETIME",
        }.items():
            if name not in knowledge_columns:
                conn.exec_driver_sql(f"ALTER TABLE knowledge_documents ADD COLUMN {name} {column_type}")

        def add_missing_columns(table: str, columns: dict[str, str]):
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                return
            for name, column_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

        add_missing_columns("router_devices", {
            "customer_id": "VARCHAR",
            "radius_external_id": "VARCHAR",
            "name": "VARCHAR",
            "model": "VARCHAR",
            "protocol": "VARCHAR",
            "host": "VARCHAR",
            "port": "INTEGER",
            "username": "VARCHAR",
            "password": "VARCHAR",
            "ssid": "VARCHAR",
            "wifi_interface": "VARCHAR",
            "wifi_profile": "VARCHAR",
            "http_method": "VARCHAR",
            "http_change_password_path": "TEXT",
            "http_payload_template": "TEXT",
            "http_status_path": "TEXT",
            "http_reboot_path": "TEXT",
            "ssh_change_password_command": "TEXT",
            "ssh_reboot_command": "TEXT",
            "enabled": "BOOLEAN DEFAULT 1",
            "last_status": "VARCHAR",
            "last_error": "TEXT",
            "last_seen_at": "DATETIME",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        })
        add_missing_columns("router_action_logs", {
            "router_id": "VARCHAR",
            "customer_id": "VARCHAR",
            "phone": "VARCHAR",
            "action": "VARCHAR",
            "success": "BOOLEAN DEFAULT 0",
            "message": "TEXT",
            "payload": "JSON",
            "created_at": "DATETIME",
        })
        add_missing_columns("router_pending_actions", {
            "customer_id": "VARCHAR",
            "router_id": "VARCHAR",
            "phone": "VARCHAR",
            "action_type": "VARCHAR",
            "status": "VARCHAR",
            "payload_json": "JSON",
            "expires_at": "DATETIME",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        })
