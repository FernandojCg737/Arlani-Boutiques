import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

# Nombre que ven los destinatarios como remitente.
FROM_NAME = "Arlani Boutiques"
MARCA_PLATAFORMA = "Arlani Boutiques"


def nombre_marca(db: Session, empresa_id: int | None) -> str:
    """Nombre que firma un correo: la tienda (si es de una empresa, ej. el alta
    de un empleado) o la plataforma (clientes, cuentas sin empresa)."""
    if empresa_id is None:
        return MARCA_PLATAFORMA
    nombre = db.execute(text("SELECT nombre FROM empresa WHERE id = :id"), {"id": empresa_id}).scalar()
    return nombre or MARCA_PLATAFORMA


def send_email(to: str, subject: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((FROM_NAME, settings.SMTP_FROM))
    msg["To"] = to
    msg.set_content("Este correo requiere un cliente compatible con HTML.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
