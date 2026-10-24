"""CU19 con el modelo del CU18: el chatbot de cada tienda y el universal.

El clasificador reconoce que pregunta el cliente (horario, stock, precio,
estado de su pedido...) y la respuesta se arma con datos reales: los de ESA
tienda (su chat, con su modelo) o los de todas las tiendas de la plataforma
(el chat del catalogo universal, con el modelo general). Lo que el modelo no
reconoce (o una charla fuera de tema) pasa a Gemini con el mismo contexto.
"""

import re
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.ml.texto import normalizar, preprocesar

# Intenciones que se responden con datos (sin Gemini).
CON_DATOS = {"saludo", "despedida", "gracias", "horario", "ubicacion", "envios", "devoluciones", "metodos_pago",
             "stock", "precio", "recomendacion", "reservas", "estado_pedido", "tiendas",
             "planes", "suscribirse", "plataforma"}

# Soporte de la plataforma (el mismo WhatsApp de la portada).
WHATSAPP_SOPORTE = "+591 73766956"
# Pagando el año se cobran 10 meses (como en la portada y en /empezar).
MESES_COBRADOS_AL_ANIO = 10

ESTADO_VENTA = {"pagada": "pagado", "pendiente": "pendiente de pago", "devuelto": "devuelto", "anulada": "anulado"}
ESTADO_ENVIO = {"pendiente": "lo estamos preparando", "enviado": "en camino", "entregado": "entregado"}

