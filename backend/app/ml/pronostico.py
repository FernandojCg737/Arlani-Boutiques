"""CU18: pronostico de ventas (aprendizaje supervisado, regresion).

Variable objetivo conocida: lo vendido (Bs) por una sucursal en un dia.

1. Datos: la serie diaria real de cada sucursal (ventas pagadas; los dias sin
   venta cuentan como 0) y, como las tiendas tienen pocas semanas de
   historia, datos sinteticos: un año previo generado con el patron propio
   de cada sucursal (promedio por dia de la semana), la temporada de la
   moda (mas en diciembre, menos en enero...), una tendencia leve y ruido.
2. Variables (por dia): dia de la semana, mes (seno/coseno), fin de mes, lo
   vendido ayer y hace 7 dias, los promedios de los ultimos 7 y 28 dias y el
   del mismo dia de la semana en las 4 semanas previas.
   Todo se divide por el promedio de la sucursal: un solo modelo sirve para
   sucursales grandes y chicas.
3. Modelos: Ridge (lineal), Random Forest y Gradient Boosting, contra una
   linea base (promedio del mismo dia de la semana en las 4 semanas previas).
4. Evaluacion temporal: se entrena con lo sintetico y el 80 % mas antiguo de
   lo real y se mide en el 20 % mas nuevo (dias reales que el modelo no vio):
   MAE, RMSE, R2 y error porcentual. Gana el de menor MAE.
5. Pronostico: los proximos 28 dias de cada sucursal, dia por dia (cada
   prediccion alimenta a la siguiente), sumados por semana.
"""

import json
import math
from datetime import date, timedelta

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sqlalchemy import text
from sqlalchemy.orm import Session

DIAS_SINTETICOS = 365
DIAS_PRONOSTICO = 28
MIN_DIAS_REALES = 21
# Temporada de la moda (Bolivia): fiestas de fin de año, rebajas de enero,
# dia de la madre (mayo), invierno (junio-julio).
TEMPORADA = {1: 0.8, 2: 0.85, 3: 0.95, 4: 0.95, 5: 1.15, 6: 1.05, 7: 1.0, 8: 0.95, 9: 1.0, 10: 1.0, 11: 1.1, 12: 1.4}
VARIABLES = [
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo",
    "Mes (seno)", "Mes (coseno)", "Fin de mes", "Venta de ayer", "Venta hace 7 días", "Promedio 7 días", "Promedio 28 días",
    "Mismo día (4 semanas)",
]


def series_reales(db: Session, empresa_id: int, hoy: date) -> list[dict]:
    """Lo vendido por dia en cada sucursal activa (con 0 los dias sin venta)."""
    filas = db.execute(
        text("""SELECT s.id, s.nombre, (v.fecha AT TIME ZONE 'UTC' AT TIME ZONE 'America/La_Paz')::date AS dia, sum(v.total) AS total
                FROM venta v JOIN sucursal s ON s.id = v.sucursal_id
                WHERE s.empresa_id = :e AND s.estado = 'activa' AND v.estado = 'pagada'
                GROUP BY s.id, s.nombre, dia ORDER BY s.id, dia"""),
        {"e": empresa_id},
    ).all()
    series: dict[int, dict] = {}
    for f in filas:
        s = series.setdefault(f.id, {"sucursal_id": f.id, "sucursal": f.nombre, "dias": {}})
        s["dias"][f.dia] = float(f.total)
    resultado = []
    for s in series.values():
        # Historia observada: del primer al ultimo dia con ventas (si la tienda
        # dejo de cargar ventas, esos dias no se toman como dias en 0).
        inicio, fin = min(s["dias"]), min(max(s["dias"]), hoy)
        n = (fin - inicio).days + 1
        fechas = [inicio + timedelta(days=i) for i in range(n)]
        resultado.append({**s, "fechas": fechas, "valores": [s["dias"].get(d, 0.0) for d in fechas]})
    return resultado


