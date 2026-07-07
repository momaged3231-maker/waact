import httpx
from config import config


class WhatsAppConnector:
    def __init__(self):
        self.base_url = config.WHATSAPP_CONNECTOR_URL
        self.timeout = 30.0

    def headers(self) -> dict:
        if config.WHATSAPP_CONNECTOR_API_KEY:
            return {"X-Connector-Key": config.WHATSAPP_CONNECTOR_API_KEY}
        return {}

    async def send_message(self, phone: str = None, message: str = None, chat_id: str = None) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {"message": message}
                if chat_id:
                    payload["chatId"] = chat_id
                else:
                    payload["phone"] = phone
                response = await client.post(
                    f"{self.base_url}/api/send",
                    json=payload,
                    headers=self.headers(),
                )
                return response.status_code == 200
        except Exception as e:
            print(f"[WhatsApp Connector] Failed to send message to {phone}: {e}")
            return False

    async def get_status(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/status", headers=self.headers())
                if response.status_code == 200:
                    return response.json()
                return {"connected": False, "error": "Status check failed"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_qr(self) -> str | None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/qr", headers=self.headers())
                if response.status_code == 200:
                    data = response.json()
                    return data.get("qr")
                return None
        except Exception:
            return None

    async def logout(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.base_url}/api/logout", headers=self.headers())
                return response.status_code == 200
        except Exception:
            return False


whatsapp_connector = WhatsAppConnector()
