import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Sum, Q
from .models import SolicitudBaja, Producto
from apps.users.decorators import solo_vendedor, solo_administrador

# ==================== SOLICITUDES DE BAJA POR VENDEDOR ====================

@solo_vendedor
@require_http_methods(["POST"])
def solicitar_baja_api(request):
    """
    POST /productos/api/solicitar-baja/
    
    Vendedor solicita una baja de producto por daño, expiración, etc.
    
    Body JSON:
    {
        "producto_id": 1,
        "cantidad": 5,
        "motivo": "Producto dañado/Expirado/Otro"
    }
    
    Respuesta:
    {
        "success": true,
        "baja_id": 10,
        "estado": "PENDIENTE",
        "mensaje": "Solicitud enviada al administrador"
    }
    
    Nota: El stock se descuenta solo cuando el admin aprueba.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            producto_id = data.get('producto_id')
            cantidad = int(data.get('cantidad', 0))
            motivo = data.get('motivo', '').strip()

            # Validaciones
            if not producto_id or cantidad <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Producto e cantidad son requeridos'
                }, status=400)

            if not motivo:
                return JsonResponse({
                    'success': False,
                    'error': 'Debe proporcionar un motivo'
                }, status=400)

            # Validar que el producto existe
            try:
                producto = Producto.objects.get(id=producto_id)
            except Producto.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Producto no encontrado'
                }, status=404)

            # Validar stock disponible
            if producto.stock_actual < cantidad:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente. Disponible: {producto.stock_actual}'
                }, status=400)

            # Crear solicitud (con transacción)
            with transaction.atomic():
                baja = SolicitudBaja.objects.create(
                    producto=producto,
                    cantidad=cantidad,
                    motivo=motivo,
                    solicitado_por=request.user,
                    estado='PENDIENTE'
                )

            return JsonResponse({
                'success': True,
                'baja_id': baja.id,
                'estado': baja.estado,
                'mensaje': f'✅ Solicitud de baja enviada. ID: {baja.id}'
            })

        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'JSON inválido'
            }, status=400)
        except Exception as e:
            print(f"Error en solicitar_baja_api: {e}")
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    return JsonResponse({
        'success': False,
        'error': 'Método no permitido'
    }, status=405)


# ==================== ADMINISTRACIÓN DE SOLICITUDES DE BAJA ====================

@solo_administrador
def bajas_pendientes(request):
    """
    GET /productos/bajas/pendientes/
    
    Bandeja de entrada del admin: Solicitudes de baja pendientes.
    
    Acciones posibles:
    - Aprobar (descuenta stock)
    - Rechazar (no afecta stock)
    
    Información mostrada:
    - Producto, cantidad solicitada, motivo
    - Vendedor solicitante, fecha
    - Botones de acción
    """
    # Opciones de filtrado
    filtro_estado = request.GET.get('estado', 'PENDIENTE')
    
    # Query base
    bajas = SolicitudBaja.objects.select_related(
        'producto', 'solicitado_por', 'revisado_por'
    ).order_by('-fecha_solicitud')
    
    # Aplicar filtro de estado
    if filtro_estado:
        bajas = bajas.filter(estado=filtro_estado)
    
    # Estadísticas
    stats = {
        'pendientes': SolicitudBaja.objects.filter(estado='PENDIENTE').count(),
        'aprobadas': SolicitudBaja.objects.filter(estado='APROBADO').count(),
        'rechazadas': SolicitudBaja.objects.filter(estado='RECHAZADO').count(),
    }

    return render(request, 'products/bajas_pendientes.html', {
        'bajas': bajas,
        'stats': stats,
        'filtro_activo': filtro_estado
    })


@solo_administrador
@require_http_methods(["POST"])
def aprobar_baja(request, baja_id):
    """
    POST /productos/api/bajas/<id>/aprobar/
    
    Admin aprueba una solicitud de baja.
    
    Acciones:
    - Descuenta el stock del producto
    - Marca solicitud como APROBADO
    - Registra quién aprobó y cuándo
    
    Respuesta:
    {
        "success": true,
        "mensaje": "Baja aprobada. Stock actualizado.",
        "producto": "Nombre Producto",
        "cantidad": 5,
        "stock_nuevo": 95
    }
    """
    try:
        baja = SolicitudBaja.objects.select_related('producto').get(id=baja_id)

        # Validar que está pendiente
        if baja.estado != 'PENDIENTE':
            return JsonResponse({
                'success': False,
                'error': f'Esta solicitud ya fue {baja.estado.lower()}'
            }, status=400)

        # Transacción atómica: descuentostock + marca aprobada
        with transaction.atomic():
            # Validar stock una última vez (por si cambió)
            if baja.producto.stock_actual < baja.cantidad:
                return JsonResponse({
                    'success': False,
                    'error': f'Stock insuficiente. Solo hay {baja.producto.stock_actual}'
                }, status=400)

            # Descontar stock
            baja.producto.stock_actual -= baja.cantidad
            baja.producto.save()

            # Marcar como aprobada
            baja.estado = 'APROBADO'
            baja.revisado_por = request.user
            baja.save()

        return JsonResponse({
            'success': True,
            'mensaje': f'✅ Baja aprobada. Stock actualizado.',
            'producto': baja.producto.nombre,
            'cantidad': baja.cantidad,
            'stock_nuevo': baja.producto.stock_actual
        })

    except SolicitudBaja.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Solicitud de baja no encontrada'
        }, status=404)
    except Exception as e:
        print(f"Error en aprobar_baja: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@solo_administrador
@require_http_methods(["POST"])
def rechazar_baja(request, baja_id):
    """
    POST /productos/api/bajas/<id>/rechazar/
    
    Admin rechaza una solicitud de baja.
    
    Body JSON:
    {
        "comentario": "Motivo del rechazo (opcional)"
    }
    
    Acciones:
    - Marca como RECHAZADO
    - Guarda comentario del admin
    - El stock NO se ve afectado
    
    Respuesta:
    {
        "success": true,
        "mensaje": "Baja rechazada",
        "producto": "Nombre Producto"
    }
    """
    try:
        data = json.loads(request.body) if request.body else {}
        comentario = data.get('comentario', '').strip()

        baja = SolicitudBaja.objects.select_related('producto').get(id=baja_id)

        # Validar que está pendiente
        if baja.estado != 'PENDIENTE':
            return JsonResponse({
                'success': False,
                'error': f'Esta solicitud ya fue {baja.estado.lower()}'
            }, status=400)

        # Marcar como rechazada
        baja.estado = 'RECHAZADO'
        baja.revisado_por = request.user
        baja.comentario_admin = comentario
        baja.save()

        return JsonResponse({
            'success': True,
            'mensaje': f'✅ Baja rechazada',
            'producto': baja.producto.nombre
        })

    except SolicitudBaja.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Solicitud de baja no encontrada'
        }, status=404)
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'JSON inválido'
        }, status=400)
    except Exception as e:
        print(f"Error en rechazar_baja: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)