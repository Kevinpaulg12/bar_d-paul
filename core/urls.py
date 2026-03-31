from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # La app de ventas es la principal, se sirve desde la raíz '/'
    path('', include('apps.sales.urls')),

    # La app de dashboard tendrá su propio prefijo
    path('dashboard/', include('apps.dashboard.urls')),

    # Productos (inventario)
    path('productos/', include('apps.products.urls')),
    
    # Cuentas (auth)
    path('cuentas/', include('apps.users.urls')),
    
    # Admin
    path('admin/', admin.site.urls),
]