import json
import re

import requests

from app.core.config import settings

_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
)

_RAZON_GENERICA = {
    "compra_conjunta": "Los clientes que compraron algo parecido tambien eligieron esto.",
    "similar_categoria": "Va a juego con productos que ya elegiste.",
    "mas_vendido": "Uno de los productos mas vendidos de la tienda.",
    "vistos_juntos": "Otros clientes que vieron esto tambien miraron esto.",
    "catalogo_general": "Otra prenda de la tienda que te podria gustar.",
    "modelo_ml": "Se parece a lo que te gusta y la eligen clientes como vos.",
}


def _razon_de_respaldo(origen: str) -> str:
    return _RAZON_GENERICA.get(origen, "Seleccionado especialmente para vos.")


_SYSTEM_PROMPT_CHAT = (
    "Sos el asistente virtual de {tienda}, {descripcion}. "
    "Respondes en espanol, de forma breve (maximo 4-5 lineas), clara y amigable, ayudando con dudas sobre "
    "productos, stock, tallas, precios, sucursales, metodos de pago, reservas y compras{extra}. "
    "Usa SOLO la informacion que te paso en el contexto para hablar de precios o stock -- si no esta ahi, "
    "decilo con honestidad ('no tengo esa info ahora mismo') y sugeri contactar a la tienda por WhatsApp, "
    "en vez de inventar numeros. Si te preguntan algo que no tiene que ver con la tienda, responde con amabilidad "
    "en una linea y ofrece ayuda con la tienda. No uses markdown ni emojis, es para leerse en voz alta."
)

_RESPUESTA_SIN_IA = (
    "Disculpa, en este momento no puedo responder tu consulta. Intenta de nuevo en unos minutos o "
    "contactanos por WhatsApp."
)


