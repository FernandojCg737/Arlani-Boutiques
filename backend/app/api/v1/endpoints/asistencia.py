from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_TIPOS, require_administrador, require_permiso
from app.core.audit import log_bitacora
from app.core.storage import upload_foto_asistencia
from app.db.session import get_db
from app.models import Empleado, MarcadoAsistencia, Usuario
from app.schemas.asistencia import (
    ConfigurarHoraRequest,
    EstadoAsistenciaOut,
    MarcadoHoyOut,
    MarcadoOut,
)

router = APIRouter()

# Personal que marca asistencia (el Administrador la gestiona, no la marca).
PERSONAL_ASISTENCIA = ("encargado_sucursal", "cajero")


def _empresa_asistencia(usuario: Usuario, empresa_id: int | None) -> int:
    """Empresa cuyo control de asistencia se consulta. Cada tienda ve la
    suya; el SuperAdministrador elige cual mirar (solo lectura)."""
    if usuario.tipo == "superadministrador":
        if empresa_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Elige la empresa cuyo control de asistencia quieres ver.")
        return empresa_id
    if usuario.empresa_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de una tienda tiene control de asistencia.")
    return usuario.empresa_id


def require_admin_tienda(admin: Usuario = Depends(require_administrador)) -> Usuario:
    # Configurar la hora y liberar la clave es del Administrador de cada
    # tienda. El SuperAdministrador solo puede mirar.
    if admin.tipo != "administrador":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "El control de asistencia lo gestiona el Administrador de cada empresa; desde la plataforma solo se consulta.",
        )
    return admin


def _utc(dt: datetime) -> datetime:
    # hora_marcado se guarda con datetime.utcnow() (naive, sin tzinfo) --
    # sin marcarlo como UTC aca, el JSON sale sin 'Z'/offset y el navegador
    # lo interpreta como si YA fuera hora local, mostrando la hora del
    # servidor (UTC) tal cual en vez de convertirla a Bolivia (UTC-4).
    return dt.replace(tzinfo=timezone.utc)


def _estado_hoy(db: Session, empresa_id: int) -> dict:
    fila = db.execute(text("SELECT * FROM fn_estado_asistencia_hoy(:e)"), {"e": empresa_id}).mappings().first()
    db.commit()
    if fila is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Configuracion de asistencia no inicializada.")
    return dict(fila)


def _estado_out(fila: dict, usuario: Usuario) -> EstadoAsistenciaOut:
    # El Administrador siempre ve la clave (para poder anunciarla/supervisar
    # sin depender de que ya este "liberada"); el resto del personal solo
    # la ve mientras la ventana este abierta.
    # El SuperAdministrador no participa del control: nunca ve la clave.
    if usuario.tipo == "superadministrador":
        mostrar_codigo = False
    else:
        mostrar_codigo = fila["liberado"] or usuario.tipo in ADMIN_TIPOS
    return EstadoAsistenciaOut(
        liberado=fila["liberado"],
        ventana_cerrada=fila["ventana_cerrada"],
        hora_liberacion=fila["hora_liberacion"],
        codigo_fecha=fila["codigo_fecha"],
        codigo=fila["codigo"] if mostrar_codigo else None,
    )


@router.get("/estado", response_model=EstadoAsistenciaOut)
def estado_asistencia(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU01")),
) -> EstadoAsistenciaOut:
    return _estado_out(_estado_hoy(db, _empresa_asistencia(usuario, empresa_id)), usuario)


@router.put("/hora", response_model=EstadoAsistenciaOut)
def configurar_hora(
    payload: ConfigurarHoraRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tienda),
) -> EstadoAsistenciaOut:
    empresa = _empresa_asistencia(admin, None)
    db.execute(
        text("SELECT sp_configurar_hora_asistencia(:e, :hora)"), {"e": empresa, "hora": payload.hora_liberacion}
    )
    db.commit()
    log_bitacora(
        db, admin, "ACTUALIZAR", "configuracion_asistencia", empresa,
        f"Hora de liberacion de asistencia cambiada a {payload.hora_liberacion}", request,
    )
    return _estado_out(_estado_hoy(db, empresa), admin)


@router.post("/liberar", response_model=EstadoAsistenciaOut)
def liberar_manual(
    request: Request,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_admin_tienda),
) -> EstadoAsistenciaOut:
    empresa = _empresa_asistencia(admin, None)
    db.execute(text("SELECT sp_liberar_asistencia_manual(:e)"), {"e": empresa})
    db.commit()
    log_bitacora(
        db, admin, "ACTUALIZAR", "configuracion_asistencia", empresa,
        "Clave de asistencia liberada manualmente (ventana de 5 min)", request,
    )
    return _estado_out(_estado_hoy(db, empresa), admin)


