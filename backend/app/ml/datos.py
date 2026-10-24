"""Datos sinteticos de entrenamiento (CU18).

Frases de ejemplo generadas con plantillas y variantes (como habla la gente,
con voseo y sin tildes, como llega un dictado por voz), etiquetadas con su
intencion. Se generan siempre igual (semilla fija): el entrenamiento es
reproducible.
"""

import random
import unicodedata

VER = ["mostrame", "muestrame", "quiero ver", "dame", "genera", "generame", "necesito", "sacame", "ensename", "ver",
       "podrias mostrarme", "me das", "quiero", "", "", ""]
PERIODO = ["de septiembre", "de octubre", "de agosto", "de este mes", "del mes pasado", "de la ultima semana", "de hoy",
           "de ayer", "de los ultimos tres meses", "entre agosto y octubre", "del 1 al 15 de octubre", "de esta semana",
           "del año", "de los ultimos 30 dias", "", "", ""]
GRANO = ["semana", "dia", "mes"]
TOP = ["5", "10", "3", "diez", "cinco", "20"]
SUCURSAL = ["equipetrol", "las palmas", "norte", "plan 3000", "la sucursal centro"]

PLANTILLAS_REPORTES: dict[str, list[str]] = {
    "ventas_periodo": [
        "{ver} las ventas {periodo}", "cuanto vendimos {periodo}", "{ver} un grafico de ventas por {grano}",
        "ventas totales {periodo}", "total vendido {periodo}", "como fueron las ventas {periodo}",
        "evolucion de las ventas por {grano}", "ingresos {periodo}", "reporte de ventas {periodo}",
        "{ver} cuanto se facturo {periodo}", "ventas por {grano} {periodo}", "cuanto ingreso {periodo}",
        "tendencia de ventas {periodo}", "{ver} las ventas diarias {periodo}", "monto vendido {periodo}",
    ],
    "ventas_sucursal": [
        "{ver} las ventas {periodo} agrupadas por sucursal", "compara las ventas de las sucursales {periodo}",
        "que sucursal vendio mas {periodo}", "ventas por sucursal {periodo}", "ranking de sucursales por ventas",
        "cuanto vendio cada sucursal {periodo}", "comparativa entre sucursales {periodo}",
        "ventas de la sucursal {sucursal} {periodo}", "{ver} como le fue a cada sucursal {periodo}",
        "cual es la sucursal con mas ventas", "sucursal {sucursal} contra las demas {periodo}",
    ],
    "top_productos": [
        "cuales fueron los {top} productos mas vendidos {periodo}", "productos mas vendidos {periodo}",
        "top {top} de prendas {periodo}", "que prendas se venden mas", "ranking de productos por unidades {periodo}",
        "los productos estrella {periodo}", "que se vendio mas {periodo}", "{ver} los {top} articulos mas vendidos",
        "cuales son las prendas mas populares", "mejores productos {periodo}", "que productos venden menos {periodo}",
    ],
    "categorias": [
        "que categorias generaron mayores ingresos {periodo}", "ventas por categoria {periodo}",
        "ingresos por categoria {periodo}", "que tipo de prenda vende mas", "compara las categorias {periodo}",
        "cuanto aporto cada categoria {periodo}", "{ver} las categorias mas vendidas", "pantalones contra camisas {periodo}",
        "que linea de ropa se vende mas", "ventas de chaquetas y poleras {periodo}",
    ],
    "stock": [
        "{ver} los productos con menor existencia", "que productos tienen poco stock", "inventario bajo",
        "prendas por agotarse", "que se esta acabando", "stock disponible por sucursal", "existencias actuales",
        "productos agotados", "{ver} el inventario de la sucursal {sucursal}", "cuantas unidades quedan en stock",
        "que tallas faltan", "valor del inventario", "{ver} las existencias por talla y color",
    ],
    "reservas": [
        "reservas {periodo}", "cuantas reservas hay pendientes", "estado de las reservas", "reservas por estado {periodo}",
        "reservas vencidas {periodo}", "cuantas reservas se concretaron {periodo}", "{ver} las reservas {periodo}",
        "reservas por sucursal {periodo}", "cuantos clientes reservaron {periodo}", "reservas canceladas {periodo}",
    ],
    "metodos_pago": [
        "ventas por metodo de pago {periodo}", "cuanto se cobro con qr {periodo}", "pagos con paypal contra efectivo",
        "como pagan los clientes", "formas de pago mas usadas {periodo}", "efectivo versus qr {periodo}",
        "{ver} los cobros por metodo de pago", "cuanto entro por paypal {periodo}", "pagos en efectivo {periodo}",
    ],
    "origen": [
        "ventas sin conexion {periodo}", "ventas offline contra online {periodo}", "{ver} las ventas offline",
        "cuanto se vendio sin internet {periodo}", "ventas en linea y de mostrador {periodo}",
        "compara ventas online y offline", "ventas de mostrador contra tienda en linea {periodo}",
        "cuantas ventas se sincronizaron {periodo}",
    ],
    "no_soportado": [
        "que hora es", "contame un chiste", "como esta el clima", "quien gano el partido", "pone musica",
        "cual es la capital de francia", "abre la camara", "hola como estas", "gracias", "apaga la luz",
        "cuanto es dos mas dos", "recordame llamar a mi mama", "escribe un poema", "traduce esto al ingles",
    ],
}