def sinteticos(fechas: list[date], valores: list[float], semilla: int) -> tuple[list[date], list[float]]:
    """Un año de historia previa con el patron de la sucursal."""
    rnd = np.random.default_rng(semilla)
    por_dia = [np.mean([v for d, v in zip(fechas, valores) if d.weekday() == w] or [0.0]) for w in range(7)]
    media = max(np.mean(valores), 1.0)
    por_dia = [p if p > 0 else media * 0.5 for p in por_dia]
    # Ruido y dias sin venta como los de la propia sucursal.
    relativos = [v / por_dia[d.weekday()] for d, v in zip(fechas, valores) if v > 0]
    ruido = float(np.clip(np.std(relativos) if len(relativos) > 1 else 0.25, 0.05, 0.6))
    sin_venta = sum(1 for v in valores if v == 0) / len(valores)
    inicio = fechas[0] - timedelta(days=DIAS_SINTETICOS)
    f_sint, v_sint = [], []
    for i in range(DIAS_SINTETICOS):
        d = inicio + timedelta(days=i)
        tendencia = 0.85 + 0.15 * i / DIAS_SINTETICOS
        valor = por_dia[d.weekday()] * TEMPORADA[d.month] * tendencia * rnd.lognormal(0, ruido)
        if rnd.random() < sin_venta:  # dias sin ventas (lluvia, feriado...)
            valor = 0.0
        f_sint.append(d)
        v_sint.append(round(float(valor), 2))
    return f_sint, v_sint


def _fila(fechas: list[date], valores: list[float], i: int, escala: float) -> list[float]:
    d = fechas[i]
    previos = valores[max(0, i - 28):i]
    return [
        *[1.0 if d.weekday() == w else 0.0 for w in range(7)],
        math.sin(2 * math.pi * d.month / 12), math.cos(2 * math.pi * d.month / 12),
        1.0 if d.day >= 25 else 0.0,
        valores[i - 1] / escala, valores[i - 7] / escala,
        float(np.mean(valores[i - 7:i])) / escala, float(np.mean(previos)) / escala,
        float(np.mean([valores[i - 7 * k] for k in range(1, 5)])) / escala,
    ]


def _matriz(fechas, valores, escala, desde: int, hasta: int):
    """Variables y objetivo. El modelo aprende la correccion sobre la linea
    base (lo que el promedio del mismo dia no capta: tendencia, temporada,
    dias fuertes): sin señal, queda igual que la base; con señal, la mejora."""
    filas = range(max(desde, 28), hasta)
    x = [_fila(fechas, valores, i, escala) for i in filas]
    y = [(valores[i] - _base(fechas, valores, i)) / escala for i in filas]
    return x, y


def _predecir(modelo, fechas, valores, escala, desde: int, hasta: int) -> np.ndarray:
    x, _ = _matriz(fechas, valores, escala, desde, hasta)
    base = np.array([_base(fechas, valores, i) for i in range(max(desde, 28), hasta)])
    return np.maximum(base + modelo.predict(np.array(x)) * escala, 0)


PESO_REAL = 3.0  # un dia real pesa como 3 sinteticos al entrenar


def _pesos(n_sinteticos: int, desde: int, hasta: int) -> list[float]:
    return [PESO_REAL if i >= n_sinteticos else 1.0 for i in range(max(desde, 28), hasta)]


def _base(fechas, valores, i) -> float:
    """Linea base: promedio del mismo dia de la semana en las 4 semanas previas."""
    return float(np.mean([valores[i - 7 * k] for k in range(1, 5)]))


def _metricas(real: np.ndarray, pred: np.ndarray) -> dict:
    total = real.sum()
    return {
        "mae": round(float(mean_absolute_error(real, pred)), 2),
        "rmse": round(float(math.sqrt(mean_squared_error(real, pred))), 2),
        "r2": round(float(r2_score(real, pred)), 4) if len(real) > 1 else None,
        "error_pct": round(float(np.abs(real - pred).sum() / total), 4) if total else None,
        # Error del total del periodo de prueba (lo que se planifica por semana).
        "error_total_pct": round(float(abs(pred.sum() - total) / total), 4) if total else None,
    }


