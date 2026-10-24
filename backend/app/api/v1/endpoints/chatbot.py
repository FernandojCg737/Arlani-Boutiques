from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permiso, require_permiso_cliente
from app.core.gemini import generar_respuesta_chat
from app.core.rate_limit import verificar_limite
from app.db.session import get_db
from app.ml.chatbot import Tienda, contexto_gemini, responder
from app.ml.entrenamiento import predecir
from app.ml.servicio import modelo_activo
from app.models import Chatbot, ChatbotMensaje, Cliente, Usuario
from app.schemas.chatbot import ChatbotUsuarioOut, MensajeIn, MensajeOut, MensajePublicoIn, RespuestaPublicaOut

router = APIRouter()

# CU19 "Atender Cliente con Chatbot": el cliente escribe (o dicta por voz,
# resuelto 100% en el navegador con la Web Speech API, sin backend de por
# medio) en el chat de la tienda que esta visitando. El modelo de esa tienda
# (CU18) reconoce que pregunta y la respuesta sale de sus datos reales
# (app/ml/chatbot.py); solo lo que no reconoce pasa a Gemini, con el contexto
# de esa misma tienda -- nunca inventa precios o stock.
# Una "sesion" (tabla Chatbot) agrupa mensajes seguidos con UNA tienda; si
# pasan mas de 3h sin actividad, el proximo mensaje abre una sesion nueva
# (asi el admin ve conversaciones separadas, no un chat infinito).

_UMBRAL_NUEVA_SESION = timedelta(hours=3)


def _get_cliente_o_403(db: Session, usuario: Usuario) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == usuario.id).first()
    if cliente is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo los clientes pueden usar el chatbot.")
    return cliente


def _tienda(db: Session, subdominio: str | None, universal: bool = False) -> Tienda:
    """La tienda del chat (por su subdominio); sin el, la tienda por defecto.
    universal: el chat del catalogo universal, con todas las tiendas."""
    if universal:
        return Tienda(None, "Arlani Boutiques")
    if subdominio:
        sql, p = "SELECT id, nombre, telefono FROM empresa WHERE subdominio = :s AND estado = 'activa'", {"s": subdominio}
    else:
        sql, p = "SELECT id, nombre, telefono FROM empresa WHERE id = fn_empresa_por_defecto()", {}
    fila = db.execute(text(sql), p).first()
    if fila is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tienda no encontrada.")
    return Tienda(fila.id, fila.nombre, fila.telefono)


def _ultima_sesion(db: Session, cliente_id: int, empresa_id: int | None) -> Chatbot | None:
    # empresa_id None: la conversacion del chat universal.
    de_la_tienda = Chatbot.empresa_id == empresa_id if empresa_id else Chatbot.empresa_id.is_(None)
    return (
        db.query(Chatbot)
        .filter(Chatbot.cliente_id == cliente_id, de_la_tienda)
        .order_by(Chatbot.fecha_inicio.desc())
        .first()
    )


def _get_or_create_sesion(db: Session, cliente_id: int, empresa_id: int | None) -> Chatbot:
    sesion = _ultima_sesion(db, cliente_id, empresa_id)
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

    nueva = Chatbot(cliente_id=cliente_id, canal="web", fecha_inicio=ahora, empresa_id=empresa_id)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


def _salida(m: ChatbotMensaje) -> MensajeOut:
    return MensajeOut(
        id=m.id, remitente=m.remitente, mensaje=m.mensaje, fecha=m.fecha, intencion=m.intencion,
        confianza=float(m.confianza) if m.confianza is not None else None,
    )


# ---------- Cliente ----------


