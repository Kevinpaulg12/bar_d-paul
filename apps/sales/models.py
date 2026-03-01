from django.db import models
from django.contrib.auth.models import User
from apps.products.models import Producto
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Caja(models.Model):
    # Estado de la caja
    ESTADO_CHOICES = [
        ('Abierta', 'Abierta'),
        ('Cerrada', 'Cerrada'),
    ]

    # PROTECT impide borrar al usuario si tiene cajas registradas
    responsable = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cajas')
    fecha = models.DateField(auto_now_add=True)
    hora_apertura = models.DateTimeField(auto_now_add=True)
    monto_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    monto_final_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    abierta = models.BooleanField(default=True)  # Mantener por backward-compatibility
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='Abierta')

    class Meta:
        unique_together = ('responsable', 'fecha')

    def __str__(self):
        return f"Caja {self.fecha} - Responsable: {self.responsable.username}"

    def esta_abierta(self):
        """Verificar si la caja está abierta"""
        return self.estado == 'Abierta'
    
    def total_ventas(self):
        """Calcula el total de ventas en efectivo"""
        return self.ventas.filter(metodo_pago='EFECTIVO').aggregate(
            total=models.Sum('total')
        )['total'] or 0
    
    def total_transferencias(self):
        """Calcula el total de transferencias"""
        return self.ventas.filter(metodo_pago='TRANSFERENCIA').aggregate(
            total=models.Sum('total')
        )['total'] or 0


class Venta(models.Model):
    caja = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='ventas')
    # Guardamos quién hizo la venta directamente por si la caja cambia de manos
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ventas_realizadas')
    hora = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cliente = models.CharField(max_length=150, default="Consumidor Final")
    METODO_PAGO = [
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO, default='EFECTIVO')
    banco_origen = models.CharField(max_length=100, null=True, blank=True)
    codigo_transferencia = models.CharField(max_length=100, null=True, blank=True)
    def __str__(self):
        return f"Venta #{self.id} - {self.vendedor.username} - Total: {self.total}"

class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT) # Protegemos el producto también
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"


class CierreCaja(models.Model):
    """Registro de cierre de caja con detalles de reconciliación"""
    caja = models.OneToOneField(Caja, on_delete=models.CASCADE, related_name='cierre')
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='cierres_caja')
    fecha_cierre = models.DateTimeField(auto_now_add=True)
    
    # Montos
    monto_inicial = models.DecimalField(max_digits=10, decimal_places=2)
    total_ventas_esperado = models.DecimalField(max_digits=10, decimal_places=2)  # Total en efectivo
    monto_teorico = models.DecimalField(max_digits=10, decimal_places=2)  # monto_inicial + total_esperado
    monto_fisico_ingresado = models.DecimalField(max_digits=10, decimal_places=2)  # Lo que entrega el vendedor
    diferencia = models.DecimalField(max_digits=10, decimal_places=2)  # monto_teorico - monto_fisico
    
    # Detalles
    total_productos_vendidos = models.PositiveIntegerField(default=0)
    total_transferencias = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Estado
    cerrado = models.BooleanField(default=True)

    class Meta:
        ordering = ['-fecha_cierre']

    def __str__(self):
        return f"Cierre {self.fecha_cierre.date()} - {self.vendedor.username}"


@receiver(post_save, sender=DetalleVenta)
def descontar_stock(sender, instance, created, **kwargs):
    if created:
        producto = instance.producto
        producto.stock_actual -= instance.cantidad
        producto.save()