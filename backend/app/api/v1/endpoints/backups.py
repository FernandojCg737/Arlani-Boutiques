"""CU21 Gestionar backups y restauracion (P1 Seguridad y Acceso).

- Tienda: el Administrador (o su personal con el permiso 2P-CU21) respalda y
  restaura los datos de su tienda. Solo planes Basico y Profesional.
- SuperAdministrador: con ?empresa_id=<id> trabaja sobre esa tienda; sin el,
  sobre el sistema completo (todas las tiendas y la plataforma).
Los backups se arman y se restauran en segundo plano (el motor esta en
app/core/backups.py); la pantalla consulta su estado.
"""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import require_permiso
from app.core import backups as motor
from app.core.audit import client_ip, client_platform
from app.db.session import get_db
from app.models import Usuario

router = APIRouter()

PERMISO = "2P-CU21"


# ---------------------------------------------------------------- esquemas


class SeccionOut(BaseModel):
    codigo: str
    nombre: str


class EstadoOut(BaseModel):
    disponible: bool
    sistema: bool
    plan: str | None
    secciones: list[SeccionOut]


class BackupIn(BaseModel):
    secciones: list[str] = Field(min_length=1)


class BackupOut(BaseModel):
    id: int
    empresa_id: int | None
    alcance: str
    secciones: list[str]
    origen: str
    programacion_id: int | None
    programacion_nombre: str | None
    estado: str
    tamano_bytes: int | None
    conteos: dict | None
    imagenes: int | None
    atrasado: bool
    error: str | None
    creado_por: str | None
    creado_en: datetime
    completado_en: datetime | None


class RestaurarIn(BaseModel):
    secciones: list[str] = Field(min_length=1)
    # El sistema completo pide escribir RESTAURAR.
    confirmacion: str | None = None


class RestauracionOut(BaseModel):
    id: int
    backup_id: int | None
    backup_creado_en: datetime | None
    secciones: list[str]
    estado: str
    resumen: dict | None
    backup_previo_id: int | None
    error: str | None
    hecho_por: str | None
    creado_en: datetime
    completado_en: datetime | None


class ProgramacionIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    frecuencia: str = Field(pattern="^(una_vez|diaria|semanal|mensual)$")
    # Hora de Bolivia.
    hora: time
    fecha: date | None = None
    dia_semana: int | None = Field(default=None, ge=0, le=6)
    dia_mes: int | None = Field(default=None, ge=1, le=31)
    secciones: list[str] = Field(min_length=1)
    retener: int = Field(default=10, ge=1, le=60)
    activa: bool = True


class ProgramacionOut(BaseModel):
    id: int
    nombre: str
    frecuencia: str
    hora: time
    fecha: date | None
    dia_semana: int | None
    dia_mes: int | None
    secciones: list[str]
    retener: int
    activa: bool
    proxima_ejecucion: datetime | None
    ultima_ejecucion: datetime | None
    backups: int
    creado_en: datetime


# ---------------------------------------------------------------- ambito


def _ambito(db: Session, usuario: Usuario, empresa_id: int | None) -> int | None:
    """Tienda sobre la que se trabaja, o None para el sistema completo."""
    if usuario.tipo == "superadministrador":
        if empresa_id is not None and db.execute(text("SELECT 1 FROM empresa WHERE id = :e"), {"e": empresa_id}).first() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa no encontrada.")
        return empresa_id
    if usuario.empresa_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Los backups son del personal de una tienda.")
    return usuario.empresa_id


def _exigir_plan(db: Session, usuario: Usuario, empresa: int | None) -> None:
    # El SuperAdministrador puede respaldar cualquier tienda, tenga el plan que tenga.
    if empresa is None or usuario.tipo == "superadministrador":
        return
    disponible, plan = motor.plan_con_backups(db.connection(), empresa)
    if not disponible:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Los backups son de los planes Básico y Profesional (la tienda tiene el plan {plan or 'actual'}).",
        )


def _secciones_validas(secciones: list[str], empresa: int | None) -> list[str]:
    permitidas = motor.SECCIONES if empresa is not None else motor.SECCIONES_SISTEMA
    malas = [s for s in secciones if s not in permitidas]
    if malas:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Sección desconocida: {', '.join(malas)}.")
    return [s for s in permitidas if s in secciones]


