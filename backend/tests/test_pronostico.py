"""CU18: pronostico de ventas (aprendizaje supervisado, regresion).

Unitarias con series controladas (sin base) y una de integracion del
endpoint del SuperAdministrador (dentro de la transaccion de prueba)."""

from datetime import date, timedelta

import numpy as np
import pytest

from app.ml import pronostico

HOY = date(2026, 11, 7)


def _serie(dias: int, sucursal_id: int = 1, base: float = 1000.0, semilla: int = 0) -> dict:
    """Ventas diarias con patron semanal claro (fin de semana fuerte) y ruido."""
    rnd = np.random.default_rng(semilla)
    fechas = [HOY - timedelta(days=dias - 1 - i) for i in range(dias)]
    patron = [0.7, 0.8, 0.8, 0.9, 1.1, 1.6, 1.4]
    valores = [round(float(base * patron[d.weekday()] * rnd.normal(1, 0.08)), 2) for d in fechas]
    return {"sucursal_id": sucursal_id, "sucursal": f"Sucursal {sucursal_id}", "fechas": fechas, "valores": valores}


def test_compara_modelos_contra_la_linea_base_y_elige_el_de_menor_error():
    r = pronostico.entrenar([_serie(90, 1), _serie(70, 2, base=400, semilla=1)], HOY)
    nombres = [c["algoritmo"] for c in r["comparacion"]]
    assert nombres[0].startswith("Línea base") and len(nombres) == 4
    modelos = [c for c in r["comparacion"] if not c["algoritmo"].startswith("Línea base")]
    assert r["algoritmo"] == min(modelos, key=lambda c: c["mae"])["algoritmo"]
    assert set(r["metricas"]) == {"mae", "rmse", "r2", "error_pct", "error_total_pct"}


@pytest.mark.parametrize("semilla", [3, 4, 5])
def test_compite_con_la_linea_base_y_acierta_el_total(semilla):
    # El modelo corrige a la linea base: en una serie con patron semanal
    # limpio no puede quedar muy por detras de ella, y el total del periodo
    # de prueba se acierta con poco error.
    r = pronostico.entrenar([_serie(120, 1, semilla=semilla)], HOY)
    base = r["comparacion"][0]["mae"]
    assert r["metricas"]["mae"] <= base * 1.15
    assert r["metricas"]["error_total_pct"] < 0.05


def test_pronostica_4_semanas_por_sucursal_sin_valores_negativos():
    r = pronostico.entrenar([_serie(60, 1), _serie(45, 2, base=300)], HOY)
    assert len(r["semanas"]) == len(r["pronostico_total"]) == 4
    assert {s["sucursal_id"] for s in r["sucursales"]} == {1, 2}
    for s in r["sucursales"]:
        assert len(s["semanas"]) == 4 and all(v >= 0 for v in s["semanas"])
    assert r["pronostico_total"] == [round(sum(s["semanas"][k] for s in r["sucursales"]), 2) for k in range(4)]


def test_entrena_con_datos_sinteticos_y_evalua_solo_con_reales():
    r = pronostico.entrenar([_serie(50, 1)], HOY)
    assert r["n_sinteticos"] == pronostico.DIAS_SINTETICOS
    assert r["n_reales"] == 50
    assert r["n_prueba"] == 50 - int(50 * 0.8)


def test_los_datos_sinteticos_siguen_el_patron_de_la_sucursal():
    s = _serie(84, 1)
    fechas, valores = pronostico.sinteticos(s["fechas"], s["valores"], semilla=7)
    assert len(valores) == pronostico.DIAS_SINTETICOS and fechas[-1] == s["fechas"][0] - timedelta(days=1)
    sabados = np.mean([v for f, v in zip(fechas, valores) if f.weekday() == 5])
    lunes = np.mean([v for f, v in zip(fechas, valores) if f.weekday() == 0])
    assert sabados > lunes


def test_sin_historia_suficiente_avisa_en_vez_de_inventar():
    with pytest.raises(ValueError, match="Faltan ventas"):
        pronostico.entrenar([_serie(10, 1)], HOY)


def test_endpoint_del_superadmin_entrena_y_guarda_la_version(prueba):
    empresa = prueba.valor(
        """SELECT s.empresa_id FROM venta v JOIN sucursal s ON s.id = v.sucursal_id WHERE v.estado = 'pagada'
           GROUP BY s.empresa_id HAVING count(DISTINCT (v.fecha)::date) >= 25 ORDER BY count(*) DESC LIMIT 1"""
    )
    if empresa is None:
        pytest.skip("no hay una tienda con suficientes ventas")
    h = prueba.superadmin()
    r = prueba.client.post("/api/v1/modelos-ml/pronostico/entrenar", params={"empresa_id": empresa}, headers=h)
    assert r.status_code == 200, r.text
    version = r.json()["version"]
    r = prueba.client.get("/api/v1/modelos-ml/pronostico", params={"empresa_id": empresa}, headers=h)
    assert r.status_code == 200 and r.json()["version"] == version
    assert prueba.valor(
        "SELECT count(*) FROM modelo_ml WHERE tarea = 'pronostico' AND empresa_id = :e AND activo", e=empresa
    ) == 1