def entrenar(series: list[dict], hoy: date) -> dict:
    """Entrena, evalua y pronostica. series: salida de series_reales()."""
    utiles = [s for s in series if len(s["valores"]) >= MIN_DIAS_REALES and sum(s["valores"]) > 0]
    if not utiles:
        raise ValueError(f"Faltan ventas para pronosticar: se necesitan al menos {MIN_DIAS_REALES} días de historia en una sucursal.")

    x_tr, y_tr, w_tr, pruebas = [], [], [], []
    for s in utiles:
        f_sint, v_sint = sinteticos(s["fechas"], s["valores"], semilla=1000 + s["sucursal_id"])
        fechas, valores = f_sint + s["fechas"], v_sint + s["valores"]
        escala = max(float(np.mean(s["valores"])), 1.0)
        corte = len(f_sint) + int(len(s["valores"]) * 0.8)
        x, y = _matriz(fechas, valores, escala, 28, corte)
        x_tr += x
        y_tr += y
        w_tr += _pesos(len(f_sint), 28, corte)
        s.update(_fechas=fechas, _valores=valores, _escala=escala, _corte=corte, _n_sint=len(f_sint))
        pruebas.append(s)

    candidatos = {
        "Ridge (regresión lineal)": Ridge(alpha=1.0),
        "Random Forest": RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=42),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, random_state=42),
    }
    comparacion = []
    reales_todos = np.array([v for s in pruebas for v in s["_valores"][s["_corte"]:]])
    base_pred = np.array([_base(s["_fechas"], s["_valores"], i) for s in pruebas for i in range(s["_corte"], len(s["_valores"]))])
    comparacion.append({"algoritmo": "Línea base (mismo día, 4 semanas)", **_metricas(reales_todos, base_pred)})
    modelos = {}
    for nombre, modelo in candidatos.items():
        modelo.fit(np.array(x_tr), np.array(y_tr), sample_weight=np.array(w_tr))
        pred = []
        for s in pruebas:
            pred += list(_predecir(modelo, s["_fechas"], s["_valores"], s["_escala"], s["_corte"], len(s["_valores"])))
        comparacion.append({"algoritmo": nombre, **_metricas(reales_todos, np.array(pred))})
        modelos[nombre] = modelo
    mejor = min((c for c in comparacion if c["algoritmo"] in modelos), key=lambda c: c["mae"])
    modelo = modelos[mejor["algoritmo"]]
    # Se reentrena con todo (sinteticos + 100 % real) para pronosticar.
    x_all, y_all, w_all = [], [], []
    for s in pruebas:
        x, y = _matriz(s["_fechas"], s["_valores"], s["_escala"], 28, len(s["_valores"]))
        x_all += x
        y_all += y
        w_all += _pesos(s["_n_sint"], 28, len(s["_valores"]))
    modelo.fit(np.array(x_all), np.array(y_all), sample_weight=np.array(w_all))

    importancia = getattr(modelo, "feature_importances_", None)
    if importancia is None:
        importancia = np.abs(modelo.coef_) / max(np.abs(modelo.coef_).sum(), 1e-9)
    variables = sorted(
        ({"variable": VARIABLES[i], "peso": round(float(p), 4)} for i, p in enumerate(importancia)), key=lambda v: -v["peso"]
    )

    # Pronostico de los proximos 28 dias, recursivo (cada dia usa los anteriores).
    semanas = [hoy + timedelta(days=1 + 7 * k) for k in range(DIAS_PRONOSTICO // 7)]
    etiquetas = [f"{d:%d/%m}–{d + timedelta(days=6):%d/%m}" for d in semanas]
    por_sucursal = []
    for s in pruebas:
        fechas, valores = list(s["_fechas"]), list(s["_valores"])
        # Desde el dia siguiente al ultimo con datos hasta 28 dias despues de hoy.
        while fechas[-1] < hoy + timedelta(days=DIAS_PRONOSTICO):
            fechas.append(fechas[-1] + timedelta(days=1))
            valores.append(0.0)
            i = len(valores) - 1
            valores[i] = float(_predecir(modelo, fechas, valores, s["_escala"], i, i + 1)[0])
        futuro = valores[-DIAS_PRONOSTICO:]
        reales = s["valores"]
        ultimas = [round(sum(reales[max(0, len(reales) - 7 * (k + 1)):len(reales) - 7 * k]), 2) for k in range(3, -1, -1)]
        por_sucursal.append({
            "sucursal_id": s["sucursal_id"], "sucursal": s["sucursal"],
            "semanas": [round(sum(futuro[7 * k:7 * k + 7]), 2) for k in range(len(semanas))],
            "ultimas_4_semanas": ultimas, "total_pronostico": round(sum(futuro), 2), "total_ultimas_4": round(sum(ultimas), 2),
        })
    total_sem = [round(sum(p["semanas"][k] for p in por_sucursal), 2) for k in range(len(semanas))]
    total_prev = [round(sum(p["ultimas_4_semanas"][k] for p in por_sucursal), 2) for k in range(4)]
    return {
        "algoritmo": mejor["algoritmo"],
        "metricas": {k: mejor[k] for k in ("mae", "rmse", "r2", "error_pct", "error_total_pct")},
        "comparacion": comparacion,
        "variables": variables,
        "n_reales": sum(len(s["valores"]) for s in pruebas),
        "n_sinteticos": DIAS_SINTETICOS * len(pruebas),
        "n_prueba": int(len(reales_todos)),
        "semanas": etiquetas,
        "pronostico_total": total_sem,
        "ultimas_4_semanas": total_prev,
        "sucursales": por_sucursal,
        "variacion": round((sum(total_sem) - sum(total_prev)) / sum(total_prev), 4) if sum(total_prev) else None,
        "datos_hasta": max(s["fechas"][-1] for s in pruebas).isoformat(),
    }


# ------------------------------------------------ versiones en modelo_ml


def hoy_bolivia(db: Session) -> date:
    return db.execute(text("SELECT (now() AT TIME ZONE 'America/La_Paz')::date")).scalar() or date.today()


def guardar(db: Session, empresa_id: int, usuario_id: int | None) -> dict:
    """Entrena con los datos de hoy y deja esta version como la activa de la tienda."""
    hoy = hoy_bolivia(db)
    r = entrenar(series_reales(db, empresa_id, hoy), hoy)
    version = (db.execute(
        text("SELECT coalesce(max(version), 0) FROM modelo_ml WHERE tarea = 'pronostico' AND empresa_id = :e"), {"e": empresa_id}
    ).scalar() or 0) + 1
    db.execute(text("UPDATE modelo_ml SET activo = false WHERE tarea = 'pronostico' AND empresa_id = :e"), {"e": empresa_id})
    nuevo = db.execute(
        text("""INSERT INTO modelo_ml (tarea, empresa_id, version, algoritmo, representacion, n_ejemplos, metricas, comparacion, entrenado_por)
                VALUES ('pronostico', :e, :v, :a, 'serie diaria', :n, CAST(:m AS JSONB), CAST(:c AS JSONB), :u) RETURNING id"""),
        {"e": empresa_id, "v": version, "a": r["algoritmo"], "n": r["n_reales"] + r["n_sinteticos"],
         "m": json.dumps({k: v for k, v in r.items() if k != "comparacion"}), "c": json.dumps(r["comparacion"]), "u": usuario_id},
    ).scalar()
    db.commit()
    return {**r, "id": nuevo, "version": version, "fecha": hoy.isoformat()}


def activo(db: Session, empresa_id: int) -> dict | None:
    """La version activa de la tienda (con su pronostico), o None."""
    fila = db.execute(
        text("""SELECT m.id, m.version, m.metricas, m.comparacion, m.entrenado_en, u.nombre AS entrenado_por
                FROM modelo_ml m LEFT JOIN usuario u ON u.id = m.entrenado_por
                WHERE m.tarea = 'pronostico' AND m.empresa_id = :e AND m.activo ORDER BY m.version DESC LIMIT 1"""),
        {"e": empresa_id},
    ).mappings().first()
    if fila is None:
        return None
    return {**fila["metricas"], "comparacion": fila["comparacion"], "id": fila["id"], "version": fila["version"],
            "entrenado_en": fila["entrenado_en"].isoformat() + "Z", "entrenado_por": fila["entrenado_por"],
            "fecha": fila["entrenado_en"].date().isoformat()}


def vigente(db: Session, empresa_id: int) -> dict:
    """El pronostico de la tienda: el de hoy, o se reentrena (una vez al dia,
    porque cada dia suma ventas nuevas)."""
    actual = activo(db, empresa_id)
    if actual is not None and actual["fecha"] >= hoy_bolivia(db).isoformat():
        return actual
    return guardar(db, empresa_id, None)
