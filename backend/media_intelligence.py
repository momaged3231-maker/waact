import io
from urllib.parse import quote

import httpx

from config import config
from whatsapp.connector import whatsapp_connector


class MediaIntelligence:
    async def analyze_whatsapp_media(self, message_id: str | None, media_type: str | None) -> dict:
        if not message_id:
            return {"status": "missing_message_id", "text": "", "detail": "No WhatsApp message id was provided."}

        normalized_type = (media_type or "").lower()
        if normalized_type in {"audio", "ptt"}:
            return {
                "status": "transcription_unavailable",
                "text": "",
                "detail": "Audio transcription hook is ready, but no local speech-to-text engine is configured.",
            }

        media = await self.fetch_whatsapp_media(message_id)
        if not media.get("ok"):
            return {"status": "media_unavailable", "text": "", "detail": media.get("error", "Media is unavailable.")}

        content_type = media.get("content_type") or "application/octet-stream"
        data = media.get("data") or b""

        if normalized_type in {"image", "sticker"} or content_type.startswith("image/"):
            return self.extract_image_text(data, content_type)

        if content_type == "application/pdf" or normalized_type == "document":
            return self.extract_document_text(data, content_type)

        if content_type.startswith("audio/"):
            return {
                "status": "transcription_unavailable",
                "text": "",
                "detail": "Audio transcription hook is ready, but no local speech-to-text engine is configured.",
            }

        return {"status": "unsupported_media", "text": "", "detail": f"Unsupported media type: {media_type or content_type}"}

    async def fetch_whatsapp_media(self, message_id: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{config.WHATSAPP_CONNECTOR_URL}/api/messages/{quote(message_id, safe='')}/media",
                    headers=whatsapp_connector.headers(),
                )
            if response.status_code != 200:
                return {"ok": False, "error": f"Connector returned HTTP {response.status_code}"}
            return {
                "ok": True,
                "data": response.content,
                "content_type": response.headers.get("content-type", "application/octet-stream").split(";", 1)[0],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def extract_image_text(self, data: bytes, content_type: str) -> dict:
        try:
            from PIL import Image
            import pytesseract
        except Exception as exc:
            return {
                "status": "ocr_unavailable",
                "text": "",
                "detail": f"Image OCR requires pillow, pytesseract, and the Tesseract binary: {exc}",
            }

        try:
            image = Image.open(io.BytesIO(data))
            text = (pytesseract.image_to_string(image, lang="ara+eng") or "").strip()
            return {"status": "ok" if text else "no_text_found", "text": text, "detail": content_type}
        except Exception as exc:
            return {"status": "ocr_failed", "text": "", "detail": str(exc)}

    def extract_document_text(self, data: bytes, content_type: str) -> dict:
        if content_type != "application/pdf":
            return {"status": "unsupported_document", "text": "", "detail": f"Unsupported document type: {content_type}"}

        try:
            from pypdf import PdfReader
        except Exception as exc:
            return {"status": "pdf_unavailable", "text": "", "detail": f"PDF extraction requires pypdf: {exc}"}

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            return {"status": "ok" if text else "no_text_found", "text": text, "detail": "application/pdf"}
        except Exception as exc:
            return {"status": "pdf_failed", "text": "", "detail": str(exc)}


media_intelligence = MediaIntelligence()
