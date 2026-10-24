import base64
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings

# Nombre que ven los destinatarios como remitente.
FROM_NAME = "Arlani Boutiques"
MARCA_PLATAFORMA = "Arlani Boutiques"
TEXTO_PLANO = "Este correo requiere un cliente compatible con HTML."


def nombre_marca(db: Session, empresa_id: int | None) -> str:
    """Nombre que firma un correo: la tienda (si es de una empresa, ej. el alta
    de un empleado) o la plataforma (clientes, cuentas sin empresa)."""
    if empresa_id is None:
        return MARCA_PLATAFORMA
    nombre = db.execute(text("SELECT nombre FROM empresa WHERE id = :id"), {"id": empresa_id}).scalar()
    return nombre or MARCA_PLATAFORMA


# Archivo adjunto: (nombre, contenido, tipo MIME), p. ej. un reporte en PDF.
Adjunto = tuple[str, bytes, str]


def send_email(to: str, subject: str, html_body: str, adjuntos: list[Adjunto] | None = None) -> None:
    # Render (plan gratis) bloquea la salida por SMTP (puertos 25/465/587):
    # en produccion el correo sale de la cuenta de Gmail a traves de un Google
    # Apps Script (HTTPS). Sin script configurado (desarrollo local), SMTP.
    if settings.GMAIL_SCRIPT_URL:
        _enviar_por_apps_script(to, subject, html_body, adjuntos or [])
    else:
        _enviar_por_smtp(to, subject, html_body, adjuntos or [])


def _enviar_por_apps_script(to: str, subject: str, html_body: str, adjuntos: list[Adjunto]) -> None:
    resp = requests.post(
        settings.GMAIL_SCRIPT_URL,
        json={
            "token": settings.GMAIL_SCRIPT_TOKEN,
            "to": to,
            "subject": subject,
            "html": html_body,
            "texto": TEXTO_PLANO,
            "nombre": FROM_NAME,
            # El script los convierte en adjuntos (Utilities.newBlob).
            "adjuntos": [
                {"nombre": n, "mime": m, "base64": base64.b64encode(c).decode("ascii")} for n, c, m in adjuntos
            ],
        },
        timeout=60,
    )
    # El script responde {"ok": true} o {"ok": false, "error": "..."}; si la
    # URL esta mal, Google devuelve una pagina HTML en vez de JSON.
    try:
        datos = resp.json()
    except ValueError:
        datos = {}
    if resp.status_code >= 400 or not datos.get("ok"):
        motivo = datos.get("error") or resp.text[:200]
        raise RuntimeError(f"El script de Gmail no envio el correo ({resp.status_code}): {motivo}")
    # El script actualizado responde cuantos archivos adjunto; uno viejo los
    # ignora (el correo sale sin el archivo): se avisa en vez de callarlo.
    if adjuntos and datos.get("adjuntos") != len(adjuntos):
        raise RuntimeError(
            "el correo salió sin el archivo adjunto porque el Google Apps Script de Gmail está desactualizado. "
            "Actualízalo con la versión que adjunta archivos."
        )


def _enviar_por_smtp(to: str, subject: str, html_body: str, adjuntos: list[Adjunto]) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((FROM_NAME, settings.SMTP_FROM))
    msg["To"] = to
    msg.set_content(TEXTO_PLANO)
    msg.add_alternative(html_body, subtype="html")
    for nombre, contenido, mime in adjuntos:
        principal, _, sub = mime.partition("/")
        msg.add_attachment(contenido, maintype=principal, subtype=sub or "octet-stream", filename=nombre)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
