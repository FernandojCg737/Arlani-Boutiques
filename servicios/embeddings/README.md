# Arlani Embeddings

Servicio del CU18 de Arlani Boutiques: corre el modelo de lenguaje preentrenado
[paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
(384 dimensiones, entiende español) fuera del backend, como un servicio web aparte en Render (Docker, plan gratis).

- `GET /salud`: estado del servicio.
- `POST /embed` con `{"textos": ["..."]}` y la cabecera `X-Clave`: un vector normalizado por frase.

Variable necesaria: `CLAVE_API` (el mismo valor que `ML_EMBEDDINGS_CLAVE` en el backend).
El backend lo usa con `ML_EMBEDDINGS_URL` = la URL de este servicio.
