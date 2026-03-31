from django.db import models
from django.contrib.auth.models import User
from apps.products.models import Producto
from django.db.models import Q
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
        constraints = [
            models.UniqueConstraint(
                fields=['abierta'],
                condition=Q(abierta=True),
                name='uniq_caja_abierta_global',
            ),
        ]

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
        ('CREDITO', 'Crédito'),
    ]
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO, default='EFECTIVO')
    banco_origen = models.CharField(max_length=100, null=True, blank=True)
    codigo_transferencia = models.CharField(max_length=100, null=True, blank=True)
    def __str__(self):
        return f"Venta #{self.id} - {self.vendedor.username} - Total: {self.total}"

class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    es_promocion = models.BooleanField(default=False)
    promocion_id = models.PositiveIntegerField(null=True, blank=True)

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
    
    # Gastos (nuevo)
    total_gastos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Balance final con gastos: (monto_inicial + efectivo - gastos)
    monto_teorico_final = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    diferencia_final = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Detalles
    total_productos_vendidos = models.PositiveIntegerField(default=0)
    total_transferencias = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_pagos_credito = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Pagos de créditos cobrados
    
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
        producto._stock_motivo = 'VENTA'
        producto._stock_usuario = getattr(instance.venta, 'vendedor', None)
        producto._stock_referencia = f"venta:{instance.venta_id}"
        producto.stock_actual -= instance.cantidad
        producto.save()


class Gasto(models.Model):
    CATEGORIAS = [
        ('INSUMOS', 'Insumos'),
        ('SERVICIOS', 'Servicios'),
        ('MANTENIMIENTO', 'Mantenimiento'),
        ('NOMINA', 'Nómina'),
        ('ALQUILER', 'Alquiler'),
        ('SERVICIOS_PUBLICOS', 'Servicios Públicos'),
        ('MARKETING', 'Marketing'),
        ('OTROS', 'Otros'),
    ]
    
    caja = models.ForeignKey(Caja, on_delete=models.CASCADE, related_name='gastos')
    usuario = models.ForeignKey(User, on_delete=models.PROTECT, related_name='gastos_registrados')
    categoria = models.CharField(max_length=30, choices=CATEGORIAS)
    descripcion = models.TextField()
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"Gasto #{self.id} - {self.categoria}: ${self.monto}"


class Credito(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('PAGADO', 'Pagado'),
        ('PARCIAL', 'Pago Parcial'),
        ('VENCIDO', 'Vencido'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='creditos')
    cliente = models.CharField(max_length=150)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    monto_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.CharField(max_length=15, choices=ESTADO_CHOICES, default='PENDIENTE')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)
    vendedor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='creditos_otorgados')
    observaciones = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Crédito #{self.id} - {self.cliente} - ${self.saldo_pendiente}"
    
    def actualizar_estado(self):
        if self.saldo_pendiente <= 0:
            self.estado = 'PAGADO'
        elif self.monto_pagado > 0:
            self.estado = 'PARCIAL'
        self.save()


