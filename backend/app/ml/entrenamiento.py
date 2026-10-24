"""Entrenamiento y evaluacion (CU18), pasos 5 y 6 del pipeline.

5. Representacion: Bolsa de palabras (BoW, conteos), TF-IDF (peso de cada
   palabra segun lo informativa que es), con palabras sueltas y pares, y, si
   esta activado, embeddings de un modelo de lenguaje preentrenado
   (app/ml/embeddings.py: el significado de la frase, no solo sus palabras).
6. Modelo supervisado: Regresion logistica, Naive Bayes multinomial, KNN
   (vecinos por similitud coseno) y Arbol de decision. Se prueban todas las
   combinaciones y se elige la mejor por el promedio de dos F1: el de la
   prueba normal (20% de las frases generadas) y el de la prueba de
   parafrasis (frases escritas a mano con otras palabras, que miden si el
   modelo entiende o solo reconoce palabras). Despues se reentrena con todos
   los datos.

No supervisado: K-Means agrupa a los clientes de una tienda por recencia,
frecuencia y monto de compra (RFM); k se elige por el coeficiente de silueta.
"""

import pickle
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support, silhouette_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from app.ml import embeddings
from app.ml.datos import PARAFRASIS, dataset
from app.ml.texto import pasos, preprocesar

# Por debajo de esta confianza la frase se toma como "no entendida".
UMBRAL = 0.40


def _representaciones():
    comun = dict(tokenizer=str.split, token_pattern=None, lowercase=False, ngram_range=(1, 2))
    reps = {"BoW": lambda: CountVectorizer(**comun), "TF-IDF": lambda: TfidfVectorizer(sublinear_tf=True, **comun)}
    # Con el servicio remoto caido no se entrena con embeddings (no se podria usar).
    if embeddings.habilitado() and embeddings.disponible():
        reps[embeddings.NOMBRE] = embeddings.Embeddings
        # Las palabras exactas (TF-IDF) y el significado (embeddings), juntos.
        reps[f"TF-IDF + {embeddings.NOMBRE}"] = lambda: FeatureUnion([
            ("tfidf", TfidfVectorizer(sublinear_tf=True, **comun)), ("significado", embeddings.Embeddings()),
        ])
    return reps


def _modelos():
    return {
        "Regresión logística": lambda: LogisticRegression(max_iter=3000, C=5),
        "Naive Bayes": lambda: MultinomialNB(alpha=0.3),
        "KNN": lambda: KNeighborsClassifier(n_neighbors=5, metric="cosine", weights="distance"),
        # Hojas de al menos 2 ejemplos: probabilidades menos tajantes y menos sobreajuste.
        "Árbol de decisión": lambda: DecisionTreeClassifier(min_samples_leaf=2, random_state=42),
    }


def _compatible(rep: str, alg: str) -> bool:
    # Naive Bayes multinomial solo acepta conteos o pesos positivos (no embeddings).
    return not (embeddings.NOMBRE in rep and alg == "Naive Bayes")


def _usa_embeddings(rep: str) -> bool:
    return embeddings.NOMBRE in rep


def entrenar_clasificador(tarea: str, datos: list[tuple[str, str]] | None = None) -> dict:
    with embeddings.para_entrenar():
        return _entrenar_clasificador(tarea, datos)


