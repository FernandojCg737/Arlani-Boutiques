"""CU18: modelo de recomendacion de prendas, uno por tienda.

Hibrido de dos fuentes:
- Contenido: cada prenda se describe con su nombre, descripcion, categoria,
  marca y colores; pasa por los pasos 1 a 4 del pipeline (normalizacion,
  tokens, stopwords, lemas) y por TF-IDF (paso 5), o por el modelo de
  lenguaje preentrenado si esta activado. Dos prendas se parecen si su
  descripcion se parece (similitud coseno).
- Colaborativo (KNN item-item): una matriz clientes x prendas con lo que
  cada cliente compro (peso 3) y miro (peso 1). Dos prendas se parecen si las
  eligen los mismos clientes; cada prenda se queda con sus K vecinos.

  similitud = a * colaborativo + (1 - a) * contenido

Evaluacion (para elegir a y la fuente de contenido): las ventas se ordenan
por fecha; con el 80% mas antiguo se entrena y en el 20% mas nuevo se mira
cada venta con 2 o mas prendas: dada una, el modelo tiene que poner a la
otra entre sus primeras K (acierto@K) y lo mas arriba posible (MRR). Se
compara contra "las mas vendidas" y contra elegir al azar.
"""

from datetime import datetime

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml import embeddings
from app.ml.texto import preprocesar

K = 3  # acierto@K: las tiendas tienen pocas prendas, K chico para que la prueba diga algo
VECINOS = 5
PESO_COMPRA, PESO_VISTA = 3.0, 1.0
ALFAS = (0.25, 0.5, 0.75)


def _datos(db: Session, empresa_id: int) -> dict:
    productos = db.execute(
        text("""SELECT p.id, p.nombre, coalesce(p.descripcion, '') AS descripcion, c.nombre AS categoria,
                       coalesce(m.nombre, '') AS marca,
                       coalesce((SELECT string_agg(DISTINCT co.nombre, ' ') FROM inventario i JOIN color co ON co.id = i.color_id
                                 WHERE i.producto_id = p.id), '') AS colores
                FROM producto p JOIN categoria c ON c.id = p.categoria_id LEFT JOIN marca m ON m.id = p.marca_id
                WHERE p.empresa_id = :e AND p.estado = 'activo' ORDER BY p.id"""),
        {"e": empresa_id},
    ).all()
    compras = db.execute(
        text("""SELECT v.id AS venta, v.cliente_id, il.producto_id, v.fecha,
                       u.email LIKE 'consumidor.final%' AS anonimo FROM item_linea il
                JOIN (SELECT id, venta_presencial_id AS venta_id FROM detalle_venta_presencial
                      UNION ALL SELECT id, venta_digital_id FROM detalle_venta_digital) d ON d.id = il.id
                JOIN venta v ON v.id = d.venta_id JOIN sucursal s ON s.id = v.sucursal_id
                JOIN producto p ON p.id = il.producto_id JOIN usuario u ON u.id = v.cliente_id
                WHERE s.empresa_id = :e AND p.empresa_id = :e AND v.estado = 'pagada' ORDER BY v.fecha"""),
        {"e": empresa_id},
    ).all()
    vistas = db.execute(
        text("""SELECT vp.cliente_id, vp.producto_id, vp.fecha FROM vista_producto vp JOIN producto p ON p.id = vp.producto_id
                WHERE p.empresa_id = :e"""),
        {"e": empresa_id},
    ).all()
    return {"productos": productos, "compras": compras, "vistas": vistas}


def _coseno(m: np.ndarray) -> np.ndarray:
    norma = np.linalg.norm(m, axis=1, keepdims=True)
    norma[norma == 0] = 1
    x = m / norma
    s = x @ x.T
    np.fill_diagonal(s, 0)
    return s


