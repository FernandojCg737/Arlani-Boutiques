from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.api.deps import ADMIN_TIPOS, get_current_user, get_current_user_optional, require_permiso, require_permiso_cliente
from app.core.gemini import generar_razones, generar_razones_relacionados
from app.db.session import get_db
from app.ml.recomendador import para_cliente, parecidas
from app.ml.servicio import recomendador_activo
from app.services.usuarios import codigos_permiso
from app.models import Cliente, Usuario
from app.schemas.recomendaciones import (
    RecomendacionAdminOut,
    RecomendacionOut,
    RecomendacionPage,
    RecomendacionResumen,
    RelacionadoAdminOut,
    RelacionadoOut,
    RelacionadoPage,
    RelacionadoResumen,
)

router = APIRouter()

# CU18 "Recomendar Prendas por IA": el ranking (que productos recomendar y
# en que orden) lo da el modelo de recomendacion de cada tienda
# (app/ml/recomendador.py: hibrido de contenido TF-IDF y filtrado
# colaborativo KNN, entrenado y evaluado con sus ventas y vistas). Las
# reglas en SQL de abajo quedan de respaldo -- prendas nuevas que el modelo
# todavia no conoce, o una tienda sin modelo entrenado --: "comprado junto
# a" (co-ocurrencia en ventas de otros clientes), "similar a lo que ya
# compraste" (misma categoria/marca) y los mas vendidos. La IA (Gemini) no elige
# los productos: solo redacta la razon personalizada de cada uno, y tiene
# una razon generica de respaldo si no hay API key o la llamada falla, asi
# que la funcionalidad nunca depende 100% de un servicio externo.

_UMBRAL_REFRESH = timedelta(hours=24)

_DETALLE_BASE = """
    SELECT dvp.id, il.producto_id, il.cantidad, v.id AS venta_id, v.cliente_id
    FROM detalle_venta_presencial dvp
    JOIN item_linea il ON il.id = dvp.id
    JOIN venta_presencial vp ON vp.id = dvp.venta_presencial_id
    JOIN venta v ON v.id = vp.id
    JOIN pago p ON p.venta_id = v.id
    WHERE p.estado = 'completado'
    UNION ALL
    SELECT dvd.id, il.producto_id, il.cantidad, v.id AS venta_id, v.cliente_id
    FROM detalle_venta_digital dvd
    JOIN item_linea il ON il.id = dvd.id
    JOIN venta_digital vd ON vd.id = dvd.venta_digital_id
    JOIN venta v ON v.id = vd.id
    JOIN pago p ON p.venta_id = v.id
    WHERE p.estado = 'completado'
"""


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes tienen recomendaciones.")
    return cliente


def _historial_nombres(db: Session, cliente_id: int) -> list[str]:
    rows = db.execute(
        text(
            f"WITH dvc AS ({_DETALLE_BASE}) "
            "SELECT DISTINCT p.nombre FROM dvc JOIN producto p ON p.id = dvc.producto_id "
            "WHERE dvc.cliente_id = :cid LIMIT 5"
        ),
        {"cid": cliente_id},
    ).all()
    return [r[0] for r in rows]


