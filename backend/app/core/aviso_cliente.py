"""Copia por correo de los avisos al cliente (devoluciones y cambios de prenda).

La notificacion del sistema (campanita) sigue siendo la principal; esto manda
ademas un correo con la marca de la tienda (su nombre, su color y su logo) para
que el cliente se entere aunque no abra la app.

El correo sale solo si la transaccion se guardo: `programar_correo` lo deja
pendiente en la sesion y se envia en segundo plano despues del commit (si hay
rollback se descarta). Asi la respuesta al encargado no espera al envio.
"""
import html
import logging
import threading

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.core import email as correo

logger = logging.getLogger(__name__)

_PENDIENTES = "correos_pendientes"
_MARCA_PLATAFORMA = "Arlani Boutiques"
_COLOR_PLATAFORMA = "#1f2a44"


def _luminancia(rgb: list[int]) -> float:
    def canal(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def color_para_texto_blanco(hexa: str | None) -> str:
    """El color de la marca, oscurecido lo justo para que el texto blanco se
    lea (contraste WCAG AA), igual que `colorParaTextoBlanco` en la web."""
    try:
        rgb = [int((hexa or _COLOR_PLATAFORMA)[i:i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return _COLOR_PLATAFORMA
    for _ in range(20):
        if 1.05 / (_luminancia(rgb) + 0.05) >= 4.5:
            break
        rgb = [round(c * 0.88) for c in rgb]
    return "#" + "".join(f"{c:02x}" for c in rgb)


def _html(tienda: str, color: str, logo: str | None, nombre: str, titulo: str, mensaje: str) -> str:
    logo_html = (
        f'<img src="{html.escape(logo)}" alt="{html.escape(tienda)}" style="max-height:56px;max-width:200px;display:block;margin:0 auto 10px">'
        if logo and logo.startswith("http")
        else ""
    )
    return f"""
<div style="background:#f7f4f2;padding:24px 12px;font-family:Arial,Helvetica,sans-serif">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden">
    <div style="background:{color};padding:24px;text-align:center;color:#ffffff">
      {logo_html}
      <div style="font-size:20px;font-weight:bold">{html.escape(tienda)}</div>
    </div>
    <div style="padding:28px 24px;color:#121a2c">
      <p style="margin:0 0 6px;font-size:13px;color:#5f6779">Hola {html.escape(nombre)},</p>
      <h1 style="margin:0 0 14px;font-size:20px">{html.escape(titulo)}</h1>
      <p style="margin:0;font-size:15px;line-height:1.6">{html.escape(mensaje)}</p>
    </div>
    <div style="padding:16px 24px;border-top:1px solid #e6e1dc;font-size:12px;color:#5f6779">
      También lo tienes en tus notificaciones de {html.escape(tienda)}. Vendido a través de Arlani Boutiques.
    </div>
  </div>
</div>"""


def programar_correo(db: Session, cliente_id: int, empresa_id: int | None, titulo: str, mensaje: str) -> None:
    """Deja listo el correo del aviso; se envia solo despues del commit."""
    try:
        cliente = db.execute(text("SELECT email, nombre FROM usuario WHERE id = :id"), {"id": cliente_id}).first()
        if not cliente or not cliente.email:
            return
        marca = None
        if empresa_id is not None:
            marca = db.execute(
                text("SELECT nombre, color_marca, logo_url, email_contacto FROM empresa WHERE id = :id"),
                {"id": empresa_id},
            ).first()
        tienda = marca.nombre if marca else _MARCA_PLATAFORMA
        cuerpo = _html(
            tienda,
            color_para_texto_blanco(marca.color_marca if marca else None),
            marca.logo_url if marca else None,
            cliente.nombre or "",
            titulo,
            mensaje,
        )
        # De parte de la tienda: su nombre como remitente y, si el cliente
        # responde, le llega a su correo de contacto.
        db.info.setdefault(_PENDIENTES, []).append(
            (cliente.email, titulo, cuerpo, tienda, marca.email_contacto if marca else None)
        )
    except Exception:
        # El aviso por correo nunca debe hacer fallar la operacion.
        logger.exception("No se pudo preparar el correo del aviso al cliente %s", cliente_id)


def _enviar(pendientes: list[tuple[str, str, str, str, str | None]]) -> None:
    for destino, asunto, cuerpo, tienda, responder_a in pendientes:
        try:
            correo.send_email(destino, asunto, cuerpo, remitente=tienda, responder_a=responder_a)
        except Exception:
            logger.exception("No se pudo enviar el aviso por correo a %s", destino)


@event.listens_for(Session, "after_commit")
def _al_guardar(sesion: Session) -> None:
    pendientes = sesion.info.pop(_PENDIENTES, None)
    if pendientes:
        threading.Thread(target=_enviar, args=(pendientes,), daemon=True).start()


@event.listens_for(Session, "after_rollback")
def _al_deshacer(sesion: Session) -> None:
    sesion.info.pop(_PENDIENTES, None)
