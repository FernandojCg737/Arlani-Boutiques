"""Exporta los modelos activos del CU18 a archivos y, si se pide, los publica
en un repositorio de modelos de Hugging Face (evidencia de lo entrenado).

    python -m app.ml.publicar --carpeta /tmp/arlani-modelos
    python -m app.ml.publicar --carpeta /tmp/arlani-modelos --repo <usuario>/arlani-modelos

Para publicar hace falta la variable HF_TOKEN (un token de Hugging Face con
permiso de escritura). El sistema NO lee los modelos de ahi: los usa de la
tabla modelo_ml; esto es solo para mostrarlos.
"""

import argparse
import json
import os

from sqlalchemy import text

from app.db.session import SessionLocal

TAREAS = {"reportes": "Intención de reportes por voz o texto (CU17)", "chatbot": "Intención del chatbot",
          "recomendaciones": "Recomendador de prendas", "segmentos": "Segmentación de clientes (K-Means)"}


def exportar(carpeta: str) -> list[dict]:
    os.makedirs(carpeta, exist_ok=True)
    resumen = []
    with SessionLocal() as db:
        filas = db.execute(text(
            """SELECT m.tarea, m.empresa_id, e.nombre AS tienda, m.version, m.algoritmo, m.representacion, m.n_ejemplos,
                      m.metricas, m.comparacion, m.artefacto, m.entrenado_en
               FROM modelo_ml m LEFT JOIN empresa e ON e.id = m.empresa_id
               WHERE m.activo ORDER BY m.tarea, m.empresa_id NULLS FIRST""")).all()
        for f in filas:
            nombre = f"{f.tarea}-{'general' if f.empresa_id is None else f'tienda{f.empresa_id}'}-v{f.version}"
            if f.artefacto:
                with open(os.path.join(carpeta, nombre + ".pkl"), "wb") as a:
                    a.write(bytes(f.artefacto))
            resumen.append({
                "archivo": nombre + ".pkl" if f.artefacto else None, "tarea": f.tarea, "tienda": f.tienda or "general",
                "version": f.version, "algoritmo": f.algoritmo, "representacion": f.representacion, "ejemplos": f.n_ejemplos,
                "entrenado_en": f.entrenado_en.isoformat(),
                "metricas": {k: v for k, v in (f.metricas or {}).items() if k not in ("matriz_confusion", "por_clase")},
                "comparacion": f.comparacion,
            })
    with open(os.path.join(carpeta, "metricas.json"), "w", encoding="utf-8") as a:
        json.dump(resumen, a, ensure_ascii=False, indent=2, default=str)
    with open(os.path.join(carpeta, "README.md"), "w", encoding="utf-8") as a:
        a.write(_ficha(resumen))
    return resumen


def _metrica(m: dict) -> str:
    if "acierto" in m:
        return f"acierto@{m.get('k')} {m['acierto']:.1%} (más vendidas {m['referencia']['acierto']:.1%}, azar {m['azar']:.1%})"
    if "f1" in m:
        para = f", F1 paráfrasis {m['f1_parafrasis']:.1%}" if "f1_parafrasis" in m else ""
        return f"F1 {m['f1']:.1%}{para}, F1 validación cruzada {m.get('f1_cv', 0):.1%}"
    if "silueta" in m:
        return f"k = {m.get('k')}, silueta {m['silueta']:.2f}"
    return ""


def _ficha(resumen: list[dict]) -> str:
    filas = "\n".join(
        f"| {TAREAS.get(r['tarea'], r['tarea'])} | {r['tienda']} | v{r['version']} | {r['representacion'] or '—'} + {r['algoritmo']} "
        f"| {_metrica(r['metricas'])} | {r['archivo'] or '—'} |" for r in resumen)
    return f"""---
language: es
library_name: scikit-learn
tags: [text-classification, recommender, scikit-learn, spanish]
---

# Modelos de Arlani Boutiques (CU18)

Modelos entrenados por la plataforma Arlani Boutiques (SaaS para boutiques de Bolivia).

**Pipeline de texto:** 1) normalización, 2) tokenización, 3) stopwords, 4) lematización (simplemma +
diccionario propio), 5) BoW, TF-IDF o embeddings del modelo preentrenado
[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2),
6) modelo: Regresión logística, Naive Bayes, KNN o Árbol de decisión. Se prueban todas las combinaciones y se
elige la mejor por el promedio del F1 de prueba y el F1 de paráfrasis (frases escritas a mano que no se usan
para entrenar).

**Recomendador:** híbrido de contenido (TF-IDF o embeddings) y filtrado colaborativo KNN ítem-ítem, evaluado
con las ventas más nuevas (acierto en las primeras K sugerencias y MRR).

| Modelo | Tienda | Versión | Representación + algoritmo | Evaluación | Archivo |
|---|---|---|---|---|---|
{filas}

`metricas.json` tiene la comparación completa de cada modelo. Los `.pkl` son objetos de scikit-learn guardados
con pickle; para cargarlos hace falta el código del backend de Arlani (`app.ml`). Abre solo archivos `.pkl` de
fuentes en las que confíes.
"""


def publicar(carpeta: str, repo: str) -> str:
    from huggingface_hub import HfApi

    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("Falta la variable HF_TOKEN (token de Hugging Face con permiso de escritura).")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="model", exist_ok=True)
    api.upload_folder(folder_path=carpeta, repo_id=repo, repo_type="model", commit_message="Modelos activos de Arlani Boutiques")
    return f"https://huggingface.co/{repo}"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Exporta (y publica) los modelos activos del CU18.")
    p.add_argument("--carpeta", default="/tmp/arlani-modelos")
    p.add_argument("--repo", help="usuario/nombre del repositorio de modelos en Hugging Face")
    args = p.parse_args()
    for r in exportar(args.carpeta):
        print(f"{r['tarea']:<16} {r['tienda']:<18} v{r['version']:<3} {r['archivo'] or '(sin archivo)'}")
    print("Exportado en", args.carpeta)
    if args.repo:
        print("Publicado en", publicar(args.carpeta, args.repo))