def _backup(db: Session, backup_id: int, empresa: int | None):
    fila = db.execute(
        text("SELECT * FROM backup WHERE id = :i AND empresa_id IS NOT DISTINCT FROM :e"), {"i": backup_id, "e": empresa}
    ).mappings().first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup no encontrado.")
    return fila


def _registrar(db: Session, usuario: Usuario, accion: str, entidad: str, entidad_id: int | None, detalle: str,
               request: Request, empresa: int | None) -> None:
    """Bitacora (CU08) con la tienda a la que se refiere, tambien si lo hizo el
    SuperAdministrador (asi la tienda lo ve en su bitacora)."""
    motor.registrar_bitacora(db.connection(), usuario.id, accion, entidad, entidad_id, detalle, empresa,
                             client_ip(request), client_platform(request))


def _donde(empresa: int | None) -> str:
    return "del sistema completo" if empresa is None else "de la tienda"


# ------------------------------------------------------------------ backups


@router.get("/estado", response_model=EstadoOut)
def estado(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> EstadoOut:
    empresa = _ambito(db, usuario, empresa_id)
    disponible, plan = (True, None) if empresa is None else motor.plan_con_backups(db.connection(), empresa)
    secciones = motor.SECCIONES if empresa is not None else motor.SECCIONES_SISTEMA
    return EstadoOut(
        disponible=disponible or usuario.tipo == "superadministrador", sistema=empresa is None, plan=plan,
        secciones=[SeccionOut(codigo=c, nombre=n) for c, n in secciones.items()],
    )


@router.get("", response_model=list[BackupOut])
def listar(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> list[BackupOut]:
    empresa = _ambito(db, usuario, empresa_id)
    filas = db.execute(
        text(
            """SELECT b.*, p.nombre AS programacion_nombre, u.nombre AS creado_por
               FROM backup b LEFT JOIN backup_programacion p ON p.id = b.programacion_id
               LEFT JOIN usuario u ON u.id = b.creado_por_id
               WHERE b.empresa_id IS NOT DISTINCT FROM :e ORDER BY b.creado_en DESC LIMIT 200"""
        ),
        {"e": empresa},
    ).mappings().all()
    return [BackupOut(**f) for f in filas]


@router.post("", response_model=BackupOut, status_code=status.HTTP_202_ACCEPTED)
def crear(
    payload: BackupIn,
    request: Request,
    tareas: BackgroundTasks,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> BackupOut:
    empresa = _ambito(db, usuario, empresa_id)
    _exigir_plan(db, usuario, empresa)
    secciones = _secciones_validas(payload.secciones, empresa)
    if db.execute(
        text("SELECT 1 FROM backup WHERE empresa_id IS NOT DISTINCT FROM :e AND estado = 'en_proceso' AND origen = 'manual'"),
        {"e": empresa},
    ).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un backup en proceso: espera a que termine.")
    backup_id = motor.crear_backup(db.connection(), empresa, secciones, "manual", usuario.id)
    _registrar(db, usuario, "CREAR", "backup", backup_id, f"Backup manual {_donde(empresa)} ({', '.join(secciones)})", request, empresa)
    db.commit()
    tareas.add_task(motor.generar_backup, backup_id)
    return next(b for b in listar(empresa_id, db, usuario) if b.id == backup_id)


@router.get("/{backup_id}/descargar")
def descargar(
    backup_id: int,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> Response:
    empresa = _ambito(db, usuario, empresa_id)
    fila = _backup(db, backup_id, empresa)
    if fila["estado"] != "completado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese backup no se completó.")
    try:
        contenido = motor.descargar_archivos(fila["archivos"])
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    _registrar(db, usuario, "DESCARGAR", "backup", backup_id, f"Descargó el backup #{backup_id} {_donde(empresa)}", request, empresa)
    db.commit()
    nombre = f"arlani-backup-{backup_id}-{fila['creado_en']:%Y%m%d-%H%M}.zip"
    return Response(contenido, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/importar", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def importar(
    request: Request,
    archivo: UploadFile = File(...),
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> BackupOut:
    """Sube un ZIP descargado antes (Descargar) y lo deja como un backup mas,
    listo para restaurar. Solo se aceptan ZIP de este sistema sin cambios
    (firma) y del mismo ambito: una tienda solo importa sus propios backups."""
    empresa = _ambito(db, usuario, empresa_id)
    _exigir_plan(db, usuario, empresa)
    contenido = archivo.file.read(motor.MAX_IMPORTAR + 1)
    if len(contenido) > motor.MAX_IMPORTAR:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "El archivo supera los 300 MB.")
    try:
        backup_id, meta = motor.importar_backup(db.connection(), contenido, empresa, usuario.id)
    except motor.ImportacionInvalida as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    original = str(meta.get("creado_en") or "")[:16].replace("T", " ")
    _registrar(
        db, usuario, "IMPORTAR", "backup", backup_id,
        f"Importó desde un archivo el backup #{meta.get('backup_id')} ({original} UTC) {_donde(empresa)} como backup #{backup_id}",
        request, empresa,
    )
    db.commit()
    return next(b for b in listar(empresa_id, db, usuario) if b.id == backup_id)


@router.delete("/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(
    backup_id: int,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> Response:
    empresa = _ambito(db, usuario, empresa_id)
    fila = _backup(db, backup_id, empresa)
    if fila["estado"] == "en_proceso":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese backup todavía se está haciendo.")
    db.execute(text("DELETE FROM backup WHERE id = :i"), {"i": backup_id})
    _registrar(db, usuario, "ELIMINAR", "backup", backup_id, f"Borró el backup #{backup_id} {_donde(empresa)}", request, empresa)
    db.commit()
    motor.borrar_archivos(fila["archivos"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------- restauracion


@router.post("/{backup_id}/restaurar", response_model=RestauracionOut, status_code=status.HTTP_202_ACCEPTED)
def restaurar(
    backup_id: int,
    payload: RestaurarIn,
    request: Request,
    tareas: BackgroundTasks,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> RestauracionOut:
    empresa = _ambito(db, usuario, empresa_id)
    _exigir_plan(db, usuario, empresa)
    fila = _backup(db, backup_id, empresa)
    if fila["estado"] != "completado":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese backup no se completó: no se puede restaurar.")
    secciones = _secciones_validas(payload.secciones, empresa)
    faltan = [s for s in secciones if s not in fila["secciones"]]
    if faltan:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Ese backup no tiene: {', '.join(faltan)}.")
    if empresa is None and (payload.confirmacion or "").strip().upper() != "RESTAURAR":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Para restaurar el sistema completo escribe RESTAURAR.")
    if db.execute(
        text("SELECT 1 FROM backup_restauracion WHERE empresa_id IS NOT DISTINCT FROM :e AND estado = 'en_proceso'"),
        {"e": empresa},
    ).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay una restauración en proceso: espera a que termine.")
    restauracion_id = db.execute(
        text(
            """INSERT INTO backup_restauracion (backup_id, empresa_id, secciones, hecho_por_id)
               VALUES (:b, :e, :s, :u) RETURNING id"""
        ),
        {"b": backup_id, "e": empresa, "s": secciones, "u": usuario.id},
    ).scalar_one()
    _registrar(
        db, usuario, "RESTAURAR", "backup", backup_id,
        f"Restauró el backup #{backup_id} {_donde(empresa)} ({', '.join(secciones)})", request, empresa,
    )
    db.commit()
    tareas.add_task(motor.restaurar_backup, restauracion_id)
    return next(r for r in restauraciones(empresa_id, db, usuario) if r.id == restauracion_id)


@router.get("/restauraciones", response_model=list[RestauracionOut])
def restauraciones(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> list[RestauracionOut]:
    empresa = _ambito(db, usuario, empresa_id)
    filas = db.execute(
        text(
            """SELECT r.*, b.creado_en AS backup_creado_en, u.nombre AS hecho_por
               FROM backup_restauracion r LEFT JOIN backup b ON b.id = r.backup_id
               LEFT JOIN usuario u ON u.id = r.hecho_por_id
               WHERE r.empresa_id IS NOT DISTINCT FROM :e ORDER BY r.creado_en DESC LIMIT 100"""
        ),
        {"e": empresa},
    ).mappings().all()
    return [RestauracionOut(**f) for f in filas]


# ------------------------------------------------------------- programacion


def _validar_programacion(payload: ProgramacionIn, empresa: int | None) -> tuple[list[str], datetime | None]:
    secciones = _secciones_validas(payload.secciones, empresa)
    if payload.frecuencia == "una_vez" and payload.fecha is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige la fecha del backup.")
    if payload.frecuencia == "semanal" and payload.dia_semana is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige el día de la semana.")
    if payload.frecuencia == "mensual" and payload.dia_mes is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige el día del mes.")
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    proxima = motor.proxima_ejecucion(payload.frecuencia, payload.hora, payload.fecha, payload.dia_semana, payload.dia_mes, ahora)
    if payload.frecuencia == "una_vez" and proxima is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La fecha y hora ya pasaron: elige una en el futuro.")
    return secciones, proxima


def _datos_programacion(payload: ProgramacionIn, secciones: list[str], proxima: datetime | None) -> dict:
    return {
        "n": payload.nombre.strip(), "f": payload.frecuencia, "h": payload.hora,
        "fe": payload.fecha if payload.frecuencia == "una_vez" else None,
        "ds": payload.dia_semana if payload.frecuencia == "semanal" else None,
        "dm": payload.dia_mes if payload.frecuencia == "mensual" else None,
        "s": secciones, "r": payload.retener, "a": payload.activa, "p": proxima if payload.activa else None,
    }


@router.get("/programaciones", response_model=list[ProgramacionOut])
def programaciones(
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> list[ProgramacionOut]:
    empresa = _ambito(db, usuario, empresa_id)
    filas = db.execute(
        text(
            """SELECT p.*, (SELECT count(*) FROM backup b WHERE b.programacion_id = p.id AND b.estado = 'completado') AS backups
               FROM backup_programacion p WHERE p.empresa_id IS NOT DISTINCT FROM :e ORDER BY p.creado_en"""
        ),
        {"e": empresa},
    ).mappings().all()
    return [ProgramacionOut(**f) for f in filas]


@router.post("/programaciones", response_model=ProgramacionOut, status_code=status.HTTP_201_CREATED)
def crear_programacion(
    payload: ProgramacionIn,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> ProgramacionOut:
    empresa = _ambito(db, usuario, empresa_id)
    _exigir_plan(db, usuario, empresa)
    secciones, proxima = _validar_programacion(payload, empresa)
    nuevo = db.execute(
        text(
            """INSERT INTO backup_programacion (empresa_id, nombre, frecuencia, hora, fecha, dia_semana, dia_mes,
                                                secciones, retener, activa, proxima_ejecucion, creado_por_id)
               VALUES (:e, :n, :f, :h, :fe, :ds, :dm, :s, :r, :a, :p, :u) RETURNING id"""
        ),
        {"e": empresa, "u": usuario.id, **_datos_programacion(payload, secciones, proxima)},
    ).scalar_one()
    _registrar(db, usuario, "CREAR", "backup_programacion", nuevo, f"Programó backups {_donde(empresa)}: {payload.nombre}", request, empresa)
    db.commit()
    return next(p for p in programaciones(empresa_id, db, usuario) if p.id == nuevo)


@router.put("/programaciones/{programacion_id}", response_model=ProgramacionOut)
def editar_programacion(
    programacion_id: int,
    payload: ProgramacionIn,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> ProgramacionOut:
    empresa = _ambito(db, usuario, empresa_id)
    _exigir_plan(db, usuario, empresa)
    secciones, proxima = _validar_programacion(payload, empresa)
    n = db.execute(
        text(
            """UPDATE backup_programacion SET nombre = :n, frecuencia = :f, hora = :h, fecha = :fe, dia_semana = :ds,
                      dia_mes = :dm, secciones = :s, retener = :r, activa = :a, proxima_ejecucion = :p
               WHERE id = :i AND empresa_id IS NOT DISTINCT FROM :e"""
        ),
        {"i": programacion_id, "e": empresa, **_datos_programacion(payload, secciones, proxima)},
    ).rowcount
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Programación no encontrada.")
    _registrar(db, usuario, "ACTUALIZAR", "backup_programacion", programacion_id,
                 f"Editó la programación de backups: {payload.nombre}", request, empresa)
    db.commit()
    return next(p for p in programaciones(empresa_id, db, usuario) if p.id == programacion_id)


@router.delete("/programaciones/{programacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar_programacion(
    programacion_id: int,
    request: Request,
    empresa_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso(PERMISO)),
) -> Response:
    empresa = _ambito(db, usuario, empresa_id)
    # Los backups que ya hizo se quedan (pasan a sin programacion).
    n = db.execute(
        text("DELETE FROM backup_programacion WHERE id = :i AND empresa_id IS NOT DISTINCT FROM :e"),
        {"i": programacion_id, "e": empresa},
    ).rowcount
    if not n:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Programación no encontrada.")
    _registrar(db, usuario, "ELIMINAR", "backup_programacion", programacion_id, "Borró una programación de backups", request, empresa)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
