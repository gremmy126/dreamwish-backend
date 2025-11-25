# backend/services/email_service.py

import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM = os.getenv("EMAIL_FROM", "Dreamwish <no-reply@dreamwish.com>")


async def send_email(message: str, recipient_email: str, subject: str = "[Dreamwish] 알림"):
    """
    간단한 텍스트 이메일 전송 (동기 SMTP → async로 감싸서 사용)
    """
    if not (SMTP_USER and SMTP_PASSWORD):
        print("⚠️ SMTP_USER or SMTP_PASSWORD missing")
        return {"status": "error", "message": "SMTP credentials not configured"}

    try:
        mime = MIMEText(message, _charset="utf-8")
        mime["Subject"] = str(Header(subject, "utf-8"))
        mime["From"] = EMAIL_FROM
        mime["To"] = recipient_email

        # 동기 실행이지만, FastAPI에서 쓰기 위해 async 함수 안에 작성
        def _send():
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(str(SMTP_USER), str(SMTP_PASSWORD))
                server.sendmail(str(SMTP_USER), [recipient_email], mime.as_string())

        # 그냥 바로 호출 (규모 커지면 ThreadPoolExecutor 등 고려)
        _send()
        print(f"✅ 이메일 전송 완료: {recipient_email}")
        return {"status": "success", "recipient": recipient_email}
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")
        return {"status": "error", "message": str(e)}
