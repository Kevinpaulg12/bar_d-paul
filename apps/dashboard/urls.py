from django.urls import path
from .views import home, dashboard_admin, dashboard_vendedor, api_reporte_mensual

app_name = 'dashboard'

urlpatterns = [
    path('', home, name='panel'),
    path('admin/', dashboard_admin, name='dashboard_admin'),
    path('vendedor/', dashboard_vendedor, name='dashboard_vendedor'),
    path('api/reporte-mensual/', api_reporte_mensual, name='api_reporte_mensual'),
]