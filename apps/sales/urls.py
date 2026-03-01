from django.urls import path
from .views import (
    listar_ventas, nueva_venta, procesar_venta,
    formulario_cierre_caja, procesar_cierre_caja,
    ver_cierre_caja, descargar_pdf_cierre,
    api_dashboard_admin, api_detalle_venta, api_anular_venta,
    abrir_caja, api_caja_activa, ticket_venta_pdf, mis_reportes
)

app_name = 'sales'

urlpatterns = [
    # Ventas
    path('', listar_ventas, name='listado'),
    path('nueva/', nueva_venta, name='nueva_venta'),
    path('api/procesar-venta/', procesar_venta, name='procesar_venta'),

    # Cierre de Caja
    path('cierre/', formulario_cierre_caja, name='formulario_cierre'),
    path('api/procesar-cierre/', procesar_cierre_caja, name='procesar_cierre'),
    path('cierre/<int:cierre_id>/', ver_cierre_caja, name='ver_cierre'),
    path('cierre/<int:cierre_id>/pdf/', descargar_pdf_cierre, name='descargar_pdf_cierre'),

    # Apertura de Caja
    path('api/abrir-caja/', abrir_caja, name='abrir_caja'),
    path('api/caja-activa/', api_caja_activa, name='api_caja_activa'),

    # Tickets/Recibos
    path('api/venta/<int:venta_id>/ticket/', ticket_venta_pdf, name='ticket_venta_pdf'),

    # Reportes
    path('reportes/', mis_reportes, name='mis_reportes'),

    # APIs para Dashboard
    path('api/dashboard/stats/', api_dashboard_admin, name='api_dashboard'),

    # APIs para Gestión de Ventas
    path('api/ventas/<int:venta_id>/', api_detalle_venta, name='api_detalle_venta'),
    path('api/ventas/<int:venta_id>/anular/', api_anular_venta, name='api_anular_venta'),
]