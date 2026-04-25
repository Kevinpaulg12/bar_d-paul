import logging
logger = logging.getLogger(__name__)
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.utils import timezone
from apps.products.models import Producto, Categoria, SolicitudBaja
from apps.users.decorators import solo_vendedor, solo_administrador, rol_requerido
import json
from django.http import JsonResponse, HttpResponse
from django.db import transaction, IntegrityError
from django.db.models import Sum, Count, DecimalField, Q, Avg
from django.db.models.functions import Coalesce
from .models import Caja, Venta, DetalleVenta, CierreCaja, Gasto, Credito, PagoCredito
from django.views.decorators.http import require_http_methods
from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO
from datetime import timedelta
# ==================== HELPER FUNCTIONS ====================
def obtener_caja_activa(usuario):
    # Caja activa global (solo puede existir 1 abierta en el sistema)
    # He corregido DoesNotExist porque filter().first() es más seguro que get()
    caja = Caja.objects.filter(
        abierta=True,
        estado='Abierta'
    ).order_by('-fecha', '-id').first() # Trae la más reciente abierta

    return caja


def _es_responsable_de_caja(user, caja):
    if not caja:
        return False
    return getattr(caja, 'responsable_id', None) == getattr(user, 'id', None)


def _usuario_puede_vender(user, caja):
    """
    Permiso de escritura de ventas (POS): solo el responsable de la caja activa
    y que además sea un vendedor marcado como RESPONSABLE.
    """
    if not _es_responsable_de_caja(user, caja):
        return False
    perfil = getattr(user, 'perfil', None)
    return bool(perfil and getattr(perfil, 'rol', None) == 'vendedor' and getattr(perfil, 'tipo_vendedor', None) == 'RESPONSABLE')


@solo_vendedor
@require_http_methods(["POST"])
def abrir_caja(request):
    try:
        data = json.loads(request.body)
        monto_inicial = Decimal(str(data.get('monto_inicial', 0)))

        # `Caja.fecha` y `Caja.hora_apertura` se setean automaticamente (auto_now_add).
        # Evitamos pasar valores manuales para no chocar con tipos (DateTimeField vs time()).

        # VALIDACIÓN: Verificar si YA existe una caja abierta (de cualquier fecha)
        # Solo puede existir UNA caja abierta en todo el sistema
        caja_abierta = Caja.objects.filter(
            abierta=True,
            estado='Abierta',
        ).exists()

        if caja_abierta:
            return JsonResponse({
                'error': 'Ya hay una caja abierta en el sistema. Debes cerrarla antes de abrir una nueva.',
                'code': 'CAJA_YA_ABIERTA_SISTEMA'
            }, status=400)

        # Solo un vendedor RESPONSABLE puede abrir caja (define quién es el responsable de la caja activa).
        if not hasattr(request.user, 'perfil') or request.user.perfil.rol != 'vendedor' or request.user.perfil.tipo_vendedor != 'RESPONSABLE':
            return JsonResponse({
                'error': 'Solo un Vendedor Responsable puede abrir caja.',
                'code': 'SOLO_RESPONSABLE_PUEDE_ABRIR_CAJA'
            }, status=403)

        # CREACIÓN: Asegúrate de que los nombres de los campos sean exactos a tu modelo
        caja = Caja.objects.create(
            responsable=request.user,
            monto_inicial=monto_inicial,
            abierta=True,      # Este es el que busca el frontend
            estado='Abierta',   # Este es el que usas para etiquetas
        )

        return JsonResponse({
            'success': True,
            'caja_id': caja.id,
            'mensaje': 'Caja abierta exitosamente'
        })
    # ... resto del catches
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except IntegrityError:
        # Fallback: si la validación previa falla por carrera u otro motivo.
        return JsonResponse({
            'error': 'Ya hay una caja abierta en el sistema. Refresca la página.',
            'code': 'CAJA_YA_ABIERTA_SISTEMA'
        }, status=400)
    except Exception as e:
        print(f"Error en abrir_caja: {e}")
        return JsonResponse({'error': 'Error interno del servidor'}, status=500)


@login_required
def listar_ventas(request):
    """
    GET /sales/
    
    Página principal adaptada por rol del usuario.
    - Admin: Ve todas las ventas del sistema
    - Vendedor: Ve solo sus ventas
    
    Requisitos:
    - Caja debe estar abierta (estado='Abierta')
    - Solo muestra ventas del día actual
    
    Si no hay caja abierta, muestra formulario de apertura.
    """
    # Si es admin, redirigir al dashboard administrativo
    if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'admin':
        return redirect('dashboard:panel')

    # Verificar que hay caja abierta hoy
    caja_activa = obtener_caja_activa(request.user)

    if not caja_activa or caja_activa.estado != 'Abierta':
        perfil = getattr(request.user, 'perfil', None)
        puede_abrir_caja = bool(perfil and perfil.rol == 'vendedor' and getattr(perfil, 'tipo_vendedor', None) == 'RESPONSABLE')
        if request.headers.get('HX-Request') == 'true':
            return HttpResponse(status=204)
        return render(request, 'sales/sales_list.html', {
            'error': '❌ Debe abrir caja para comenzar',
            'sin_caja': True,
            'puede_abrir_caja': puede_abrir_caja,
        })

    # Obtener el rango del día actual
    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_dia = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Filtrar SOLO por caja activa y rango de fecha (base del día)
    ventas_hoy_base = caja_activa.ventas.filter(
        hora__range=(inicio_dia, fin_dia)
    ).order_by('-hora')

    # Filtros (UX dinámico con HTMX)
    q = (request.GET.get('q') or '').strip()
    metodo_pago = (request.GET.get('metodo_pago') or '').strip().upper()

    ventas_hoy = ventas_hoy_base
    if q:
        ventas_hoy = ventas_hoy.filter(cliente__icontains=q)
    if metodo_pago in {'EFECTIVO', 'TRANSFERENCIA', 'CREDITO'}:
        ventas_hoy = ventas_hoy.filter(metodo_pago=metodo_pago)
    elif metodo_pago:
        metodo_pago = ''

    # Calcular estadísticas del día (base, no filtrado)
    stats = ventas_hoy_base.aggregate(
        total_dia=Coalesce(Sum('total'), 0, output_field=DecimalField()),
        num_ventas=Count('id'),
        efectivo=Coalesce(
            Sum('total', filter=Q(metodo_pago='EFECTIVO')), 0, 
            output_field=DecimalField()
        ),
        transferencias=Coalesce(
            Sum('total', filter=Q(metodo_pago='TRANSFERENCIA')), 0,
            output_field=DecimalField()
        )
    )
    
    total_dia = stats['total_dia']
    num_ventas = stats['num_ventas']
    ticket_promedio = total_dia / num_ventas if num_ventas > 0 else Decimal(0)

    # Paginación (tabla, filtrada)
    paginator = Paginator(ventas_hoy, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ultima_venta = ventas_hoy_base.first()

    # Productos para el modal de bajas
    productos_baja = Producto.objects.filter(stock_actual__gt=0).order_by('nombre')

    context = {
        'ventas': page_obj,
        'total_dia': total_dia,
        'ticket_promedio': ticket_promedio,
        'num_ventas': num_ventas,
        'total_efectivo': stats['efectivo'],
        'total_transferencias': stats['transferencias'],
        'fecha_hoy': ahora.date(),
        'sin_caja': False,
        'caja_activa': caja_activa,
        'hora_apertura': timezone.localtime(caja_activa.hora_apertura).strftime('%H:%M') if caja_activa.hora_apertura else 'N/A',
        'productos_baja': productos_baja,
        'es_responsable_caja': _es_responsable_de_caja(request.user, caja_activa),
        'puede_vender': _usuario_puede_vender(request.user, caja_activa),
        'ultima_venta': ultima_venta,
        'filtros': {
            'q': q,
            'metodo_pago': metodo_pago,
        },
    }

    return render(request, 'sales/sales_list.html', context)
@solo_vendedor
def nueva_venta(request):
    """
    GET /sales/nueva/
    
    Punto de Venta (POS). Permite crear y procesar nuevas ventas.
    
    Requisitos:
    - Caja debe estar abierta
    - Solo accesible para vendedores
    
    Muestra:
    - Productos disponibles ordenados por demanda
    - Promociones vigentes
    - Carrito de compras
    - Métodos de pago (efectivo/transferencia)
    """
    # Verificar caja abierta
    caja_activa = obtener_caja_activa(request.user)
    
    if not caja_activa or caja_activa.estado != 'Abierta':
        return render(request, 'sales/pos.html', {
            'error': '❌ Debes abrir caja primero para acceder al POS',
            'sin_caja': True,
            'puede_abrir_caja': True
        })

    puede_vender = _usuario_puede_vender(request.user, caja_activa)

    # Obtener productos ordenados por demanda
    productos = Producto.objects.filter(
        stock_actual__gt=0
    ).annotate(
        total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0)
    ).order_by('-total_vendido', 'nombre')
    
    categorias = Categoria.objects.all()
    
    # Obtener promociones vigentes
    from django.utils import timezone
    from apps.products.models import Promocion
    promociones = Promocion.objects.filter(
        activa=True,
        fecha_inicio__lte=timezone.now().date(),
        fecha_fin__gte=timezone.now().date()
    ).select_related('producto')
    
    return render(request, 'sales/pos.html', {
        'productos': productos,
        'categorias': categorias,
        'promociones': promociones,
        'sin_caja': False,
        'caja_activa': caja_activa,
        'es_responsable_caja': _es_responsable_de_caja(request.user, caja_activa),
        'puede_vender': puede_vender,
    })
