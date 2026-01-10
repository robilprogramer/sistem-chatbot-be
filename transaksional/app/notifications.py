"""
Notification Service
====================
Service untuk mengirim notifikasi (email, webhook, dll).
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod
import json
import asyncio
import httpx

from transaksional.app.config import settings


@dataclass
class NotificationPayload:
    """Payload untuk notifikasi"""
    event_type: str
    registration_number: Optional[str]
    data: Dict[str, Any]
    timestamp: str = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "registration_number": self.registration_number,
            "data": self.data,
            "timestamp": self.timestamp
        }


class NotificationChannel(ABC):
    """Base class untuk notification channels"""
    
    @abstractmethod
    async def send(self, payload: NotificationPayload) -> bool:
        """Send notification"""
        pass
    
    @abstractmethod
    def is_enabled(self) -> bool:
        """Check if channel is enabled"""
        pass


class WebhookChannel(NotificationChannel):
    """Webhook notification channel"""
    
    def __init__(self):
        config = settings.notifications.get("webhook", {})
        self.enabled = config.get("enabled", False)
        self.url = config.get("url", "")
        self.secret = config.get("secret", "")
        self.timeout = config.get("timeout_seconds", 10)
        self.retry_count = config.get("retry_count", 3)
    
    def is_enabled(self) -> bool:
        return self.enabled and bool(self.url)
    
    async def send(self, payload: NotificationPayload) -> bool:
        """Send webhook notification"""
        if not self.is_enabled():
            return False
        
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.secret:
            headers["Authorization"] = f"Bearer {self.secret}"
        
        for attempt in range(self.retry_count):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url,
                        json=payload.to_dict(),
                        headers=headers,
                        timeout=self.timeout
                    )
                    
                    if response.status_code in (200, 201, 202):
                        return True
                    
                    print(f"Webhook failed with status {response.status_code}: {response.text}")
                    
            except Exception as e:
                print(f"Webhook error (attempt {attempt + 1}): {e}")
                if attempt < self.retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return False


class EmailChannel(NotificationChannel):
    """Email notification channel"""
    
    def __init__(self):
        config = settings.notifications.get("email", {})
        self.enabled = config.get("enabled", False)
        self.smtp_host = config.get("smtp_host", "")
        self.smtp_port = config.get("smtp_port", 587)
        self.smtp_user = config.get("smtp_user", "")
        self.smtp_password = config.get("smtp_password", "")
        self.from_email = config.get("from_email", "")
        self.from_name = config.get("from_name", "YPI Al-Azhar")
    
    def is_enabled(self) -> bool:
        return self.enabled and all([
            self.smtp_host,
            self.smtp_user,
            self.smtp_password,
            self.from_email
        ])
    
    async def send(self, payload: NotificationPayload) -> bool:
        """Send email notification"""
        if not self.is_enabled():
            return False
        
        # Get recipient email from data
        to_email = payload.data.get("email")
        if not to_email:
            print("No recipient email in payload")
            return False
        
        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Build email
            message = MIMEMultipart("alternative")
            message["Subject"] = self._get_subject(payload)
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Build content
            html_content = self._build_html_content(payload)
            text_content = self._build_text_content(payload)
            
            message.attach(MIMEText(text_content, "plain"))
            message.attach(MIMEText(html_content, "html"))
            
            # Send
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.smtp_user,
                password=self.smtp_password,
                start_tls=True
            )
            
            return True
            
        except ImportError:
            print("aiosmtplib not installed. Run: pip install aiosmtplib")
            return False
        except Exception as e:
            print(f"Email error: {e}")
            return False
    
    def _get_subject(self, payload: NotificationPayload) -> str:
        """Get email subject based on event type"""
        subjects = {
            "registration.confirmed": f"Konfirmasi Pendaftaran - {payload.registration_number}",
            "registration.updated": f"Update Pendaftaran - {payload.registration_number}",
            "registration.reminder": "Reminder: Lengkapi Pendaftaran Anda",
        }
        return subjects.get(payload.event_type, "Notifikasi YPI Al-Azhar")
    
    def _build_html_content(self, payload: NotificationPayload) -> str:
        """Build HTML email content"""
        data = payload.data
        
        if payload.event_type == "registration.confirmed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #2c5aa0;">🎉 Pendaftaran Berhasil!</h1>
                    
                    <p>Terima kasih telah mendaftar di YPI Al-Azhar.</p>
                    
                    <div style="background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <p><strong>Nomor Registrasi:</strong> {payload.registration_number}</p>
                        <p><strong>Nama Siswa:</strong> {data.get('nama_lengkap', '-')}</p>
                        <p><strong>Sekolah:</strong> {data.get('nama_sekolah', '-')}</p>
                        <p><strong>Tingkatan:</strong> {data.get('tingkatan', '-')}</p>
                    </div>
                    
                    <h3>Langkah Selanjutnya:</h3>
                    <ol>
                        <li>Lakukan pembayaran biaya pendaftaran</li>
                        <li>Tunggu verifikasi dokumen (1-3 hari kerja)</li>
                        <li>Cek email untuk informasi selanjutnya</li>
                    </ol>
                    
                    <p style="color: #666; font-size: 12px; margin-top: 30px;">
                        Email ini dikirim otomatis. Mohon tidak membalas email ini.
                    </p>
                </div>
            </body>
            </html>
            """
        
        return f"""
        <html>
        <body>
            <h1>Notifikasi YPI Al-Azhar</h1>
            <p>Event: {payload.event_type}</p>
            <pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>
        </body>
        </html>
        """
    
    def _build_text_content(self, payload: NotificationPayload) -> str:
        """Build plain text email content"""
        data = payload.data
        
        if payload.event_type == "registration.confirmed":
            return f"""
Pendaftaran Berhasil!

Terima kasih telah mendaftar di YPI Al-Azhar.

Nomor Registrasi: {payload.registration_number}
Nama Siswa: {data.get('nama_lengkap', '-')}
Sekolah: {data.get('nama_sekolah', '-')}
Tingkatan: {data.get('tingkatan', '-')}

Langkah Selanjutnya:
1. Lakukan pembayaran biaya pendaftaran
2. Tunggu verifikasi dokumen (1-3 hari kerja)
3. Cek email untuk informasi selanjutnya

---
Email ini dikirim otomatis. Mohon tidak membalas email ini.
"""
        
        return f"Event: {payload.event_type}\n\nData: {json.dumps(data, indent=2, ensure_ascii=False)}"