def _entrenar_clasificador(tarea: str, datos: list[tuple[str, str]] | None) -> dict:
    datos = datos or dataset(tarea)
    textos = [preprocesar(t) for t, _ in datos]
    etiquetas = [e for _, e in datos]
    x_tr, x_te, y_tr, y_te = train_test_split(textos, etiquetas, test_size=0.2, random_state=42, stratify=etiquetas)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clases_datos = set(etiquetas)
    parafrasis = [(preprocesar(t), e) for t, e in PARAFRASIS.get(tarea, []) if e in clases_datos]

    comparacion, mejor, mejor_sin = [], None, None
    for rep, hacer_rep in _representaciones().items():
        for alg, hacer_alg in _modelos().items():
            if not _compatible(rep, alg):
                continue
            pipe = Pipeline([("vector", hacer_rep()), ("modelo", hacer_alg())])
            f1_cv = cross_val_score(pipe, x_tr, y_tr, cv=cv, scoring="f1_macro").mean()
            pipe.fit(x_tr, y_tr)
            pred = pipe.predict(x_te)
            fila = {
                "representacion": rep, "algoritmo": alg,
                "accuracy": round(accuracy_score(y_te, pred), 4),
                "f1": round(f1_score(y_te, pred, average="macro"), 4),
                "f1_cv": round(float(f1_cv), 4),
            }
            if parafrasis:
                y_pa = [e for _, e in parafrasis]
                p_pa = pipe.predict([t for t, _ in parafrasis])
                fila["f1_parafrasis"] = round(f1_score(y_pa, p_pa, labels=sorted(set(y_pa)), average="macro", zero_division=0), 4)
                fila["accuracy_parafrasis"] = round(accuracy_score(y_pa, p_pa), 4)
            fila["puntaje"] = round((fila["f1"] + fila.get("f1_parafrasis", fila["f1"])) / 2, 4)
            comparacion.append(fila)
            if mejor is None or (fila["puntaje"], fila["f1_cv"]) > (mejor[0]["puntaje"], mejor[0]["f1_cv"]):
                mejor = (fila, pipe, pred)
            # El mejor que NO necesita el modelo de lenguaje: respaldo si el servicio se cae.
            if not _usa_embeddings(rep) and (
                mejor_sin is None or (fila["puntaje"], fila["f1_cv"]) > (mejor_sin["puntaje"], mejor_sin["f1_cv"])
            ):
                mejor_sin = fila

    fila, pipe, pred = mejor
    clases = sorted(set(etiquetas))
    p, r, f, s = precision_recall_fscore_support(y_te, pred, labels=clases, zero_division=0)
    metricas = {
        **fila,
        "precision": round(float(np.mean(p)), 4), "recall": round(float(np.mean(r)), 4),
        "clases": clases,
        "por_clase": [{"clase": c, "precision": round(float(p[i]), 3), "recall": round(float(r[i]), 3),
                       "f1": round(float(f[i]), 3), "soporte": int(s[i])} for i, c in enumerate(clases)],
        "matriz_confusion": confusion_matrix(y_te, pred, labels=clases).tolist(),
        "n_entrenamiento": len(x_tr), "n_prueba": len(x_te), "n_parafrasis": len(parafrasis),
        "vocabulario": len({t for x in textos for t in x.split()}),
    }
    # El modelo que se usa se reentrena con todos los ejemplos.
    final = Pipeline([("vector", _representaciones()[fila["representacion"]]()), ("modelo", _modelos()[fila["algoritmo"]]())])
    final.fit(textos, etiquetas)
    # Las palabras vistas al entrenar: una frase sin ninguna no se puede decidir.
    final.palabras_conocidas_ = {t for x in textos for t in x.split()}
    if _usa_embeddings(fila["representacion"]):
        respaldo = Pipeline([("vector", _representaciones()[mejor_sin["representacion"]]()),
                             ("modelo", _modelos()[mejor_sin["algoritmo"]]())])
        respaldo.fit(textos, etiquetas)
        respaldo.palabras_conocidas_ = final.palabras_conocidas_
        final.respaldo_ = respaldo
        metricas["respaldo"] = {k: mejor_sin[k] for k in ("representacion", "algoritmo", "f1", "f1_cv", "puntaje")
                                if k in mejor_sin}
    comparacion.sort(key=lambda x: (x["puntaje"], x["f1_cv"]), reverse=True)
    return {"pipeline": final, "metricas": metricas, "comparacion": comparacion, "n_ejemplos": len(datos),
            "algoritmo": fila["algoritmo"], "representacion": fila["representacion"]}


def serializar(pipeline) -> bytes:
    return pickle.dumps(pipeline)


def cargar(artefacto: bytes):
    return pickle.loads(artefacto)  # noqa: S301 - artefacto propio guardado por el backend


