"""Metodos de pago de cada tienda (CU: Gestionar metodos de pago).

- El Administrador de la tienda registra como cobra: PayPal con SUS
  credenciales (el cobro se confirma solo), QR, transferencia u otro (el
  cliente sube su comprobante y el personal de la tienda lo aprueba).
- El Secret de PayPal se guarda cifrado y nunca se devuelve; al guardarlo se
  prueba contra PayPal.
- /metodos-pago/tienda/{empresa_id}: los metodos activos de una tienda para
  el checkout (publico, sin datos secretos).
- /mi-empresa/facturacion (en mi_empresa.py): los datos de sus facturas.
"""

import base64
import binascii

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_administrador
from app.core.audit import log_bitacora
from app.core.cifrado import cifrar, descifrar, enmascarar
from app.core.paypal import CuentaPaypal, verificar_credenciales
from app.core.storage import upload_qr_metodo_pago
from app.db.session import get_db
from app.models import Empresa, MetodoPagoEmpresa, Usuario
from app.schemas.metodos_pago import MetodoPagoIn, MetodoPagoOut, MetodoPagoPublicoOut

router = APIRouter()


def _empresa_operada(
    x_empresa: int | None = Header(default=None, alias="X-Empresa"),
    admin: Usuario = Depends(require_administrador),
) -> int:
    """La tienda del Administrador, o la que eligio el SuperAdministrador
    (CU19 del 2do parcial, por tienda)."""
    if admin.empresa_id is not None:
        return admin.empresa_id
    if admin.tipo == "superadministrador" and x_empresa is not None:
        return x_empresa
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Elige primero la tienda de la que quieres ver los métodos de pago.")


def _publico(m: MetodoPagoEmpresa) -> dict:
    return dict(
        id=m.id,
        tipo=m.tipo,
        nombre=m.nombre,
        instrucciones=m.instrucciones,
        paypal_client_id=m.paypal_client_id,
        qr_url=m.qr_url,
        banco=m.banco,
        numero_cuenta=m.numero_cuenta,
        tipo_cuenta=m.tipo_cuenta,
        titular=m.titular,
        documento_titular=m.documento_titular,
        requiere_comprobante=m.tipo != "paypal",
    )


def _to_out(m: MetodoPagoEmpresa) -> MetodoPagoOut:
    secreto = descifrar(m.paypal_secret_cifrado) if m.paypal_secret_cifrado else None
    return MetodoPagoOut(
        **_publico(m),
        activo=m.activo,
        orden=m.orden,
        paypal_modo=m.paypal_modo,
        paypal_email=m.paypal_email,
        paypal_secret_mascara=enmascarar(secreto),
    )


def _imagen_de(data_url: str) -> tuple[bytes, str]:
    cabecera, _, datos = data_url.partition(",")
    tipo = cabecera.removeprefix("data:").split(";")[0] or "image/png"
    try:
        return base64.b64decode(datos), tipo
    except (binascii.Error, ValueError) as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La imagen del QR no es válida.") from err


def _limpio(texto: str | None) -> str | None:
    texto = (texto or "").strip()
    return texto or None


def _aplicar(m: MetodoPagoEmpresa, p: MetodoPagoIn, empresa_id: int, nuevo: bool) -> None:
    m.tipo = p.tipo
    m.nombre = p.nombre.strip()
    m.instrucciones = _limpio(p.instrucciones)
    m.activo = p.activo
    m.orden = p.orden
    if p.tipo == "paypal":
        client_id = _limpio(p.paypal_client_id)
        secret = _limpio(p.paypal_secret)
        if not client_id or not p.paypal_modo or (nuevo and not secret):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Para PayPal completa el Client ID, el Secret y el modo (sandbox o real).",
            )
        # Con este correo Arlani le envia a la tienda lo suyo en "Pagar todo".
        if not _limpio(p.paypal_email) or "@" not in p.paypal_email:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Escribe el correo de tu cuenta PayPal: ahí te llega lo de las compras con \"Pagar todo\".",
            )
        secreto_final = secret or (descifrar(m.paypal_secret_cifrado) if m.paypal_secret_cifrado else None)
        if not secreto_final:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vuelve a escribir el Secret de PayPal.")
        # Se prueba antes de guardar: credenciales malas = ventas que no se cobran.
        if not verificar_credenciales(CuentaPaypal(client_id, secreto_final, p.paypal_modo)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "PayPal rechazó esas credenciales. Revisa el Client ID, el Secret y el modo (sandbox o real).",
            )
        m.paypal_client_id = client_id
        m.paypal_secret_cifrado = cifrar(secreto_final)
        m.paypal_modo = p.paypal_modo
        m.paypal_email = _limpio(p.paypal_email)
    else:
        m.paypal_client_id = m.paypal_secret_cifrado = m.paypal_modo = m.paypal_email = None
    if p.tipo == "qr":
        if p.qr_imagen:
            contenido, tipo = _imagen_de(p.qr_imagen)
            m.qr_url = upload_qr_metodo_pago(empresa_id, contenido, tipo)
        if not m.qr_url:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Sube la imagen de tu QR de cobro.")
    else:
        m.qr_url = None
    if p.tipo == "transferencia":
        if not (_limpio(p.banco) and _limpio(p.numero_cuenta) and _limpio(p.titular)):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Para transferencia completa el banco, el número de cuenta y el titular."
            )
    for campo in ("banco", "numero_cuenta", "tipo_cuenta", "titular", "documento_titular"):
        setattr(m, campo, _limpio(getattr(p, campo)) if p.tipo in ("transferencia", "qr", "otro") else None)
    m.actualizado_en = func.now()


