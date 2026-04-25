from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Ventas
    path('', views.listar_ventas, name='listado'),
    path('nueva/', views.nueva_venta, name='nueva_venta'),
    path('api/procesar-venta/', views.procesar_venta, name='procesar_venta'),

    # Cierre de Caja
    path('cierre/', views.formulario_cierre_caja, name='formulario_cierre'),
    path('api/procesar-cierre/', views.procesar_cierre_caja, name='procesar_cierre'),
    path('cierre/<int:cierre_id>/', views.ver_cierre_caja, name='ver_cierre'),
    path('cierre/<int:cierre_id>/pdf/', views.descargar_pdf_cierre, name='descargar_pdf_cierre'),
    path('historial-cierres/', views.historial_cierres, name='historial_cierres'),

    # Apertura de Caja
    path('api/abrir-caja/', views.abrir_caja, name='abrir_caja'),
    path('api/caja-activa/', views.api_caja_activa, name='api_caja_activa'),

    # Tickets/Recibos
    path('api/venta/<int:venta_id>/ticket/', views.ticket_venta_pdf, name='ticket_venta_pdf'),

    # Reportes
    path('reportes/', views.mis_reportes, name='mis_reportes'),

    # Reporte Mensual PDF
    path('reporte-mensual/<int:año>/<int:mes>/pdf/', views.reporte_mensual_pdf, name='reporte_mensual_pdf'),

    # APIs para Dashboard
    path('api/dashboard/stats/', views.api_dashboard_admin, name='api_dashboard'),

    # APIs para Gestión de Ventas
    path('api/ventas/<int:venta_id>/', views.api_detalle_venta, name='api_detalle_venta'),
    path('api/ventas/<int:venta_id>/anular/', views.api_anular_venta, name='api_anular_venta'),

    # Gastos
    path('gastos/', views.listar_gastos, name='listar_gastos'),
    path('api/gastos/', views.registrar_gasto, name='registrar_gasto'),
    path('gastos/reportes/', views.reportes_gastos, name='reportes_gastos'),

    # Movimientos / Auditoría
    path('movimientos/', views.movimientos_auditoria, name='movimientos_auditoria'),

    # Créditos (se generan automáticamente con ventas a crédito)
    path('creditos/', views.listar_creditos, name='listar_creditos'),
    path('creditos/<int:credito_id>/', views.detalle_credito, name='detalle_credito'),
    path('api/creditos/<int:credito_id>/pago/', views.registrar_pago_credito, name='registrar_pago_credito'),
    path('api/creditos/<int:credito_id>/cancelar/', views.cancelar_credito, name='cancelar_credito'),
]