class NotificationService:
    """
    Service untuk mengelola notifikasi.
    Mengirim ke semua channel yang aktif.
    """
    
    def __init__(self):
        self.channels: List[NotificationChannel] = [
            WebhookChannel(),
            EmailChannel(),
        ]
    
    async def notify(
        self,
        event_type: str,
        registration_number: str = None,
        data: Dict[str, Any] = None
    ) -> Dict[str, bool]:
        """
        Send notification to all enabled channels.
        
        Args:
            event_type: Type of event (e.g., "registration.confirmed")
            registration_number: Registration number (optional)
            data: Additional data to include
            
        Returns:
            Dict of channel name -> success status
        """
        payload = NotificationPayload(
            event_type=event_type,
            registration_number=registration_number,
            data=data or {}
        )
        
        results = {}
        
        for channel in self.channels:
            channel_name = channel.__class__.__name__
            
            if not channel.is_enabled():
                results[channel_name] = None  # Not enabled
                continue
            
            try:
                success = await channel.send(payload)
                results[channel_name] = success
            except Exception as e:
                print(f"Notification error for {channel_name}: {e}")
                results[channel_name] = False
        
        return results
    
    async def notify_registration_confirmed(
        self,
        registration_number: str,
        data: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Notify when registration is confirmed"""
        return await self.notify(
            event_type="registration.confirmed",
            registration_number=registration_number,
            data=data
        )
    
    async def notify_registration_updated(
        self,
        registration_number: str,
        data: Dict[str, Any]
    ) -> Dict[str, bool]:
        """Notify when registration is updated"""
        return await self.notify(
            event_type="registration.updated",
            registration_number=registration_number,
            data=data
        )


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get singleton notification service"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
