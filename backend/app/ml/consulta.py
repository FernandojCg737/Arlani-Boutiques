"""CU17: de lo que pidio el usuario (voz o texto) a un reporte.

El modelo del CU18 decide QUE reporte es (la intencion). Estas reglas sacan
los filtros de la frase: el periodo, el "top N", la sucursal y si agrupa por
dia, semana o mes. Con eso se arma la consulta del motor dinamico (solo con
piezas permitidas: nunca SQL a partir del texto).
"""

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.ml.texto import normalizar

MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
           "nueve": 9, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30}

NOMBRES = {
    "ventas_periodo": "Ventas en el tiempo", "ventas_sucursal": "Ventas por sucursal", "top_productos": "Productos más vendidos",
    "categorias": "Ingresos por categoría", "stock": "Existencias (stock)", "reservas": "Reservas",
    "metodos_pago": "Ventas por método de pago", "origen": "Ventas online y offline",
}

SUGERENCIAS = [
    "Mostrame las ventas de septiembre agrupadas por sucursal",
    "¿Cuáles fueron los diez productos más vendidos este mes?",
    "Generá un gráfico de ventas por semana",
    "Mostrame los productos con menor existencia",
    "¿Qué categorías generaron mayores ingresos en los últimos tres meses?",
]


@dataclass
class Consulta:
    fuente: str
    agrupar: list[str]
    metricas: list[str]
    desde: date | None = None
    hasta: date | None = None
    limite: int | None = None
    ascendente: bool = False
    sucursal_id: int | None = None
    grafico: str = "bar"
    filtros: list[str] = field(default_factory=list)