@router.post("/marcar", response_model=MarcadoOut, status_code=status.HTTP_201_CREATED)
async def marcar_asistencia(
    request: Request,
    codigo: str = Form(...),
    latitud: float = Form(...),
    longitud: float = Form(...),
    foto: UploadFile = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU01")),
) -> MarcadoOut:
    empleado = db.query(Empleado).filter(Empleado.id == usuario.id).first()
    if empleado is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el personal de la tienda puede marcar asistencia.")

    if foto is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Debes adjuntar una foto de verificacion.")
    contenido = await foto.read()
    foto_url = upload_foto_asistencia(empleado.id, contenido, foto.content_type or "")

    try:
        result = db.execute(
            text("SELECT sp_marcar_asistencia(:empleado_id, :codigo, :lat, :lng, :foto_url)"),
            {"empleado_id": empleado.id, "codigo": codigo, "lat": latitud, "lng": longitud, "foto_url": foto_url},
        )
        marcado_id = result.scalar_one()
        db.commit()
    except DBAPIError as exc:
        db.rollback()
        mensaje = str(getattr(exc.orig, "args", [""])[0]) if exc.orig else "No se pudo registrar la asistencia."
        # postgres antepone el codigo de error al mensaje de RAISE EXCEPTION;
        # nos quedamos solo con el texto que le escribimos en el SP. El
        # mensaje de distancia lleva un numero variable, por eso ese caso se
        # matchea por prefijo en vez de texto exacto.
        if "Estas a " in mensaje and "metros de tu sucursal" in mensaje:
            inicio = mensaje.find("Estas a ")
            fin = mensaje.find("No se pudo marcar.") + len("No se pudo marcar.")
            raise HTTPException(status.HTTP_400_BAD_REQUEST, mensaje[inicio:fin])
        for candidato in (
            "La ventana de 5 minutos para marcar ya se cerro.",
            "La clave de asistencia todavia no fue liberada.",
            "La clave ingresada no es correcta.",
            "Ya marcaste tu asistencia hoy.",
            "Solo el personal de una tienda puede marcar asistencia.",
        ):
            if candidato in mensaje:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, candidato)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No se pudo registrar la asistencia.")

    log_bitacora(db, usuario, "CREAR", "marcado_asistencia", marcado_id, "Asistencia marcada", request)

    marcado = db.query(MarcadoAsistencia).filter(MarcadoAsistencia.id == marcado_id).first()
    return MarcadoOut(
        id=marcado.id,
        empleado_id=marcado.empleado_id,
        empleado_nombre=usuario.nombre,
        sucursal_nombre=empleado.sucursal.nombre if empleado.sucursal else None,
        fecha=marcado.fecha,
        hora_marcado=_utc(marcado.hora_marcado),
        latitud=marcado.latitud,
        longitud=marcado.longitud,
        foto_url=marcado.foto_url,
    )


@router.get("/mia", response_model=list[MarcadoOut])
def mi_historial(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso("CU01")),
) -> list[MarcadoOut]:
    # Historial completo del empleado (el frontend arma la tabla Lunes-
    # Domingo de la semana actual a partir de esta lista).
    filas = (
        db.query(MarcadoAsistencia)
        .filter(MarcadoAsistencia.empleado_id == usuario.id)
        .order_by(MarcadoAsistencia.fecha.desc())
        .limit(90)
        .all()
    )
    return [
        MarcadoOut(
            id=m.id, empleado_id=m.empleado_id, empleado_nombre=usuario.nombre,
            sucursal_nombre=empleado.sucursal.nombre if (empleado := m.empleado) and empleado.sucursal else None,
            fecha=m.fecha, hora_marcado=_utc(m.hora_marcado), latitud=m.latitud, longitud=m.longitud, foto_url=m.foto_url,
        )
        for m in filas
    ]


@router.get("/hoy", response_model=list[MarcadoHoyOut])
def marcados_hoy(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
) -> list[MarcadoHoyOut]:
    empresa = _empresa_asistencia(admin, empresa_id)
    fila_estado = _estado_hoy(db, empresa)
    hoy: date = fila_estado["codigo_fecha"]
    empleados = (
        db.query(Empleado)
        .filter(
            Empleado.estado == "activo",
            Empleado.empresa_id == empresa,
            Empleado.tipo.in_(PERSONAL_ASISTENCIA),
        )
        .all()
    )
    marcados = {m.empleado_id: m for m in db.query(MarcadoAsistencia).filter(MarcadoAsistencia.fecha == hoy).all()}

    resultado = []
    for emp in empleados:
        m = marcados.get(emp.id)
        if m is not None:
            estado = "marco"
        elif fila_estado["ventana_cerrada"]:
            estado = "falta"
        else:
            estado = "pendiente"
        resultado.append(
            MarcadoHoyOut(
                empleado_id=emp.id,
                empleado_nombre=emp.nombre,
                sucursal_nombre=emp.sucursal.nombre if emp.sucursal else None,
                marco=m is not None,
                hora_marcado=_utc(m.hora_marcado) if m else None,
                estado=estado,
            )
        )
    orden = {"pendiente": 0, "falta": 1, "marco": 2}
    resultado.sort(key=lambda r: (orden[r.estado], r.empleado_nombre))
    return resultado


@router.get("/historial", response_model=list[MarcadoOut])
def historial_completo(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    empleado_id: int | None = Query(default=None),
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_administrador),
) -> list[MarcadoOut]:
    empresa = _empresa_asistencia(admin, empresa_id)
    desde = fecha_desde or (date.today() - timedelta(days=7))
    hasta = fecha_hasta or date.today()

    # Solo los marcados del personal de esa empresa.
    query = (
        db.query(MarcadoAsistencia)
        .join(Empleado, Empleado.id == MarcadoAsistencia.empleado_id)
        .filter(
            MarcadoAsistencia.fecha >= desde,
            MarcadoAsistencia.fecha <= hasta,
            Empleado.empresa_id == empresa,
        )
    )
    if empleado_id:
        query = query.filter(MarcadoAsistencia.empleado_id == empleado_id)

    filas = query.order_by(MarcadoAsistencia.fecha.desc(), MarcadoAsistencia.hora_marcado.desc()).all()
    return [
        MarcadoOut(
            id=m.id, empleado_id=m.empleado_id, empleado_nombre=m.empleado.nombre,
            sucursal_nombre=m.empleado.sucursal.nombre if m.empleado.sucursal else None,
            fecha=m.fecha, hora_marcado=_utc(m.hora_marcado), latitud=m.latitud, longitud=m.longitud, foto_url=m.foto_url,
        )
        for m in filas
    ]