def _guardar(db: Session, m: MetodoPagoEmpresa) -> None:
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        if "ux_metodo_pago_un_paypal" in str(err.orig):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Tu tienda ya tiene una cuenta de PayPal registrada: edítala en vez de crear otra."
            ) from err
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Faltan datos para ese método de pago.") from err
    db.refresh(m)


@router.get("", response_model=list[MetodoPagoOut])
def listar(db: Session = Depends(get_db), empresa: int = Depends(_empresa_operada)) -> list[MetodoPagoOut]:
    metodos = (
        db.query(MetodoPagoEmpresa)
        .filter(MetodoPagoEmpresa.empresa_id == empresa)
        .order_by(MetodoPagoEmpresa.orden, MetodoPagoEmpresa.id)
        .all()
    )
    return [_to_out(m) for m in metodos]


@router.post("", response_model=MetodoPagoOut, status_code=status.HTTP_201_CREATED)
def crear(
    payload: MetodoPagoIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
    empresa: int = Depends(_empresa_operada),
) -> MetodoPagoOut:
    m = MetodoPagoEmpresa(empresa_id=empresa)
    _aplicar(m, payload, empresa, nuevo=True)
    db.add(m)
    _guardar(db, m)
    log_bitacora(db, admin, "CREAR", "metodo_pago", m.id, f"Método de pago {m.tipo}: {m.nombre}", request)
    return _to_out(m)


def _de_la_tienda(db: Session, metodo_id: int, empresa: int) -> MetodoPagoEmpresa:
    m = db.query(MetodoPagoEmpresa).filter(
        MetodoPagoEmpresa.id == metodo_id, MetodoPagoEmpresa.empresa_id == empresa
    ).first()
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Método de pago no encontrado.")
    return m


@router.put("/{metodo_id}", response_model=MetodoPagoOut)
def actualizar(
    metodo_id: int,
    payload: MetodoPagoIn,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
    empresa: int = Depends(_empresa_operada),
) -> MetodoPagoOut:
    m = _de_la_tienda(db, metodo_id, empresa)
    _aplicar(m, payload, empresa, nuevo=m.tipo != payload.tipo)
    _guardar(db, m)
    log_bitacora(db, admin, "ACTUALIZAR", "metodo_pago", m.id, f"Método de pago {m.tipo}: {m.nombre}", request)
    return _to_out(m)


@router.delete("/{metodo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    metodo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
    empresa: int = Depends(_empresa_operada),
) -> None:
    m = _de_la_tienda(db, metodo_id, empresa)
    nombre = m.nombre
    db.delete(m)
    db.commit()
    log_bitacora(db, admin, "ELIMINAR", "metodo_pago", metodo_id, f"Método de pago eliminado: {nombre}", request)


@router.get("/tienda/{empresa_id}", response_model=list[MetodoPagoPublicoOut])
def publicos_de_tienda(empresa_id: int, db: Session = Depends(get_db)) -> list[MetodoPagoPublicoOut]:
    """Metodos activos de una tienda para el checkout (sin datos secretos)."""
    if db.query(Empresa.id).filter(Empresa.id == empresa_id).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tienda no encontrada.")
    metodos = (
        db.query(MetodoPagoEmpresa)
        .filter(MetodoPagoEmpresa.empresa_id == empresa_id, MetodoPagoEmpresa.activo.is_(True))
        .order_by(MetodoPagoEmpresa.orden, MetodoPagoEmpresa.id)
        .all()
    )
    return [MetodoPagoPublicoOut(**_publico(m)) for m in metodos]