def generar_respuesta_chat(
    historial: list[tuple[str, str]], contexto: str, mensaje: str, tienda: str = "la tienda", plataforma: bool = False
) -> str:
    """historial: [(remitente, mensaje), ...] en orden cronologico, remitente
    'cliente'|'bot' (sin incluir el mensaje nuevo). contexto: info real del
    catalogo/stock/sucursales relevante a la pregunta. plataforma: el chat
    universal de Arlani (todas las tiendas, planes para duenos de boutiques).
    Si no hay API key o la llamada falla, devuelve una disculpa generica -- el
    chat sigue funcionando, solo sin IA."""
    if not settings.GEMINI_API_KEY:
        return _RESPUESTA_SIN_IA

    contents = [
        {"role": "user" if remitente == "cliente" else "model", "parts": [{"text": texto}]}
        for remitente, texto in historial[-10:]
    ]
    contents.append({"role": "user", "parts": [{"text": mensaje}]})

    prompt = _SYSTEM_PROMPT_CHAT.format(
        tienda=tienda,
        descripcion="la plataforma de boutiques de Bolivia, con el catalogo de todas sus tiendas" if plataforma
        else "una tienda de ropa en Bolivia",
        extra=", y para duenos de boutiques: planes de suscripcion y como crear su tienda" if plataforma else "",
    )
    body = {
        "systemInstruction": {"parts": [{"text": f"{prompt}\n\nContexto para esta consulta:\n{contexto}"}]},
        "contents": contents,
    }

    try:
        res = requests.post(f"{_URL}?key={settings.GEMINI_API_KEY}", json=body, timeout=20)
        res.raise_for_status()
        cuerpo = json.loads(res.content.decode("utf-8"))
        return cuerpo["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return _RESPUESTA_SIN_IA


def _pedir_razones(prompt: str, candidatos: list[dict]) -> dict[int, str]:
    """Logica compartida por generar_razones y generar_razones_relacionados:
    le manda el prompt ya armado a Gemini y espera un array JSON de strings
    en el mismo orden que candidatos. Si no hay API key, la llamada falla o
    la respuesta no tiene la forma esperada, cae en una razon generica por
    origen -- el ranking en si nunca depende de esto."""
    if not settings.GEMINI_API_KEY or not candidatos:
        return {c["producto_id"]: _razon_de_respaldo(c["origen"]) for c in candidatos}

    try:
        res = requests.post(
            f"{_URL}?key={settings.GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=15,
        )
        res.raise_for_status()
        # requests adivina el charset de la respuesta (a veces mal, cae en
        # Latin-1) para decodificar .text/.json() -- se fuerza UTF-8 sobre
        # los bytes crudos para no romper tildes/enies.
        cuerpo = json.loads(res.content.decode("utf-8"))
        texto = cuerpo["candidates"][0]["content"]["parts"][0]["text"]
        texto_limpio = re.sub(r"^```(json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
        razones = json.loads(texto_limpio)
        if not isinstance(razones, list) or len(razones) != len(candidatos):
            raise ValueError("respuesta con forma inesperada")
        return {c["producto_id"]: str(r).strip() for c, r in zip(candidatos, razones)}
    except Exception:
        return {c["producto_id"]: _razon_de_respaldo(c["origen"]) for c in candidatos}


def generar_razones(
    cliente_nombre: str, historial: list[str], candidatos: list[dict]
) -> dict[int, str]:
    """candidatos: [{"producto_id": int, "nombre": str, "origen": str}, ...].
    Devuelve {producto_id: razon}, personalizada segun el HISTORIAL DE
    COMPRAS del cliente -- para el listado "Recomendado para ti" (dashboard
    del cliente)."""
    if not candidatos:
        return {}
    lista_candidatos = "\n".join(f'{i + 1}. "{c["nombre"]}" (motivo interno: {c["origen"]})' for i, c in enumerate(candidatos))
    historial_texto = ", ".join(historial) if historial else "todavia no tiene compras registradas"

    prompt = (
        "Sos el motor de recomendaciones de Atelier Aranier, una tienda de ropa. "
        f"El cliente se llama {cliente_nombre} y compro antes: {historial_texto}. "
        "Le vamos a mostrar estos productos recomendados:\n"
        f"{lista_candidatos}\n\n"
        "Para cada uno, escribi una razon breve y personalizada (maximo 12 palabras, en espanol, "
        "tono cercano y directo, sin comillas ni emojis) de por que se lo recomendamos. "
        'Responde SOLO con un array JSON de strings, en el mismo orden, ejemplo: ["razon 1", "razon 2"]. '
        "No agregues nada mas fuera del JSON."
    )
    return _pedir_razones(prompt, candidatos)


def generar_razones_relacionados(producto_base_nombre: str, candidatos: list[dict]) -> dict[int, str]:
    """candidatos: [{"producto_id": int, "nombre": str, "origen": str}, ...].
    Devuelve {producto_id: razon}, redactada en base a QUE PRODUCTO esta
    mirando el cliente ahora mismo (seccion "Tambien te puede interesar" en
    el detalle de producto) -- a diferencia de generar_razones, no depende
    de que el cliente tenga historial ni sesion iniciada."""
    if not candidatos:
        return {}
    lista_candidatos = "\n".join(f'{i + 1}. "{c["nombre"]}" (motivo interno: {c["origen"]})' for i, c in enumerate(candidatos))

    prompt = (
        "Sos el motor de recomendaciones de Atelier Aranier, una tienda de ropa. "
        f'Un cliente esta viendo el producto "{producto_base_nombre}". '
        "Le vamos a mostrar estos otros productos relacionados, justo debajo:\n"
        f"{lista_candidatos}\n\n"
        "Para cada uno, escribi una razon breve (maximo 10 palabras, en espanol, tono cercano, "
        "sin comillas ni emojis) de por que se lo mostramos junto al producto que esta viendo. "
        'Responde SOLO con un array JSON de strings, en el mismo orden, ejemplo: ["razon 1", "razon 2"]. '
        "No agregues nada mas fuera del JSON."
    )
    return _pedir_razones(prompt, candidatos)
