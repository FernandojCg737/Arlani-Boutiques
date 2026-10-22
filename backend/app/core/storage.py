import uuid

import requests
from fastapi import HTTPException, status

from app.core.config import settings

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def upload_producto_imagen(producto_id: int, content: bytes, content_type: str) -> str:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Formato de imagen no soportado (usa JPG, PNG o WEBP).")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La imagen supera el tamano maximo de 10MB.")
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Almacenamiento de imagenes no configurado.")

    ext = ALLOWED_CONTENT_TYPES[content_type]
    path = f"{producto_id}/{uuid.uuid4().hex}.{ext}"

    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
        },
        data=content,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir la imagen al almacenamiento.")

    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{path}"


AR_ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/webp": "webp",
    "image/jpeg": "jpg",
}


def upload_prenda_ar_imagen(producto_id: int, content: bytes, content_type: str) -> str:
    if content_type not in AR_ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "La imagen debe ser JPG, PNG o WEBP.",
        )
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La imagen supera el tamano maximo de 10MB.")
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Almacenamiento de imagenes no configurado.")

    ext = AR_ALLOWED_CONTENT_TYPES[content_type]
    path = f"ar/{producto_id}/{uuid.uuid4().hex}.{ext}"

    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
        },
        data=content,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir la imagen al almacenamiento.")

    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{path}"


def upload_comprobante_pago(cliente_id: int, content: bytes, content_type: str) -> str:
    """CU11: foto del comprobante de una transferencia por QR. No hay forma
    de verificar un QR automaticamente (a diferencia de PayPal), asi que
    esta imagen es lo que un cajero/encargado revisa a mano para aprobar o
    rechazar el pago."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Formato de imagen no soportado (usa JPG, PNG o WEBP).")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La imagen supera el tamano maximo de 10MB.")
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Almacenamiento de imagenes no configurado.")

    ext = ALLOWED_CONTENT_TYPES[content_type]
    path = f"comprobantes/{cliente_id}/{uuid.uuid4().hex}.{ext}"

    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
        },
        data=content,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir el comprobante al almacenamiento.")

    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{path}"


def upload_foto_asistencia(empleado_id: int, content: bytes, content_type: str) -> str:
    """CU01: foto de verificacion que el empleado se toma al marcar
    asistencia (evidencia visual, ademas de la clave y la ubicacion)."""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Formato de imagen no soportado (usa JPG, PNG o WEBP).")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La imagen supera el tamano maximo de 10MB.")
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Almacenamiento de imagenes no configurado.")

    ext = ALLOWED_CONTENT_TYPES[content_type]
    path = f"asistencia/{empleado_id}/{uuid.uuid4().hex}.{ext}"

    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
        },
        data=content,
        timeout=15,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir la foto al almacenamiento.")

    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{path}"


def delete_prenda_ar_imagen(url: str) -> None:
    delete_producto_imagen(url)


def delete_producto_imagen(url: str) -> None:
    marker = f"/object/public/{settings.SUPABASE_STORAGE_BUCKET}/"
    idx = url.find(marker)
    if idx == -1:
        return
    path = url[idx + len(marker) :]

    requests.delete(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        },
        timeout=15,
    )


# ---------------------------------------------------------- logo de empresa
LOGO_MAX_BYTES = 5 * 1024 * 1024
LOGO_LADO_MAX = 512


def _recortar_margenes(imagen):
    """Quita el margen vacio alrededor del logo (transparente o del color del
    fondo) para que el dibujo ocupe todo su espacio al mostrarlo chico."""
    from PIL import ImageChops

    alfa = imagen.getchannel("A")
    caja = alfa.getbbox() if alfa.getextrema()[0] < 255 else None
    if caja is None:
        # Sin transparencia: el fondo es el color de la esquina.
        fondo = imagen.convert("RGB")
        esquina = fondo.getpixel((0, 0))
        plano = fondo.copy()
        plano.paste(esquina, (0, 0, *fondo.size))
        diferencia = ImageChops.difference(fondo, plano).convert("L").point(lambda v: 255 if v > 24 else 0)
        caja = diferencia.getbbox()
    if not caja:
        return imagen
    # Un pequeno respiro (3 %) para que el dibujo no quede pegado al borde.
    margen = round(max(caja[2] - caja[0], caja[3] - caja[1]) * 0.03)
    x0, y0 = max(caja[0] - margen, 0), max(caja[1] - margen, 0)
    x1, y1 = min(caja[2] + margen, imagen.width), min(caja[3] + margen, imagen.height)
    return imagen.crop((x0, y0, x1, y1))


def upload_logo_empresa(empresa_id: int, content: bytes) -> str:
    """Logo de una boutique en cualquier formato de imagen. Las imagenes de
    mapa de bits (JPG, PNG, WEBP, GIF, BMP, TIFF, HEIC del iPhone, AVIF...)
    se pasan a PNG de hasta 512 px, conservando la transparencia; un SVG se
    guarda tal cual (es vectorial)."""
    import io

    import pillow_heif
    from PIL import Image, UnidentifiedImageError

    if len(content) > LOGO_MAX_BYTES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El logo supera el tamaño máximo de 5 MB.")
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Almacenamiento de imagenes no configurado.")

    inicio = content[:512].lstrip().lower()
    if inicio.startswith(b"<svg") or (inicio.startswith(b"<?xml") and b"<svg" in content[:2048].lower()):
        datos, tipo, ext = content, "image/svg+xml", "svg"
    else:
        pillow_heif.register_heif_opener()
        try:
            imagen = Image.open(io.BytesIO(content))
            imagen.load()
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo del logo no es una imagen válida.")
        imagen = _recortar_margenes(imagen.convert("RGBA"))
        imagen.thumbnail((LOGO_LADO_MAX, LOGO_LADO_MAX))
        salida = io.BytesIO()
        imagen.save(salida, format="PNG", optimize=True)
        datos, tipo, ext = salida.getvalue(), "image/png", "png"

    path = f"empresas/{empresa_id}/logo-{uuid.uuid4().hex}.{ext}"
    resp = requests.post(
        f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_STORAGE_BUCKET}/{path}",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": tipo,
        },
        data=datos,
        timeout=20,
    )
    if not resp.ok:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "No se pudo subir el logo al almacenamiento.")
    return f"{settings.SUPABASE_URL}/storage/v1/object/public/{settings.SUPABASE_STORAGE_BUCKET}/{path}"