def _con_stock(db: Session, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    return {f[0] for f in db.execute(
        text("""SELECT p.id FROM producto p WHERE p.id IN :ids AND p.estado = 'activo'
                AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = p.id AND inv.cantidad > 0)"""
             ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    )}


def _candidatos_modelo(db: Session, cliente_id: int, n: int) -> list[dict]:
    """Con el modelo de cada tienda donde el cliente compro o miro algo: lo
    parecido a su historial (compras pesan 3, vistas 1), sin lo que compro
    en los ultimos 30 dias."""
    filas = db.execute(
        text(f"""SELECT p.empresa_id, x.producto_id, sum(x.peso) AS peso, bool_or(x.reciente) AS reciente FROM (
                     SELECT dvc.producto_id, 3.0 AS peso, v.fecha > now() - interval '30 days' AS reciente
                     FROM ({_DETALLE_BASE}) dvc JOIN venta v ON v.id = dvc.venta_id WHERE dvc.cliente_id = :cid
                     UNION ALL
                     SELECT producto_id, 1.0, false FROM vista_producto WHERE cliente_id = :cid
                 ) x JOIN producto p ON p.id = x.producto_id GROUP BY p.empresa_id, x.producto_id"""),
        {"cid": cliente_id},
    ).all()
    por_tienda: dict[int, list] = {}
    for f in filas:
        por_tienda.setdefault(f.empresa_id, []).append(f)
    candidatos: list[dict] = []
    for empresa_id, historial in por_tienda.items():
        artefacto = recomendador_activo(db, empresa_id)
        if artefacto is None:
            continue
        perfil = {f.producto_id: float(f.peso) for f in historial}
        recientes = {f.producto_id for f in historial if f.reciente}
        for pid, score in para_cliente(artefacto, perfil, recientes, n):
            candidatos.append({"producto_id": pid, "score": score, "origen": "modelo_ml"})
    disponibles = _con_stock(db, [c["producto_id"] for c in candidatos])
    candidatos = [c for c in candidatos if c["producto_id"] in disponibles]
    candidatos.sort(key=lambda c: -c["score"])
    return candidatos[:n]


def _generar_candidatos(db: Session, cliente_id: int, n: int = 8) -> list[dict]:
    # Primero el modelo; las reglas completan si faltan.
    candidatos = _candidatos_modelo(db, cliente_id, n)
    if len(candidatos) >= n:
        return candidatos
    compras = [
        r[0]
        for r in db.execute(
            text(f"WITH dvc AS ({_DETALLE_BASE}) SELECT DISTINCT producto_id FROM dvc WHERE cliente_id = :cid"),
            {"cid": cliente_id},
        ).all()
    ]

    vistos: set[int] = set(compras) | {c["producto_id"] for c in candidatos}

    if compras and len(candidatos) < n:
        co_occurrence = db.execute(
            text(
                f"""
                WITH dvc AS ({_DETALLE_BASE}),
                ventas_relacionadas AS (
                    SELECT DISTINCT venta_id FROM dvc WHERE producto_id IN :compras
                )
                SELECT dvc.producto_id, COUNT(DISTINCT dvc.venta_id) AS frecuencia
                FROM dvc
                WHERE dvc.venta_id IN (SELECT venta_id FROM ventas_relacionadas)
                  AND dvc.producto_id NOT IN :compras
                  AND EXISTS (SELECT 1 FROM producto pr WHERE pr.id = dvc.producto_id AND pr.estado = 'activo')
                  AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = dvc.producto_id AND inv.cantidad > 0)
                GROUP BY dvc.producto_id
                ORDER BY frecuencia DESC
                LIMIT 6
                """
            ).bindparams(bindparam("compras", expanding=True)),
            {"compras": compras},
        ).all()

        if co_occurrence:
            max_frec = max(f for _, f in co_occurrence)
            for producto_id, frecuencia in co_occurrence:
                candidatos.append(
                    {"producto_id": producto_id, "score": round(float(frecuencia) / max_frec, 4), "origen": "compra_conjunta"}
                )
                vistos.add(producto_id)

        if len(candidatos) < n:
            contenido = db.execute(
                text(
                    """
                    SELECT p.id, COUNT(*) AS coincidencias
                    FROM producto p
                    JOIN producto pc ON pc.id IN :compras
                    WHERE p.estado = 'activo' AND p.id NOT IN :compras
                      AND (p.categoria_id = pc.categoria_id OR p.marca_id = pc.marca_id)
                      AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = p.id AND inv.cantidad > 0)
                    GROUP BY p.id
                    ORDER BY coincidencias DESC
                    LIMIT 12
                    """
                ).bindparams(bindparam("compras", expanding=True)),
                {"compras": compras},
            ).all()
            max_coinc = max((c for _, c in contenido), default=1)
            for producto_id, coincidencias in contenido:
                if len(candidatos) >= n:
                    break
                if producto_id in vistos:
                    continue
                candidatos.append(
                    {
                        "producto_id": producto_id,
                        "score": round((float(coincidencias) / max_coinc) * 0.8, 4),
                        "origen": "similar_categoria",
                    }
                )
                vistos.add(producto_id)

    if len(candidatos) < n:
        excluidos = list(vistos) or [0]
        mas_vendidos = db.execute(
            text(
                f"""
                WITH dvc AS ({_DETALLE_BASE})
                SELECT dvc.producto_id, SUM(dvc.cantidad) AS unidades
                FROM dvc
                WHERE dvc.producto_id NOT IN :excluidos
                  AND EXISTS (SELECT 1 FROM producto pr WHERE pr.id = dvc.producto_id AND pr.estado = 'activo')
                  AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = dvc.producto_id AND inv.cantidad > 0)
                GROUP BY dvc.producto_id
                ORDER BY unidades DESC
                LIMIT 20
                """
            ).bindparams(bindparam("excluidos", expanding=True)),
            {"excluidos": excluidos},
        ).all()
        max_unidades = max((u for _, u in mas_vendidos), default=1)
        for producto_id, unidades in mas_vendidos:
            if len(candidatos) >= n:
                break
            if producto_id in vistos:
                continue
            candidatos.append(
                {"producto_id": producto_id, "score": round((float(unidades) / max_unidades) * 0.6, 4), "origen": "mas_vendido"}
            )
            vistos.add(producto_id)

    return candidatos


def _regenerar_recomendaciones(db: Session, cliente: Cliente) -> None:
    candidatos = _generar_candidatos(db, cliente.id)
    if not candidatos:
        return

    ids = [c["producto_id"] for c in candidatos]
    nombres = dict(
        db.execute(
            text("SELECT id, nombre FROM producto WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    )
    for c in candidatos:
        c["nombre"] = nombres.get(c["producto_id"], "")

    razones = generar_razones(cliente.nombre, _historial_nombres(db, cliente.id), candidatos)

    for c in candidatos:
        db.execute(
            text(
                """
                INSERT INTO recomendacion (cliente_id, producto_id, score, origen, fecha, razon, convertido)
                VALUES (:cliente_id, :producto_id, :score, :origen, now(), :razon, false)
                ON CONFLICT (cliente_id, producto_id) DO UPDATE SET
                    score = EXCLUDED.score, origen = EXCLUDED.origen, fecha = EXCLUDED.fecha, razon = EXCLUDED.razon
                """
            ),
            {
                "cliente_id": cliente.id,
                "producto_id": c["producto_id"],
                "score": c["score"],
                "origen": c["origen"],
                "razon": razones.get(c["producto_id"], ""),
            },
        )
    db.commit()


# ---------- Cliente ----------


@router.get("/mias", response_model=list[RecomendacionOut])
def mis_recomendaciones(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU18")),
) -> list[RecomendacionOut]:
    cliente = _get_cliente_o_403(db, usuario)

    ultima = db.execute(
        text("SELECT MAX(fecha) FROM recomendacion WHERE cliente_id = :cid"), {"cid": cliente.id}
    ).scalar_one()
    if ultima is None or (datetime.utcnow() - ultima) > _UMBRAL_REFRESH:
        _regenerar_recomendaciones(db, cliente)

    filas = db.execute(
        text(
            "SELECT r.producto_id, p.nombre, r.score, r.origen, r.razon "
            "FROM recomendacion r JOIN producto p ON p.id = r.producto_id "
            "WHERE r.cliente_id = :cid ORDER BY r.score DESC"
        ),
        {"cid": cliente.id},
    ).all()

    return [
        RecomendacionOut(
            producto_id=f[0], producto_nombre=f[1], score=Decimal(str(f[2])), origen=f[3], razon=f[4] or ""
        )
        for f in filas
    ]


# ---------- Staff: Administrador (CU18) ----------


@router.get("", response_model=RecomendacionPage)
def listar_recomendaciones(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    origen: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU18")),
) -> RecomendacionPage:
    where = "1=1" if not origen else "r.origen = :origen"
    params: dict = {"origen": origen} if origen else {}

    resumen_row = db.execute(
        text(
            f"SELECT COUNT(*), COUNT(*) FILTER (WHERE r.convertido) FROM recomendacion r WHERE {where}"
        ),
        params,
    ).one()
    total_activas, convertidas = int(resumen_row[0]), int(resumen_row[1])
    tasa = round((convertidas / total_activas * 100), 1) if total_activas else 0.0

    total = db.execute(text(f"SELECT COUNT(*) FROM recomendacion r WHERE {where}"), params).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT r.id, r.cliente_id, u.nombre, u.email, r.producto_id, p.nombre, r.score, r.origen,
                   r.razon, r.convertido, r.fecha
            FROM recomendacion r
            JOIN cliente c ON c.id = r.cliente_id
            JOIN usuario u ON u.id = c.id
            JOIN producto p ON p.id = r.producto_id
            WHERE {where}
            ORDER BY r.fecha DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    items = [
        RecomendacionAdminOut(
            id=r[0], cliente_id=r[1], cliente_nombre=r[2], cliente_email=r[3], producto_id=r[4],
            producto_nombre=r[5], score=Decimal(str(r[6])), origen=r[7], razon=r[8], convertido=r[9], fecha=r[10],
        )
        for r in rows
    ]

    return RecomendacionPage(
        resumen=RecomendacionResumen(total_activas=total_activas, convertidas=convertidas, tasa_conversion=tasa),
        items=items,
        total=int(total),
        page=page,
        page_size=page_size,
    )


# ----------------------------------------------------------------------
# "Tambien te puede interesar" (detalle de producto) -- a diferencia de
# "Recomendado para ti" (dashboard, arriba), esto no depende del historial
# de UN cliente: el ranking se arma por PRODUCTO, en base a que otros
# productos vieron juntos los clientes que pasaron por este mismo, con la
# misma logica de respaldo en cascada que el resto del motor (co-vista ->
# misma categoria/marca -> mas vendido). Se muestra a cualquier visitante,
# tenga sesion o no; solo se registra la vista (para alimentar la senal de
# co-vista a futuro) cuando hay un cliente autenticado.
# ----------------------------------------------------------------------

_UMBRAL_REFRESH_RELACIONADOS = timedelta(hours=24)


def _generar_relacionados(db: Session, producto_id: int, n: int = 6) -> list[dict]:
    candidatos: list[dict] = []
    vistos: set[int] = {producto_id}
    # Solo prendas de la MISMA tienda (antes las reglas mezclaban tiendas).
    empresa_id = db.execute(text("SELECT empresa_id FROM producto WHERE id = :pid"), {"pid": producto_id}).scalar()
    e = {"e": empresa_id}

    # Primero el modelo de la tienda; las reglas completan si faltan.
    artefacto = recomendador_activo(db, empresa_id) if empresa_id else None
    if artefacto is not None:
        sugeridas = parecidas(artefacto, producto_id, n * 2)
        disponibles = _con_stock(db, [pid for pid, _ in sugeridas])
        for pid, score in sugeridas:
            if pid in disponibles and len(candidatos) < n:
                candidatos.append({"producto_id": pid, "score": score, "origen": "modelo_ml"})
                vistos.add(pid)

    co_vista = [] if len(candidatos) >= n else db.execute(
        text(
            """
            SELECT vp2.producto_id, COUNT(DISTINCT vp2.cliente_id) AS frecuencia
            FROM vista_producto vp1
            JOIN vista_producto vp2 ON vp2.cliente_id = vp1.cliente_id AND vp2.producto_id != vp1.producto_id
            WHERE vp1.producto_id = :pid
              AND EXISTS (SELECT 1 FROM producto pr WHERE pr.id = vp2.producto_id AND pr.estado = 'activo' AND pr.empresa_id = :e)
              AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = vp2.producto_id AND inv.cantidad > 0)
            GROUP BY vp2.producto_id
            ORDER BY frecuencia DESC
            LIMIT 6
            """
        ),
        {"pid": producto_id, **e},
    ).all()
    if co_vista:
        max_frec = max(f for _, f in co_vista)
        for pid, frecuencia in co_vista:
            if pid in vistos or len(candidatos) >= n:
                continue
            candidatos.append({"producto_id": pid, "score": round(float(frecuencia) / max_frec, 4), "origen": "vistos_juntos"})
            vistos.add(pid)

    if len(candidatos) < n:
        contenido = db.execute(
            text(
                """
                SELECT p.id, (CASE WHEN p.categoria_id = pb.categoria_id THEN 1 ELSE 0 END
                            + CASE WHEN p.marca_id = pb.marca_id THEN 1 ELSE 0 END) AS coincidencias
                FROM producto p, producto pb
                WHERE pb.id = :pid AND p.id != :pid AND p.estado = 'activo' AND p.empresa_id = pb.empresa_id
                  AND (p.categoria_id = pb.categoria_id OR p.marca_id = pb.marca_id)
                  AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = p.id AND inv.cantidad > 0)
                ORDER BY coincidencias DESC, p.id
                LIMIT 12
                """
            ),
            {"pid": producto_id},
        ).all()
        for pid, coincidencias in contenido:
            if len(candidatos) >= n:
                break
            if pid in vistos:
                continue
            candidatos.append({"producto_id": pid, "score": round(0.5 + 0.15 * coincidencias, 4), "origen": "similar_categoria"})
            vistos.add(pid)

    if len(candidatos) < n:
        excluidos = list(vistos)
        mas_vendidos = db.execute(
            text(
                f"""
                WITH dvc AS ({_DETALLE_BASE})
                SELECT dvc.producto_id, SUM(dvc.cantidad) AS unidades
                FROM dvc
                WHERE dvc.producto_id NOT IN :excluidos
                  AND EXISTS (SELECT 1 FROM producto pr WHERE pr.id = dvc.producto_id AND pr.estado = 'activo' AND pr.empresa_id = :e)
                  AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = dvc.producto_id AND inv.cantidad > 0)
                GROUP BY dvc.producto_id
                ORDER BY unidades DESC
                LIMIT 20
                """
            ).bindparams(bindparam("excluidos", expanding=True)),
            {"excluidos": excluidos, **e},
        ).all()
        max_unidades = max((u for _, u in mas_vendidos), default=1)
        for pid, unidades in mas_vendidos:
            if len(candidatos) >= n:
                break
            if pid in vistos:
                continue
            candidatos.append({"producto_id": pid, "score": round((float(unidades) / max_unidades) * 0.4, 4), "origen": "mas_vendido"})
            vistos.add(pid)

    # Ultimo respaldo: si el producto no tiene vistas en conjunto todavia,
    # no comparte categoria/marca con ningun otro producto activo, y nunca
    # se vendio (asi que tampoco aparece en "mas_vendido"), los pasos de
    # arriba pueden devolver la lista vacia -- reportado por el usuario
    # probando: "algunos productos no tienen recomendaciones". Este ultimo
    # nivel no filtra por nada mas que "activo y con stock", asi que
    # siempre hay candidatos mientras exista al menos otro producto asi en
    # el catalogo.
    if len(candidatos) < n:
        excluidos = list(vistos)
        resto = db.execute(
            text(
                """
                SELECT p.id FROM producto p
                WHERE p.id NOT IN :excluidos AND p.estado = 'activo' AND p.empresa_id = :e
                  AND EXISTS (SELECT 1 FROM inventario inv WHERE inv.producto_id = p.id AND inv.cantidad > 0)
                ORDER BY p.id
                LIMIT 12
                """
            ).bindparams(bindparam("excluidos", expanding=True)),
            {"excluidos": excluidos, **e},
        ).all()
        for (pid,) in resto:
            if len(candidatos) >= n:
                break
            candidatos.append({"producto_id": pid, "score": 0.1, "origen": "catalogo_general"})
            vistos.add(pid)

    return candidatos


def _regenerar_relacionados(db: Session, producto_id: int, producto_nombre: str) -> None:
    candidatos = _generar_relacionados(db, producto_id)
    if not candidatos:
        return

    ids = [c["producto_id"] for c in candidatos]
    nombres = dict(
        db.execute(
            text("SELECT id, nombre FROM producto WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    )
    for c in candidatos:
        c["nombre"] = nombres.get(c["producto_id"], "")

    razones = generar_razones_relacionados(producto_nombre, candidatos)

    for c in candidatos:
        db.execute(
            text(
                """
                INSERT INTO producto_relacionado (producto_id, relacionado_id, score, origen, fecha, razon)
                VALUES (:producto_id, :relacionado_id, :score, :origen, now(), :razon)
                ON CONFLICT (producto_id, relacionado_id) DO UPDATE SET
                    score = EXCLUDED.score, origen = EXCLUDED.origen, fecha = EXCLUDED.fecha, razon = EXCLUDED.razon
                """
            ),
            {
                "producto_id": producto_id,
                "relacionado_id": c["producto_id"],
                "score": c["score"],
                "origen": c["origen"],
                "razon": razones.get(c["producto_id"], ""),
            },
        )
    db.commit()


@router.post("/vista/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def registrar_vista(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_current_user_optional),
) -> None:
    """Se llama al abrir el detalle de un producto (web y movil), sin
    bloquear la pagina por el resultado. Si no hay sesion (cliente
    navegando sin loguearse) simplemente no queda registro -- la vista no
    es obligatoria para VER la pagina, solo alimenta la senal de "vistos
    juntos" para clientes logueados."""
    if usuario is None:
        return
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        return
    db.execute(
        text("INSERT INTO vista_producto (cliente_id, producto_id, fecha) VALUES (:cid, :pid, now())"),
        {"cid": cliente.id, "pid": producto_id},
    )
    db.commit()


@router.get("/relacionados/{producto_id}", response_model=list[RelacionadoOut])
def productos_relacionados(
    producto_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_current_user_optional),
) -> list[RelacionadoOut]:
    # Publico (funciona para visitantes sin sesion, igual que antes). Si hay
    # un cliente logueado y CU18 esta apagado para el rol Cliente (CU02),
    # se devuelve vacio en vez de la lista -- no rompe la pagina, solo no
    # muestra el widget. A un visitante anonimo no le afecta este toggle.
    if usuario is not None and usuario.tipo not in ADMIN_TIPOS:
        if "CU18" not in codigos_permiso(usuario):
            return []

    producto = db.execute(text("SELECT nombre FROM producto WHERE id = :pid"), {"pid": producto_id}).first()
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado.")

    ultima = db.execute(
        text("SELECT MAX(fecha) FROM producto_relacionado WHERE producto_id = :pid"), {"pid": producto_id}
    ).scalar_one()
    if ultima is None or (datetime.utcnow() - ultima) > _UMBRAL_REFRESH_RELACIONADOS:
        _regenerar_relacionados(db, producto_id, producto[0])

    filas = db.execute(
        text(
            "SELECT pr.relacionado_id, p.nombre, pr.origen, pr.razon "
            "FROM producto_relacionado pr JOIN producto p ON p.id = pr.relacionado_id "
            "WHERE pr.producto_id = :pid AND p.estado = 'activo' ORDER BY pr.score DESC"
        ),
        {"pid": producto_id},
    ).all()

    return [
        RelacionadoOut(producto_id=f[0], producto_nombre=f[1], origen=f[2], razon=f[3] or "") for f in filas
    ]


@router.get("/relacionados-admin", response_model=RelacionadoPage)
def listar_relacionados_admin(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    origen: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU18")),
) -> RelacionadoPage:
    """Auditoria de "Tambien te puede interesar" (tabla producto_relacionado,
    separada de "recomendacion"): a diferencia del panel de arriba, aca no
    hay conversion que medir (no es una recomendacion personalizada a UN
    cliente) -- lo que importa auditar es la COBERTURA: cuantos de los
    productos activos ya tienen su cache de relacionados generada, para
    confirmar que ningun producto se quede sin recomendaciones (el bug que
    reporto el usuario y que motivo el fallback "catalogo_general")."""
    where = "1=1" if not origen else "pr.origen = :origen"
    params: dict = {"origen": origen} if origen else {}

    productos_totales = db.execute(
        text("SELECT COUNT(*) FROM producto WHERE estado = 'activo'")
    ).scalar_one()
    productos_cubiertos = db.execute(
        text("SELECT COUNT(DISTINCT producto_id) FROM producto_relacionado")
    ).scalar_one()
    cobertura = round((productos_cubiertos / productos_totales * 100), 1) if productos_totales else 0.0

    total = db.execute(text(f"SELECT COUNT(*) FROM producto_relacionado pr WHERE {where}"), params).scalar_one()

    rows = db.execute(
        text(
            f"""
            SELECT pr.id, pr.producto_id, pbase.nombre, pr.relacionado_id, prel.nombre, pr.score, pr.origen,
                   pr.razon, pr.fecha
            FROM producto_relacionado pr
            JOIN producto pbase ON pbase.id = pr.producto_id
            JOIN producto prel ON prel.id = pr.relacionado_id
            WHERE {where}
            ORDER BY pr.fecha DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {**params, "limit": page_size, "offset": (page - 1) * page_size},
    ).all()

    items = [
        RelacionadoAdminOut(
            id=r[0], producto_id=r[1], producto_nombre=r[2], relacionado_id=r[3], relacionado_nombre=r[4],
            score=Decimal(str(r[5])), origen=r[6], razon=r[7], fecha=r[8],
        )
        for r in rows
    ]

    return RelacionadoPage(
        resumen=RelacionadoResumen(
            productos_totales=int(productos_totales), productos_cubiertos=int(productos_cubiertos), cobertura_pct=cobertura
        ),
        items=items,
        total=int(total),
        page=page,
        page_size=page_size,
    )