class PagoCredito(models.Model):
    METODO_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('DEPOSITO', 'Depósito'),
    ]
    
    credito = models.ForeignKey(Credito, on_delete=models.CASCADE, related_name='pagos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo_pago = models.CharField(max_length=20, choices=METODO_PAGO_CHOICES, default='EFECTIVO')
    fecha_pago = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey(User, on_delete=models.PROTECT, related_name='pagos_credito')
    observaciones = models.TextField(blank=True, default='')
    
    class Meta:
        ordering = ['-fecha_pago']

    def __str__(self):
        return f"Pago #{self.id} - ${self.monto} - {self.credito.cliente}"


class Movimiento(models.Model):
    """
    Modelo para auditoría - registra todos los movimientos del sistema.
    """
    TIPO_CHOICES = [
        ('VENTA', 'Venta'),
        ('VENTA_DETALLE', 'Detalle Venta'),
        ('CAJA_APERTURA', 'Apertura Caja'),
        ('CAJA_CIERRE', 'Cierre Caja'),
        ('GASTO', 'Gasto'),
        ('CREDITO', 'Crédito'),
        ('PAGO_CREDITO', 'Pago Crédito'),
        ('STOCK_ENTRADA', 'Entrada Stock'),
        ('STOCK_SALIDA', 'Salida Stock'),
        ('BAJA_STOCK', 'Baja Stock'),
        ('PRODUCTO', 'Producto'),
        ('PROMOCION', 'Promoción'),
        ('USUARIO', 'Usuario'),
        ('OTRO', 'Otro'),
    ]

    ACCION_CHOICES = [
        ('CREAR', 'Crear'),
        ('MODIFICAR', 'Modificar'),
        ('ELIMINAR', 'Eliminar'),
        ('APERTURAR', 'Aperturar'),
        ('CERRAR', 'Cerrar'),
        ('REGISTRAR', 'Registrar'),
        ('PAGAR', 'Pagar'),
        ('ANULAR', 'Anular'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    accion = models.CharField(max_length=15, choices=ACCION_CHOICES)
    descripcion = models.TextField()
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='movimientos')
    referencia_id = models.PositiveIntegerField(null=True, blank=True)
    referencia_tipo = models.CharField(max_length=30, null=True, blank=True)
    datos_previos = models.JSONField(null=True, blank=True)
    datos_nuevos = models.JSONField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'
        indexes = [
            models.Index(fields=['tipo', '-fecha']),
            models.Index(fields=['usuario', '-fecha']),
        ]

    def __str__(self):
        return f"{self.tipo} - {self.accion} - {self.fecha.strftime('%d/%m/%Y %H:%M')}"


def registrar_movimiento(tipo, accion, descripcion, usuario=None, referencia_id=None, referencia_tipo=None, datos_previos=None, datos_nuevos=None, request=None):
    """Función helper para registrar movimientos del sistema."""
    movimiento = Movimiento.objects.create(
        tipo=tipo,
        accion=accion,
        descripcion=descripcion,
        usuario=usuario,
        referencia_id=referencia_id,
        referencia_tipo=referencia_tipo,
        datos_previos=datos_previos,
        datos_nuevos=datos_nuevos,
        ip_address=request.META.get('REMOTE_ADDR') if request else None
    )
    return movimiento


@receiver(post_save, sender=Venta)
def movimiento_venta(sender, instance, created, **kwargs):
    if created:
        registrar_movimiento(
            tipo='VENTA',
            accion='CREAR',
            descripcion=f"Venta #{instance.id} - Total: ${instance.total} - Cliente: {instance.cliente}",
            usuario=instance.vendedor,
            referencia_id=instance.id,
            referencia_tipo='Venta',
            datos_nuevos={
                'total': str(instance.total),
                'metodo_pago': instance.metodo_pago,
                'cliente': instance.cliente
            }
        )


@receiver(post_save, sender=Caja)
def movimiento_caja(sender, instance, created, **kwargs):
    if created:
        registrar_movimiento(
            tipo='CAJA_APERTURA',
            accion='APERTURAR',
            descripcion=f"Caja #{instance.id} abierta por {instance.responsable.username} - Monto inicial: ${instance.monto_inicial}",
            usuario=instance.responsable,
            referencia_id=instance.id,
            referencia_tipo='Caja',
            datos_nuevos={'monto_inicial': str(instance.monto_inicial)}
        )
    elif not instance.abierta and instance.estado == 'Cerrada':
        registrar_movimiento(
            tipo='CAJA_CIERRE',
            accion='CERRAR',
            descripcion=f"Caja #{instance.id} cerrada por {instance.responsable.username} - Monto final: ${instance.monto_final_real or 0}",
            usuario=instance.responsable,
            referencia_id=instance.id,
            referencia_tipo='Caja',
            datos_nuevos={'monto_final': str(instance.monto_final_real)}
        )


@receiver(post_save, sender=Gasto)
def movimiento_gasto(sender, instance, created, **kwargs):
    if created:
        registrar_movimiento(
            tipo='GASTO',
            accion='REGISTRAR',
            descripcion=f"Gasto #{instance.id} - {instance.categoria}: ${instance.monto}",
            usuario=instance.usuario,
            referencia_id=instance.id,
            referencia_tipo='Gasto',
            datos_nuevos={
                'categoria': instance.categoria,
                'monto': str(instance.monto),
                'descripcion': instance.descripcion
            }
        )


@receiver(post_save, sender=Credito)
def movimiento_credito(sender, instance, created, **kwargs):
    if created:
        registrar_movimiento(
            tipo='CREDITO',
            accion='CREAR',
            descripcion=f"Crédito #{instance.id} - Cliente: {instance.cliente} - Total: ${instance.monto_total}",
            usuario=instance.vendedor,
            referencia_id=instance.id,
            referencia_tipo='Credito',
            datos_nuevos={
                'cliente': instance.cliente,
                'total': str(instance.monto_total),
                'estado': instance.estado
            }
        )
    else:
        if instance.estado in ['PAGADO', 'CANCELADO']:
            registrar_movimiento(
                tipo='CREDITO',
                accion='MODIFICAR',
                descripcion=f"Crédito #{instance.id} marcado como {instance.estado}",
                referencia_id=instance.id,
                referencia_tipo='Credito',
                datos_nuevos={'estado': instance.estado}
            )


@receiver(post_save, sender=PagoCredito)
def movimiento_pago_credito(sender, instance, created, **kwargs):
    if created:
        registrar_movimiento(
            tipo='PAGO_CREDITO',
            accion='PAGAR',
            descripcion=f"Pago #{instance.id} - Crédito #{instance.credito.id} - Monto: ${instance.monto}",
            usuario=instance.registrado_por,
            referencia_id=instance.id,
            referencia_tipo='PagoCredito',
            datos_nuevos={
                'credito_id': instance.credito_id,
                'monto': str(instance.monto),
                'metodo_pago': instance.metodo_pago
            }
        )


@receiver(post_save, sender=DetalleVenta)
def movimiento_detalle_venta(sender, instance, created, **kwargs):
    if created:
        producto_nombre = instance.producto.nombre if instance.producto else 'Unknown'
        if instance.es_promocion:
            tipo = 'VENTA_DETALLE'
            desc = f"Promoción '{producto_nombre}' en Venta #{instance.venta_id}: {instance.cantidad} x ${instance.precio_unitario}"
        else:
            tipo = 'VENTA_DETALLE'
            desc = f"Producto '{producto_nombre}' en Venta #{instance.venta_id}: {instance.cantidad} x ${instance.precio_unitario}"
        
        registrar_movimiento(
            tipo=tipo,
            accion='CREAR',
            descripcion=desc,
            usuario=getattr(instance.venta, 'vendedor', None),
            referencia_id=instance.id,
            referencia_tipo='DetalleVenta',
            datos_nuevos={
                'producto_id': instance.producto_id,
                'cantidad': str(instance.cantidad),
                'precio_unitario': str(instance.precio_unitario),
                'es_promocion': instance.es_promocion
            }
        )
