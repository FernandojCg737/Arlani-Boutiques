from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_password_strength


class PerfilUpdate(BaseModel):
    # Nombres (o el nombre completo si no se mandan apellidos aparte).
    nombre: str = Field(min_length=2, max_length=150)
    apellidos: str | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=30)
    direccion: str | None = Field(default=None, max_length=255)


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str = Field(min_length=8, max_length=72)

    @field_validator("password_nueva")
    @classmethod
    def _check_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)
