"""Modelo de lenguaje preentrenado (descargado) para el CU18.

paraphrase-multilingual-MiniLM-L12-v2 (sentence-transformers, 384
dimensiones, entiende espanol) convierte una frase en un vector que capta su
SIGNIFICADO: "me sale caro" y "es muy costoso" quedan cerca aunque no
compartan palabras, cosa que BoW y TF-IDF no ven. Corre con onnxruntime, sin
PyTorch: la version cuantizada a int8 (Xenova) y el tokenizador SentencePiece
original, unos 230 MB en memoria.

Dos formas de usarlo (si no hay ninguna, el sistema usa solo BoW / TF-IDF):
- Remoto (ML_EMBEDDINGS_URL + ML_EMBEDDINGS_CLAVE): el modelo corre en un
  servicio web aparte (servicios/embeddings, otro servicio gratis de
  Render) y el backend le pide los vectores por HTTP. Asi el servidor del
  backend no carga el modelo.
- Local (ML_EMBEDDINGS=1): el modelo corre dentro del backend, con el mismo
  codigo que el servicio (los vectores son identicos).

Si el servicio remoto no responde (por ejemplo, se durmio), se lanza
NoDisponible y quien lo usa sigue con su respaldo sin embeddings.
"""

import contextlib
import contextvars
import os
import threading
import time

import numpy as np
import requests
from sklearn.base import BaseEstimator, TransformerMixin

MODELO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CUANTIZADO = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"
NOMBRE = "Embeddings MiniLM"
LOTE = 64
MAX_TOKENS = 128

_modelo = None
_cache: dict[str, np.ndarray] = {}
_lock = threading.Lock()
_disponible: tuple[float, bool] | None = None
# Esperar al servicio: poco al responder un chat, mucho al entrenar.
_espera = contextvars.ContextVar("espera_embeddings", default=6.0)


class NoDisponible(RuntimeError):
    """El servicio de embeddings no respondio."""


def _url() -> str:
    return os.getenv("ML_EMBEDDINGS_URL", "").rstrip("/")


def modo() -> str:
    if _url():
        return "remoto"
    if os.getenv("ML_EMBEDDINGS", "0").lower() in ("1", "true", "si"):
        try:
            import onnxruntime  # noqa: F401
            import sentencepiece  # noqa: F401
        except ImportError:
            return "apagado"
        return "local"
    return "apagado"


def habilitado() -> bool:
    return modo() != "apagado"


@contextlib.contextmanager
def para_entrenar():
    """Al entrenar se espera mas al servicio (puede estar despertando)."""
    token = _espera.set(90.0)
    try:
        yield
    finally:
        _espera.reset(token)


def disponible() -> bool:
    """Si se puede usar ahora. En remoto pregunta al servicio (lo despierta
    si dormia) y recuerda la respuesta un par de minutos."""
    global _disponible
    if modo() == "local":
        return True
    if modo() == "apagado":
        return False
    if _disponible and time.time() - _disponible[0] < 120:
        return _disponible[1]
    try:
        r = requests.get(_url() + "/salud", timeout=_espera.get())
        ok = r.ok and r.json().get("ok") is True
    except (requests.RequestException, ValueError):
        ok = False
    _disponible = (time.time(), ok)
    return ok


class _Local:
    """El mismo modelo que corre el servicio (servicios/embeddings/app.py)."""

    def __init__(self, carpeta: str):
        import onnxruntime as ort
        import sentencepiece as spm
        from huggingface_hub import hf_hub_download

        onnx = hf_hub_download(CUANTIZADO, "onnx/model_quantized.onnx", cache_dir=carpeta)
        tokens = hf_hub_download(MODELO, "sentencepiece.bpe.model", cache_dir=carpeta)
        opciones = ort.SessionOptions()
        opciones.enable_cpu_mem_arena = False
        opciones.enable_mem_pattern = False
        opciones.intra_op_num_threads = 1
        opciones.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.sesion = ort.InferenceSession(onnx, opciones, providers=["CPUExecutionProvider"])
        self.sp = spm.SentencePieceProcessor(model_file=tokens)

    def _ids(self, texto: str) -> list[int]:
        # Tokenizador de XLM-R: ids de SentencePiece corridos en 1; <s>=0, <pad>=1, </s>=2, <unk>=3.
        piezas = [(i + 1 if i != 0 else 3) for i in self.sp.encode(texto)][: MAX_TOKENS - 2]
        return [0] + piezas + [2]

    def vectores(self, textos: list[str]) -> list[np.ndarray]:
        salida: list[np.ndarray] = []
        for i in range(0, len(textos), 16):
            lote = [self._ids(t[:2000]) for t in textos[i:i + 16]]
            largo = max(map(len, lote))
            ids = np.array([x + [1] * (largo - len(x)) for x in lote], dtype=np.int64)
            mascara = (ids != 1).astype(np.int64)
            ocultos = self.sesion.run(None, {"input_ids": ids, "attention_mask": mascara, "token_type_ids": np.zeros_like(ids)})[0]
            salida += list((ocultos * mascara[..., None]).sum(1) / mascara.sum(1, keepdims=True))
        return salida


def _cargar_local() -> _Local:
    global _modelo
    with _lock:
        if _modelo is None:
            _modelo = _Local(os.getenv("ML_MODELOS_DIR", os.path.expanduser("~/.cache/arlani-modelos")))
    return _modelo


def _remoto(textos: list[str]) -> list[np.ndarray]:
    global _disponible
    # Si acaba de fallar, no se hace esperar a cada chat: se reintenta al minuto.
    if _disponible and not _disponible[1] and time.time() - _disponible[0] < 60:
        raise NoDisponible("El servicio de embeddings no respondió hace un momento.")
    salida: list[np.ndarray] = []
    for i in range(0, len(textos), LOTE):
        try:
            r = requests.post(
                _url() + "/embed", json={"textos": textos[i:i + LOTE]},
                headers={"X-Clave": os.getenv("ML_EMBEDDINGS_CLAVE", "")}, timeout=_espera.get(),
            )
            r.raise_for_status()
            # Un Space dormido puede contestar una pagina HTML en vez de los vectores.
            salida += [np.asarray(v, dtype=np.float32) for v in r.json()["vectores"]]
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            _disponible = (time.time(), False)
            raise NoDisponible(f"El servicio de embeddings no respondió: {exc}") from exc
    _disponible = (time.time(), True)
    return salida


def vectores(textos: list[str]) -> np.ndarray:
    """Un vector normalizado por texto (se recuerdan los ya calculados)."""
    if len(_cache) > 20_000:
        _cache.clear()
    faltan = list(dict.fromkeys(t for t in textos if t not in _cache))
    if faltan:
        nuevos = _remoto(faltan) if modo() == "remoto" else _cargar_local().vectores(faltan)
        for t, v in zip(faltan, nuevos):
            _cache[t] = (v / (np.linalg.norm(v) or 1.0)).astype(np.float32)
    return np.vstack([_cache[t] for t in textos]) if textos else np.zeros((0, 384), dtype=np.float32)


class Embeddings(BaseEstimator, TransformerMixin):
    """Paso 5 del pipeline con el modelo preentrenado (en vez de BoW/TF-IDF).
    No guarda el modelo dentro: al usarlo lo pide al servicio o lo carga."""

    def fit(self, x, y=None):
        return self

    def transform(self, x):
        return vectores([str(t) for t in x])
