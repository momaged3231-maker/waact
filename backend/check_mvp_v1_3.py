from fastapi.testclient import TestClient

from config import config
from database.db import SessionLocal, init_db
from database.models import Customer, OptOut, RouterActionLog, RouterDevice, RouterPendingAction
from main import app
from router_service import router_service


SMOKE_PHONE = "209999999993"


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def cleanup_smoke_data():
    db = SessionLocal()
    try:
        db.query(RouterPendingAction).filter(RouterPendingAction.phone == SMOKE_PHONE).delete()
        db.query(RouterActionLog).filter(RouterActionLog.phone == SMOKE_PHONE).delete()
        db.query(OptOut).filter(OptOut.phone == SMOKE_PHONE).delete()
        customers = db.query(Customer).filter(Customer.phone == SMOKE_PHONE).all()
        for customer in customers:
            for router in list(customer.router_devices):
                db.delete(router)
            db.delete(customer)
        db.commit()
    finally:
        db.close()


def check_get(client: TestClient, path: str):
    response = client.get(path)
    print(f"{path}: {response.status_code}")
    require(response.status_code == 200, f"Expected 200 from {path}, got {response.status_code}")
    return response


def check_router_create_with_blank_port(client: TestClient):
    cleanup_smoke_data()
    response = client.post(
        "/routers/create",
        data={
            "customer_phone": SMOKE_PHONE,
            "name": "MVP V1.3 Smoke Router",
            "protocol": "manual",
            "port": "",
            "enabled": "on",
        },
    )
    print(f"/routers/create blank port: {response.status_code}")
    require(response.status_code == 200, "Router create with blank port failed")
    lookup = client.get(f"/api/routers/lookup?phone={SMOKE_PHONE}")
    data = lookup.json()
    require(lookup.status_code == 200, "Router lookup failed after create")
    require(data.get("router", {}).get("name") == "MVP V1.3 Smoke Router", "Created router not found by phone")
    cleanup_smoke_data()


def create_manual_pending_request() -> str:
    cleanup_smoke_data()
    db = SessionLocal()
    try:
        customer = Customer(phone=SMOKE_PHONE)
        db.add(customer)
        db.commit()
        router = RouterDevice(customer_id=customer.id, name="MVP V1.3 Manual Router", protocol="manual", enabled=True)
        db.add(router)
        db.commit()
        pending = RouterPendingAction(
            customer_id=customer.id,
            router_id=router.id,
            phone=SMOKE_PHONE,
            status="manual_required",
            payload_json={"password_length": 10},
        )
        db.add(pending)
        db.commit()
        return pending.id
    finally:
        db.close()


def check_manual_router_request_completion(client: TestClient):
    pending_id = create_manual_pending_request()
    response = client.post(f"/routers/pending/{pending_id}/complete", data={})
    print(f"/routers/pending/{{id}}/complete: {response.status_code}")
    require(response.status_code == 200, "Manual router pending completion failed")
    db = SessionLocal()
    try:
        pending = db.query(RouterPendingAction).filter(RouterPendingAction.id == pending_id).first()
        require(pending and pending.status == "completed_manual", "Manual router request was not completed")
    finally:
        db.close()
    cleanup_smoke_data()


def check_manual_router_request_close(client: TestClient):
    pending_id = create_manual_pending_request()
    response = client.post(f"/routers/pending/{pending_id}/close", data={})
    print(f"/routers/pending/{{id}}/close: {response.status_code}")
    require(response.status_code == 200, "Manual router pending close failed")
    db = SessionLocal()
    try:
        pending = db.query(RouterPendingAction).filter(RouterPendingAction.id == pending_id).first()
        require(pending and pending.status == "closed", "Manual router request was not closed")
    finally:
        db.close()
    cleanup_smoke_data()


def check_wifi_intent_normalization():
    examples = [
        "محتاج اغير باسورد الواى فاى",
        "عايز اغير كلمة سر الواى فاى",
        "wifi password change",
    ]
    results = [(text, router_service.is_wifi_command(text)) for text in examples]
    print(f"wifi intent: {results}")
    require(all(ok for _, ok in results), "WiFi password intent normalization failed")


def check_soft_handoff_does_not_pause_customer(client: TestClient):
    cleanup_smoke_data()
    headers = {"X-Webhook-Secret": config.WHATSAPP_WEBHOOK_SECRET} if config.WHATSAPP_WEBHOOK_SECRET else {}
    response = client.post(
        "/api/whatsapp/webhook",
        headers=headers,
        json={"phone": SMOKE_PHONE, "message": "حالة الاشتراك", "message_id": "mvp-v13-soft-handoff"},
    )
    print(f"/api/whatsapp/webhook soft handoff: {response.status_code}")
    require(response.status_code == 200, "Webhook soft handoff request failed")
    db = SessionLocal()
    try:
        customer = db.query(Customer).filter(Customer.phone == SMOKE_PHONE).first()
        require(customer and customer.is_handover is False, "Soft handoff paused auto replies unexpectedly")
    finally:
        db.close()
    cleanup_smoke_data()


def main():
    init_db()
    client = TestClient(app)

    health = check_get(client, "/api/health").json()
    require(health.get("version") == "1.3.0", f"Unexpected version: {health.get('version')}")
    require(health.get("release") == "MVP V1.3", f"Unexpected release: {health.get('release')}")
    require(health.get("prd_version") == "v5", f"Unexpected PRD version: {health.get('prd_version')}")

    for path in [
        "/",
        "/whatsapp-chats",
        "/support",
        "/isp",
        "/isp?q=201000000000",
        "/radius",
        "/routers",
        "/analytics",
        "/integrations",
        "/maintenance",
        "/export/radius.csv",
        "/export/routers.csv",
        "/api/routers/lookup?phone=201000000000",
        "/api/routers/discover?phone=201000000000",
    ]:
        check_get(client, path)

    check_wifi_intent_normalization()
    check_router_create_with_blank_port(client)
    check_manual_router_request_completion(client)
    check_manual_router_request_close(client)
    check_soft_handoff_does_not_pause_customer(client)
    print("MVP V1.3 checks passed")


if __name__ == "__main__":
    main()
