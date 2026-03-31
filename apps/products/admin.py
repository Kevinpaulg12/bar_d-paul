from django.contrib import admin
from .models import Categoria, Producto, SolicitudBaja, MovimientoStock

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
                producto._stock_motivo = 'BAJA'
                producto._stock_usuario = request.user
                producto._stock_referencia = f"baja:{obj.pk}"
                producto.stock_actual = max(producto.stock_actual - obj.cantidad, 0) # Evitamos stock negativo
                producto.save()
        super().save_model(request, obj, form, change)


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'producto', 'motivo', 'delta', 'stock_anterior', 'stock_nuevo', 'usuario')
    list_filter = ('motivo', 'fecha')
    search_fields = ('producto__nombre', 'producto__code', 'referencia', 'usuario__username')
