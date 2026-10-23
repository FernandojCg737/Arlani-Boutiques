from pydantic import BaseModel, Field

TIPOS = r"^(paypal|qr|transferencia|otro)$"


class MetodoPagoIn(BaseModel):
    tipo: str = Field(pattern=TIPOS)
    nombre: str = Field(min_length=2, max_length=80)
    instrucciones: str | None = Field(default=None, max_length=1000)
    activo: bool = True
    orden: int = Field(default=0, ge=0, le=99)
    # PayPal de la tienda. Al editar, un Secret vacio deja el que ya estaba.
    paypal_client_id: str | None = Field(default=None, max_length=200)
    paypal_secret: str | None = Field(default=None, max_length=200)
    paypal_modo: str | None = Field(default=None, pattern=r"^(sandbox|live)$")
    paypal_email: str | None = Field(default=None, max_length=150)
    # QR: imagen nueva como data URL (si no se manda, queda la anterior).
    qr_imagen: str | None = Field(default=None, max_length=7_500_000)
    banco: str | None = Field(default=None, max_length=80)
    numero_cuenta: str | None = Field(default=None, max_length=40)
    tipo_cuenta: str | None = Field(default=None, max_length=20)
    titular: str | None = Field(default=None, max_length=120)
    documento_titular: str | None = Field(default=None, max_length=30)


class MetodoPagoPublicoOut(BaseModel):
    # Lo que ve el cliente en el checkout (nunca el Secret de PayPal).
    id: int
    tipo: str
    nombre: str
    instrucciones: str | None
    paypal_client_id: str | None
    qr_url: str | None
    banco: str | None
    numero_cuenta: str | None
    tipo_cuenta: str | None
    titular: str | None
    documento_titular: str | None
    # PayPal se confirma solo; el resto necesita comprobante y aprobacion.
    requiere_comprobante: bool


class MetodoPagoOut(MetodoPagoPublicoOut):
    activo: bool
    orden: int
    paypal_modo: str | None
    paypal_email: str | None
    # Solo los ultimos 4 caracteres, para saber cual esta cargado.
    paypal_secret_mascara: str | None


class FacturacionIO(BaseModel):
    # Datos que salen en las facturas de la tienda.
    razon_social: str | None = Field(default=None, max_length=150)
    nit: str | None = Field(default=None, max_length=20, pattern=r"^[0-9A-Za-z-]*$")
    direccion_fiscal: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=30)
    email_contacto: str | None = Field(default=None, max_length=150)
