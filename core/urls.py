from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # La app de ventas es la principal, se sirve desde la raíz '/'
    # Esto significa que al entrar a la web, verás la lista de ventas.
    path('', include('apps.sales.urls')),

    # La app de dashboard tendrá su propio prefijo
    path('dashboard/', include('apps.dashboard.urls')),

    # Cuando desees habilitar las otras, asegúrate de usar el prefijo apps.
    path('productos/', include('apps.products.urls')),
    path('cuentas/', include('apps.users.urls')), # Rutas de autenticación: /cuentas/login/, /cuentas/logout/
]