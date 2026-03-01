from django.contrib import admin
from .models import Categoria, Producto, SolicitudBaja

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'code', 'categoria', 'precio_venta', 'stock_actual') # Cambiado aquí
    list_filter = ('categoria',)
    search_fields = ('nombre', 'code') # Cambiado aquí
@admin.register(SolicitudBaja)
class SolicitudBajaAdmin(admin.ModelAdmin):
    list_display = ('producto', 'cantidad', 'motivo', 'solicitado_por', 'fecha_solicitud', 'estado')
    list_filter = ('estado', 'fecha_solicitud')
    search_fields = ('producto__nombre', 'solicitado_por__username')
    readonly_fields = ('fecha_solicitud',)
    def save_model(self, request, obj, form, change):
        if change:  # Solo actuamos si es una edición, no una creación
            original = SolicitudBaja.objects.get(pk=obj.pk)
            if original.estado == 'PENDIENTE' and obj.estado == 'APROBADO':
                # Aquí descontamos el stock del producto
                producto = obj.producto
                producto.stock_actual = max(producto.stock_actual - obj.cantidad, 0) # Evitamos stock negativo
                producto.save()
        super().save_model(request, obj, form, change)
        