PRODUCTO = ["la polera negra", "el jean slim", "la chaqueta de cuero", "el hoodie gris", "la camisa blanca", "la chompa beige"]
CATEGORIA = ["poleras", "jeans", "chaquetas", "camisas", "vestidos", "pantalones", "accesorios", "hoodies", "faldas",
             "blusas", "leggings", "pijamas", "zapatos"]
PUBLICO = ["mujer", "dama", "hombre", "caballero", "nina", "nino", "ninos", "bebe", "mi hija", "mi hijo", "mi esposa", "mi novio"]
MONTO = ["100", "150", "200", "250", "300", "500", "cien", "doscientos", "trescientos", "quinientos", "80", "120"]
MONEDA = ["bolivianos", "bs", "", "pesos"]
NOMBRE_TIENDA = ["atelier", "fashion store", "la boutique", "esa tienda"]
PLAN = ["basico", "profesional", "prueba", "gratis", "mas caro"]

PLANTILLAS_CHATBOT: dict[str, list[str]] = {
    "saludo": ["hola", "buenas", "buenos dias", "buenas tardes", "hola que tal", "hey hola", "buenas noches", "hola tienda",
               "holi", "hola buen dia", "que tal", "hola hay alguien", "saludos"],
    "despedida": ["chau", "adios", "hasta luego", "nos vemos", "me voy", "hasta pronto", "bye", "chao", "hasta manana",
                  "eso es todo", "nada mas por ahora"],
    "gracias": ["gracias", "muchas gracias", "te agradezco", "genial gracias", "mil gracias", "ok gracias", "perfecto gracias",
                "muy amable", "excelente gracias", "buenisimo gracias"],
    "horario": ["a que hora abren", "cual es el horario", "atienden los domingos", "hasta que hora estan abiertos",
                "que dias atienden", "horario de atencion", "estan abiertos hoy", "a que hora cierran", "abren los feriados",
                "atienden el sabado en la tarde", "a que hora puedo ir"],
    "ubicacion": ["donde estan ubicados", "cual es la direccion", "donde queda la tienda", "que sucursales tienen",
                  "tienen tienda en el norte", "como llego a la sucursal", "donde puedo ir a ver la ropa", "ubicacion de la tienda",
                  "tienen local fisico", "en que zona estan", "pasame la direccion"],
    "envios": ["hacen envios", "envian a domicilio", "cuanto cuesta el envio", "cuanto tarda el envio", "envian a todo el pais",
               "puedo recibir en mi casa", "hacen delivery", "como funciona el envio", "envian a la paz", "llevan a domicilio",
               "cuanto demora en llegar"],
    "devoluciones": ["puedo devolver una prenda", "como hago un cambio de talla", "politica de devoluciones", "me quedo chico puedo cambiarlo",
                     "cuanto tiempo tengo para devolver", "quiero cambiar mi compra", "como pido un reembolso", "aceptan cambios",
                     "me llego fallada la prenda", "quiero devolver {producto}"],
    "metodos_pago": ["como puedo pagar", "aceptan qr", "puedo pagar con paypal", "aceptan tarjeta", "se puede pagar en efectivo",
                     "que metodos de pago tienen", "pago contra entrega", "puedo pagar al recibir", "formas de pago",
                     "puedo pagar con transferencia", "aceptan tarjeta de debito"],
    "stock": ["tienen {producto} en talla m", "hay stock de {producto}", "queda {producto}", "tienen {producto} disponible",
              "hay {producto} en negro", "les queda talla l de {producto}", "tienen tallas grandes", "hay disponibilidad de {producto}",
              "tienen {producto}", "venden {producto}", "hay {producto}", "todavia tienen {producto}", "les llego {producto}",
              "tienen {categoria}", "hay {categoria} en talla s", "en que tallas viene {producto}", "{producto} en que colores hay",
              "hay talla xl de {categoria}", "se agoto {producto}", "tienen {categoria} para {publico}",
              "hay ropa para {publico}", "que tallas tienen para {publico}", "hay {categoria} de {publico} en talla 8"],
    "precio": ["cuanto cuesta {producto}", "precio de {producto}", "cuanto sale {producto}", "que precio tiene {producto}",
               "tienen ofertas", "hay descuentos", "{producto} esta en oferta", "cuanto vale {producto}",
               "que productos tienen precio menor a {monto} {moneda}", "que productos cuestan menos de {monto} {moneda}",
               "prendas de menos de {monto} {moneda}", "que hay por menos de {monto} {moneda}", "algo que cueste hasta {monto} {moneda}",
               "productos entre {monto} y {monto} {moneda}", "que cuesta mas de {monto} {moneda}", "lo mas barato que tengan",
               "que es lo mas economico", "prendas baratas", "busco algo barato", "tienen algo economico", "lo mas caro que tengan",
               "{categoria} de menos de {monto} {moneda}", "{categoria} baratas", "cuanto cuestan las {categoria}",
               "tengo {monto} {moneda} que puedo comprar", "mi presupuesto es de {monto} {moneda}", "precios de {categoria}",
               "{categoria} en oferta", "que hay en liquidacion", "precio maximo {monto} {moneda}",
               "{categoria} para {publico} de menos de {monto} {moneda}", "cuanto cuestan los {categoria} de {publico}"],
    "recomendacion": ["que me recomiendas", "que me queda bien para una fiesta", "busco ropa para el trabajo", "que esta de moda",
                      "recomiendame algo casual", "que combina con {producto}", "busco un regalo", "que ropa tienen para el frio",
                      "que me sugieres", "ideas para un outfit", "que {categoria} me recomiendas", "que es lo mas vendido",
                      "que prendas son tendencia", "busco algo para una boda", "que me recomiendas para {publico}",
                      "busco un regalo para {publico}", "que ropa tienen para {publico}", "ideas de outfit para {publico}"],
    "reservas": ["puedo reservar {producto}", "como hago una reserva", "me guardan {producto}", "quiero apartar una prenda",
                 "cuanto tiempo dura la reserva", "puedo reservar y pagar en tienda", "como reservo sin pagar",
                 "quiero reservar para recoger manana", "se puede separar una prenda"],
    "estado_pedido": ["donde esta mi pedido", "ya enviaron mi compra", "cuando llega mi pedido", "estado de mi compra",
                      "no me llego el pedido", "mi pedido esta en camino", "quiero rastrear mi envio", "ya despacharon mi pedido",
                      "que paso con mi compra", "cuando me entregan"],
    "tiendas": ["que tiendas hay", "que tiendas tienen", "cuales son las tiendas", "que boutiques hay en arlani",
                "en que tienda encuentro {producto}", "que tienda vende {producto}", "donde puedo comprar {producto}",
                "que tiendas venden {categoria}", "cuantas tiendas hay", "tiendas disponibles", "que marcas venden aqui",
                "quien vende {categoria}", "que hay en {tienda}", "que vende {tienda}", "otras tiendas",
                "que tiendas venden ropa de {publico}", "hay tiendas para {publico}"],
    # Plataforma (portada de Arlani): para duenos de boutiques que quieren su tienda.
    "planes": ["que planes tienen", "cuanto cuesta la suscripcion", "precio de los planes", "cuanto cuesta el plan {plan}",
               "que incluye el plan {plan}", "diferencia entre el plan basico y el profesional", "hay plan gratis",
               "cuanto dura la prueba gratis", "cuantas sucursales permite el plan {plan}", "cuanto sale al año",
               "hay descuento si pago anual", "que comision cobran por venta", "el plan {plan} tiene reportes con ia",
               "que plan me conviene si tengo {top} sucursales", "cual es el plan mas barato", "planes de suscripcion",
               "cuanto cuesta usar arlani", "tienen plan mensual", "el plan {plan} incluye venta offline"],
    "suscribirse": ["como registro mi tienda", "como creo mi boutique", "quiero vender en arlani", "como me suscribo",
                    "pasos para abrir mi tienda", "como empiezo", "quiero crear mi tienda online", "como contrato un plan",
                    "como pago la suscripcion", "quiero registrar mi boutique", "que necesito para crear mi tienda",
                    "como subo mis productos", "como activo la prueba gratis", "quiero poner mi negocio en la plataforma",
                    "como me uno a arlani", "puedo tener mi propia tienda aqui"],
    "plataforma": ["que es arlani", "que es arlani boutiques", "como funciona la plataforma", "que funciones tiene",
                   "para que sirve arlani", "que ventajas tiene", "funciona sin internet", "tiene app movil",
                   "puedo manejar varias sucursales", "tiene probador virtual", "necesito soporte", "como contacto a soporte",
                   "tienen whatsapp", "quienes son ustedes", "es seguro vender aqui", "que hace el chatbot"],
    "otro": ["que hora es", "contame un chiste", "quien gano el partido", "cual es la capital de francia", "cuanto es dos mas dos",
             "me ayudas con mi tarea", "pone musica", "como esta el clima", "como te llamas", "eres un robot",
             "cuentame algo", "que opinas de la politica", "escribe un poema", "cual es tu color favorito"],
}


