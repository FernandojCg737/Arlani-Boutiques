"""Preprocesamiento del texto (CU18), pasos 1 a 4 del pipeline:

1. Normalizacion: minusculas, sin tildes ni signos, numeros unificados.
2. Tokenizacion: el texto se parte en palabras.
3. Stopwords: se quitan las palabras vacias del espanol ("de", "la", "que"...).
4. Lematizacion: cada palabra a su forma base ("vendidos" -> "vender").

Los pasos 5 (BoW / TF-IDF) y 6 (modelo) estan en entrenamiento.py.
"""

import re
import unicodedata

import simplemma

# Palabras vacias del espanol (sin tildes, como quedan tras normalizar).
# NO se quitan las que cambian el sentido de un reporte: "mas", "menos",
# "mejor", "por", "cada", "entre", "vs".
STOPWORDS = set("""
a al algo alguna alguno algunos ante antes aqui asi aun aunque bien con contra cual cuales cuando de del desde donde
durante e el ella ellas ello ellos en era eran es esa esas ese eso esos esta estaba estado estan estar este esto estos
fue fueron ha han hasta la las le les lo los me mi mis mucho muy nada ni no nos nosotros o os otra otro para pero poco
porque que quien se sea ser si sin sobre solo son su sus tambien te todo todos tu tus un una uno unos y ya yo
favor porfa porfavor oye che pues entonces podrias puedes podes quisiera
""".split())
# No son stopwords aunque lo parezcan: "hola" y "buenas" son el saludo del
# chatbot, y "hay"/"tienen" casi siempre preguntan por stock.

# Lemas del dominio que el lematizador general no resuelve bien.
LEMAS = {
    "ventas": "venta", "venta": "venta", "vendido": "vender", "vendidos": "vender", "vendidas": "vender", "vendio": "vender",
    "vendimos": "vender", "vende": "vender", "venden": "vender", "mejores": "mejor", "mostrame": "mostrar",
    "muestrame": "mostrar", "mostrar": "mostrar", "dame": "dar", "generame": "generar", "genera": "generar",
    "compara": "comparar", "comparame": "comparar", "sacame": "sacar", "pasame": "pasar", "ensename": "mostrar",
    "productos": "producto", "prendas": "prenda", "sucursales": "sucursal", "categorias": "categoria",
    "reservas": "reserva", "reservo": "reservar", "pagos": "pago", "pagan": "pagar", "envios": "envio",
    "existencias": "existencia", "agotados": "agotar", "agotadas": "agotar", "horarios": "horario",
    "devoluciones": "devolucion", "cambios": "cambio", "tallas": "talla", "colores": "color", "precios": "precio",
    "meses": "mes", "dias": "dia", "semanas": "semana", "ultimos": "ultimo", "ultimas": "ultimo",
    "mayores": "mayor", "menores": "menor", "ingresos": "ingreso", "clientes": "cliente", "unidades": "unidad",
    "jeans": "jean", "hay": "haber", "tiene": "tener", "tienen": "tener", "queda": "quedar", "quedan": "quedar",
    "buenas": "bueno", "buenos": "bueno", "noches": "noche", "tardes": "tarde",
}

NUMEROS = {"uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "veinte", "cien"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    texto = re.sub(r"\d+", " num ", texto)
    texto = re.sub(r"[^a-z\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokenizar(texto: str) -> list[str]:
    return [t if t not in NUMEROS else "num" for t in texto.split()]


def quitar_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOPWORDS]


def lematizar(tokens: list[str]) -> list[str]:
    return [LEMAS.get(t) or simplemma.lemmatize(t, lang="es") for t in tokens]


def preprocesar(texto: str) -> str:
    """Texto listo para el paso 5 (lemas separados por espacio)."""
    return " ".join(lematizar(quitar_stopwords(tokenizar(normalizar(texto)))))


def pasos(texto: str) -> dict:
    """Cada paso por separado, para mostrar el pipeline en el CU18."""
    normal = normalizar(texto)
    tokens = tokenizar(normal)
    sin_stop = quitar_stopwords(tokens)
    lemas = lematizar(sin_stop)
    return {"original": texto, "normalizado": normal, "tokens": tokens, "sin_stopwords": sin_stop, "lemas": lemas}