@solo_vendedor
@require_http_methods(["POST"])
def procesar_venta(request):
    """
    POST /sales/api/procesar-venta/
    
    Procesa una nueva venta y la carga al carrito.
    
    Body JSON:
    {
        "carrito": [{"id": 1, "cantidad": 2, "precio": 10.00}, ...],
        "total": 20.00,
        "cliente": "Juan Pérez",
        "metodo_pago": "EFECTIVO",
        "banco": "Banco XYZ",      // Si es transferencia
        "codigo": "ABC123456"       // Si es transferencia
    }
    
    Validaciones:
    - Caja debe estar abierta
    - Stock suficiente
    - Monto total válido
    """
    if request.method == 'POST':
        try:
            # 1. Leer los datos enviados por JavaScript
            data = json.loads(request.body)
            carrito = data.get('carrito', [])
            total = Decimal(str(data.get('total', 0)))
            
            # Datos de la venta
            nombre_cliente = data.get('cliente', 'Consumidor Final')
            metodo_pago = data.get('metodo_pago', 'EFECTIVO')
            banco = data.get('banco')
            codigo_transferencia = data.get('codigo')
            metodo_pago = (metodo_pago or 'EFECTIVO').strip().upper()

            if not carrito:
                return JsonResponse({'error': 'El carrito está vacío'}, status=400)

            if total <= 0:
                return JsonResponse({'error': 'El total debe ser mayor a 0'}, status=400)

            if metodo_pago not in {'EFECTIVO', 'TRANSFERENCIA', 'CREDITO'}:
                return JsonResponse({'error': 'Método de pago inválido'}, status=400)

            nombre_cliente = (nombre_cliente or '').strip()
            if metodo_pago == 'CREDITO':
                if not nombre_cliente or nombre_cliente.lower() == 'consumidor final':
                    return JsonResponse({
                        'error': 'En crédito es obligatorio ingresar nombre y apellido del cliente.',
                        'code': 'CREDITO_REQUIERE_CLIENTE'
                    }, status=400)

            # 2. Buscar CAJA ACTIVA usando la función helper
            caja = obtener_caja_activa(request.user)
            
            if not caja:
                return JsonResponse({
                    'error': f'❌ No hay caja abierta. Por favor, abre una caja antes de realizar ventas.',
                    'code': 'NO_CAJA_ABIERTA'
                }, status=400)
            
            # Validar que la caja está realmente abierta
            if not caja.abierta or caja.estado != 'Abierta':
                return JsonResponse({
                    'error': f'La caja no está en estado Abierta. Ciérrala y abre una nueva.',
                    'code': 'CAJA_NO_ABIERTA'
                    }, status=400)

            if not _usuario_puede_vender(request.user, caja):
                return JsonResponse({
                    'error': 'No tienes permisos para registrar ventas. Solo el Vendedor Responsable puede confirmar ventas.',
                    'code': 'SOLO_RESPONSABLE_PUEDE_VENDER'
                }, status=403)

            # 3. TRANSACCIÓN SEGURA: Todo o nada
            with transaction.atomic():
                # A. Crear la cabecera de la Venta
                venta = Venta.objects.create(
                    caja=caja,
                    vendedor=request.user,
                    total=total,
                    cliente=nombre_cliente or 'Consumidor Final',
                    metodo_pago=metodo_pago,
                    banco_origen=banco if metodo_pago == 'TRANSFERENCIA' else None,
                    codigo_transferencia=codigo_transferencia if metodo_pago == 'TRANSFERENCIA' else None
                )
                
                # B. Si es crédito, crear el registro de crédito automáticamente
                if metodo_pago == 'CREDITO':
                    Credito.objects.create(
                        venta=venta,
                        cliente=nombre_cliente,
                        monto_total=total,
                        monto_pagado=0,
                        saldo_pendiente=total,
                        estado='PENDIENTE',
                        vendedor=request.user
                    )
                
                updated_stock = []
                # B. Registrar cada producto en DetalleVenta
                for item in carrito:
                    cantidad = int(item['cantidad'])
                    
                    # Verificar si es una promoción
                    es_promocion = item.get('es_promocion', False)
                    
                    if es_promocion:
                        # Es promoción: descontar stock del producto base
                        from apps.products.models import Promocion
                        try:
                            # Usar valor absoluto del ID de promoción
                            promocion_id = abs(item['promocion_id'])
                            promocion = Promocion.objects.get(id=promocion_id)
                            producto = Producto.objects.select_for_update().get(id=promocion.producto_id)
                            
                            if producto.stock_actual < cantidad:
                                raise ValueError(
                                    f"❌ Stock insuficiente para {producto.nombre} (promoción: {promocion.nombre}). "
                                    f"Disponible: {producto.stock_actual}, Solicitado: {cantidad}"
                                )
                            
                            producto._stock_motivo = 'VENTA_PROMO'
                            producto._stock_usuario = request.user
                            producto._stock_referencia = f"venta:{venta.id}/promo:{promocion.id}"
                            producto.stock_actual -= cantidad
                            producto.save()
                            
                            updated_stock.append({
                                'id': producto.id,
                                'stock_actual': producto.stock_actual,
                                'nota': f'Descontado por promoción: {promocion.nombre}'
                            })
                        except Promocion.DoesNotExist:
                            raise ValueError("Promoción no encontrada")
                        except Producto.DoesNotExist:
                            raise ValueError("Producto de la promoción no encontrado")
                    else:
                        # Producto normal: validar y descontar stock
                        producto = Producto.objects.select_for_update().get(id=item['id'])
                        if producto.stock_actual < cantidad:
                            raise ValueError(
                                f"❌ Stock insuficiente para {producto.nombre}. "
                                f"Disponible: {producto.stock_actual}, Solicitado: {cantidad}"
                            )

                    # Crear el detalle de venta (siempre se crea, para historial)
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio_unitario=Decimal(str(item['precio'])),
                        es_promocion=es_promocion,
                        promocion_id=item.get('promocion_id') if es_promocion else None
                    )

                    # El signal descontar_stock se ejecuta automáticamente para productos normales
                    # Para promociones ya descontamos arriba manualmente
                    if not es_promocion:
                        producto.refresh_from_db()
                        updated_stock.append({
                            'id': producto.id,
                            'stock_actual': producto.stock_actual
                        })

            # Si todo sale bien, respondemos con éxito
            return JsonResponse({
                'success': True, 
                'venta_id': venta.id,
                'cliente': venta.cliente,
                'total': float(total),
                'updated_stock': updated_stock,
                'mensaje': f'✅ Venta registrada exitosamente'
            })

        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Producto.DoesNotExist:
            return JsonResponse({'error': 'Producto no encontrado'}, status=404)
        except Exception as e:
            import traceback
            print(f"Error en procesar_venta: {e}")
            traceback.print_exc()
            logger.error(f"Error en procesar_venta: {e}")
            logger.error(traceback.format_exc())
            return JsonResponse({'error': f'Error interno del servidor: {type(e).__name__}: {str(e)}'}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)


# ==================== CIERRE DE CAJA ====================

