from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # ... tus otras rutas ...
    path('solicitar-baja/', views.solicitar_baja_api, name='solicitar_baja_api'),

    # Administración de solicitudes de baja
    path('bajas/pendientes/', views.bajas_pendientes, name='bajas_pendientes'),
    path('bajas/<int:baja_id>/aprobar/', views.aprobar_baja, name='aprobar_baja'),
    path('bajas/<int:baja_id>/rechazar/', views.rechazar_baja, name='rechazar_baja'),
]