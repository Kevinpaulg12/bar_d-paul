from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Producto, MovimientoStock, Promocion


@receiver(pre_save, sender=Producto)
def producto_pre_save(sender, instance: Producto, **kwargs):
    if not instance.pk:
        instance._stock_prev = 0
        instance._es_nuevo = True
        return

    try:
        prev = Producto.objects.only('stock_actual').get(pk=instance.pk)
        instance._stock_prev = prev.stock_actual
    except Producto.DoesNotExist:
        instance._stock_prev = 0


@receiver(post_save, sender=Producto)
def producto_post_save(sender, instance: Producto, created: bool, **kwargs):
    prev = getattr(instance, '_stock_prev', None)
    if prev is None:
        return

    es_nuevo = getattr(instance, '_es_nuevo', False)
    
    if es_nuevo:
        try:
            from apps.sales.models import Movimiento, registrar_movimiento
            usuario = getattr(instance, '_stock_usuario', None)
            registrar_movimiento(
                tipo='PRODUCTO',
                accion='CREAR',
                descripcion=f"Producto creado: {instance.nombre} (Code: {instance.code}) - Stock inicial: {instance.stock_actual}",
                usuario=usuario,
                referencia_id=instance.id,
                referencia_tipo='Producto',
                datos_nuevos={
                    'nombre': instance.nombre,
                    'code': instance.code,
                    'categoria': instance.categoria.nombre if instance.categoria else None,
                    'precio_venta': str(instance.precio_venta),
                    'stock_actual': instance.stock_actual,
                }
            )
        except Exception:
            pass

    if instance.stock_actual == prev:
        return

    delta = int(instance.stock_actual) - int(prev)
    if created and delta == 0:
        return

    motivo = getattr(instance, '_stock_motivo', 'AJUSTE')
    usuario = getattr(instance, '_stock_usuario', None)
    referencia = getattr(instance, '_stock_referencia', '')
    nota = getattr(instance, '_stock_nota', '')

    def _crear_movimiento():
        MovimientoStock.objects.create(
            producto=instance,
            usuario=usuario,
            stock_anterior=prev,
            stock_nuevo=instance.stock_actual,
            delta=delta,
            motivo=motivo,
            referencia=referencia,
            nota=nota,
        )

    transaction.on_commit(_crear_movimiento)

    try:
        from apps.sales.models import Movimiento, registrar_movimiento
        if delta > 0:
            tipo_mov = 'STOCK_ENTRADA'
            acc = 'REGISTRAR'
            desc = f"Entrada de stock: {instance.nombre} +{delta} (antes: {prev}, ahora: {instance.stock_actual})"
        elif delta < 0:
            tipo_mov = 'STOCK_SALIDA'
            acc = 'REGISTRAR'
            desc = f"Salida de stock: {instance.nombre} {delta} (antes: {prev}, ahora: {instance.stock_actual})"
        else:
            tipo_mov = None
            
        if tipo_mov:
            registrar_movimiento(
                tipo=tipo_mov,
                accion=acc,
                descripcion=desc,
                usuario=usuario,
                referencia_id=instance.id,
                referencia_tipo='Producto',
                datos_nuevos={
                    'producto': instance.nombre,
                    'stock_anterior': prev,
                    'stock_nuevo': instance.stock_actual,
                    'delta': delta,
                    'motivo': motivo,
                }
            )
    except Exception:
        pass

    for attr in (
        '_stock_prev',
        '_stock_motivo',
        '_stock_usuario',
        '_stock_referencia',
        '_stock_nota',
        '_es_nuevo',
    ):
        if hasattr(instance, attr):
            delattr(instance, attr)


@receiver(post_save, sender=Promocion)
def promocion_post_save(sender, instance: Promocion, created: bool, **kwargs):
    try:
        from apps.sales.models import registrar_movimiento
        request = getattr(instance, '_request', None)
        
        if created:
            registrar_movimiento(
                tipo='PROMOCION',
                accion='CREAR',
                descripcion=f"Promoción creada: {instance.nombre} - Producto: {instance.producto.nombre}",
                usuario=getattr(instance, '_creado_por', None),
                referencia_id=instance.id,
                referencia_tipo='Promocion',
                datos_nuevos={
                    'nombre': instance.nombre,
                    'producto': instance.producto.nombre,
                    'tipo_descuento': instance.tipo_descuento,
                    'valor_descuento': str(instance.valor_descuento),
                    'precio_promocional': str(instance.precio_promocional) if instance.precio_promocional else None,
                },
                request=request
            )
        else:
            old_instance = Promocion.objects.get(pk=instance.pk)
            if old_instance.activa != instance.activa:
                accion = 'MODIFICAR'
                estado = 'activada' if instance.activa else 'desactivada'
                desc = f"Promoción {estado}: {instance.nombre}"
                registrar_movimiento(
                    tipo='PROMOCION',
                    accion=accion,
                    descripcion=desc,
                    usuario=getattr(instance, '_modificado_por', None),
                    referencia_id=instance.id,
                    referencia_tipo='Promocion',
                    datos_nuevos={'activa': instance.activa},
                    request=request
                )
    except Exception:
        pass

