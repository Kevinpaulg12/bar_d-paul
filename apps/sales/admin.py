from django.contrib import admin
from .models import Caja, Venta, DetalleVenta, CierreCaja

@admin.register(Caja)
class CajaAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'responsable', 'monto_inicial', 'monto_final_real', 'abierta')
    list_filter = ('abierta', 'fecha', 'responsable')

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'caja', 'vendedor', 'hora', 'total', 'metodo_pago')
    list_filter = ('metodo_pago', 'hora', 'vendedor')
    inlines = [DetalleVentaInline]

@admin.register(CierreCaja)
class CierreCajaAdmin(admin.ModelAdmin):
    list_display = ('fecha_cierre', 'vendedor', 'monto_teorico', 'monto_fisico_ingresado', 'diferencia')
    list_filter = ('fecha_cierre', 'vendedor')
    readonly_fields = ('monto_teorico', 'diferencia')
    
    fieldsets = (
        ('Información del Cierre', {
            'fields': ('caja', 'vendedor', 'fecha_cierre')
        }),
        ('Montos', {
            'fields': ('monto_inicial', 'total_ventas_esperado', 'monto_teorico', 'monto_fisico_ingresado', 'diferencia')
        }),
        ('Detalles', {
            'fields': ('total_productos_vendidos', 'total_transferencias', 'cerrado')
        })
    )