@solo_vendedor
def formulario_cierre_caja(request):
    """
    GET /sales/cierre/
    
    Formulario para cerrar la caja del día.
    
    Muestra:
    - Monto inicial
    - Total de ventas en efectivo y transferencias
    - Monto teórico esperado
    - Campo para ingresar monto físico
    - Cálculo automático de diferencias
    """
    
    caja = obtener_caja_activa(request.user)
    
    if not caja or not caja.abierta or caja.estado != 'Abierta':
        return render(request, 'sales/cierre_caja.html', {
            'error': '❌ No hay caja abierta. Abre una caja antes de intentar cierre.',
            'sin_caja': True
        })

    if not _usuario_puede_vender(request.user, caja):
        return render(request, 'sales/cierre_caja.html', {
            'error': '⛔ Solo el Vendedor Responsable puede cerrar la caja.',
            'sin_caja': False
        }, status=403)
    
    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_dia = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Calcular datos
    ventas_efectivo = caja.ventas.filter(metodo_pago='EFECTIVO')
    total_efectivo = ventas_efectivo.aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
    
    total_transferencias = caja.ventas.filter(
        metodo_pago='TRANSFERENCIA'
    ).aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
    
    total_productos = DetalleVenta.objects.filter(
        venta__caja=caja
    ).aggregate(t=Coalesce(Sum('cantidad'), 0))['t']
    
    # Calcular gastos del día
    total_gastos = Gasto.objects.filter(caja=caja).aggregate(t=Coalesce(Sum('monto'), 0, output_field=DecimalField()))['t']
    
    # Calcular pagos de créditos cobrados en esta caja
    from apps.sales.models import PagoCredito, Credito
    creditos_de_caja = Credito.objects.filter(venta__caja=caja)
    total_pagos_credito = PagoCredito.objects.filter(
        credito__in=creditos_de_caja
    ).aggregate(t=Coalesce(Sum('monto'), 0, output_field=DecimalField()))['t']
    
    # El monto teórico debe considerar: inicial + efectivo + pagos_credito - gastos
    monto_teorico = caja.monto_inicial + total_efectivo + total_pagos_credito - total_gastos
    
    resumen = {
        'caja': caja,
        'monto_inicial': caja.monto_inicial,
        'total_efectivo': total_efectivo,
        'total_ventas': total_efectivo,
        'total_transferencias': total_transferencias,
        'total_gastos': total_gastos,
        'total_pagos_credito': total_pagos_credito,
        'monto_teorico': monto_teorico,
        'num_ventas': caja.ventas.count(),
        'total_productos': total_productos,
        'hora_apertura': timezone.localtime(caja.hora_apertura).strftime('%H:%M') if caja.hora_apertura else 'N/A',
        'sin_caja': False
    }
    
    return render(request, 'sales/cierre_caja.html', resumen)


