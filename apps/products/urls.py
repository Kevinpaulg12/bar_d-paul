from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Inventario
    path('', views.inventario, name='inventario'),
    path('hx/inventario/', views.inventario_table, name='inventario_table'),
    path('api/productos/<int:producto_id>/ajustar-stock/', views.ajustar_stock, name='ajustar_stock'),

    # Gestión de productos (Admin)
    path('productos/crear/', views.crear_producto, name='crear_producto'),
    path('productos/<int:producto_id>/editar/', views.editar_producto, name='editar_producto'),
    path('api/productos/<int:producto_id>/eliminar/', views.eliminar_producto, name='eliminar_producto'),

    # Solicitar baja
    path('solicitar-baja/', views.solicitar_baja_api, name='solicitar_baja_api'),

    # Mis solicitudes de baja (vendedor)
    path('mis-solicitudes-baja/', views.mis_solicitudes_baja, name='mis_solicitudes_baja'),

    # Administración de solicitudes de baja (admin)
    path('bajas/pendientes/', views.bajas_pendientes, name='bajas_pendientes'),
    path('bajas/<int:baja_id>/aprobar/', views.aprobar_baja, name='aprobar_baja'),
    path('bajas/<int:baja_id>/rechazar/', views.rechazar_baja, name='rechazar_baja'),

    # Reportes de inventario
    path('reportes/inventario.pdf', views.inventario_pdf, name='inventario_pdf'),
    path('reportes/inventario.xlsx', views.inventario_excel, name='inventario_excel'),

    # Promociones
    path('promociones/', views.listar_promociones, name='listar_promociones'),
    path('promociones/crear/', views.crear_promocion, name='crear_promocion'),
    path('promociones/<int:promocion_id>/editar/', views.editar_promocion, name='editar_promocion'),
    path('promociones/<int:promocion_id>/toggle/', views.toggle_promocion, name='toggle_promocion'),
]