def _mes(m: int, hoy: date) -> tuple[date, date]:
    anio = hoy.year if m <= hoy.month else hoy.year - 1
    inicio = date(anio, m, 1)
    fin = (date(anio + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    return inicio, min(fin, hoy)


def _numero(palabra: str) -> int | None:
    return int(palabra) if palabra.isdigit() else NUMEROS.get(palabra)


def periodo(t: str, hoy: date) -> tuple[date | None, date | None, str | None]:
    """Fechas de la frase (ya normalizada, con los numeros como digitos)."""
    m = re.search(r"del? (\d{1,2}) al (\d{1,2}) de (\w+)", t)
    if m and m.group(3) in MESES:
        ini, _ = _mes(MESES[m.group(3)], hoy)
        return ini.replace(day=int(m.group(1))), ini.replace(day=min(int(m.group(2)), 28 if ini.month == 2 else 30)), m.group(0)
    m = re.search(r"entre (\w+) y (\w+)", t)
    if m and m.group(1) in MESES and m.group(2) in MESES:
        return _mes(MESES[m.group(1)], hoy)[0], _mes(MESES[m.group(2)], hoy)[1], f"entre {m.group(1)} y {m.group(2)}"
    m = re.search(r"ultim[oa]s? (\w+) (dias|semanas|meses)", t)
    if m and _numero(m.group(1)):
        n = _numero(m.group(1))
        dias = {"dias": n, "semanas": n * 7, "meses": n * 30}[m.group(2)]
        return hoy - timedelta(days=dias - 1), hoy, f"últimos {n} {m.group(2)}"
    if re.search(r"\bhoy\b", t):
        return hoy, hoy, "hoy"
    if re.search(r"\bayer\b", t):
        return hoy - timedelta(days=1), hoy - timedelta(days=1), "ayer"
    if re.search(r"(esta|este) semana", t):
        return hoy - timedelta(days=hoy.weekday()), hoy, "esta semana"
    if re.search(r"(ultima|pasada) semana|semana pasada", t):
        return hoy - timedelta(days=7), hoy, "última semana"
    if re.search(r"mes pasado|ultimo mes|mes anterior", t):
        ini = (hoy.replace(day=1) - timedelta(days=1)).replace(day=1)
        return _mes(ini.month, hoy)[0], hoy.replace(day=1) - timedelta(days=1), "el mes pasado"
    if re.search(r"(este|esta) mes|del mes\b|en el mes", t):
        return hoy.replace(day=1), hoy, "este mes"
    if re.search(r"(este|del) ano|anual", t):
        return date(hoy.year, 1, 1), hoy, "este año"
    for palabra, numero in MESES.items():
        if re.search(rf"\b{palabra}\b", t):
            ini, fin = _mes(numero, hoy)
            return ini, fin, palabra
    return None, None, None


def interpretar(texto: str, intencion: str, hoy: date, sucursales: list[tuple[int, str]]) -> Consulta:
    t = normalizar(texto)
    # normalizar convierte los digitos en "num": se recuperan del texto original.
    digitos = iter(re.findall(r"\d+", texto))
    t_num = re.sub(r"\bnum\b", lambda _: next(digitos, "0"), t)

    desde, hasta, texto_periodo = periodo(t_num, hoy)
    filtros = [f"Periodo: {texto_periodo}"] if texto_periodo else []

    top = None
    m = re.search(r"\b(top|los|las|primer[oa]s)\s+(\w+)", t_num)
    if m and _numero(m.group(2)) and _numero(m.group(2)) <= 100:
        top = _numero(m.group(2))
    if re.search(r"\btop (\d+)", t_num):
        top = int(re.search(r"\btop (\d+)", t_num).group(1))

    sucursal_id = None
    for sid, nombre in sucursales:
        clave = normalizar(nombre).replace("sucursal ", "")
        if clave and re.search(rf"\b{re.escape(clave)}\b", t):
            sucursal_id = sid
            filtros.append(f"Sucursal: {nombre}")
            break

    grano = next((g for g, p in (("dia", r"\b(por|cada) dia|diari"), ("semana", r"\b(por|cada) semana|semanal"),
                                 ("mes", r"\b(por|cada) mes|mensual")) if re.search(p, t)), None)
    menos = bool(re.search(r"\b(menos|menor|menores|peor|peores|bajo|poco)\b", t))

    if intencion == "ventas_periodo":
        dias = ((hasta or hoy) - (desde or hoy - timedelta(days=60))).days
        g = grano or ("dia" if dias <= 31 else "semana" if dias <= 120 else "mes")
        c = Consulta("ventas", [g], ["cantidad", "total"], grafico="line")
    elif intencion == "ventas_sucursal":
        c = Consulta("ventas", ([grano] if grano else []) + ["sucursal"], ["total", "cantidad"])
    elif intencion == "top_productos":
        c = Consulta("productos", ["producto"], ["unidades", "ingresos"], limite=top or 10, ascendente=menos)
    elif intencion == "categorias":
        c = Consulta("productos", ["categoria"], ["ingresos", "unidades"], limite=top)
    elif intencion == "stock":
        c = Consulta("inventario", ["producto"], ["stock", "valor"], limite=top or 15, ascendente=not re.search(r"\b(mas|mayor)\b", t))
    elif intencion == "reservas":
        c = Consulta("reservas", [grano] if grano else ["estado"], ["cantidad"], grafico="line" if grano else "doughnut")
    elif intencion == "metodos_pago":
        c = Consulta("ventas", ["metodo"], ["total", "cantidad"], grafico="doughnut")
    else:  # origen
        c = Consulta("ventas", ["origen", "tipo"], ["total", "cantidad"])

    if c.fuente != "inventario" and desde is None:
        # Sin periodo en la frase: los ultimos 30 dias.
        desde, hasta = hoy - timedelta(days=29), hoy
        filtros.append("Periodo: últimos 30 días (no se indicó)")
    c.desde, c.hasta, c.sucursal_id, c.filtros = (desde, hasta, sucursal_id, filtros) if c.fuente != "inventario" else (None, None, sucursal_id, filtros)
    if c.limite:
        c.filtros.append(f"Los {c.limite} {'de menor' if c.ascendente else 'de mayor'} {'stock' if c.fuente == 'inventario' else 'venta'}")
    return c


def narrar(intencion: str, tabla: dict) -> str:
    """Resumen en palabras del reporte (para leerlo en voz alta)."""
    filas, cols = tabla["filas"], tabla["columnas"]
    if not filas:
        return "No encontré datos para lo que pediste en ese periodo."
    dim = cols[0]["clave"]
    med = next(c for c in cols if c["tipo"] in ("numero", "moneda"))
    valor = lambda f: float(f.get(med["clave"]) or 0)  # noqa: E731
    unidad = {"top_productos": " unidades", "reservas": " reservas"}.get(intencion, "")
    fmt = lambda v: (f"Bs {v:,.2f}" if med["tipo"] == "moneda" else f"{v:,.0f}{unidad}").replace(",", "X").replace(".", ",").replace("X", ".")  # noqa: E731
    total = sum(valor(f) for f in filas)
    if intencion == "ventas_periodo":
        mejor = max(filas, key=valor)
        total_bs = f"Bs {sum(float(f.get('total') or 0) for f in filas):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        periodo_top = str(mejor[dim]).replace("-S", ", semana ")
        return (f"En total se vendieron {total_bs} en {int(sum(float(f.get('cantidad') or 0) for f in filas))} ventas. "
                f"El mejor período fue {periodo_top}.")
    primero = filas[0]
    partes = f"{primero[dim]} lidera con {fmt(valor(primero))}"
    if len(filas) > 1:
        partes += f", seguido de {filas[1][dim]} con {fmt(valor(filas[1]))}"
    if intencion == "stock":
        return f"La prenda con menos existencias es {primero[dim]}, con {fmt(valor(primero))} unidades. Revisé {len(filas)} productos."
    if med["tipo"] == "moneda" and total:
        partes += f". El primero representa el {valor(primero) / total:.0%} del total de {fmt(total)}"
    return partes + "."
