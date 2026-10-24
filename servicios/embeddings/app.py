"""Servicio de embeddings de Arlani Boutiques (un servicio web aparte en Render).

Corre el modelo de lenguaje preentrenado paraphrase-multilingual-MiniLM-L12-v2
fuera del backend: el backend le manda frases y recibe un vector de 384
numeros por frase (su significado).

Para que entre en los 512 MB de un servicio gratis de Render se usa:
- la version cuantizada a int8 del modelo (Xenova, ~118 MB en vez de ~470), y
- el tokenizador SentencePiece original (~5 MB): da los mismos tokens que el
  tokenizer.json, que solo al cargarse ocupa unos 260 MB.
Asi el servicio usa unos 270 MB.

POST /embed   {"textos": ["frase 1", ...]}   cabecera X-Clave: <CLAVE_API>
GET  /salud   estado del servicio (sirve para despertarlo)
"""

import os
import secrets
import threading

import numpy as np
import onnxruntime as ort
import sentencepiece as spm
from fastapi import FastAPI, Header, HTTPException
from huggingface_hub import hf_hub_download
from pydantic import BaseModel, Field

ORIGINAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CUANTIZADO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
CARPETA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos")
MAX_TOKENS = 128
LOTE = 16


class Modelo:
    def __init__(self, carpeta: str):
        onnx = hf_hub_download(CUANTIZADO, "onnx/model_quantized.onnx", cache_dir=carpeta)
        tokens = hf_hub_download(ORIGINAL, "sentencepiece.bpe.model", cache_dir=carpeta)
        opciones = ort.SessionOptions()
        # Sin reservar memoria de mas (el "arena" de onnxruntime).
        opciones.enable_cpu_mem_arena = False
        opciones.enable_mem_pattern = False
        opciones.intra_op_num_threads = 1
        opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.sesion = ort.InferenceSession(onnx, opciones, providers=["CPUExecutionProvider"])
        self.sp = spm.SentencePieceProcessor(model_file=tokens)

    def _ids(self, texto: str) -> list[int]:
        # Tokenizador de XLM-R: los ids de SentencePiece van corridos en 1;
        # <s>=0, <pad>=1, </s>=2, <unk>=3.
        piezas = [(i + 1 if i != 0 else 3) for i in self.sp.encode(texto)][: MAX_TOKENS - 2]
        return [0] + piezas + [2]

    def vectores(self, textos: list[str]) -> np.ndarray:
        salida = []
        for i in range(0, len(textos), LOTE):
            lote = [self._ids(t) for t in textos[i:i + LOTE]]
            largo = max(map(len, lote))
            ids = np.array([x + [1] * (largo - len(x)) for x in lote], dtype=np.int64)
            mascara = (ids != 1).astype(np.int64)
            ocultos = self.sesion.run(None, {"input_ids": ids, "attention_mask": mascara, "token_type_ids": np.zeros_like(ids)})[0]
            # Promedio de los tokens (mean pooling) y largo 1.
            v = (ocultos * mascara[..., None]).sum(1) / mascara.sum(1, keepdims=True)
            salida.append(v / np.linalg.norm(v, axis=1, keepdims=True))
        return np.vstack(salida).astype(np.float32)


_modelo: Modelo | None = None
_lock = threading.Lock()


def cargar() -> Modelo:
    global _modelo
    with _lock:
        if _modelo is None:
            _modelo = Modelo(CARPETA)
    return _modelo


app = FastAPI(title="Arlani Embeddings", docs_url=None, redoc_url=None)


class PedidoIn(BaseModel):
    textos: list[str] = Field(min_length=1, max_length=128)


@app.on_event("startup")
def al_arrancar() -> None:
    cargar()


@app.get("/")
@app.get("/salud")
def salud() -> dict:
    return {"ok": True, "modelo": ORIGINAL, "variante": "int8 (Xenova)", "dimensiones": 384}


@app.post("/embed")
def embed(pedido: PedidoIn, x_clave: str | None = Header(default=None)) -> dict:
    clave = os.getenv("CLAVE_API", "")
    if not clave:
        raise HTTPException(503, "Falta configurar la variable CLAVE_API del servicio.")
    if not x_clave or not secrets.compare_digest(x_clave, clave):
        raise HTTPException(401, "Clave incorrecta.")
    vectores = cargar().vectores([t[:2000] for t in pedido.textos])
    return {"modelo": ORIGINAL, "dimensiones": 384, "vectores": vectores.round(6).tolist()}
