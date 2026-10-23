from fastapi import APIRouter

from app.api.v1.endpoints.ar_uso import router as ar_uso_router
from app.api.v1.endpoints.asistencia import router as asistencia_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.bitacora import router as bitacora_router
from app.api.v1.endpoints.carrito import admin_router as carritos_admin_router
from app.api.v1.endpoints.carrito import router as carrito_router
from app.api.v1.endpoints.calificaciones import router as calificaciones_router
from app.api.v1.endpoints.catalogo import router as catalogo_router
from app.api.v1.endpoints.chatbot import router as chatbot_router
from app.api.v1.endpoints.clientes import router as clientes_router
from app.api.v1.endpoints.colecciones import router as colecciones_router
from app.api.v1.endpoints.cambios import router as cambios_router
from app.api.v1.endpoints.devoluciones import router as devoluciones_router
from app.api.v1.endpoints.direcciones import router as direcciones_router
from app.api.v1.endpoints.empleados import router as empleados_router
from app.api.v1.endpoints.notificaciones import router as notificaciones_router
from app.api.v1.endpoints.perfil import router as perfil_router
from app.api.v1.endpoints.mi_empresa import router as mi_empresa_router
from app.api.v1.endpoints.mi_empresa import tiendas_router
from app.api.v1.endpoints.metodos_pago import router as metodos_pago_router
from app.api.v1.endpoints.registro_empresa import router as registro_empresa_router
from app.api.v1.endpoints.plataforma import router as plataforma_router
from app.api.v1.endpoints.productos import router as productos_router
from app.api.v1.endpoints.proveedores import router as proveedores_router
from app.api.v1.endpoints.recomendaciones import router as recomendaciones_router
from app.api.v1.endpoints.reportes import router as reportes_router
from app.api.v1.endpoints.reservas import router as reservas_router
from app.api.v1.endpoints.roles import router as roles_router
from app.api.v1.endpoints.sesiones import router as sesiones_router
from app.api.v1.endpoints.sucursales import router as sucursales_router
from app.api.v1.endpoints.temporadas import router as temporadas_router
from app.api.v1.endpoints.ventas import router as ventas_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(bitacora_router, prefix="/bitacora", tags=["bitacora"])
api_router.include_router(ar_uso_router, prefix="/ar-uso", tags=["ar-uso"])
api_router.include_router(sesiones_router, prefix="/sesiones", tags=["sesiones"])
api_router.include_router(asistencia_router, prefix="/asistencia", tags=["asistencia"])
api_router.include_router(sucursales_router, prefix="/sucursales", tags=["sucursales"])
api_router.include_router(perfil_router, prefix="/perfil", tags=["perfil"])
api_router.include_router(clientes_router, prefix="/clientes", tags=["clientes"])
api_router.include_router(empleados_router, prefix="/empleados", tags=["empleados"])
api_router.include_router(roles_router, prefix="/roles", tags=["roles"])
api_router.include_router(proveedores_router, prefix="/proveedores", tags=["proveedores"])
api_router.include_router(productos_router, prefix="/productos", tags=["productos"])
api_router.include_router(temporadas_router, prefix="/temporadas", tags=["temporadas"])
api_router.include_router(colecciones_router, prefix="/colecciones", tags=["colecciones"])
api_router.include_router(catalogo_router, prefix="/catalogo", tags=["catalogo"])
api_router.include_router(reservas_router, prefix="/reservas", tags=["reservas"])
api_router.include_router(carrito_router, prefix="/carrito", tags=["carrito"])
api_router.include_router(carritos_admin_router, prefix="/carritos", tags=["carrito"])
api_router.include_router(ventas_router, prefix="/ventas", tags=["ventas"])
api_router.include_router(devoluciones_router, prefix="/devoluciones", tags=["devoluciones"])
api_router.include_router(cambios_router, prefix="/cambios", tags=["cambios"])
api_router.include_router(direcciones_router, prefix="/direcciones", tags=["direcciones"])
api_router.include_router(notificaciones_router, prefix="/notificaciones", tags=["notificaciones"])
api_router.include_router(reportes_router, prefix="/reportes", tags=["reportes"])
api_router.include_router(recomendaciones_router, prefix="/recomendaciones", tags=["recomendaciones"])
api_router.include_router(chatbot_router, prefix="/chatbot", tags=["chatbot"])
api_router.include_router(calificaciones_router, prefix="/calificaciones", tags=["calificaciones"])
# 2do parcial -- plataforma SaaS: panel del SuperAdministrador (CU09, CU10).
api_router.include_router(plataforma_router, prefix="/plataforma", tags=["plataforma"])
# Compra de la suscripcion de una boutique desde la portada (/empezar).
api_router.include_router(registro_empresa_router, prefix="/empresas", tags=["plataforma"])
# Cada tienda: su suscripcion (Administrador) y su enlace publico /tienda/<subdominio>.
api_router.include_router(mi_empresa_router, prefix="/mi-empresa", tags=["plataforma"])
api_router.include_router(tiendas_router, prefix="/tiendas", tags=["plataforma"])
api_router.include_router(metodos_pago_router, prefix="/metodos-pago", tags=["metodos-pago"])


@api_router.get("/ping", tags=["health"])
def ping() -> dict[str, str]:
    return {"status": "ok"}