@router.post("/mensajes", response_model=MensajeOut, status_code=status.HTTP_201_CREATED)
def enviar_mensaje(
    payload: MensajeIn,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_permiso_cliente("CU19")),
) -> MensajeOut:
    cliente = _get_cliente_o_403(db, usuario)
    # Un mensaje puede terminar en una llamada paga a Gemini: tope por
    # cliente para que un script no dispare la factura.
    verificar_limite("chatbot-min", str(cliente.id), maximo=15, segundos=60)
    verificar_limite("chatbot-dia", str(cliente.id), maximo=300, segundos=86_400)
    tienda = _tienda(db, payload.tienda, payload.universal)
    sesion = _get_or_create_sesion(db, cliente.id, tienda.id)

    pred = predecir(modelo_activo(db, "chatbot", tienda.id), payload.mensaje)
    db.add(ChatbotMensaje(chatbot_id=sesion.id, remitente="cliente", mensaje=payload.mensaje,
                          intencion=pred["intencion"], confianza=pred["confianza"]))
    db.commit()

    respuesta = responder(db, tienda, cliente.id, usuario.nombre, pred["intencion"], payload.mensaje)
    if respuesta is None:
        # Solo los ultimos mensajes (Gemini usa los 10 previos al actual).
        ultimos = (
            db.query(ChatbotMensaje)
            .filter(ChatbotMensaje.chatbot_id == sesion.id)
            .order_by(ChatbotMensaje.fecha.desc(), ChatbotMensaje.id.desc())
            .limit(11)
            .all()
        )
        historial = [(m.remitente, m.mensaje) for m in reversed(ultimos)][:-1]
        contexto = contexto_gemini(db, tienda, payload.mensaje)
        respuesta = generar_respuesta_chat(historial, contexto, payload.mensaje, tienda.nombre, tienda.universal)

    bot_msg = ChatbotMensaje(chatbot_id=sesion.id, remitente="bot", mensaje=respuesta)
    db.add(bot_msg)
    db.commit()
    db.refresh(bot_msg)
    return _salida(bot_msg)


@router.post("/publico", response_model=RespuestaPublicaOut)
def mensaje_publico(payload: MensajePublicoIn, request: Request, db: Session = Depends(get_db)) -> RespuestaPublicaOut:
    """El asistente universal para quien todavia no tiene sesion (la portada y
    el catalogo de Arlani): un dueno de boutique que mira los planes o un
    visitante que busca prendas. No se guarda la conversacion (el historial
    lo manda el navegador) y el tope es por IP."""
    ip = request.client.host if request.client else "desconocida"
    verificar_limite("chatbot-publico-min", ip, maximo=10, segundos=60)
    verificar_limite("chatbot-publico-dia", ip, maximo=150, segundos=86_400)
    tienda = _tienda(db, None, universal=True)
    pred = predecir(modelo_activo(db, "chatbot"), payload.mensaje)
    respuesta = responder(db, tienda, None, "", pred["intencion"], payload.mensaje)
    if respuesta is None:
        historial = [(m.remitente, m.mensaje) for m in payload.historial[-10:]]
        respuesta = generar_respuesta_chat(historial, contexto_gemini(db, tienda, payload.mensaje), payload.mensaje,
                                           tienda.nombre, plataforma=True)
    return RespuestaPublicaOut(mensaje=respuesta, intencion=pred["intencion"], confianza=pred["confianza"])


@router.get("/mias", response_model=list[MensajeOut])
def mis_mensajes(
    tienda: str | None = Query(default=None, max_length=60),
    universal: bool = Query(default=False),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[MensajeOut]:
    cliente = _get_cliente_o_403(db, usuario)
    sesion = _ultima_sesion(db, cliente.id, _tienda(db, tienda, universal).id)
    if sesion is None:
        return []

    mensajes = (
        db.query(ChatbotMensaje)
        .filter(ChatbotMensaje.chatbot_id == sesion.id)
        .order_by(ChatbotMensaje.fecha)
        .all()
    )
    return [_salida(m) for m in mensajes]


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
            "SELECT m.id, m.remitente, m.mensaje, m.fecha, m.intencion, m.confianza "
            "FROM chatbot_mensaje m JOIN chatbot c ON c.id = m.chatbot_id "
            "WHERE c.cliente_id = :cid ORDER BY m.fecha"
        ),
        {"cid": cliente_id},
    ).all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este cliente no tiene conversaciones registradas.")

    return [
        MensajeOut(id=r[0], remitente=r[1], mensaje=r[2], fecha=r[3], intencion=r[4],
                   confianza=float(r[5]) if r[5] is not None else None)
        for r in rows
    ]