@solo_vendedor
@require_http_methods(["POST"])
def procesar_cierre_caja(request):
    """
    POST /sales/api/procesar-cierre/
    
    Procesa el cierre de caja del día.
    
    Body JSON:
    {
        "monto_fisico": 500.50,
        "observaciones": "Descripción del cierre (opcional)"
    }
    
    Acciones:
    - Cierra la caja (estado='Cerrada')
    - Registra el monto físico vs teórico
    - Calcula diferencias
    - Genera registro de cierre en BD
    
    Al cerrar la caja, las "Ventas del Día" se reinician a 0 (nueva caja vacía).
    """
    try:
        data = json.loads(request.body)
        monto_fisico = Decimal(str(data.get('monto_fisico', 0)))
        observaciones = data.get('observaciones', '')
        
        # Obtener CAJA ACTIVA
        caja = obtener_caja_activa(request.user)
        
        if not caja or not caja.abierta or caja.estado != 'Abierta':
            return JsonResponse({
                'error': '❌ No hay caja abierta. Recarga la página e intenta de nuevo.',
                'code': 'NO_CAJA'
            }, status=400)

        if not _usuario_puede_vender(request.user, caja):
            return JsonResponse({
                'error': 'Solo el Vendedor Responsable puede cerrar la caja.',
                'code': 'SOLO_RESPONSABLE_PUEDE_CERRAR_CAJA'
            }, status=403)
        
        # Calcular totales para reconciliación
        total_efectivo = caja.ventas.filter(
            metodo_pago='EFECTIVO'
        ).aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
        
        total_transferencias = caja.ventas.filter(
            metodo_pago='TRANSFERENCIA'
        ).aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
        
        # Calcular total de gastos
        total_gastos = Gasto.objects.filter(
            caja=caja
        ).aggregate(t=Coalesce(Sum('monto'), 0, output_field=DecimalField()))['t']
        
        # Calcular total de pagos de créditos cobrados en esta caja
        from apps.sales.models import PagoCredito, Credito
        creditos_de_caja = Credito.objects.filter(venta__caja=caja)
        total_pagos_credito = PagoCredito.objects.filter(
            credito__in=creditos_de_caja
        ).aggregate(t=Coalesce(Sum('monto'), 0, output_field=DecimalField()))['t']
        
        # Cálculos incluyendo pagos de créditos
        # El efectivo en caja = inicial + ventas_efectivo + pagos_credito - gastos
        monto_teorico = caja.monto_inicial + total_efectivo + total_pagos_credito
        diferencia = monto_teorico - monto_fisico
        
        # Cálculo con gastos
        monto_teorico_final = monto_teorico - total_gastos
        diferencia_final = monto_teorico_final - monto_fisico
        
        # Contar productos vendidos
        total_productos = DetalleVenta.objects.filter(
            venta__in=caja.ventas.all()
        ).aggregate(t=Coalesce(Sum('cantidad'), 0))['t']
        
        # Crear registro de cierre de forma segura (transaction)
        with transaction.atomic():
            cierre = CierreCaja.objects.create(
                caja=caja,
                vendedor=request.user,
                monto_inicial=caja.monto_inicial,
                total_ventas_esperado=total_efectivo,
                monto_teorico=monto_teorico,
                monto_fisico_ingresado=monto_fisico,
                diferencia=diferencia,
                total_gastos=total_gastos,
                monto_teorico_final=monto_teorico_final,
                diferencia_final=diferencia_final,
                total_productos_vendidos=total_productos,
                total_transferencias=total_transferencias,
                total_pagos_credito=total_pagos_credito,
                cerrado=True
            )
            
            # Cerrar caja
            caja.abierta = False
            caja.estado = 'Cerrada'
            caja.monto_final_real = monto_fisico
            caja.save()
        
        # Determinar estado de reconciliación
        estado = 'balanceado'
        if diferencia > 0:
            estado = 'faltante'
        elif diferencia < 0:
            estado = 'sobrante'
        
        return JsonResponse({
            'success': True,
            'cierre_id': cierre.id,
            'diferencia': float(diferencia),
            'estado': estado,
            'mensaje': f'✅ Caja cerrada exitosamente',
            'redirect_url': f'/sales/cierre/{cierre.id}/'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except Exception as e:
        print(f"Error en procesar_cierre_caja: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@rol_requerido('admin', 'vendedor')
def ver_cierre_caja(request, cierre_id):
    """
    GET /sales/cierre/<id>/
    
    Muestra detalles del cierre de caja especificado.
    
    Admin puede ver cualquier cierre.
    Vendedor solo puede ver sus propios cierres.
    """
    try:
        # Admin puede ver cualquier cierre, vendedor solo los propios
        if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'admin':
            cierre = CierreCaja.objects.select_related('caja', 'vendedor').get(id=cierre_id)
        else:
            cierre = CierreCaja.objects.select_related('caja', 'vendedor').get(
                id=cierre_id,
                vendedor=request.user
            )
    except CierreCaja.DoesNotExist:
        return render(request, 'sales/detalle_cierre.html', {
            'error': 'Cierre de caja no encontrado o no tienes permiso para verlo'
        }, status=404)
    
    caja = cierre.caja
    
    # Obtener ventas con detalles
    ventas = caja.ventas.all().prefetch_related('detalles__producto').order_by('hora')
    
    # Obtener gastos de la caja
    gastos_list = caja.gastos.all().order_by('-fecha')
    
    # Agrupar productos vendidos
    productos_vendidos = {}
    for venta in ventas:
        for detalle in venta.detalles.all():
            key = detalle.producto.id
            if key not in productos_vendidos:
                productos_vendidos[key] = {
                    'nombre': detalle.producto.nombre,
                    'codigo': detalle.producto.code,
                    'cantidad': 0,
                    'precio_unitario': detalle.precio_unitario,
                    'subtotal': Decimal(0)
                }
            productos_vendidos[key]['cantidad'] += detalle.cantidad
            productos_vendidos[key]['subtotal'] += detalle.cantidad * detalle.precio_unitario
    
    context = {
        'cierre': cierre,
        'caja': caja,
        'ventas': ventas,
        'productos_vendidos': sorted(productos_vendidos.values(), key=lambda x: x['nombre']),
        'gastos_list': gastos_list,
        'num_ventas': ventas.count(),
        'diferencia_signo': '❌ FALTANTE' if cierre.diferencia_final > 0 else ('✅ BALANCEADO' if cierre.diferencia_final == 0 else '⬆️ SOBRANTE'),
    }
    
    return render(request, 'sales/detalle_cierre.html', context)


@rol_requerido('admin', 'vendedor')
def descargar_pdf_cierre(request, cierre_id):
    """
    GET /sales/cierre/<id>/pdf/
    
    Descarga un PDF profesional del cierre de caja.
    
    Incluye:
    - Información general (vendedor, fecha, hora)
    - Cálculo de reconciliación (monto inicial + ventas = teórico)
    - Estado (balanceado, faltante, sobrante)
    - Lista de productos vendidos
    - Resumen financiero
    """
    
    try:
        # Admin puede ver cualquier cierre, vendedor solo los propios
        if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'admin':
            cierre = CierreCaja.objects.select_related('caja', 'vendedor').get(id=cierre_id)
        else:
            cierre = CierreCaja.objects.select_related('caja', 'vendedor').get(
                id=cierre_id,
                vendedor=request.user
            )
    except CierreCaja.DoesNotExist:
        return JsonResponse({'error': 'Cierre no encontrado'}, status=404)
    
    caja = cierre.caja
    ventas = caja.ventas.all().prefetch_related('detalles__producto').order_by('hora')
    
    # Crear documento PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#22c55e'),
        spaceAfter=6,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=8,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # Título principal
    elements.append(Paragraph("🧾 CIERRE DE CAJA", title_style))
    elements.append(Spacer(1, 0.1*inch))
    
    # SECCIÓN 1: INFORMACIÓN GENERAL
    elements.append(Paragraph("1. INFORMACIÓN GENERAL", section_style))
    
    fecha_cierre_local = timezone.localtime(cierre.fecha_cierre) if timezone.is_aware(cierre.fecha_cierre) else cierre.fecha_cierre
    
    info_data = [
        ['Vendedor:', cierre.vendedor.get_full_name() or cierre.vendedor.username],
        ['Fecha de Cierre:', fecha_cierre_local.strftime('%d/%m/%Y a las %H:%M:%S')],
        ['Hora de Apertura:', timezone.localtime(caja.hora_apertura).strftime('%d/%m/%Y a las %H:%M:%S') if caja.hora_apertura else 'N/A'],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # SECCIÓN 2: CÁLCULOS DE RECONCILIACIÓN
    elements.append(Paragraph("2. CÁLCULO DE RECONCILIACIÓN", section_style))
    
    calc_data = [
        ['Concepto', 'Monto'],
        ['Monto Inicial en Caja', f"${float(cierre.monto_inicial):,.2f}"],
        ['+ Total Ventas (Efectivo)', f"${float(cierre.total_ventas_esperado):,.2f}"],
        ['= Subtotal', f"${float(cierre.monto_teorico):,.2f}"],
    ]
    
    # Agregar transferencias y pagos de crédito
    if cierre.total_transferencias and cierre.total_transferencias > 0:
        calc_data.append(['+ Total Transferencias', f"${float(cierre.total_transferencias):,.2f}"])
    
    if cierre.total_pagos_credito and cierre.total_pagos_credito > 0:
        calc_data.append(['+ Pagos Créditos Cobrados', f"${float(cierre.total_pagos_credito):,.2f}"])
    
    # Agregar gastos si existen
    if cierre.total_gastos and cierre.total_gastos > 0:
        calc_data.append(['- Total Gastos', f"(${float(cierre.total_gastos):,.2f})"])
        calc_data.append(['= MONTO TEÓRICO FINAL', f"${float(cierre.monto_teorico_final):,.2f}"])
    else:
        calc_data.append(['= MONTO TEÓRICO ESPERADO', f"${float(cierre.monto_teorico):,.2f}"])
    
    calc_data.append(['', ''])
    calc_data.append(['Monto Físico Ingresado', f"${float(cierre.monto_fisico_ingresado):,.2f}"])
    
    calc_table = Table(calc_data, colWidths=[3.5*inch, 2.5*inch])
    
    # Usar diferencia_final si hay gastos, sino diferencia original
    diff_display = cierre.diferencia_final if cierre.total_gastos and cierre.total_gastos > 0 else cierre.diferencia
    
    # Colorear según estado
    if diff_display == 0:
        status_color = colors.HexColor('#10b981')  # Verde - Balanceado
        status_text = "✓ BALANCEADO PERFECTAMENTE"
    elif diff_display > 0:
        status_color = colors.HexColor('#ef4444')  # Rojo - Faltante
        status_text = f"⚠ FALTANTE: ${float(diff_display):,.2f}"
    else:
        status_color = colors.HexColor('#3b82f6')  # Azul - Sobrante
        status_text = f"↑ SOBRANTE: ${abs(float(diff_display)):,.2f}"
    
    calc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 2), (0, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (0, 2), 11),
        ('TEXTCOLOR', (0, 2), (-1, 2), colors.HexColor('#22c55e')),
        ('BACKGROUND', (0, -3), (-1, -3), colors.HexColor('#ecf0f1')),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(calc_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # Mostrar estado
    status_style = ParagraphStyle(
        'Status',
        parent=styles['Normal'],
        fontSize=12,
        textColor=status_color,
        fontName='Helvetica-Bold',
        alignment=1
    )
    elements.append(Paragraph(status_text, status_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # SECCIÓN 3: GASTOS (si hay)
    if cierre.total_gastos and cierre.total_gastos > 0:
        elementos_gastos = cierre.caja.gastos.all().order_by('-fecha')
        if elementos_gastos.exists():
            elements.append(Paragraph("3. DETALLE DE GASTOS", section_style))
            
            gastos_data = [['#', 'Categoría', 'Descripción', 'Monto']]
            for idx, gasto in enumerate(elementos_gastos, 1):
                desc = gasto.descripcion[:30] if gasto.descripcion else '-'
                gastos_data.append([
                    str(idx),
                    gasto.get_categoria_display(),
                    desc,
                    f"${float(gasto.monto):,.2f}"
                ])
            gastos_data.append(['', '', 'TOTAL GASTOS', f"${float(cierre.total_gastos):,.2f}"])
            
            gastos_table = Table(gastos_data, colWidths=[0.4*inch, 1.3*inch, 2.5*inch, 1.2*inch])
            gastos_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('ALIGN', (2, 0), (2, -1), 'LEFT'),
                ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fee2e2')),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ]))
            elements.append(gastos_table)
            elements.append(Spacer(1, 0.2*inch))
            section_num = 4
        else:
            section_num = 3
    else:
        section_num = 3
    
    # SECCIÓN: PRODUCTOS VENDIDOS
    elements.append(Paragraph(f"{section_num}. PRODUCTOS VENDIDOS", section_style))
    
    productos_data = [['Producto', 'Cantidad', 'Precio Unit', 'Total']]
    productos_agg = {}
    
    for venta in ventas:
        for detalle in venta.detalles.all():
            nombre = detalle.producto.nombre
            if detalle.es_promocion:
                nombre = f"PROMO: {nombre}"
            
            key = (nombre, float(detalle.precio_unitario))
            if key not in productos_agg:
                productos_agg[key] = {'cantidad': 0, 'total': Decimal('0')}
            productos_agg[key]['cantidad'] += detalle.cantidad
            productos_agg[key]['total'] += detalle.cantidad * detalle.precio_unitario
    
    total_productos = 0
    total_monto_productos = Decimal('0')
    
    for (nombre, precio_unit), data in sorted(productos_agg.items()):
        productos_data.append([
            nombre[:30],
            str(data['cantidad']),
            f"${float(precio_unit):,.2f}",
            f"${float(data['total']):,.2f}"
        ])
        total_productos += data['cantidad']
        total_monto_productos += data['total']
    
    # Agregar fila de total
    productos_data.append([
        'TOTAL', str(total_productos), '', f"${float(total_monto_productos):,.2f}"
    ])
    
    productos_table = Table(productos_data, colWidths=[2.5*inch, 1*inch, 1.3*inch, 1.3*inch])
    productos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#22c55e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, -1), (-1, -1), 10),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f9f9f9')]),
    ]))
    elements.append(productos_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # SECCIÓN 4: RESUMEN FINANCIERO
    elements.append(Paragraph("4. RESUMEN FINANCIERO", section_style))
    
    summary_data = [
        ['Concepto', 'Monto'],
        ['Total Ventas (Efectivo)', f"${float(cierre.total_ventas_esperado):,.2f}"],
        ['Total Transferencias', f"${float(cierre.total_transferencias):,.2f}"],
        ['Productos Vendidos', f"{cierre.total_productos_vendidos} unidades"],
        ['Diferencia de Caja', f"${abs(float(cierre.diferencia)):,.2f}"],
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 3*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Pie de página
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#999999'),
        alignment=1
    )
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(
        f"Documento generado el {timezone.now().strftime('%d/%m/%Y %H:%M:%S')} | "
        f"Sistema de Gestión de Cajas | Confidencial",
        footer_style
    ))
    
    # Construir PDF
    doc.build(elements)
    
    # Retornar como descarga
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="cierre_caja_{cierre_id}.pdf"'
    return response


# ==================== SISTEMA DE TICKETS/RECIBOS ====================
from io import BytesIO
from decimal import Decimal
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

def ticket_venta_pdf(request, venta_id):
    try:
        # 1. Datos (Ajusta según tus modelos)
        venta = Venta.objects.get(id=venta_id)
        detalles = venta.detalles.all().prefetch_related('producto')
        
        buffer = BytesIO()
        # Papel 55mm
        doc = SimpleDocTemplate(
            buffer,
            pagesize=(55 * mm, 297 * mm),
            rightMargin=2 * mm,
            leftMargin=2 * mm,
            topMargin=2 * mm,
            bottomMargin=2 * mm,
        )

        elements = []
        styles = getSampleStyleSheet()

        # ── CONFIGURACIÓN MONOSPACIO ──────────────────────────────────────────
        CHARS = 32 

        def fmt(v): return f"${float(v):,.2f}"

        # CORRECCIÓN: Se agrega el parámetro 'color' a la función
        def mk_style(name, size=7, bold=False, align=0, leading=8, color=colors.black):
            return ParagraphStyle(
                name,
                fontName='Courier-Bold' if bold else 'Courier',
                fontSize=size,
                leading=leading,
                alignment=align, 
                textColor=color,  # Aquí se aplica el color
                wordWrap=None
            )

        S_NORMAL = mk_style('Normal', align=0)
        S_BOLD   = mk_style('Bold', bold=True, align=0)
        S_CENTER = mk_style('Center', align=1)
        S_TITLE  = mk_style('Title', size=9, bold=True, align=1, leading=10)
        S_TOTAL  = mk_style('Total', size=10, bold=True, align=1, leading=12)
        # Ahora S_PROMO funcionará correctamente
        S_PROMO  = mk_style('Promo', size=6, color=colors.HexColor('#2a6e3a'))

        # ── HELPERS DE ALINEACIÓN MANUAL ──────────────────────────────────────
        def line(char='-'): return char * CHARS
        
        def fit(txt, w, side='L'):
            txt = str(txt)[:w]
            return txt.ljust(w) if side == 'L' else txt.rjust(w)

        def kv(k, v):
            return fit(k, 12) + fit(v, 20, 'R')

        # ════════════════════════════════════════════════════════════════════════
        # CONSTRUCCIÓN DEL TICKET
        # ════════════════════════════════════════════════════════════════════════
        elements.append(Paragraph(line('='), S_CENTER))
        elements.append(Paragraph("BAR D'PAUL", S_TITLE))
        elements.append(Paragraph("RUC: 1234567890001", S_CENTER))
        elements.append(Paragraph("La Libertad", S_CENTER))
        elements.append(Paragraph("Tel: +593 99 999 9999", S_CENTER))
        elements.append(Paragraph(line('='), S_CENTER))
        
        elements.append(Paragraph("COMPROBANTE DE VENTA", mk_style('sub', size=6, align=1)))
        elements.append(Paragraph(f"<b>[ TICKET # {venta.id:05d} ]</b>", S_CENTER))
        elements.append(Paragraph(line('-'), S_CENTER))

        # INFO CLIENTE
        fecha_dt = timezone.localtime(venta.hora)
        elements.append(Paragraph(kv("Fecha:", fecha_dt.strftime('%d/%m/%Y')), S_NORMAL))
        elements.append(Paragraph(kv("Hora:", fecha_dt.strftime('%H:%M:%S')), S_NORMAL))
        elements.append(Paragraph(kv("Cajero:", (venta.vendedor.username)[:15]), S_NORMAL))
        elements.append(Paragraph(kv("Cliente:", (venta.cliente or 'Consumidor Final')[:15]), S_NORMAL))
        elements.append(Paragraph(line('-'), S_CENTER))

        # CABECERA PRODUCTOS
        # Ct(3) + Pr(13) + P/U(8) + Tot(8) = 32
        head = fit("Ct", 3) + fit("Producto", 13) + fit("P/U", 8, 'R') + fit("Total", 8, 'R')
        elements.append(Paragraph(head, S_BOLD))
        elements.append(Paragraph(line('-'), S_CENTER))

        subtotal_bruto = Decimal('0')
        descuento_total = Decimal('0')

        for d in detalles:
            p_orig = d.producto.precio_venta
            p_unit = d.precio_unitario
            total_f = p_unit * d.cantidad
            subtotal_bruto += (p_orig * d.cantidad)
            descuento_total += (p_orig * d.cantidad) - (p_unit * d.cantidad)

            nombre = f"*{d.producto.nombre[:10]}*" if d.es_promocion else d.producto.nombre[:12]
            
            item_row = (fit(f"{int(d.cantidad)}x", 4) + 
                        fit(nombre, 12) + 
                        fit(fmt(p_unit), 8, 'R') + 
                        fit(fmt(total_f), 8, 'R'))
            
            elements.append(Paragraph(item_row, S_NORMAL))
            if d.es_promocion:
                elements.append(Paragraph(fit("   [DESC aplicado]", 32, 'L'), S_PROMO))

        elements.append(Paragraph(line('-'), S_CENTER))

        # TOTALES
        if descuento_total > 0:
            elements.append(Paragraph(kv("Subtotal:", fmt(subtotal_bruto)), S_NORMAL))
            elements.append(Paragraph(kv("Descuento:", f"-{fmt(descuento_total)}"), S_PROMO))

        elements.append(Paragraph(line('='), S_CENTER))
        elements.append(Paragraph(f"TOTAL: {fmt(venta.total)}", S_TOTAL))
        elements.append(Paragraph(line('='), S_CENTER))

        # PAGO
        elements.append(Paragraph(kv("Metodo:", venta.metodo_pago), S_NORMAL))
        if venta.metodo_pago == 'EFECTIVO':
            rec = float(getattr(venta, 'monto_recibido', venta.total))
            elements.append(Paragraph(kv("Recibido:", fmt(rec)), S_NORMAL))

        # PIE
        elements.append(Paragraph(line('-'), S_CENTER))
        elements.append(Paragraph("Gracias por su compra!", S_CENTER))
        elements.append(Paragraph("Conserve su ticket", S_CENTER))
        elements.append(Spacer(1, 2*mm))
        elements.append(Paragraph("Sistema: Kevin Davila", mk_style('dev', size=5, align=1, color=colors.gray)))
        elements.append(Paragraph(line('='), S_CENTER))

        doc.build(elements)
        buffer.seek(0)
        return HttpResponse(buffer.getvalue(), content_type='application/pdf')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

# ==================== APIS PARA DASHBOARD ====================

@solo_administrador
def api_dashboard_admin(request):
    """
    GET /sales/api/dashboard/stats/
    
    API que devuelve datos para el dashboard administrativo.
    
    Retorna JSON con:
    - Ventas diarias (semana actual, lunes a domingo)
    - Top 5 productos
    - Stock bajo alertas
    - Estadísticas por método de pago (mes actual)
    - Totales: ventas, productos, vendedores (mes actual)
    
    Solo accesible por administradores.
    """
    ahora = timezone.now()
    
    # Semana actual (lunes a domingo según ISO)
    inicio_semana = ahora.date() - timedelta(days=ahora.weekday())
    fin_semana = inicio_semana + timedelta(days=6)
    
    # Mes actual
    inicio_mes = ahora.date().replace(day=1)
    if ahora.month == 12:
        fin_mes = ahora.date().replace(day=1, month=1, year=ahora.year + 1) - timedelta(days=1)
    else:
        fin_mes = ahora.date().replace(day=1, month=ahora.month + 1) - timedelta(days=1)
    
    # 1. VENTAS: semana actual (lunes a hoy)
    ventas_por_dia = Venta.objects.filter(
        hora__date__gte=inicio_semana,
        hora__date__lte=ahora.date()
    ).values('hora__date').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('hora__date')
    
    ventas_dict = {v['hora__date'].isoformat(): float(v['total'] or 0) for v in ventas_por_dia}
    labels_ventas = []
    datos_ventas = []
    
    # Solo días desde lunes hasta hoy
    dia_actual = inicio_semana
    while dia_actual <= ahora.date():
        labels_ventas.append(dia_actual.strftime('%Y-%m-%d'))
        datos_ventas.append(ventas_dict.get(dia_actual.isoformat(), 0))
        dia_actual += timedelta(days=1)
    
    # 2. TOP 5 PRODUCTOS (mes actual)
    top_productos = Producto.objects.annotate(
        total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0)
    ).order_by('-total_vendido')[:5]
    
    labels_top = [p.nombre for p in top_productos]
    datos_top = [p.total_vendido for p in top_productos]
    
    # 3. STOCK BAJO (menos de 10 unidades)
    stock_bajo = Producto.objects.filter(stock_actual__lt=10).count()
    stock_ok = Producto.objects.filter(stock_actual__gte=10).count()
    total_productos = stock_bajo + stock_ok
    
    # 4. MÉTODOS DE PAGO (mes actual)
    metodos = Venta.objects.filter(
        hora__date__gte=inicio_mes,
        hora__date__lte=fin_mes
    ).values('metodo_pago').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    )
    
    labels_metodos = [m['metodo_pago'] for m in metodos]
    datos_metodos_cantidad = [m['cantidad'] for m in metodos]
    datos_metodos_monto = [float(m['total'] or 0) for m in metodos]
    
    # 5. ESTADÍSTICAS GENERALES (mes actual)
    total_ventas_mes = Venta.objects.filter(
        hora__date__gte=inicio_mes,
        hora__date__lte=fin_mes
    ).aggregate(total=Coalesce(Sum('total'), 0))['total']
    total_productos_vendidos = sum(datos_top)
    num_vendedores = Caja.objects.filter(
        fecha__gte=inicio_mes
    ).values('responsable').distinct().count()
    
    # 6. BAJAS PENDIENTES
    bajas_pendientes = SolicitudBaja.objects.filter(estado='PENDIENTE').count()
    
    return JsonResponse({
        'success': True,
        'ventas_diarias': {
            'labels': labels_ventas,
            'datos': datos_ventas
        },
        'top_productos': {
            'labels': labels_top,
            'datos': datos_top
        },
        'stock': {
            'bajo': stock_bajo,
            'ok': stock_ok,
            'total': total_productos,
            'alertas': stock_bajo  # Número de productos con stock bajo
        },
        'metodos_pago': {
            'labels': labels_metodos,
            'cantidad': datos_metodos_cantidad,
            'monto': datos_metodos_monto
        },
        'gestiones_pendientes': {
            'bajas': bajas_pendientes
        },
        'totales': {
            'ventas_30dias': float(total_ventas_30dias),
            'productos_vendidos': total_productos_vendidos,
            'vendedores_activos': num_vendedores,
            'total_ordenes': Venta.objects.filter(hora__gte=hace_30_dias).count()
        }
    })


# ==================== APIs PARA GESTIÓN DE VENTAS ====================

@solo_vendedor
def api_detalle_venta(request, venta_id):
    """
    GET /sales/api/ventas/<id>/
    
    Retorna detalles de una venta específica (solo propia).
    
    Información incluida:
    - ID, cliente, fecha/hora
    - Método de pago (efectivo/transferencia)
    - Total y detalles de productos
    """
    try:
        caja_activa = obtener_caja_activa(request.user)
        if not caja_activa:
            return JsonResponse({'success': False, 'error': 'No hay caja activa'}, status=400)

        venta = Venta.objects.select_related('vendedor').prefetch_related(
            'detalles__producto'
        ).get(id=venta_id, caja=caja_activa)
        
        # Obtener detalles de productos
        detalles = venta.detalles.all()
        
        detalles_list = []
        for detalle in detalles:
            detalles_list.append({
                'id': detalle.id,
                'producto': detalle.producto.nombre,
                'codigo': detalle.producto.code,
                'cantidad': detalle.cantidad,
                'precio': float(detalle.precio_unitario),
                'subtotal': float(detalle.cantidad * detalle.precio_unitario)
            })
        
        return JsonResponse({
            'success': True,
            'id': venta.id,
            'cliente': venta.cliente,
            'fecha': venta.hora.strftime('%d/%m/%Y'),
            'hora': venta.hora.strftime('%H:%M'),
            'metodo_pago': venta.metodo_pago,
            'estatus': 'Completada',
            'total': float(venta.total),
            'detalles': detalles_list,
            'vendedor': venta.vendedor.get_full_name() or venta.vendedor.username
        })
    except Venta.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Venta no encontrada o no tienes permiso'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@solo_vendedor
@require_http_methods(["POST"])
def api_anular_venta(request, venta_id):
    """
    POST /sales/api/ventas/<id>/anular/
    
    Anula una venta y revierte el stock de productos.
    
    Acciones:
    - Restaura stock de todos los productos
    - Elimina la venta de forma segura (transacción)
    - Solo permite anular ventas propias
    """
    try:
        caja_activa = obtener_caja_activa(request.user)
        if not caja_activa:
            return JsonResponse({'success': False, 'error': 'No hay caja activa'}, status=400)

        if not _usuario_puede_vender(request.user, caja_activa):
            return JsonResponse({
                'success': False,
                'error': 'No tienes permisos para anular ventas.'
            }, status=403)

        venta = Venta.objects.select_for_update().get(
            id=venta_id,
            caja=caja_activa
        )

        # Transacción atómica para revertir stock
        with transaction.atomic():
            # Por cada producto vendido, restaurar stock
            detalles = venta.detalles.all()
            
            for detalle in detalles:
                producto = Producto.objects.select_for_update().get(id=detalle.producto_id)
                producto.stock_actual += detalle.cantidad
                producto.save()

            # Eliminar la venta
            venta.delete()

        return JsonResponse({
            'success': True,
            'message': f'✅ Venta #{venta_id} anulada correctamente.',
            'stock_restaurado': True
        })
    except Venta.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Venta no encontrada o no tienes permiso para anularla'
        }, status=404)
    except Exception as e:
        print(f"Error en api_anular_venta: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== MÓDULO DE REPORTES ====================

@rol_requerido('admin', 'vendedor')
def mis_reportes(request):
    """
    GET /sales/reportes/
    
    Módulo de reportes para vendedores y admins.
    Muestra historial completo de ventas con filtros.
    
    Filtros disponibles:
    - fecha_desde: YYYY-MM-DD
    - fecha_hasta: YYYY-MM-DD
    - cliente: búsqueda por nombre
    - metodo_pago: EFECTIVO o TRANSFERENCIA
    """
    # Admin ve todas las ventas, vendedor solo las de su caja activa
    if request.user.perfil.rol == 'admin':
        ventas = Venta.objects.select_related('caja', 'vendedor').prefetch_related('detalles__producto').order_by('-hora')
    else:
        caja_activa = obtener_caja_activa(request.user)
        ventas = Venta.objects.none()
        if caja_activa:
            ventas = Venta.objects.filter(
                caja=caja_activa
            ).select_related('caja', 'vendedor').prefetch_related('detalles__producto').order_by('-hora')

    # Aplicar filtros
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    cliente = request.GET.get('cliente')
    metodo_pago = request.GET.get('metodo_pago')

    if fecha_desde:
        ventas = ventas.filter(hora__date__gte=fecha_desde)
    if fecha_hasta:
        ventas = ventas.filter(hora__date__lte=fecha_hasta)
    if cliente:
        ventas = ventas.filter(cliente__icontains=cliente)
    if metodo_pago and metodo_pago.strip():
        ventas = ventas.filter(metodo_pago=metodo_pago)

    # Paginación
    paginator = Paginator(ventas, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Estadísticas
    from django.db.models import Avg
    stats_agg = ventas.aggregate(
        total_ventas=Coalesce(Sum('total'), Decimal(0), output_field=DecimalField()),
        num_ventas=Count('id'),
    )
    # Calcular promedio manualmente para evitar conflictos
    if stats_agg['num_ventas'] > 0:
        stats_agg['promedio'] = stats_agg['total_ventas'] / stats_agg['num_ventas']
    else:
        stats_agg['promedio'] = Decimal(0)
    stats_agg['total'] = stats_agg['total_ventas']
    
    stats = stats_agg

    return render(request, 'sales/reportes.html', {
        'ventas': page_obj,
        'stats': stats,
        'filtros': {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'cliente': cliente,
            'metodo_pago': metodo_pago,
        }
    })


@solo_vendedor
def api_caja_activa(request):
    """
    GET /sales/api/caja-activa/
    Devuelve el estado de la caja activa del usuario.
    """
    caja = obtener_caja_activa(request.user)
    if not caja:
        return JsonResponse({
            'activa': False,
            'caja_activa': False,
            'mensaje': 'No hay caja activa en el sistema.'
        })
    return JsonResponse({
        'activa': True,
        'caja_activa': True,  # alias para compatibilidad con JS/plantillas antiguas
        'caja_id': caja.id,
        'estado': caja.estado,
        'monto_inicial': float(caja.monto_inicial),
        'hora_apertura': timezone.localtime(caja.hora_apertura).strftime('%H:%M') if caja.hora_apertura else 'N/A',
        'responsable': caja.responsable.get_full_name() if hasattr(caja.responsable, 'get_full_name') else str(caja.responsable),
        'responsable_id': caja.responsable_id,
        'usuario_id': request.user.id,
        'es_responsable_caja': _es_responsable_de_caja(request.user, caja),
        'puede_vender': _usuario_puede_vender(request.user, caja),
    })


# ==================== GESTIÓN DE GASTOS ====================

@rol_requerido('admin', 'vendedor')
def listar_gastos(request):
    """
    GET /sales/gastos/
    Lista todos los gastos de la caja activa.
    """
    caja = obtener_caja_activa(request.user)
    
    if not caja:
        return render(request, 'sales/gastos_list.html', {
            'error': 'Debe abrir caja para registrar gastos',
            'sin_caja': True,
            'gastos': []
        })
    
    gastos = Gasto.objects.filter(caja=caja).order_by('-fecha')
    
    total_gastos = gastos.aggregate(total=Sum('monto'))['total'] or Decimal(0)
    
    return render(request, 'sales/gastos_list.html', {
        'gastos': gastos,
        'total_gastos': total_gastos,
        'sin_caja': False,
        'caja': caja,
    })


@rol_requerido('admin', 'vendedor')
@require_http_methods(["POST"])
def registrar_gasto(request):
    """
    POST /sales/api/gastos/
    Registra un nuevo gasto.
    """
    try:
        data = json.loads(request.body)
        
        categoria = data.get('categoria')
        descripcion = data.get('descripcion', '').strip()
        monto = Decimal(str(data.get('monto', 0)))
        
        if not categoria:
            return JsonResponse({'error': 'Seleccione una categoría'}, status=400)
        
        if monto <= 0:
            return JsonResponse({'error': 'El monto debe ser mayor a 0'}, status=400)
        
        caja = obtener_caja_activa(request.user)
        if not caja:
            return JsonResponse({'error': 'No hay caja abierta'}, status=400)
        
        with transaction.atomic():
            gasto = Gasto.objects.create(
                caja=caja,
                usuario=request.user,
                categoria=categoria,
                descripcion=descripcion,
                monto=monto
            )
        
        return JsonResponse({
            'success': True,
            'gasto_id': gasto.id,
            'mensaje': 'Gasto registrado correctamente'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except Exception as e:
        print(f"Error en registrar_gasto: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@rol_requerido('admin', 'vendedor')
def reportes_gastos(request):
    """
    GET /sales/gastos/reportes/
    Reportes de gastos por período.
    """
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    gastos = Gasto.objects.select_related('caja', 'usuario')
    
    if fecha_desde:
        gastos = gastos.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        gastos = gastos.filter(fecha__date__lte=fecha_hasta)
    
    # Agrupar por categoría
    por_categoria = gastos.values('categoria').annotate(
        total=Sum('monto'),
        cantidad=Count('id')
    ).order_by('-total')
    
    total_general = gastos.aggregate(total=Sum('monto'))['total'] or Decimal(0)
    
    return render(request, 'sales/gastos_reportes.html', {
        'gastos': gastos,
        'por_categoria': por_categoria,
        'total_general': total_general,
        'filtros': {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
        }
    })


@solo_administrador
def movimientos_auditoria(request):
    """
    GET /sales/movimientos/
    
    Módulo de auditoría que muestra todos los movimientos del sistema.
    Permite filtrar por tipo, acción, usuario y fecha.
    """
    from apps.sales.models import Movimiento
    
    movimientos = Movimiento.objects.select_related('usuario').order_by('-fecha')
    
    # Filtros
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    tipo = request.GET.get('tipo')
    accion = request.GET.get('accion')
    usuario_id = request.GET.get('usuario')
    busqueda = request.GET.get('q')
    
    if fecha_desde:
        movimientos = movimientos.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        movimientos = movimientos.filter(fecha__date__lte=fecha_hasta)
    if tipo:
        movimientos = movimientos.filter(tipo=tipo)
    if accion:
        movimientos = movimientos.filter(accion=accion)
    if usuario_id:
        movimientos = movimientos.filter(usuario_id=usuario_id)
    if busqueda:
        movimientos = movimientos.filter(descripcion__icontains=busqueda)
    
    # Paginación
    paginator = Paginator(movimientos, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Estadísticas
    stats = {
        'total_movimientos': movimientos.count(),
        'ventas': movimientos.filter(tipo='VENTA').count(),
        'cajas': movimientos.filter(tipo__in=['CAJA_APERTURA', 'CAJA_CIERRE']).count(),
        'gastos': movimientos.filter(tipo='GASTO').count(),
        'creditos': movimientos.filter(tipo='CREDITO').count(),
    }
    
    usuarios = User.objects.filter(is_active=True).order_by('username')
    
    return render(request, 'sales/movimientos.html', {
        'movimientos': page_obj,
        'stats': stats,
        'usuarios': usuarios,
        'filtros': {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tipo': tipo,
            'accion': accion,
            'usuario_id': usuario_id,
            'busqueda': busqueda,
        }
    })


# ==================== MÓDULO DE CRÉDITOS ====================

@rol_requerido('admin', 'vendedor')
def listar_creditos(request):
    """
    GET /sales/creditos/
    Lista todos los créditos del sistema (admin) o solo del vendedor (vendedor).
    """
    filtro_estado = request.GET.get('estado', '').strip()
    busqueda = request.GET.get('q', '').strip()
    
    creditos = Credito.objects.select_related('venta', 'vendedor')
    
    if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'vendedor':
        creditos = creditos.filter(vendedor=request.user)
    
    if filtro_estado:
        creditos = creditos.filter(estado=filtro_estado)
    
    if busqueda:
        creditos = creditos.filter(cliente__icontains=busqueda)
    
    # Estadísticas
    stats = {
        'total': creditos.count(),
        'pendientes': creditos.filter(estado='PENDIENTE').count(),
        'parciales': creditos.filter(estado='PARCIAL').count(),
        'pagados': creditos.filter(estado='PAGADO').count(),
        'total_pendiente': sum([c.saldo_pendiente for c in creditos.filter(estado__in=['PENDIENTE', 'PARCIAL'])]),
    }
    
    # Paginación
    paginator = Paginator(creditos, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'sales/creditos_list.html', {
        'creditos': page_obj,
        'stats': stats,
        'filtros': {
            'estado': filtro_estado,
            'q': busqueda,
        }
    })


@rol_requerido('admin', 'vendedor')
@require_http_methods(["POST"])
def registrar_pago_credito(request, credito_id):
    """
    POST /sales/api/creditos/<id>/pago/
    Registra un pago parcial o total para un crédito.
    """
    try:
        data = json.loads(request.body)
        monto = Decimal(str(data.get('monto', 0)))
        metodo_pago = data.get('metodo_pago', 'EFECTIVO')
        observaciones = data.get('observaciones', '').strip()
        
        if monto <= 0:
            return JsonResponse({'success': False, 'error': 'El monto debe ser mayor a 0'}, status=400)
        
        with transaction.atomic():
            try:
                credito = Credito.objects.select_for_update().get(id=credito_id)
            except Credito.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Crédito no encontrado'}, status=404)
            
            if credito.estado == 'PAGADO':
                return JsonResponse({'success': False, 'error': 'Este crédito ya está pagado'}, status=400)
            
            if monto > credito.saldo_pendiente:
                monto = credito.saldo_pendiente
            
            PagoCredito.objects.create(
                credito=credito,
                monto=monto,
                metodo_pago=metodo_pago,
                registrado_por=request.user,
                observaciones=observaciones
            )
            
            credito.monto_pagado += monto
            credito.saldo_pendiente -= monto
            credito.actualizar_estado()
        
        return JsonResponse({
            'success': True,
            'mensaje': f'Pago de ${monto} registrado correctamente',
            'credito': {
                'id': credito.id,
                'estado': credito.estado,
                'monto_pagado': float(credito.monto_pagado),
                'saldo_pendiente': float(credito.saldo_pendiente),
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Datos inválidos en la solicitud'}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error en registrar_pago_credito: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False, 
            'error': f'Error del servidor: {type(e).__name__}: {str(e)}'
        }, status=500)


@rol_requerido('admin', 'vendedor')
def detalle_credito(request, credito_id):
    """
    GET /sales/creditos/<id>/
    Muestra el detalle de un crédito con sus pagos.
    """
    try:
        credito = Credito.objects.select_related('venta', 'vendedor').prefetch_related('pagos__registrado_por').get(id=credito_id)
        
        if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'vendedor' and credito.vendedor_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'No tienes permiso para ver este crédito'}, status=403)
        
        pagos = credito.pagos.all().order_by('-fecha_pago')
        
        return render(request, 'sales/credito_detalle.html', {
            'credito': credito,
            'pagos': pagos,
        })
        
    except Credito.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Crédito no encontrado'}, status=404)


@rol_requerido('admin', 'vendedor')
@require_http_methods(["POST"])
def cancelar_credito(request, credito_id):
    """
    POST /sales/api/creditos/<id>/cancelar/
    Cancela un crédito (soloadmin o el vendedor que lo creó).
    """
    try:
        credito = Credito.objects.get(id=credito_id)
        
        if credito.estado == 'PAGADO':
            return JsonResponse({'success': False, 'error': 'No se puede cancelar un crédito ya pagado'}, status=400)
        
        if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'vendedor' and credito.vendedor_id != request.user.id:
            return JsonResponse({'success': False, 'error': 'No tienes permiso para cancelar este crédito'}, status=403)
        
        credito.estado = 'CANCELADO'
        credito.save()
        
        return JsonResponse({
            'success': True,
            'mensaje': 'Crédito cancelado correctamente',
            'credito_estado': credito.estado
        })
        
    except Credito.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Crédito no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== HISTORIAL DE CIERRES DE CAJA ====================

@rol_requerido('admin', 'vendedor')
def historial_cierres(request):
    """
    GET /sales/historial-cierres/
    Muestra el historial de todos los cierres de caja.
    Admin ve todos, vendedor ve los suyos.
    """
    cierres = CierreCaja.objects.select_related('caja', 'vendedor').order_by('-fecha_cierre')
    
    if hasattr(request.user, 'perfil') and request.user.perfil.rol == 'vendedor':
        cierres = cierres.filter(vendedor=request.user)
    
    # Estadísticas
    stats = {
        'total_cierres': cierres.count(),
        'total_efectivo': sum([c.total_ventas_esperado for c in cierres]),
        'total_gastos': sum([c.total_gastos or 0 for c in cierres]),
        'total_transferencias': sum([c.total_transferencias or 0 for c in cierres]),
    }
    
    # Paginación de 10 en 10
    paginator = Paginator(cierres, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'sales/historial_cierres.html', {
        'cierres': page_obj,
        'stats': stats,
    })


# ==================== REPORTE MENSUAL PDF ====================

import calendar as cal_module

@solo_administrador
def reporte_mensual_pdf(request, año, mes):
    """
    GET /sales/reporte-mensual/<año>/<mes>/pdf/
    
    Genera un PDF detallado del reporte mensual de ventas.
    Incluye:
    - Resumen general del mes
    - Rendimiento por vendedor (con desglose por método de pago)
    - Productos vendidos por vendedor
    """
    try:
        año = int(año)
        mes = int(mes)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)
    
    inicio_mes = timezone.make_aware(timezone.datetime(año, mes, 1))
    ultimo_dia = cal_module.monthrange(año, mes)[1]
    fin_mes = timezone.make_aware(timezone.datetime(año, mes, ultimo_dia, 23, 59, 59))
    
    ventas_mes = Venta.objects.filter(
        hora__gte=inicio_mes,
        hora__lte=fin_mes
    ).select_related('vendedor').prefetch_related('detalles__producto')
    
    total_mes = sum(float(v.total) for v in ventas_mes)
    num_ventas = ventas_mes.count()
    
    nombre_mes = cal_module.month_name[mes]
    
    vendedores_data = {}
    for venta in ventas_mes:
        vid = venta.vendedor_id
        if vid not in vendedores_data:
            vendedores_data[vid] = {
                'id': venta.vendedor_id,
                'nombre': venta.vendedor.get_full_name() or venta.vendedor.username,
                'num_ventas': 0,
                'total_generado': Decimal('0'),
                'por_metodo_pago': {
                    'EFECTIVO': Decimal('0'),
                    'TRANSFERENCIA': Decimal('0'),
                    'CREDITO': Decimal('0'),
                },
                'productos_dict': {},
            }
        
        vendedores_data[vid]['num_ventas'] += 1
        vendedores_data[vid]['total_generado'] += venta.total
        
        metodo = venta.metodo_pago or 'EFECTIVO'
        if metodo in vendedores_data[vid]['por_metodo_pago']:
            vendedores_data[vid]['por_metodo_pago'][metodo] += venta.total
        
        for detalle in venta.detalles.all():
            pid = detalle.producto_id
            if pid not in vendedores_data[vid]['productos_dict']:
                vendedores_data[vid]['productos_dict'][pid] = {
                    'nombre': detalle.producto.nombre,
                    'cantidad': 0
                }
            vendedores_data[vid]['productos_dict'][pid]['cantidad'] += detalle.cantidad
    
    vendedores_list = []
    for vdata in vendedores_data.values():
        productos = [
            {'nombre': p['nombre'], 'cantidad': p['cantidad']}
            for p in vdata['productos_dict'].values()
        ]
        productos.sort(key=lambda x: x['cantidad'], reverse=True)
        
        por_metodo = {
            k: float(v) for k, v in vdata['por_metodo_pago'].items()
        }
        
        vendedores_list.append({
            'id': vdata['id'],
            'nombre': vdata['nombre'],
            'num_ventas': vdata['num_ventas'],
            'total_generado': float(vdata['total_generado']),
            'por_metodo_pago': por_metodo,
            'productos': productos
        })
    
    vendedores_list.sort(key=lambda x: x['total_generado'], reverse=True)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#22c55e'),
        spaceAfter=4,
        alignment=1,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=12,
        textColor=colors.HexColor('#666666'),
        spaceAfter=10,
        alignment=1,
        fontName='Helvetica'
    )
    
    section_style = ParagraphStyle(
        'SectionTitle',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=6,
        spaceBefore=10,
        fontName='Helvetica-Bold'
    )
    
    vendedor_style = ParagraphStyle(
        'VendedorTitle',
        parent=styles['Heading3'],
        fontSize=11,
        textColor=colors.HexColor('#22c55e'),
        spaceAfter=4,
        spaceBefore=8,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#333333'),
        fontName='Helvetica'
    )
    
    elements.append(Paragraph("BAR D'PAUL", title_style))
    elements.append(Paragraph("Reporte Mensual de Ventas", subtitle_style))
    elements.append(Paragraph(f"Período: {nombre_mes} {año}", subtitle_style))
    elements.append(Spacer(1, 0.1*inch))
    
    elements.append(Paragraph("RESUMEN GENERAL", section_style))
    
    resumen_data = [
        ['Total del Mes', f"${total_mes:,.2f}"],
        ['Número de Ventas', str(num_ventas)],
        ['Vendedores Activos', str(len(vendedores_list))],
    ]
    
    resumen_table = Table(resumen_data, colWidths=[2*inch, 2*inch])
    resumen_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    elements.append(resumen_table)
    elements.append(Spacer(1, 0.2*inch))
    
    for vendedor in vendedores_list:
        elements.append(Paragraph(f"VENDEDOR: {vendedor['nombre'].upper()}", vendedor_style))
        
        vendedor_info = [
            [f"Total Generado: ${vendedor['total_generado']:,.2f}", f"Ventas: {vendedor['num_ventas']}"]
        ]
        info_table = Table(vendedor_info, colWidths=[2.5*inch, 2.5*inch])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f5e9')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.1*inch))
        
        elements.append(Paragraph("Desglose por Método de Pago:", normal_style))
        metodos_list = []
        por_metodo = vendedor['por_metodo_pago']
        for metodo, monto in por_metodo.items():
            if monto > 0:
                metodo_nombre = {
                    'EFECTIVO': 'Efectivo',
                    'TRANSFERENCIA': 'Transferencia',
                    'CREDITO': 'Crédito'
                }.get(metodo, metodo)
                metodos_list.append(f"  • {metodo_nombre}: ${monto:,.2f}")
        
        if metodos_list:
            for metodo_text in metodos_list:
                elements.append(Paragraph(metodo_text, normal_style))
        else:
            elements.append(Paragraph("  Sin ventas registradas", normal_style))
        
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Productos Vendidos:", normal_style))
        
        productos_data = [['Producto', 'Cantidad']]
        for producto in vendedor['productos']:
            productos_data.append([
                producto['nombre'][:40],
                str(producto['cantidad'])
            ])
        
        productos_table = Table(productos_data, colWidths=[4*inch, 1*inch])
        productos_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#22c55e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        elements.append(productos_table)
        elements.append(Spacer(1, 0.15*inch))
        
        subtotal_para = Paragraph(
            f"Subtotal {vendedor['nombre']}: ${vendedor['total_generado']:,.2f}",
            ParagraphStyle('Subtotal', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', alignment=2)
        )
        elements.append(subtotal_para)
        elements.append(Spacer(1, 0.2*inch))
    
    elements.append(Spacer(1, 0.1*inch))
    elements.append(Paragraph("_" * 80, normal_style))
    
    total_style = ParagraphStyle(
        'TotalGeneral',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#22c55e'),
        alignment=1
    )
    elements.append(Paragraph(f"TOTAL GENERAL DEL MES: ${total_mes:,.2f}", total_style))
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#999999'),
        alignment=1
    )
    elements.append(Spacer(1, 0.3*inch))
    elements.append(Paragraph(
        f"Documento generado el {timezone.now().strftime('%d/%m/%Y %H:%M:%S')} | Sistema de Gestión | BAR D'PAUL",
        footer_style
    ))
    
    doc.build(elements)
    
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="reporte_mensual_{nombre_mes}_{año}.pdf"'
    return response
