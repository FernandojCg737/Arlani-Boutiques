import json

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:4200", "http://127.0.0.1:4200"]
DEFAULT_SECRET_KEY = "change-this-secret-key-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "AtelierAranier API"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql://atelier_user:atelier_pass@db:5432/atelieraranier"

    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # str (no list[str]): asi pydantic-settings no intenta json.loads() el
    # valor crudo de la env var antes de que lleguemos a parsearlo nosotros.
    # Tolerante con como se escriba en paneles como Render: JSON
    # ("[\"a\",\"b\"]"), texto separado por comas ("a,b"), o vacio (default).
    BACKEND_CORS_ORIGINS: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        value = self.BACKEND_CORS_ORIGINS.strip()
        if not value:
            return DEFAULT_CORS_ORIGINS
        if value.startswith("["):
            return json.loads(value)
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    GOOGLE_CLIENT_ID: str = ""

    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "productos"

    # CU09: probador de realidad aumentada (Decart lucy-vton). La key
    # permanente vive solo en el backend; el frontend solo recibe tokens
    # de cliente de corta duracion (10 min) generados a partir de ella.
    DECART_API_KEY: str = ""

    # CU11: pasarela de pago para la compra digital (PayPal/tarjeta). El QR
    # no usa pasarela -- se verifica a mano, ver Pago.comprobante_url.
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_MODE: str = "sandbox"

    # CU18: redacta la razon personalizada de cada recomendacion (el ranking
    # en si lo calcula el motor de reglas en SQL, no el modelo). Si esta
    # vacia, se usa una razon generica de respaldo por origen.
    GEMINI_API_KEY: str = ""

    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@atelieraranier.com"
    SMTP_USE_TLS: bool = False
    # Produccion (Render): el plan gratis bloquea SMTP, asi que el correo sale
    # de la cuenta de Gmail por un Google Apps Script publicado como app web
    # (HTTPS). El token es la clave compartida que el script exige.
    # URL vacia = SMTP (desarrollo local).
    GMAIL_SCRIPT_URL: str = ""
    GMAIL_SCRIPT_TOKEN: str = ""

    @property
    def es_produccion(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in ("production", "produccion", "prod")


settings = Settings()

# Con la clave por defecto cualquiera puede firmar JWT validos (es publica en
# el repo). En desarrollo se tolera; en produccion el backend no arranca.
if settings.es_produccion and (settings.SECRET_KEY == DEFAULT_SECRET_KEY or len(settings.SECRET_KEY) < 32):
    raise RuntimeError(
        "SECRET_KEY no configurada (o demasiado corta) en produccion. "
        "Defini una clave aleatoria de al menos 32 caracteres en las variables de entorno."
    )
