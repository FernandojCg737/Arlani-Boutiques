"""Traduce las excepciones que levantan las funciones/PA y triggers de
Postgres (RAISE EXCEPTION 'codigo' USING DETAIL = ...) a errores HTTP con un
mensaje para el usuario."""

from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError

MENSAJES: dict[str, tuple[int, str]] = {
    # Empresas (CU09)
    "empresa_nombre_invalido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "El nombre de la empresa es muy corto."),
    "subdominio_en_uso": (status.HTTP_409_CONFLICT, "Esa dirección ya la usa otra empresa."),
    "empresa_no_encontrada": (status.HTTP_404_NOT_FOUND, "Empresa no encontrada."),
    "empresa_con_sucursales": (
        status.HTTP_409_CONFLICT,
        "No se puede eliminar: la empresa tiene sucursales. Suspéndela en su lugar.",
    ),
    "empresa_con_usuarios": (
        status.HTTP_409_CONFLICT,
        "No se puede eliminar: la empresa tiene personal registrado. Suspéndela en su lugar.",
    ),
    "empresa_suspendida": (status.HTTP_409_CONFLICT, "La empresa está suspendida: no puede habilitar sucursales."),
    "sucursal_de_otra_empresa": (
        status.HTTP_409_CONFLICT,
        "Esa sucursal es de otra empresa: el personal solo puede trabajar en sucursales de su empresa.",
    ),
    "rol_no_es_de_tienda": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Ese rol no tiene permisos por empresa."),
    "estado_invalido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Estado no válido."),
    # Planes y límites (CU10)
    "plan_no_encontrado": (status.HTTP_404_NOT_FOUND, "Plan no encontrado."),
    "periodo_invalido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Periodo de facturación no válido."),
    "plan_no_cubre_sucursales": (status.HTTP_409_CONFLICT, "El plan elegido no cubre las sucursales de la empresa."),
    "plan_limite_menor_al_uso": (
        status.HTTP_409_CONFLICT,
        "No se puede bajar el límite: hay empresas que ya lo superan.",
    ),
    "plan_valores_invalidos": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Precio o límite de sucursales no válidos."),
    "limite_sucursales_plan": (
        status.HTTP_409_CONFLICT,
        "Se alcanzó el límite de sucursales activas del plan. Cambia a un plan superior para habilitar más.",
    ),
}


def codigo_pg(err: DBAPIError) -> tuple[str, str | None]:
    """(mensaje primario, detalle) de la excepcion de Postgres."""
    diag = getattr(err.orig, "diag", None)
    if diag is not None:
        return (diag.message_primary or "", diag.message_detail)
    return (str(err.orig).splitlines()[0] if err.orig else "", None)


def http_desde_pg(err: DBAPIError) -> HTTPException | None:
    """HTTPException para un codigo conocido, o None si es otro error."""
    codigo, detalle = codigo_pg(err)
    if codigo not in MENSAJES:
        return None
    estado, mensaje = MENSAJES[codigo]
    return HTTPException(estado, f"{mensaje} {detalle}".strip() if detalle else mensaje)
