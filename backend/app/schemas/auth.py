from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import validate_password_strength


class ClienteRegister(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    telefono: str | None = Field(default=None, max_length=30)

    @field_validator("password")
    @classmethod
    def _check_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class ClienteLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthPayload(BaseModel):
    credential: str


class UsuarioOut(BaseModel):
    id: int
    nombre: str
    apellidos: str | None = None
    foto_url: str | None = None
    email: EmailStr
    telefono: str | None = None
    direccion: str | None = None
    tipo: str
    rol: str | None = None
    permisos: list[str] = []
    sucursal_id: int | None = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut


class MessageResponse(BaseModel):
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResetTokenResponse(BaseModel):
    reset_token: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _check_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginWithResetTokenRequest(BaseModel):
    reset_token: str