def predecir(pipeline, texto: str) -> dict:
    """Intencion de una frase, con la confianza y cada paso del pipeline."""
    detalle = pasos(texto)
    entrada = " ".join(detalle["lemas"])
    con_respaldo = False
    try:
        probas = pipeline.predict_proba([entrada])[0]
    except embeddings.NoDisponible:
        # El servicio del modelo de lenguaje no respondio: el respaldo sin embeddings.
        respaldo = getattr(pipeline, "respaldo_", None)
        if respaldo is None:
            raise
        pipeline, con_respaldo = respaldo, True
        probas = pipeline.predict_proba([entrada])[0]
    clases = pipeline.classes_
    orden = np.argsort(probas)[::-1]
    vectorizador = pipeline.named_steps["vector"]
    if isinstance(vectorizador, FeatureUnion):
        # Se muestran los pesos de la parte TF-IDF (la de embeddings no son palabras).
        vectorizador = dict(vectorizador.transformer_list)["tfidf"]
    if hasattr(vectorizador, "vocabulary_"):
        vector = vectorizador.transform([entrada])
        vocab = {i: t for t, i in vectorizador.vocabulary_.items()}
        pesos = sorted(((vocab[i], round(float(v), 3)) for i, v in zip(vector.indices, vector.data)), key=lambda x: -x[1])
    else:
        # Embeddings: 384 numeros que no son palabras; se muestran los mas fuertes.
        v = vectorizador.transform([entrada])[0]
        pesos = [(f"dimensión {i}", round(float(v[i]), 3)) for i in np.argsort(-np.abs(v))[:12]]
    # Sin ninguna palabra que el modelo conozca, no hay de donde decidir.
    conocidas = getattr(pipeline, "palabras_conocidas_", None)
    hay_conocidas = any(t in conocidas for t in detalle["lemas"]) if conocidas is not None else bool(pesos)
    confianza = float(probas[orden[0]]) if hay_conocidas else 0.0
    return {
        **detalle,
        "vector": [{"termino": t, "peso": w} for t, w in pesos[:12]],
        "intencion": str(clases[orden[0]]) if confianza >= UMBRAL else "no_entendido",
        "confianza": round(confianza, 3),
        "alternativas": [{"intencion": str(clases[i]), "probabilidad": round(float(probas[i]), 3)} for i in orden[:3]],
        # True: respondio el modelo de respaldo (el servicio de embeddings no estaba).
        "con_respaldo": con_respaldo,
    }


# ------------------------------------------------------------ K-Means (RFM)

NOMBRES_SEGMENTO = ["Clientes VIP", "Frecuentes", "Ocasionales", "En riesgo", "Nuevos"]


def segmentar_clientes(filas: list[dict], hoy: datetime) -> dict:
    """filas: cliente, ultima_compra, compras, monto. Devuelve los segmentos."""
    if len(filas) < 6:
        return {"error": "Faltan clientes con compras para segmentar (mínimo 6)."}
    rfm = np.array([[(hoy - f["ultima_compra"]).days, f["compras"], float(f["monto"])] for f in filas], dtype=float)
    x = StandardScaler().fit_transform(rfm)
    siluetas = []
    for k in range(2, min(6, len(filas) - 1) + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(x)
        siluetas.append({"k": k, "silueta": round(float(silhouette_score(x, km.labels_)), 4), "inercia": round(float(km.inertia_), 2)})
    k = max(siluetas, key=lambda s: s["silueta"])["k"]
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(x)

    grupos = []
    for g in range(k):
        idx = np.where(km.labels_ == g)[0]
        datos = rfm[idx]
        grupos.append({
            "grupo": g, "clientes": len(idx),
            "recencia_dias": round(float(datos[:, 0].mean()), 1), "compras": round(float(datos[:, 1].mean()), 2),
            "monto": round(float(datos[:, 2].mean()), 2),
        })
    # Nombre segun el valor (monto x frecuencia) y lo reciente de la ultima compra.
    por_valor = sorted(grupos, key=lambda g: g["monto"] * g["compras"], reverse=True)
    nombres = {}
    for i, g in enumerate(por_valor):
        if i == 0:
            nombres[g["grupo"]] = "Clientes VIP"
        elif g["recencia_dias"] == max(x["recencia_dias"] for x in grupos):
            nombres[g["grupo"]] = "En riesgo"
        else:
            nombres[g["grupo"]] = ["Frecuentes", "Ocasionales", "Nuevos"][min(i - 1, 2)]
    for g in grupos:
        g["segmento"] = nombres[g["grupo"]]
    clientes = [{**{k2: v for k2, v in f.items() if k2 != "ultima_compra"}, "ultima_compra": f["ultima_compra"].strftime("%d/%m/%Y"),
                 "segmento": nombres[int(km.labels_[i])]} for i, f in enumerate(filas)]
    return {"k": k, "siluetas": siluetas, "silueta": max(s["silueta"] for s in siluetas),
            "segmentos": sorted(grupos, key=lambda g: g["monto"] * g["compras"], reverse=True),
            "clientes": sorted(clientes, key=lambda c: -float(c["monto"])), "variables": ["Recencia (días)", "Frecuencia (compras)", "Monto (Bs)"]}
