from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permiso, require_permiso_cliente
from app.core.gemini import generar_respuesta_chat
from app.core.rate_limit import verificar_limite
from app.db.session import get_db
from app.models import Chatbot, ChatbotMensaje, Cliente, Usuario
from app.schemas.chatbot import ChatbotUsuarioOut, MensajeIn, MensajeOut

router = APIRouter()

# CU19 "Atender Cliente con Chatbot": el cliente escribe (o dicta por voz,
# resuelto 100% en el navegador con la Web Speech API, sin backend de por
# medio) y el bot responde con ayuda de Gemini, usando SOLO datos reales del
# catalogo/stock/sucursales como contexto -- nunca inventa precios o stock.
# Una "sesion" (tabla Chatbot) agrupa mensajes seguidos; si pasan mas de 3h
# sin actividad, el proximo mensaje abre una sesion nueva (asi el admin ve
# conversaciones separadas, no un chat infinito).

_UMBRAL_NUEVA_SESION = timedelta(hours=3)
_STOPWORDS = {
    "que", "para", "por", "con", "los", "las", "una", "unos", "unas", "del", "tiene", "tienen",
    "hay", "esta", "estan", "como", "cual", "cuales", "algo", "sobre", "quiero", "necesito", "puedo",
    "buenas", "hola", "gracias", "porfavor", "favor", "the", "and",
}


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden usar el chatbot.")
    return cliente


def _get_or_create_sesion(db: Session, cliente_id: int) -> Chatbot:
    sesion = (
        db.query(Chatbot)
        .filter(Chatbot.cliente_id == cliente_id)
        .order_by(Chatbot.fecha_inicio.desc())
        .first()
    )
    ahora = datetime.utcnow()

    if sesion:
        ultimo = (
            db.query(ChatbotMensaje)
            .filter(ChatbotMensaje.chatbot_id == sesion.id)
            .order_by(ChatbotMensaje.fecha.desc())
            .first()
        )
        referencia = ultimo.fecha if ultimo else sesion.fecha_inicio
        if ahora - referencia <= _UMBRAL_NUEVA_SESION:
            return sesion
        sesion.fecha_fin = referencia
        db.commit()

    nueva = Chatbot(cliente_id=cliente_id, canal="web", fecha_inicio=ahora)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


def _palabras_clave(mensaje: str) -> list[str]:
    crudas = "".join(c if c.isalnum() else " " for c in mensaje.lower()).split()
    return [p for p in crudas if len(p) >= 3 and p not in _STOPWORDS]