def _contenido(productos, fuente: str) -> np.ndarray:
    if fuente == embeddings.NOMBRE:
        textos = [f"{p.nombre}. {p.descripcion}. {p.categoria} {p.marca} {p.colores}" for p in productos]
        return _coseno(embeddings.vectores(textos).astype(float))
    textos = [preprocesar(f"{p.nombre} {p.descripcion} {p.categoria} {p.categoria} {p.marca} {p.colores}") for p in productos]
    tfidf = TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False, sublinear_tf=True)
    return _coseno(tfidf.fit_transform(textos).toarray())


def _colaborativo(indice: dict[int, int], compras, vistas) -> np.ndarray:
    # Las ventas sin cuenta (consumidor final) no son de UN cliente: no cuentan aca.
    compras = [f for f in compras if not f.anonimo]
    clientes = {c: i for i, c in enumerate(sorted({f.cliente_id for f in compras} | {f.cliente_id for f in vistas}))}
    r = np.zeros((len(indice), max(1, len(clientes))))
    for f in compras:
        if f.producto_id in indice:
            r[indice[f.producto_id], clientes[f.cliente_id]] += PESO_COMPRA
    for f in vistas:
        if f.producto_id in indice:
            r[indice[f.producto_id], clientes[f.cliente_id]] += PESO_VISTA
    s = _coseno(np.log1p(r))
    # KNN: cada prenda conserva solo sus K vecinos mas parecidos.
    for i in range(len(s)):
        lejos = np.argsort(s[i])[:-VECINOS]
        s[i, lejos] = 0
    return s


def _normalizar(s: np.ndarray) -> np.ndarray:
    tope = s.max(axis=1, keepdims=True)
    tope[tope == 0] = 1
    return s / tope


def _popularidad(indice: dict[int, int], compras) -> np.ndarray:
    p = np.zeros(len(indice))
    for f in compras:
        if f.producto_id in indice:
            p[indice[f.producto_id]] += 1
    return p / (p.max() or 1)


def _evaluar(matriz: np.ndarray, pares: list[tuple[int, int]]) -> dict:
    aciertos, rr = 0, 0.0
    for a, b in pares:
        fila = matriz[a].copy()
        fila[a] = -np.inf
        orden = np.argsort(-fila, kind="stable")
        pos = int(np.where(orden == b)[0][0]) + 1
        aciertos += pos <= K
        rr += 1 / pos
    n = len(pares) or 1
    return {"acierto": round(aciertos / n, 4), "mrr": round(rr / n, 4)}


