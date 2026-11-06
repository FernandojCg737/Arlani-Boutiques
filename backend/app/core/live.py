"""CU22 Live commerce: LiveKit Cloud (salas, permisos, grabacion) y Backblaze
B2 (donde quedan las grabaciones).

El navegador del vendedor transmite directo a LiveKit; el backend solo crea la
sala, firma los permisos de cada uno (vendedor: transmite; espectador: solo
mira), reparte los comentarios a la sala y pide la grabacion (MP4) que LiveKit
sube sola al bucket privado de B2.
"""

import asyncio
import json
from datetime import timedelta

import boto3
from fastapi import HTTPException, status
from livekit import api

from app.core.config import settings

# Si el vendedor se desconecta (cerro el navegador, se corto internet) y no
# vuelve en 5 minutos, la sala se cierra sola y el live termina.
ESPERA_VENDEDOR = 300
TEMA = "live"


def configurado() -> bool:
    return bool(settings.LIVEKIT_URL and settings.LIVEKIT_API_KEY and settings.LIVEKIT_API_SECRET)


def _exigir() -> None:
    if not configurado():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El live todavía no está configurado en el servidor.")


def _ejecutar(funcion):
    """Corre una llamada a la API de LiveKit (asincrona) desde codigo normal."""
    async def correr():
        cliente = api.LiveKitAPI(settings.LIVEKIT_URL.replace("wss://", "https://"),
                                 settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        try:
            return await funcion(cliente)
        finally:
            await cliente.aclose()

    return asyncio.run(correr())


def crear_sala(sala: str) -> None:
    _exigir()
    _ejecutar(lambda c: c.room.create_room(api.CreateRoomRequest(
        name=sala, empty_timeout=ESPERA_VENDEDOR, departure_timeout=ESPERA_VENDEDOR, max_participants=1000,
    )))


def token(sala: str, identidad: str, nombre: str, vendedor: bool, metadata: dict | None = None) -> str:
    """Permiso para entrar a la sala: el vendedor publica camara y microfono;
    el espectador solo mira (los comentarios pasan por el backend)."""
    _exigir()
    return (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(identidad)
        .with_name(nombre)
        .with_metadata(json.dumps(metadata or {}))
        .with_ttl(timedelta(hours=12))
        .with_grants(api.VideoGrants(
            room_join=True, room=sala, can_subscribe=True, can_publish=vendedor, can_publish_data=False,
        ))
        .to_jwt()
    )


def enviar(sala: str, mensaje: dict) -> None:
    """Manda un mensaje a todos en la sala (comentario, prenda fijada, fin...)."""
    if not configurado():
        return
    try:
        _ejecutar(lambda c: c.room.send_data(api.SendDataRequest(
            room=sala, data=json.dumps(mensaje, default=str).encode(), kind=api.DataPacket.Kind.RELIABLE, topic=TEMA,
        )))
    except Exception:  # noqa: BLE001 - la sala pudo cerrarse: el mensaje ya quedo guardado
        pass


def expulsar(sala: str, identidad: str) -> None:
    try:
        _ejecutar(lambda c: c.room.remove_participant(api.RoomParticipantIdentity(room=sala, identity=identidad)))
    except Exception:  # noqa: BLE001 - ya no estaba conectado
        pass


def cerrar_sala(sala: str) -> None:
    try:
        _ejecutar(lambda c: c.room.delete_room(api.DeleteRoomRequest(room=sala)))
    except Exception:  # noqa: BLE001 - ya estaba cerrada
        pass


# ------------------------------------------------------------------ grabacion


def b2_configurado() -> bool:
    return bool(settings.B2_ENDPOINT and settings.B2_BUCKET and settings.B2_KEY_ID and settings.B2_APPLICATION_KEY)


def iniciar_grabacion(sala: str, clave: str) -> str | None:
    """Pide a LiveKit grabar la sala en MP4 directo al bucket de B2."""
    if not b2_configurado():
        return None
    salida = api.EncodedFileOutput(
        file_type=api.EncodedFileType.MP4,
        filepath=clave,
        s3=api.S3Upload(
            access_key=settings.B2_KEY_ID, secret=settings.B2_APPLICATION_KEY, region=settings.B2_REGION,
            endpoint=settings.B2_ENDPOINT, bucket=settings.B2_BUCKET, force_path_style=True,
        ),
    )
    info = _ejecutar(lambda c: c.egress.start_room_composite_egress(api.RoomCompositeEgressRequest(
        room_name=sala, layout="speaker", file_outputs=[salida],
    )))
    return info.egress_id


def detener_grabacion(egress_id: str | None) -> None:
    if not egress_id:
        return
    try:
        _ejecutar(lambda c: c.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id)))
    except Exception:  # noqa: BLE001 - ya habia terminado
        pass


def estado_grabacion(egress_id: str) -> api.EgressInfo | None:
    respuesta = _ejecutar(lambda c: c.egress.list_egress(api.ListEgressRequest(egress_id=egress_id)))
    return respuesta.items[0] if respuesta.items else None


def _b2():
    return boto3.client(
        "s3", endpoint_url=settings.B2_ENDPOINT, region_name=settings.B2_REGION,
        aws_access_key_id=settings.B2_KEY_ID, aws_secret_access_key=settings.B2_APPLICATION_KEY,
    )


def enlace_grabacion(clave: str, segundos: int = 3 * 3600) -> str:
    """Enlace temporal para ver o descargar la grabacion (el bucket es privado)."""
    return _b2().generate_presigned_url("get_object", Params={"Bucket": settings.B2_BUCKET, "Key": clave}, ExpiresIn=segundos)


def borrar_grabacion(clave: str) -> None:
    cliente = _b2()
    # B2 guarda versiones: se borran todas para liberar el espacio.
    versiones = cliente.list_object_versions(Bucket=settings.B2_BUCKET, Prefix=clave).get("Versions", [])
    for v in versiones:
        if v["Key"] == clave:
            cliente.delete_object(Bucket=settings.B2_BUCKET, Key=clave, VersionId=v["VersionId"])
    if not versiones:
        cliente.delete_object(Bucket=settings.B2_BUCKET, Key=clave)


def recibir_webhook(cuerpo: str, autorizacion: str) -> api.WebhookEvent:
    receptor = api.WebhookReceiver(api.TokenVerifier(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET))
    return receptor.receive(cuerpo, autorizacion)
