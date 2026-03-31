from django.db import models
from django.contrib.auth.models import User
from django.db.models import F, Sum
from django.db.models.functions import Coalesce


class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre


class ProductoQuerySet(models.QuerySet):
    def stock_bajo(self):
        return self.filter(stock_actual__lte=F('stock_minimo'))

    def con_ventas(self):
        return self.annotate(
            total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0),
        )

    def mas_vendidos(self):
        return self.con_ventas().order_by('-total_vendido', 'nombre')


class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name='productos')
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    costo_compra = models.DecimalField(max_digits=10, decimal_places=2)
    stock_actual = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=5)

    objects = ProductoQuerySet.as_manager()

    def __str__(self):
        return f"{self.nombre} ({self.code})"
    
    @property
    def margen_porcentaje(self):
        if self.costo_compra > 0:
            return int(((self.precio_venta - self.costo_compra) / self.costo_compra) * 100)
        return 0


class Promocion(models.Model):
    TIPO_DESCUENTO = [
        ('PORCENTAJE', 'Porcentaje'),
        ('FIJO', 'Monto Fijo'),
        ('2X1', '2x1 (Lleva 2, paga 1'),
    ]
    
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='promociones')
    tipo_descuento = models.CharField(max_length=20, choices=TIPO_DESCUENTO, default='PORCENTAJE')
    valor_descuento = models.DecimalField(max_digits=10, decimal_places=2)
    precio_promocional = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-activa', '-fecha_inicio']

    def __str__(self):
        return self.nombre
    
    @property
    def esta_vigente(self):
        from django.utils import timezone
        hoy = timezone.now().date()
        return self.activa and self.fecha_inicio <= hoy <= self.fecha_fin
    
    def calcular_precio_promocional(self):
        """Calcula el precio promocional basado en el tipo de descuento."""
        if self.tipo_descuento == '2X1':
            return self.producto.precio_venta
        elif self.tipo_descuento == 'PORCENTAJE':
            return self.producto.precio_venta * (1 - self.valor_descuento / 100)
        else:
            return self.producto.precio_venta - self.valor_descuento
    
    def save(self, *args, **kwargs):
        if not self.precio_promocional:
            self.precio_promocional = self.calcular_precio_promocional()
        super().save(*args, **kwargs)


class PromocionProducto(models.Model):
    """Productos que forman parte de una promoción (para combos)"""
    promocion = models.ForeignKey(Promocion, on_delete=models.CASCADE, related_name='productos_incluidos')
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    
    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"


class MovimientoStock(models.Model):
    MOTIVOS = [
        ('CREACION', 'Creacion'),
        ('VENTA', 'Venta'),
        ('BAJA', 'Baja'),
        ('AJUSTE', 'Ajuste'),
        ('OTRO', 'Otro'),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='movimientos')
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_stock',
    )
    stock_anterior = models.PositiveIntegerField()
    stock_nuevo = models.PositiveIntegerField()
    delta = models.IntegerField()
    motivo = models.CharField(max_length=12, choices=MOTIVOS, default='AJUSTE')
    referencia = models.CharField(max_length=120, blank=True, default='')
    nota = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f"{self.producto.code}: {self.stock_anterior}->{self.stock_nuevo} ({self.delta})"


# apps/products/models.py
class SolicitudBaja(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado'),
    ]

    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField()
    motivo = models.TextField()
    solicitado_por = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bajas_pedidas')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=15, choices=ESTADOS, default='PENDIENTE')
    revisado_por = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bajas_revisadas')
    comentario_admin = models.TextField(null=True, blank=True) # Por qué se rechazó

    def __str__(self):
        return f"Baja {self.producto.nombre} ({self.cantidad}) - {self.estado}"