def entrenar(db: Session, empresa_id: int) -> dict:
    d = _datos(db, empresa_id)
    db.commit()  # se suelta la conexion mientras se calcula
    productos, compras, vistas = d["productos"], d["compras"], d["vistas"]
    if len(productos) < 3:
        raise ValueError("La tienda necesita al menos 3 prendas activas para entrenar el recomendador.")
    indice = {p.id: i for i, p in enumerate(productos)}
    n = len(productos)

    # Separacion por tiempo: 80% de las ventas mas antiguas para entrenar.
    ventas = list(dict.fromkeys(f.venta for f in compras))
    corte = set(ventas[: int(len(ventas) * 0.8)])
    entreno = [f for f in compras if f.venta in corte]
    limite = max((f.fecha for f in entreno), default=datetime.max)
    vistas_entreno = [f for f in vistas if f.fecha <= limite]
    canastas: dict[int, set[int]] = {}
    for f in compras:
        if f.venta not in corte and f.producto_id in indice:
            canastas.setdefault(f.venta, set()).add(indice[f.producto_id])
    pares = [(a, b) for c in canastas.values() if len(c) >= 2 for a in c for b in c if a != b]

    # La matriz se guarda ya calculada: al recomendar no se necesita el servicio de embeddings.
    with embeddings.para_entrenar():
        usar_embeddings = embeddings.habilitado() and embeddings.disponible()
    fuentes = ["TF-IDF"] + ([embeddings.NOMBRE] if usar_embeddings else [])
    with embeddings.para_entrenar():
        contenidos = {f: _normalizar(_contenido(productos, f)) for f in fuentes}
    colab = _normalizar(_colaborativo(indice, entreno, vistas_entreno))
    popular = np.tile(_popularidad(indice, entreno), (n, 1))

    candidatos = {"Más vendidas (referencia)": (popular, None, None)}
    for f, c in contenidos.items():
        candidatos[f"Contenido ({f})"] = (c, f, 0.0)
    candidatos["Colaborativo (KNN ítem-ítem)"] = (colab, None, 1.0)
    for f, c in contenidos.items():
        for a in ALFAS:
            candidatos[f"Híbrido {f} (a = {a})"] = (a * colab + (1 - a) * c, f, a)

    azar = round(min(1.0, K / max(1, n - 1)), 4)
    comparacion = []
    for nombre, (m, fuente, alfa) in candidatos.items():
        # Desempate por popularidad (lo mas vendido primero entre iguales).
        r = _evaluar(m + 1e-6 * popular, pares)
        comparacion.append({"modelo": nombre, "fuente": fuente, "alfa": alfa, **r})
    comparacion.sort(key=lambda x: (x["acierto"], x["mrr"]), reverse=True)
    elegibles = [c for c in comparacion if c["alfa"] is not None]
    mejor = elegibles[0]

    # Modelo final con TODAS las ventas y vistas.
    c_final = contenidos[mejor["fuente"]] if mejor["fuente"] else 0
    matriz = mejor["alfa"] * _normalizar(_colaborativo(indice, compras, vistas)) + (1 - mejor["alfa"]) * c_final
    artefacto = {
        "ids": [p.id for p in productos],
        "matriz": np.asarray(matriz, dtype=np.float32),
        "popularidad": _popularidad(indice, compras).astype(np.float32),
        "modelo": mejor["modelo"], "alfa": mejor["alfa"], "fuente": mejor["fuente"],
    }
    clientes = {f.cliente_id for f in compras if not f.anonimo}
    metricas = {
        "k": K, "acierto": mejor["acierto"], "mrr": mejor["mrr"], "azar": azar,
        "referencia": next(c for c in comparacion if c["alfa"] is None),
        "n_productos": n, "n_clientes": len(clientes), "n_ventas": len(ventas), "n_vistas": len(vistas),
        "n_pares_prueba": len(pares), "vecinos": VECINOS,
    }
    return {"artefacto": artefacto, "metricas": metricas, "comparacion": comparacion,
            "algoritmo": mejor["modelo"], "representacion": mejor["fuente"] or "—", "n_ejemplos": len(compras) + len(vistas)}


def parecidas(artefacto: dict, producto_id: int, n: int = 6) -> list[tuple[int, float]]:
    """Las prendas mas parecidas a una (para "Tambien te puede interesar")."""
    ids = artefacto["ids"]
    if producto_id not in ids:
        return []
    i = ids.index(producto_id)
    fila = artefacto["matriz"][i] + 1e-6 * artefacto["popularidad"]
    orden = [j for j in np.argsort(-fila, kind="stable") if j != i]
    return [(ids[j], round(float(fila[j]), 4)) for j in orden[:n] if fila[j] > 0]


def para_cliente(artefacto: dict, perfil: dict[int, float], excluir: set[int], n: int = 8) -> list[tuple[int, float]]:
    """Recomendaciones para un cliente: suma de lo parecido a lo que compro y
    miro (perfil: producto -> peso), sin lo que acaba de comprar."""
    ids = artefacto["ids"]
    pesos = np.zeros(len(ids), dtype=np.float32)
    for pid, w in perfil.items():
        if pid in ids:
            pesos[ids.index(pid)] = w
    if not pesos.any():
        return []
    puntaje = pesos @ artefacto["matriz"] + 1e-3 * artefacto["popularidad"]
    tope = float(puntaje.max()) or 1.0
    orden = np.argsort(-puntaje, kind="stable")
    return [(ids[j], round(float(puntaje[j]) / tope, 4)) for j in orden if ids[j] not in excluir][:n]
