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
    "plan_valores_invalidos": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Precio, límite de sucursales o comisión no válidos (la comisión va de 0 % a 30 %).",
    ),
    "prueba_no_renovable": (
        status.HTTP_409_CONFLICT,
        "El plan de prueba no se puede volver a contratar: elige el plan Básico o Profesional.",
    ),
    "pago_ya_usado": (status.HTTP_409_CONFLICT, "Ese pago de PayPal ya se usó para otra suscripción."),
    # Metodos de pago de cada tienda
    "metodo_pago_invalido": (
        status.HTTP_409_CONFLICT,
        "Ese método de pago no está disponible para esta tienda. Elige otro.",
    ),
    "tienda_no_operativa": (status.HTTP_409_CONFLICT, "Esta tienda no está recibiendo pedidos por ahora."),
    "comprobante_requerido": (status.HTTP_400_BAD_REQUEST, "Sube la foto de tu comprobante de pago."),
    "pago_no_verificable": (status.HTTP_409_CONFLICT, "Este pago ya fue revisado o no tiene comprobante que revisar."),
    "motivo_rechazo_requerido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Escribe el motivo del rechazo."),
    # Cambio de prendas
    "cambio_venta_invalida": (status.HTTP_409_CONFLICT, "Esa compra no admite cambios (debe estar pagada y ser tuya)."),
    "cambio_fuera_de_plazo": (
        status.HTTP_409_CONFLICT,
        "Pasaron más de 24 horas desde tu compra: ya no se puede cambiar.",
    ),
    "cambio_cantidad_invalida": (
        status.HTTP_409_CONFLICT,
        "No puedes cambiar esa cantidad: revisa cuántas prendas te quedan por cambiar.",
    ),
    "prenda_ya_solicitada": (
        status.HTTP_409_CONFLICT,
        "Esa prenda ya tuvo una solicitud de cambio o devolución: solo se permite una.",
    ),
    "cambio_sucursal_invalida": (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Elige una sucursal de la misma tienda para recoger tu prenda.",
    ),
    "cambio_misma_prenda": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige una prenda distinta a la que compraste."),
    "cambio_no_pendiente": (status.HTTP_409_CONFLICT, "Este cambio ya fue atendido."),
    "cambio_sin_pago_pendiente": (status.HTTP_409_CONFLICT, "Este cambio no tiene una diferencia por pagar."),
    "destino_invalido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "Elige qué hacer con la prenda devuelta."),
    # Caja (CU16)
    "caja_cerrada": (
        status.HTTP_409_CONFLICT,
        "La caja de esta sucursal está cerrada: ábrela en Arqueo y cierre de caja para poder cobrar en mostrador.",
    ),
    "caja_ya_abierta": (status.HTTP_409_CONFLICT, "Esta sucursal ya tiene una caja abierta."),
    "caja_no_abierta": (status.HTTP_409_CONFLICT, "Esa caja ya está cerrada."),
    "caja_no_encontrada": (status.HTTP_404_NOT_FOUND, "Caja no encontrada."),
    "caja_monto_invalido": (status.HTTP_422_UNPROCESSABLE_ENTITY, "El monto no puede ser negativo."),
    "sucursal_no_encontrada": (status.HTTP_404_NOT_FOUND, "Sucursal no encontrada."),
    # "Pagar todo": liquidacion a cada tienda
    "liquidacion_invalida": (status.HTTP_409_CONFLICT, "No se pudo liquidar la compra a una de las tiendas."),
    "tienda_sin_paypal_email": (
        status.HTTP_409_CONFLICT,
        "Una de las tiendas de tu carrito no recibe pagos con PayPal: págala por separado.",
    ),
    # Estado de cuenta de la tienda (comisiones de Arlani)
    "saldo_sin_deuda": (status.HTTP_409_CONFLICT, "No tienes comisiones pendientes de pago."),
    "saldo_cambio": (
        status.HTTP_409_CONFLICT,
        "Tu saldo cambió mientras pagabas (entró una venta nueva). Vuelve a intentarlo.",
    ),
    # Compra de la suscripcion (/empezar)
    "correo_en_uso": (
        status.HTTP_409_CONFLICT,
        "Ese correo ya tiene una cuenta en Arlani. Usa otro correo para el administrador de tu boutique.",
    ),
    "pago_requerido": (status.HTTP_402_PAYMENT_REQUIRED, "Este plan requiere el pago de la suscripción."),
    "monto_pago_incorrecto": (status.HTTP_409_CONFLICT, "El monto pagado no coincide con el precio del plan."),
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