PALABRAS_NUMERO = {"cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
                   "quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
                   "mil": 1000, "cincuenta": 50, "setenta": 70, "ochenta": 80, "noventa": 90,
                   "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}

# Tiendas que se muestran en la plataforma (activas y con la suscripcion al dia).
_TIENDAS_VISIBLES = "SELECT id FROM empresa WHERE estado = 'activa' AND fn_empresa_operativa(id)"


@dataclass
class Tienda:
    """id None: el chat universal (todas las tiendas)."""

    id: int | None
    nombre: str
    telefono: str | None = None

    @property
    def universal(self) -> bool:
        return self.id is None


def _bs(v) -> str:
    return f"Bs {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _lista(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _de(tienda: Tienda, alias: str) -> str:
    """Filtro SQL de las filas de la tienda (o de todas las visibles)."""
    return f"{alias}.empresa_id = :e" if tienda.id else f"{alias}.empresa_id IN ({_TIENDAS_VISIBLES})"


def _texto_con_numeros(mensaje: str) -> str:
    """Normalizado pero con los numeros (digitos o en palabras) como digitos."""
    t = normalizar(mensaje)
    digitos = iter(re.findall(r"\d+", mensaje.replace(".", "").replace(",", "")))
    t = re.sub(r"\bnum\b", lambda _: next(digitos, "0"), t)
    return re.sub(r"\b(" + "|".join(PALABRAS_NUMERO) + r")\b", lambda m: str(PALABRAS_NUMERO[m.group(1)]), t)


def rango_precio(mensaje: str) -> tuple[float | None, float | None, str] | None:
    """(minimo, maximo, orden) si la frase busca por precio: "menos de 200 bs",
    "entre 100 y 300", "lo mas barato"... None si no."""
    t = _texto_con_numeros(mensaje)
    bs = r"(?:bs |bolivianos |pesos )?"
    m = re.search(rf"entre {bs}(\d+)(?: bs| bolivianos)? y {bs}(\d+)", t)
    if m:
        a, b = sorted((float(m.group(1)), float(m.group(2))))
        return a, b, "asc"
    m = re.search(rf"\b(menos|menor|menores|debajo|bajo|hasta|maximo|max|inferior|no mas)\b(?: \w+){{0,2}} {bs}(\d+)", t)
    if m:
        return None, float(m.group(2)), "asc"
    m = re.search(rf"\b(mas|mayor|mayores|encima|arriba|minimo|desde|superior)\b(?: \w+){{0,2}} {bs}(\d+)", t)
    if m:
        return float(m.group(2)), None, "asc"
    # "tengo 250 bs", "mi presupuesto es de 300": hasta ese monto.
    m = re.search(rf"\b(tengo|presupuesto|cuento con|gastar)\b(?: \w+){{0,2}} {bs}(\d+)", t)
    if m:
        return None, float(m.group(2)), "asc"
    if re.search(r"\b(barat[oa]s?|economic[oa]s?|accesibles?|mas bajo|menor precio)\b", t):
        return None, None, "asc"
    if re.search(r"\b(car[oa]s?|mas exclusiv[oa]s?|mayor precio|premium)\b", t):
        return None, None, "desc"
    return None


PUBLICOS = {"mujer": "mujer", "hombre": "hombre", "unisex": "unisex", "nina": "niña", "nino": "niño", "bebe": "bebé"}
# Del mas especifico al mas general (normalizado: sin tildes ni enies).
_PALABRAS_PUBLICO = [
    (r"\b(bebe|bebes|recien nacid[oa]s?)\b", ("bebe",)),
    (r"\b(nina|ninas|hija|hijas)\b", ("nina",)),
    (r"\b(nino|ninos|infantil|infantiles|hijo|hijos|escolar|escolares)\b", ("nino", "nina")),
    (r"\b(mujer|mujeres|dama|damas|femenin[oa]s?|chica|chicas|senora|senoras)\b", ("mujer", "unisex")),
    (r"\b(hombre|hombres|caballero|caballeros|varon|varones|masculin[oa]s?|chico|chicos)\b", ("hombre", "unisex")),
]


def publico_mencionado(mensaje: str) -> tuple[str, ...] | None:
    """Para quien busca el cliente ("vestidos para mujer", "ropa de nino")."""
    t = normalizar(mensaje)
    for patron, publicos in _PALABRAS_PUBLICO:
        if re.search(patron, t):
            return publicos
    return None


def _sucursales(db: Session, tienda: Tienda, mensaje: str) -> list:
    filas = db.execute(
        text(f"""SELECT s.nombre, s.direccion, s.horario_atencion, s.telefono, c.nombre AS ciudad, e.nombre AS tienda
                 FROM sucursal s LEFT JOIN ciudad c ON c.id = s.ciudad_id JOIN empresa e ON e.id = s.empresa_id
                 WHERE {_de(tienda, 's')} AND s.estado = 'activa' ORDER BY e.nombre, s.nombre"""),
        {"e": tienda.id},
    ).all()
    # Si nombra una sucursal ("la de Equipetrol") o una tienda, solo esas.
    t = normalizar(mensaje)
    nombradas = [f for f in filas if re.search(rf"\b{re.escape(normalizar(f.nombre).replace('sucursal ', ''))}\b", t)]
    if not nombradas and tienda.universal:
        nombradas = [f for f in filas if normalizar(f.tienda) in t]
    return nombradas or filas


def _productos(db: Session, tienda: Tienda) -> list:
    return db.execute(
        text(f"""SELECT p.id, p.nombre, p.precio, p.precio_original, c.nombre AS categoria, m.nombre AS marca, e.nombre AS tienda,
                        p.publico
                 FROM producto p JOIN categoria c ON c.id = p.categoria_id LEFT JOIN marca m ON m.id = p.marca_id
                 JOIN empresa e ON e.id = p.empresa_id
                 WHERE {_de(tienda, 'p')} AND p.estado = 'activo'"""),
        {"e": tienda.id},
    ).all()


def _raiz(palabra: str) -> str:
    """Sin el plural, para comparar "hoodies" con "Hoodie" o "jeans" con "Jean"."""
    # Sin la "s" y luego sin la "e" final: "pantalones" y "pantalon" quedan
    # en "pantalon"; "hoodies" y "hoodie", en "hoodi".
    if palabra.endswith("s") and len(palabra) > 4:
        palabra = palabra[:-1]
    return palabra[:-1] if palabra.endswith("e") and len(palabra) > 4 else palabra


def _raices(texto: str) -> set[str]:
    return {_raiz(p) for p in preprocesar(texto).split()}


def _palabras(mensaje: str) -> set[str]:
    return {_raiz(p) for p in preprocesar(mensaje).split()
            if len(p) >= 4 and p not in ("num", "precio", "producto", "prenda", "tienda", "vender", "tener", "haber")}


def _para_quien(db: Session, tienda: Tienda, mensaje: str) -> list:
    """Las prendas de la tienda, solo las del publico que se nombra (si se nombra)."""
    publicos = publico_mencionado(mensaje)
    return [p for p in _productos(db, tienda) if not publicos or p.publico in publicos]


def productos_mencionados(db: Session, tienda: Tienda, mensaje: str, limite: int = 4) -> list:
    """Productos que el cliente nombra (por nombre, categoria o marca)."""
    palabras = _palabras(mensaje)
    if not palabras:
        return []
    puntaje = []
    for f in _para_quien(db, tienda, mensaje):
        nombre = _raices(f.nombre)
        resto = _raices(f"{f.categoria} {f.marca or ''}")
        valor = 2 * len(palabras & nombre) + len(palabras & resto)
        if valor:
            puntaje.append((valor, f))
    puntaje.sort(key=lambda x: -x[0])
    mejor = puntaje[0][0] if puntaje else 0
    return [f for v, f in puntaje if v == mejor][:limite]


def _categorias_mencionadas(db: Session, tienda: Tienda, mensaje: str) -> set[str]:
    palabras = _palabras(mensaje)
    return {f.categoria for f in _productos(db, tienda) if palabras & _raices(f.categoria)}


def _stock(db: Session, ids: list[int]) -> dict[int, list[tuple[str, int]]]:
    if not ids:
        return {}
    filas = db.execute(
        text("""SELECT i.producto_id, s.nombre, sum(i.cantidad) FROM inventario i JOIN sucursal s ON s.id = i.sucursal_id
                WHERE i.producto_id IN :ids AND s.estado = 'activa' GROUP BY 1, 2 HAVING sum(i.cantidad) > 0 ORDER BY 3 DESC"""
             ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    ).all()
    salida: dict[int, list[tuple[str, int]]] = {}
    for pid, sucursal, cantidad in filas:
        salida.setdefault(pid, []).append((sucursal, int(cantidad)))
    return salida


def _categorias(db: Session, tienda: Tienda) -> list[str]:
    return [f[0].lower() for f in db.execute(
        text(f"""SELECT c.nombre FROM categoria c JOIN producto p ON p.categoria_id = c.id
                 WHERE {_de(tienda, 'p')} AND p.estado = 'activo' GROUP BY c.nombre ORDER BY count(*) DESC"""),
        {"e": tienda.id},
    )]


def _mas_vendidos(db: Session, tienda: Tienda, limite: int = 3) -> list:
    return db.execute(
        text(f"""SELECT p.nombre, p.precio, e.nombre AS tienda, sum(il.cantidad) AS unidades
                 FROM item_linea il
                 JOIN (SELECT id, venta_presencial_id AS venta_id FROM detalle_venta_presencial
                       UNION ALL SELECT id, venta_digital_id FROM detalle_venta_digital) d ON d.id = il.id
                 JOIN venta v ON v.id = d.venta_id JOIN producto p ON p.id = il.producto_id JOIN empresa e ON e.id = p.empresa_id
                 WHERE {_de(tienda, 'p')} AND p.estado = 'activo' AND v.estado = 'pagada' AND v.fecha >= now() - interval '60 days'
                 GROUP BY p.id, p.nombre, p.precio, e.nombre ORDER BY unidades DESC LIMIT :n"""),
        {"e": tienda.id, "n": limite},
    ).all()


def _nombre(p, tienda: Tienda) -> str:
    """En el chat universal cada prenda dice de que tienda es."""
    return f"{p.nombre} de {p.tienda}" if tienda.universal else p.nombre


def _por_precio(db: Session, tienda: Tienda, mensaje: str, rango: tuple[float | None, float | None, str]) -> str:
    minimo, maximo, orden = rango
    categorias = _categorias_mencionadas(db, tienda, mensaje)
    filas = [p for p in _para_quien(db, tienda, mensaje)
             if (minimo is None or float(p.precio) >= minimo) and (maximo is None or float(p.precio) <= maximo)
             and (not categorias or p.categoria in categorias)]
    filas.sort(key=lambda p: float(p.precio), reverse=orden == "desc")
    cual = (f" entre {_bs(minimo)} y {_bs(maximo)}" if minimo is not None and maximo is not None
            else f" de hasta {_bs(maximo)}" if maximo is not None else f" desde {_bs(minimo)}" if minimo is not None else "")
    que = _lista(sorted(c.lower() for c in categorias)) if categorias else "prendas"
    publicos = publico_mencionado(mensaje)
    if publicos:
        que += " para " + PUBLICOS[publicos[0]]
    if not filas:
        return f"No encontré {que}{cual}. " + ("Prueba con otro monto." if cual else "")
    if not cual:
        cual = " más económicas" if orden == "asc" else " de mayor precio"
    lineas = [f"{_nombre(p, tienda)} a {_bs(p.precio)}" for p in filas[:6]]
    extra = f" (y {len(filas) - 6} más en el catálogo)" if len(filas) > 6 else ""
    return f"Estas son {que}{cual}: " + "; ".join(lineas) + extra + "."


def _tiendas(db: Session, tienda: Tienda, mensaje: str) -> str:
    filas = db.execute(
        text(f"""SELECT e.nombre, e.ciudad, count(DISTINCT p.id) AS productos, string_agg(DISTINCT lower(c.nombre), ', ') AS categorias
                 FROM empresa e JOIN producto p ON p.empresa_id = e.id AND p.estado = 'activo' JOIN categoria c ON c.id = p.categoria_id
                 WHERE e.id IN ({_TIENDAS_VISIBLES}) GROUP BY e.id, e.nombre, e.ciudad ORDER BY e.nombre""")
    ).all()
    if not filas:
        return "Por ahora no hay tiendas con catálogo publicado."
    # "¿Qué tienda vende chaquetas?": solo las que tienen esa prenda.
    buscadas = productos_mencionados(db, Tienda(None, "Arlani Boutiques"), mensaje, 20)
    if buscadas:
        tiendas = sorted({p.tienda for p in buscadas})
        return f"Lo encuentras en {_lista(tiendas)}: " + "; ".join(f"{p.nombre} ({p.tienda}) a {_bs(p.precio)}" for p in buscadas[:5]) + "."
    actual = f"Estás en {tienda.nombre}. " if not tienda.universal else ""
    lineas = [f"{f.nombre}" + (f" ({f.ciudad})" if f.ciudad else "") + f", con {f.productos} prendas: {f.categorias}" for f in filas]
    return actual + f"En Arlani Boutiques hay {len(filas)} tiendas: " + "; ".join(lineas) + "."


def _planes_activos(db: Session) -> list:
    return db.execute(
        text("""SELECT codigo, nombre, precio_mensual, max_sucursales, dias_prueba, ia_generativa, operacion_offline, comision_pct
                FROM plan_suscripcion WHERE activo ORDER BY orden""")
    ).all()


def _plan_texto(p) -> str:
    sucursales = f"hasta {p.max_sucursales} {'sucursal' if p.max_sucursales == 1 else 'sucursales'}"
    if p.dias_prueba:
        precio = f"gratis por {p.dias_prueba} días"
    else:
        precio = f"{_bs(p.precio_mensual)} al mes, o {_bs(p.precio_mensual * MESES_COBRADOS_AL_ANIO)} al año (2 meses gratis)"
    incluye = [sucursales, "tienda en línea con tu marca, productos, ventas, reservas y reportes"]
    if p.operacion_offline:
        incluye.append("venta sin internet")
    if p.ia_generativa:
        incluye.append("reportes con IA por voz o texto")
    return f"{p.nombre}: {precio}. Incluye {_lista(incluye)}; comisión de {float(p.comision_pct):g}% por venta en línea"


def _planes(db: Session, mensaje: str) -> str:
    planes = _planes_activos(db)
    if not planes:
        return f"Ahora mismo no hay planes publicados. Escríbenos al WhatsApp {WHATSAPP_SOPORTE}."
    t = _texto_con_numeros(mensaje)
    # "Tengo 3 sucursales, ¿qué plan me conviene?": el pago más chico que alcanza.
    m = re.search(r"(\d+) sucursal", t)
    if m:
        n = int(m.group(1))
        pagos = [p for p in planes if not p.dias_prueba]
        plan = next((p for p in pagos if n <= p.max_sucursales), None)
        if plan is None:
            return (f"Con {n} sucursales escríbenos al WhatsApp {WHATSAPP_SOPORTE}: el plan más grande llega a "
                    f"{max(p.max_sucursales for p in planes)}.")
        return f"Para {n} sucursales te conviene el plan {_plan_texto(plan)}."
    pagos = [p for p in planes if not p.dias_prueba]
    if re.search(r"anual|al ano|por ano|descuento|ahorr", t):
        return ("Sí: pagando el año se cobran 10 meses, o sea 2 meses gratis. " + "; ".join(
            f"{p.nombre}: {_bs(p.precio_mensual * MESES_COBRADOS_AL_ANIO)} al año en vez de {_bs(p.precio_mensual * 12)}"
            for p in pagos) + ". Lo eliges en el primer paso de «Crear mi boutique».")
    if re.search(r"comision|porcentaje|cobran por venta", t):
        return ("Por cada venta en línea Arlani cobra una comisión según el plan: " + "; ".join(
            f"{p.nombre} {float(p.comision_pct):g}%" for p in planes) + ". En el Profesional la comisión es la más baja.")
    elegidos = [p for p in planes if p.codigo in t or normalizar(p.nombre) in t or (p.dias_prueba and "gratis" in t)]
    if elegidos:
        return ". ".join(_plan_texto(p) for p in elegidos) + ". Lo contratas en «Crear mi boutique»."
    return ("Estos son los planes de Arlani Boutiques: " + ". ".join(_plan_texto(p) for p in planes) +
            ". Puedes empezar con la prueba y cambiar de plan cuando quieras desde tu panel.")


def _suscribirse(db: Session, mensaje: str = "") -> str:
    if re.search(r"\b(pago|pagar|pagas|paypal|tarjeta|renuev|renovar)", normalizar(mensaje)):
        return ("La suscripción se paga con PayPal (con tu cuenta o con tarjeta) en el último paso de «Crear mi boutique», "
                "mensual o anual; la prueba gratis no se paga. Después la renuevas o cambias de plan desde «Mi suscripción» "
                "en el panel de tu boutique.")
    prueba = next((p for p in _planes_activos(db) if p.dias_prueba), None)
    gratis = f"Prueba gratis por {prueba.dias_prueba} días, " if prueba else ""
    return ("Así creas tu boutique en Arlani: 1) Crea tu cuenta (o inicia sesión) y toca «Crear mi boutique». "
            f"2) Elige tu plan: {gratis}Básico o Profesional, mensual o anual (con 2 meses gratis). "
            "3) Cuéntanos de tu boutique: nombre, enlace de tu tienda, ciudad, sucursales, color y logo, y el nombre y "
            "correo del administrador. 4) Confirma y paga con PayPal; la prueba se activa sin pagar. "
            "5) Te llega al correo la contraseña del administrador: entras a tu panel, cargas tus productos y tu tienda "
            f"ya queda en línea. Si te trabas en algún paso, escríbenos al WhatsApp {WHATSAPP_SOPORTE}.")


def _plataforma(db: Session, mensaje: str) -> str:
    if re.search(r"soporte|whatsapp|contact|ayuda|telefono|llamar", normalizar(mensaje)):
        return f"Para soporte o dudas sobre los planes, escríbenos al WhatsApp {WHATSAPP_SOPORTE}; también puedes preguntarme aquí."
    if re.search(r"internet|offline|sin conexion|se cae", normalizar(mensaje)):
        sin = [p.nombre for p in _planes_activos(db) if p.operacion_offline]
        return ("Sí: la caja guarda cada venta y reserva sin conexión y las sincroniza sola apenas vuelve internet; si algo "
                "choca (por ejemplo, una prenda vendida dos veces) te avisa para resolverlo." +
                (f" Viene en {_lista(sin)}." if sin else ""))
    tiendas = db.execute(text(f"SELECT count(*) FROM empresa WHERE id IN ({_TIENDAS_VISIBLES})")).scalar() or 0
    return ("Arlani Boutiques es la plataforma para boutiques de Bolivia: tu tienda en línea con tu marca (catálogo, "
            "carrito, reservas y probador virtual), todas tus sucursales en un solo panel (inventario, ventas, reservas y "
            "empleados), venta en mostrador aunque se caiga internet (se sincroniza sola) y reportes; con el plan "
            "Profesional, además, reportes con IA por voz o texto. Tus clientes tienen un asistente como yo en tu tienda. "
            f"Hoy hay {tiendas} {'tienda' if tiendas == 1 else 'tiendas'} vendiendo aquí. ¿Te cuento los planes o cómo empezar?")


def contexto_plataforma(db: Session) -> str:
    """Para Gemini en el chat universal: planes, como empezar y soporte."""
    return ("Planes:\n" + "\n".join(f"- {_plan_texto(p)}" for p in _planes_activos(db)) +
            f"\n\nComo crear una boutique: {_suscribirse(db)}\n\nSoporte: WhatsApp {WHATSAPP_SOPORTE}.")


def responder(db: Session, tienda: Tienda, cliente_id: int | None, cliente_nombre: str, intencion: str, mensaje: str) -> str | None:
    """Respuesta con los datos (de la tienda o de todas), o None si la decide Gemini.
    cliente_id None: un visitante sin sesion (chat de la portada)."""
    if intencion == "planes":
        return _planes(db, mensaje)
    if intencion == "suscribirse":
        return _suscribirse(db, mensaje)
    if intencion == "plataforma":
        return _plataforma(db, mensaje)
    rango = rango_precio(mensaje)
    # Una busqueda por precio ("menos de 200 bs") se responde con el catalogo
    # aunque el modelo la haya tomado como otra cosa.
    if rango and intencion in ("precio", "stock", "recomendacion", "otro", "no_entendido", "tiendas"):
        return _por_precio(db, tienda, mensaje, rango)
    if intencion not in CON_DATOS:
        return None
    nombre = (cliente_nombre or "").split(" ")[0]
    hola = f"¡Hola{', ' + nombre if nombre else ''}! "

    if intencion == "saludo":
        if tienda.universal:
            tiendas = [f[0] for f in db.execute(text(f"SELECT nombre FROM empresa WHERE id IN ({_TIENDAS_VISIBLES}) ORDER BY nombre"))]
            cuales = f" ({_lista(tiendas)})" if tiendas else ""
            return (hola + f"Soy el asistente de Arlani Boutiques. Te ayudo a encontrar prendas, precios y stock en todas nuestras "
                    f"tiendas{cuales}, además de sucursales, formas de pago y tus pedidos. Y si tienes una boutique, "
                    "te cuento los planes y cómo crear la tuya. ¿Qué buscas?")
        return (hola + f"Soy el asistente de {tienda.nombre}. Puedo ayudarte con precios y stock, "
                "sucursales y horarios, formas de pago, reservas y el estado de tu pedido. ¿Qué necesitas?")
    if intencion == "despedida":
        return f"¡Gracias por escribir a {tienda.nombre}! Que tengas un lindo día."
    if intencion == "gracias":
        return "¡De nada! Si necesitas algo más, aquí estoy."
    if intencion == "tiendas":
        return _tiendas(db, tienda, mensaje)

    if intencion in ("horario", "ubicacion"):
        sucursales = _sucursales(db, tienda, mensaje)
        if not sucursales:
            return f"{tienda.nombre} todavía no tiene sucursales abiertas al público; puedes comprar en la tienda en línea."
        de = (lambda s: f" ({s.tienda})") if tienda.universal else (lambda s: "")
        if intencion == "horario":
            lineas = [f"{s.nombre}{de(s)}: {s.horario_atencion or 'consultar horario'}" for s in sucursales]
            return "Horarios de atención: " + "; ".join(lineas) + "."
        lineas = [f"{s.nombre}{de(s)}, {s.direccion}" + (f" ({s.ciudad})" if s.ciudad else "") for s in sucursales]
        inicio = "Estamos en " if len(sucursales) == 1 else f"Hay {len(sucursales)} sucursales: "
        return inicio + "; ".join(lineas) + "."

    if intencion == "metodos_pago":
        filas = db.execute(
            text(f"""SELECT e.nombre AS tienda, string_agg(m.nombre, ', ' ORDER BY m.orden) AS metodos
                     FROM metodo_pago_empresa m JOIN empresa e ON e.id = m.empresa_id
                     WHERE {_de(tienda, 'm')} AND m.activo GROUP BY e.nombre ORDER BY e.nombre"""),
            {"e": tienda.id},
        ).all()
        if tienda.universal:
            en_linea = ("Pagos en línea según la tienda: " + "; ".join(f"{f.tienda}: {f.metodos}" for f in filas) + ". ") if filas else ""
        else:
            metodos = filas[0].metodos.split(", ") if filas else []
            en_linea = f"En la tienda en línea puedes pagar con {_lista(metodos)}. " if metodos else ""
        return en_linea + "En las sucursales también se acepta efectivo."

    if intencion == "envios":
        ciudades = sorted({s.ciudad for s in _sucursales(db, tienda, "") if s.ciudad})
        donde = f" (despachamos desde {_lista(ciudades)})" if ciudades else ""
        return ("Sí, hay envíos a domicilio: al comprar en línea eliges «envío» y cargas tu dirección" + donde +
                ". Puedes seguir tu pedido desde Mis compras, o preguntarme por su estado aquí.")

    if intencion == "devoluciones":
        donde = "la sucursal de la tienda donde compraste" if tienda.universal else f"cualquier sucursal de {tienda.nombre}"
        return (f"Puedes pedir un cambio de talla o una devolución en {donde}, con la prenda "
                "sin uso y tu comprobante de compra. El personal la revisa y te hace el cambio o el reembolso.")

    if intencion == "reservas":
        return ("Puedes reservar desde la ficha de la prenda con el botón Reservar: eliges la sucursal y el día en que pasas a "
                "retirarla, y pagas en la tienda. Si no pasas en ese horario, la reserva vence y la prenda vuelve a la venta.")

    if intencion == "estado_pedido":
        if cliente_id is None:
            return "Para ver tus pedidos inicia sesión con tu cuenta de cliente y pregúntame de nuevo (o entra a Mis compras)."
        v = db.execute(
            text(f"""SELECT v.id, v.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz' AS fecha, v.total, v.estado,
                            e.estado AS envio, em.nombre AS tienda
                     FROM venta v JOIN sucursal s ON s.id = v.sucursal_id JOIN empresa em ON em.id = s.empresa_id
                     LEFT JOIN venta_envio e ON e.venta_id = v.id
                     WHERE v.cliente_id = :c AND {_de(tienda, 's')} AND v.tipo = 'venta_digital'
                     ORDER BY v.fecha DESC LIMIT 1"""),
            {"c": cliente_id, "e": tienda.id},
        ).first()
        if v is None:
            return f"No encuentro compras en línea tuyas en {tienda.nombre}. Si compraste en una sucursal, el comprobante te lo dieron ahí."
        de = f" en {v.tienda}" if tienda.universal else ""
        texto = f"Tu último pedido{de} (n.º {v.id}, del {v.fecha:%d/%m/%Y}, por {_bs(v.total)}) está {ESTADO_VENTA.get(v.estado, v.estado)}"
        if v.envio:
            texto += f", y el envío: {ESTADO_ENVIO.get(v.envio, v.envio)}"
        return texto + ". Puedes ver el detalle en Mis compras."

    productos = productos_mencionados(db, tienda, mensaje)
    if intencion == "recomendacion":
        publicos = publico_mencionado(mensaje)
        if not productos and publicos:
            productos = sorted(_para_quien(db, tienda, mensaje), key=lambda p: -float(p.precio_original or p.precio))[:3]
            if not productos:
                return f"Por ahora no hay prendas para {PUBLICOS[publicos[0]]} en {tienda.nombre}."
        elegidos = productos[:3] or _mas_vendidos(db, tienda)
        if not elegidos:
            return None
        lineas = [f"{_nombre(p, tienda)} ({_bs(p.precio)})" for p in elegidos]
        return f"Te recomiendo {_lista(lineas)}: {'van con lo que buscas' if productos else 'son de lo más elegido estos días'}. ¿Quieres saber si hay tu talla?"

    # stock / precio
    if not productos:
        if intencion == "precio" and re.search(r"oferta|descuento|rebaja|promo|liquidacion", normalizar(mensaje)):
            ofertas = [p for p in _productos(db, tienda) if p.precio_original and p.precio_original > p.precio]
            ofertas.sort(key=lambda p: float((p.precio_original - p.precio) / p.precio_original), reverse=True)
            if ofertas:
                return "Ahora en oferta: " + "; ".join(f"{_nombre(o, tienda)} a {_bs(o.precio)} (antes {_bs(o.precio_original)})" for o in ofertas[:4]) + "."
            return "En este momento no hay prendas en oferta."
        categorias = _categorias(db, tienda)
        return (f"No encontré esa prenda en {tienda.nombre}." + (f" Hay {_lista(categorias[:6])}." if categorias else "") +
                " Dime el nombre de la prenda (o hasta cuánto quieres gastar) y te digo " +
                ("el precio." if intencion == "precio" else "si hay stock."))
    stock = _stock(db, [p.id for p in productos])
    lineas = []
    for p in productos:
        precio = _bs(p.precio) + (f" (antes {_bs(p.precio_original)})" if p.precio_original and p.precio_original > p.precio else "")
        disponibles = stock.get(p.id, [])
        if intencion == "precio":
            lineas.append(f"{_nombre(p, tienda)} cuesta {precio}")
        elif disponibles:
            lineas.append(f"{_nombre(p, tienda)}: " + ", ".join(f"{n} {'unidad' if n == 1 else 'unidades'} en {s}" for s, n in disponibles[:3]))
        else:
            lineas.append(f"{_nombre(p, tienda)}: agotado por ahora")
    return "; ".join(lineas) + ". Las tallas y colores los ves en la ficha de cada prenda."


def contexto_gemini(db: Session, tienda: Tienda, mensaje: str) -> str:
    """Lo que Gemini puede usar cuando el modelo no reconocio la pregunta: las
    sucursales y el catalogo con sus precios (asi nunca dice "no tengo esa info")."""
    bloques = [f"Tienda: {tienda.nombre}." if not tienda.universal else
               "Plataforma Arlani Boutiques: el cliente esta en el catalogo universal, con las prendas de todas las tiendas."]
    sucursales = _sucursales(db, tienda, "")
    if sucursales:
        bloques.append("Sucursales:\n" + "\n".join(
            f"- {s.nombre}" + (f" ({s.tienda})" if tienda.universal else "") + f": {s.direccion}"
            + (f" (horario: {s.horario_atencion})" if s.horario_atencion else "") for s in sucursales))
    productos = productos_mencionados(db, tienda, mensaje, 6)
    if productos:
        stock = _stock(db, [p.id for p in productos])
        bloques.append("Productos relevantes:\n" + "\n".join(
            f"- {_nombre(p, tienda)} ({p.categoria}) -- {_bs(p.precio)} -- Stock: "
            + ("; ".join(f"{s}: {n}" for s, n in stock.get(p.id, [])) or "agotado")
            for p in productos))
    if tienda.universal:
        bloques.append(contexto_plataforma(db))
    catalogo = sorted(_productos(db, tienda), key=lambda p: float(p.precio))[:40]
    if catalogo:
        bloques.append("Catalogo (nombre, categoria, precio):\n" + "\n".join(
            f"- {_nombre(p, tienda)} ({p.categoria.lower()}) -- {_bs(p.precio)}" for p in catalogo))
    return "\n\n".join(bloques)