def _construir_contexto(db: Session, mensaje: str) -> str:
    bloques: list[str] = []

    sucursales = db.execute(
        text("SELECT nombre, direccion, horario_atencion FROM sucursal WHERE estado = 'activa'")
    ).all()
    if sucursales:
        lineas = [f"- {s[0]}: {s[1]}" + (f" (horario: {s[2]})" if s[2] else "") for s in sucursales]
        bloques.append("Sucursales:\n" + "\n".join(lineas))

    bloques.append(
        "Metodos de pago aceptados: efectivo en sucursal, QR por transferencia (se revisa manualmente), "
        "PayPal/tarjeta (compra en linea, cobrado en USD)."
    )

    palabras = _palabras_clave(mensaje)
    productos = db.execute(
        text(
            "SELECT p.id, p.nombre, p.descripcion, p.precio, cat.nombre, marca.nombre "
            "FROM producto p JOIN categoria cat ON cat.id = p.categoria_id JOIN marca ON marca.id = p.marca_id "
            "WHERE p.estado = 'activo'"
        )
    ).all()

    coincidencias = []
    for row in productos:
        texto = f"{row[1]} {row[2] or ''} {row[4]} {row[5]}".lower()
        if any(p in texto for p in palabras):
            coincidencias.append(row)
    coincidencias = coincidencias[:6]

    if coincidencias:
        ids = [c[0] for c in coincidencias]
        stock_rows = db.execute(
            text(
                "SELECT i.producto_id, s.nombre, SUM(i.cantidad) "
                "FROM inventario i JOIN sucursal s ON s.id = i.sucursal_id "
                "WHERE i.producto_id IN :ids GROUP BY i.producto_id, s.nombre"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
        stock_por_producto: dict[int, list[str]] = {}
        for producto_id, sucursal_nombre, cantidad in stock_rows:
            stock_por_producto.setdefault(producto_id, []).append(f"{sucursal_nombre}: {cantidad} unidades")

        lineas = []
        for pid, nombre, descripcion, precio, categoria, marca in coincidencias:
            stock_txt = "; ".join(stock_por_producto.get(pid, ["sin stock registrado"]))
            lineas.append(f"- {nombre} ({categoria}, marca {marca}) -- {precio} Bs -- Stock: {stock_txt}")
        bloques.append("Productos relevantes a la consulta:\n" + "\n".join(lineas))
    else:
        categorias = db.execute(text("SELECT DISTINCT nombre FROM categoria ORDER BY nombre")).all()
        marcas = db.execute(text("SELECT DISTINCT nombre FROM marca ORDER BY nombre")).all()
        bloques.append(
            "No se encontro un producto especifico para esta consulta. Categorias disponibles: "
            + ", ".join(c[0] for c in categorias)
            + ". Marcas disponibles: "
            + ", ".join(m[0] for m in marcas)
            + "."
        )

    return "\n\n".join(bloques)


# ---------- Cliente ----------


@router.post("/mensajes", response_model=MensajeOut, status_code=status.HTTP_201_CREATED)
def enviar_mensaje(
    payload: MensajeIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU19")),
) -> MensajeOut:
    cliente = _get_cliente_o_403(db, usuario)
    # Cada mensaje es una llamada paga a Gemini: tope por cliente para que
    # un script no dispare la factura.
    verificar_limite("chatbot-min", str(cliente.id), maximo=15, segundos=60)
    verificar_limite("chatbot-dia", str(cliente.id), maximo=300, segundos=86_400)
    sesion = _get_or_create_sesion(db, cliente.id)

    db.add(ChatbotMensaje(chatbot_id=sesion.id, remitente="cliente", mensaje=payload.mensaje))
    db.commit()

    # Solo los ultimos mensajes (Gemini usa los 10 previos al actual): antes
    # se cargaba la conversacion entera en cada mensaje.
    ultimos = (
        db.query(ChatbotMensaje)
        .filter(ChatbotMensaje.chatbot_id == sesion.id)
        .order_by(ChatbotMensaje.fecha.desc(), ChatbotMensaje.id.desc())
        .limit(11)
        .all()
    )
    historial = [(m.remitente, m.mensaje) for m in reversed(ultimos)][:-1]

    contexto = _construir_contexto(db, payload.mensaje)
    respuesta = generar_respuesta_chat(historial, contexto, payload.mensaje)

    bot_msg = ChatbotMensaje(chatbot_id=sesion.id, remitente="bot", mensaje=respuesta)
    db.add(bot_msg)
    db.commit()
    db.refresh(bot_msg)

    return MensajeOut(id=bot_msg.id, remitente=bot_msg.remitente, mensaje=bot_msg.mensaje, fecha=bot_msg.fecha)


@router.get("/mias", response_model=list[MensajeOut])
def mis_mensajes(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[MensajeOut]:
    cliente = _get_cliente_o_403(db, usuario)
    sesion = (
        db.query(Chatbot).filter(Chatbot.cliente_id == cliente.id).order_by(Chatbot.fecha_inicio.desc()).first()
    )
    if sesion is None:
        return []

    mensajes = (
        db.query(ChatbotMensaje)
        .filter(ChatbotMensaje.chatbot_id == sesion.id)
        .order_by(ChatbotMensaje.fecha)
        .all()
    )
    return [MensajeOut(id=m.id, remitente=m.remitente, mensaje=m.mensaje, fecha=m.fecha) for m in mensajes]


# ---------- Staff: Administrador (CU19) ----------


@router.get("", response_model=list[ChatbotUsuarioOut])
def listar_usuarios_chatbot(
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU19")),
) -> list[ChatbotUsuarioOut]:
    rows = db.execute(
        text(
            "SELECT c.cliente_id, u.nombre, u.email, COUNT(m.id), MAX(m.fecha) "
            "FROM chatbot c "
            "JOIN cliente cl ON cl.id = c.cliente_id "
            "JOIN usuario u ON u.id = cl.id "
            "JOIN chatbot_mensaje m ON m.chatbot_id = c.id "
            "GROUP BY c.cliente_id, u.nombre, u.email "
            "ORDER BY MAX(m.fecha) DESC"
        )
    ).all()
    return [
        ChatbotUsuarioOut(
            cliente_id=r[0], cliente_nombre=r[1], cliente_email=r[2], total_mensajes=int(r[3]), ultima_actividad=r[4]
        )
        for r in rows
    ]


@router.get("/cliente/{cliente_id}", response_model=list[MensajeOut])
def transcripcion_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _empleado: Usuario = Depends(require_permiso("CU19")),
) -> list[MensajeOut]:
    rows = db.execute(
        text(
            "SELECT m.id, m.remitente, m.mensaje, m.fecha "
            "FROM chatbot_mensaje m JOIN chatbot c ON c.id = m.chatbot_id "
            "WHERE c.cliente_id = :cid ORDER BY m.fecha"
        ),
        {"cid": cliente_id},
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este cliente no tiene conversaciones registradas.")

    return [MensajeOut(id=r[0], remitente=r[1], mensaje=r[2], fecha=r[3]) for r in rows]