def _sin_tildes(texto: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", texto) if unicodedata.category(ch) != "Mn")


def _variantes(texto: str, rnd: random.Random) -> str:
    """Ruido realista: mayusculas, signos, palabras de cortesia."""
    texto = " ".join(texto.split())
    if rnd.random() < 0.3:
        texto = texto.capitalize()
    if rnd.random() < 0.2:
        texto = rnd.choice(["por favor ", "oye ", "che ", "porfa "]) + texto
    if rnd.random() < 0.25:
        texto += rnd.choice(["?", " por favor", " porfa", ".", " gracias"])
    return texto


def generar(
    plantillas: dict[str, list[str]], por_intencion: int, semilla: int, rellenos: dict[str, list[str]] | None = None
) -> list[tuple[str, str]]:
    """rellenos: valores propios para {producto}, {sucursal}... (los de una tienda)."""
    valores = {"ver": VER, "periodo": PERIODO, "grano": GRANO, "top": TOP, "sucursal": SUCURSAL, "producto": PRODUCTO,
               "categoria": CATEGORIA, "publico": PUBLICO, "monto": MONTO, "moneda": MONEDA, "tienda": NOMBRE_TIENDA, "plan": PLAN,
               **{k: v for k, v in (rellenos or {}).items() if v}}
    rnd = random.Random(semilla)
    datos: list[tuple[str, str]] = []
    for intencion, frases in plantillas.items():
        vistas: set[str] = set()
        intentos = 0
        while len(vistas) < por_intencion and intentos < por_intencion * 30:
            intentos += 1
            f = rnd.choice(frases).format(**{k: rnd.choice(v) for k, v in valores.items()})
            f = _variantes(_sin_tildes(f) if rnd.random() < 0.5 else f, rnd)
            if f.lower() not in vistas:
                vistas.add(f.lower())
                datos.append((f, intencion))
    rnd.shuffle(datos)
    return datos


# Frases que solo tienen sentido con los datos reales (sucursales con
# nombre): se suman al entrenar el chatbot de una tienda o el universal.
PLANTILLAS_TIENDA: dict[str, list[str]] = {
    "ubicacion": ["donde queda la {sucursal}", "como llego a {sucursal}", "direccion de {sucursal}"],
    "horario": ["a que hora abre {sucursal}", "horario de {sucursal}", "{sucursal} abre el sabado"],
}


def dataset(tarea: str, tienda: dict[str, list[str]] | None = None, semilla: int = 0) -> list[tuple[str, str]]:
    """tienda (solo el chatbot): sus productos, categorias, sucursales (y en
    el universal, los nombres de las tiendas), para que el modelo reconozca
    como preguntan sus clientes."""
    if tarea == "reportes":
        return generar(PLANTILLAS_REPORTES, 70, 18)
    if not tienda:
        return generar(PLANTILLAS_CHATBOT, 60, 19)
    plantillas = {k: v + (PLANTILLAS_TIENDA.get(k, []) if tienda.get("sucursal") else []) for k, v in PLANTILLAS_CHATBOT.items()}
    return generar(plantillas, 60, 19 + semilla, tienda)


# Prueba de parafrasis: frases escritas a mano, con palabras DISTINTAS a las
# de las plantillas, que nunca se usan para entrenar. Miden si el modelo
# entiende lo que se pide o solo reconoce las palabras que ya vio.
PARAFRASIS: dict[str, list[tuple[str, str]]] = {
    "reportes": [
        ("cuanta plata entro en septiembre", "ventas_periodo"), ("como nos fue vendiendo el mes pasado", "ventas_periodo"),
        ("la facturacion de la semana", "ventas_periodo"), ("evolucion diaria de lo vendido", "ventas_periodo"),
        ("cual local facturo mas", "ventas_sucursal"), ("comparame los locales", "ventas_sucursal"),
        ("rendimiento de cada tienda fisica", "ventas_sucursal"), ("que local anda mejor este mes", "ventas_sucursal"),
        ("las prendas que mas salieron", "top_productos"), ("lo que mas se llevaron los clientes", "top_productos"),
        ("articulos estrella de octubre", "top_productos"), ("que es lo que menos sale", "top_productos"),
        ("que rubro deja mas plata", "categorias"), ("ingresos segun el tipo de ropa", "categorias"),
        ("que linea aporta mas", "categorias"), ("chaquetas o poleras que rinde mas", "categorias"),
        ("que se nos esta terminando", "stock"), ("cuanta mercaderia queda", "stock"),
        ("prendas casi agotadas", "stock"), ("unidades disponibles de cada articulo", "stock"),
        ("cuantas prendas apartaron los clientes", "reservas"), ("separaciones pendientes", "reservas"),
        ("reservas que no se retiraron", "reservas"), ("cuantos apartados hubo", "reservas"),
        ("cuanto se cobro con tarjeta y con efectivo", "metodos_pago"), ("como nos pagan mas", "metodos_pago"),
        ("cobros por qr de la semana", "metodos_pago"), ("forma de pago preferida", "metodos_pago"),
        ("lo que se vendio cuando no habia internet", "origen"), ("ventas por la web contra ventas del local", "origen"),
        ("cuanto se vendio en linea", "origen"), ("ventas sincronizadas despues del corte", "origen"),
        ("pone una cancion", "no_soportado"), ("que tiempo hace hoy", "no_soportado"),
        ("cuentame algo gracioso", "no_soportado"), ("quien es el presidente", "no_soportado"),
    ],
    "chatbot": [
        ("que onda", "saludo"), ("buen dia como va", "saludo"), ("holaa", "saludo"),
        ("eso seria todo", "despedida"), ("me retiro, hasta la proxima", "despedida"), ("cuidate, chao", "despedida"),
        ("te pasaste, gracias", "gracias"), ("agradecido", "gracias"), ("re amable, gracias", "gracias"),
        ("a que hora atienden ustedes", "horario"), ("el domingo esta abierto", "horario"), ("hasta que hora puedo pasar", "horario"),
        ("en que calle estan", "ubicacion"), ("donde los encuentro", "ubicacion"), ("tienen local en santa cruz", "ubicacion"),
        ("me lo pueden mandar a mi casa", "envios"), ("hacen entregas", "envios"), ("en cuanto tiempo me llega a la paz", "envios"),
        ("me quedo grande, lo puedo cambiar", "devoluciones"), ("quiero mi plata de vuelta", "devoluciones"),
        ("la prenda vino fallada", "devoluciones"), ("puedo abonar con tarjeta", "metodos_pago"),
        ("se puede pagar con transferencia bancaria", "metodos_pago"), ("aceptan efectivo", "metodos_pago"),
        ("les queda la chaqueta en talla l", "stock"), ("todavia hay jeans", "stock"), ("hay en otro color", "stock"),
        ("me sale muy costoso, algo mas accesible", "precio"), ("que vale la polera", "precio"),
        ("algo por debajo de 150", "precio"), ("tienen rebajas", "precio"),
        ("que me pongo para una cena", "recomendacion"), ("sugerime algo lindo", "recomendacion"),
        ("que esta de moda ahora", "recomendacion"), ("me la pueden guardar hasta el sabado", "reservas"),
        ("quiero apartarla y pagar alla", "reservas"), ("como separo una prenda", "reservas"),
        ("ya salio mi compra", "estado_pedido"), ("todavia no recibo lo que pedi", "estado_pedido"),
        ("en que va mi envio", "estado_pedido"), ("cuantas boutiques estan aqui", "tiendas"),
        ("quien vende chaquetas", "tiendas"), ("en que local encuentro hoodies", "tiendas"),
        ("cuanto me cobran al mes por usar la plataforma", "planes"), ("hay alguna opcion gratuita", "planes"),
        ("que trae el plan mas completo", "planes"), ("quisiera abrir mi propia boutique", "suscribirse"),
        ("como pongo mi negocio aqui", "suscribirse"), ("que tengo que hacer para vender con ustedes", "suscribirse"),
        ("de que se trata esta pagina", "plataforma"), ("con quien hablo si tengo un problema", "plataforma"),
        ("sirve si se corta el internet", "plataforma"), ("dime la capital de peru", "otro"),
        ("cantame algo", "otro"), ("quien gano el clasico", "otro"),
    ],
}
