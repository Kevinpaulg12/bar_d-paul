from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from apps.products.models import Producto, Categoria, SolicitudBaja
from apps.users.decorators import solo_vendedor, solo_administrador
import json
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.db.models import Sum, Count, DecimalField, Q, Avg
from django.db.models.functions import Coalesce
from .models import Caja, Venta, DetalleVenta, CierreCaja
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
    ahora = timezone.now()
    hoy = ahora.date()

    # Filtro unificado: Buscamos por responsable, estado y el flag booleano
    # He corregido DoesNotExist porque filter().first() es más seguro que get()
    caja = Caja.objects.filter(
        responsable=usuario,
        abierta=True,
        estado='Abierta'
    ).order_by('-fecha', '-id').first() # Trae la más reciente abierta

    return caja
@solo_vendedor
@require_http_methods(["POST"])
def abrir_caja(request):
    try:
        data = json.loads(request.body)
        monto_inicial = Decimal(str(data.get('monto_inicial', 0)))

        ahora = timezone.now()
        hoy = ahora.date()

        # VALIDACIÓN: Verificar si YA existe una caja abierta (de cualquier fecha)
        # Si el responsable tiene CUALQUIER caja con abierta=True, no dejamos crear otra
        caja_abierta = Caja.objects.filter(
            responsable=request.user,
            abierta=True
        ).exists()

        if caja_abierta:
            return JsonResponse({
                'error': 'Ya tienes una caja abierta. Debes cerrarla antes de abrir una nueva.',
                'code': 'CAJA_YA_ABIERTA'
            }, status=400)

        # CREACIÓN: Asegúrate de que los nombres de los campos sean exactos a tu modelo
        caja = Caja.objects.create(
            responsable=request.user,
            fecha=hoy,
            monto_inicial=monto_inicial,
            abierta=True,      # Este es el que busca el frontend
            estado='Abierta',   # Este es el que usas para etiquetas
            hora_apertura=ahora.time() # Asegúrate de que este campo exista en tu modelo
        )

        return JsonResponse({
            'success': True,
            'caja_id': caja.id,
            'mensaje': 'Caja abierta exitosamente'
        })
    # ... resto del catches
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)
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
        return render(request, 'sales/sales_list.html', {
            'error': '❌ Debe abrir caja para comenzar',
            'sin_caja': True,
            'puede_abrir_caja': True  # Mostrar botón de abrir caja
        })

    # Obtener el rango del día actual
    ahora = timezone.now()
    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_dia = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Filtrar SOLO por caja activa y rango de fecha
    ventas_hoy = caja_activa.ventas.filter(
        hora__range=(inicio_dia, fin_dia)
    ).order_by('-hora')

    # Calcular estadísticas del día
    stats = ventas_hoy.aggregate(
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

    # Paginación
    paginator = Paginator(ventas_hoy, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Productos para el modal de bajas
    productos_baja = Producto.objects.filter(stock_actual__gt=0).order_by('nombre')

    return render(request, 'sales/sales_list.html', {
        'ventas': page_obj,
        'total_dia': total_dia,
        'ticket_promedio': ticket_promedio,
        'num_ventas': num_ventas,
        'total_efectivo': stats['efectivo'],
        'total_transferencias': stats['transferencias'],
        'fecha_hoy': ahora.date(),
        'sin_caja': False,
        'caja_activa': caja_activa,
        'hora_apertura': caja_activa.hora_apertura.strftime('%H:%M') if caja_activa.hora_apertura else 'N/A',
        'productos_baja': productos_baja
    })
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
    
    # Obtener productos ordenados por demanda
    productos = Producto.objects.filter(
        stock_actual__gt=0
    ).annotate(
        total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0)
    ).order_by('-total_vendido', 'nombre')
    
    categorias = Categoria.objects.all()
    
    return render(request, 'sales/pos.html', {
        'productos': productos,
        'categorias': categorias,
        'sin_caja': False,
        'caja_activa': caja_activa
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

            if not carrito:
                return JsonResponse({'error': 'El carrito está vacío'}, status=400)

            if total <= 0:
                return JsonResponse({'error': 'El total debe ser mayor a 0'}, status=400)

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

            # 3. TRANSACCIÓN SEGURA: Todo o nada
            with transaction.atomic():
                # A. Crear la cabecera de la Venta
                venta = Venta.objects.create(
                    caja=caja,
                    vendedor=request.user,
                    total=total,
                    cliente=nombre_cliente,
                    metodo_pago=metodo_pago,
                    banco_origen=banco if metodo_pago == 'TRANSFERENCIA' else None,
                    codigo_transferencia=codigo_transferencia if metodo_pago == 'TRANSFERENCIA' else None
                )
                
                updated_stock = []
                # B. Registrar cada producto en DetalleVenta
                for item in carrito:
                    producto = Producto.objects.select_for_update().get(id=item['id'])
                    cantidad = int(item['cantidad'])
                    
                    # Validar stock
                    if producto.stock_actual < cantidad:
                        raise ValueError(
                            f"❌ Stock insuficiente para {producto.nombre}. "
                            f"Disponible: {producto.stock_actual}, Solicitado: {cantidad}"
                        )

                    # Crear el detalle de venta
                    DetalleVenta.objects.create(
                        venta=venta,
                        producto=producto,
                        cantidad=cantidad,
                        precio_unitario=Decimal(str(item['precio']))
                    )

                    # El signal descontar_stock se ejecuta automáticamente
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
            print(f"Error en procesar_venta: {e}")
            return JsonResponse({'error': 'Error interno del servidor'}, status=500)
            
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
    
    monto_teorico = caja.monto_inicial + total_efectivo
    
    resumen = {
        'caja': caja,
        'monto_inicial': caja.monto_inicial,
        'total_efectivo': total_efectivo,
        # Alias compatible con la plantilla antigua
        'total_ventas': total_efectivo,
        'total_transferencias': total_transferencias,
        'monto_teorico': monto_teorico,
        'num_ventas': caja.ventas.count(),
        'total_productos': total_productos,
        'hora_apertura': caja.hora_apertura.strftime('%H:%M'),
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
        
        # Calcular totales para reconciliación
        total_efectivo = caja.ventas.filter(
            metodo_pago='EFECTIVO'
        ).aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
        
        total_transferencias = caja.ventas.filter(
            metodo_pago='TRANSFERENCIA'
        ).aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField()))['t']
        
        monto_teorico = caja.monto_inicial + total_efectivo
        diferencia = monto_teorico - monto_fisico
        
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
                total_productos_vendidos=total_productos,
                total_transferencias=total_transferencias,
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


@solo_vendedor
def ver_cierre_caja(request, cierre_id):
    """
    GET /sales/cierre/<id>/
    
    Muestra detalles del cierre de caja especificado.
    
    El usuario solo puede ver cierres propios.
    """
    try:
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
        'num_ventas': ventas.count(),
        'diferencia_signo': '❌ FALTANTE' if cierre.diferencia > 0 else ('✅ BALANCEADO' if cierre.diferencia == 0 else '⬆️ SOBRANTE'),
    }
    
    return render(request, 'sales/detalle_cierre.html', context)


@solo_vendedor
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
    
    info_data = [
        ['Vendedor:', cierre.vendedor.get_full_name() or cierre.vendedor.username],
        ['Fecha de Cierre:', cierre.fecha_cierre.strftime('%d/%m/%Y a las %H:%M:%S')],
        ['Hora de Apertura:', caja.hora_apertura.strftime('%d/%m/%Y a las %H:%M:%S') if caja.hora_apertura else 'N/A'],
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
        ['= MONTO TEÓRICO ESPERADO', f"${float(cierre.monto_teorico):,.2f}"],
        ['', ''],
        ['Monto Físico Ingresado', f"${float(cierre.monto_fisico_ingresado):,.2f}"],
    ]
    
    calc_table = Table(calc_data, colWidths=[3.5*inch, 2.5*inch])
    
    # Colorear según estado
    if cierre.diferencia == 0:
        status_color = colors.HexColor('#10b981')  # Verde - Balanceado
        status_text = "✓ BALANCEADO PERFECTAMENTE"
    elif cierre.diferencia > 0:
        status_color = colors.HexColor('#ef4444')  # Rojo - Faltante
        status_text = f"⚠ FALTANTE: ${float(cierre.diferencia):,.2f}"
    else:
        status_color = colors.HexColor('#3b82f6')  # Azul - Sobrante
        status_text = f"↑ SOBRANTE: ${abs(float(cierre.diferencia)):,.2f}"
    
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
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#ecf0f1')),
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
    
    # SECCIÓN 3: PRODUCTOS VENDIDOS
    elements.append(Paragraph("3. PRODUCTOS VENDIDOS", section_style))
    
    productos_data = [['Código', 'Producto', 'Cantidad', 'Precio€', 'Subtotal']]
    total_productos = 0
    total_monto_productos = Decimal('0')
    
    for venta in ventas:
        for detalle in venta.detalles.all():
            subtotal = detalle.cantidad * detalle.precio_unitario
            productos_data.append([
                str(getattr(detalle.producto, 'code', detalle.producto.id)),
                detalle.producto.nombre[:25],  # Truncar nombre largo
                str(detalle.cantidad),
                f"${float(detalle.precio_unitario):,.2f}",
                f"${float(subtotal):,.2f}"
            ])
            total_productos += detalle.cantidad
            total_monto_productos += subtotal
    
    # Agregar fila de total
    productos_data.append([
        '', 'TOTAL', str(total_productos), '', f"${float(total_monto_productos):,.2f}"
    ])
    
    productos_table = Table(productos_data, colWidths=[0.8*inch, 2.2*inch, 1*inch, 1.2*inch, 1.2*inch])
    productos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#22c55e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
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

@solo_vendedor
def ticket_venta_pdf(request, venta_id):
    """
    GET /sales/api/venta/<id>/ticket/
    
    Genera PDF de recibo para impresora térmica (80mm).
    
    Incluye:
    - Header con datos del negocio y ticket
    - Información de venta (fecha, hora, cliente)
    - Lista de productos con cantidades y precios
    - Total y método de pago
    - Pie de página con vendedor
    - Formato de recibo (80mm x 200mm)
    """
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    try:
        venta = Venta.objects.get(id=venta_id, vendedor=request.user)
        detalles = venta.detalles.all().prefetch_related('producto')

        # Tamaño 80mm x 200mm (ancho x alto aproximado)
        buffer = BytesIO()
        pagesize = (80*mm, 250*mm)
        doc = SimpleDocTemplate(buffer, pagesize=pagesize,
                               rightMargin=2*mm, leftMargin=2*mm,
                               topMargin=3*mm, bottomMargin=3*mm)

        elements = []
        styles = getSampleStyleSheet()

        # Estilos personalizados para ticket
        ticket_title = ParagraphStyle(
            'TicketTitle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.black,
            alignment=1,
            fontName='Helvetica-Bold'
        )

        ticket_small = ParagraphStyle(
            'TicketSmall',
            parent=styles['Normal'],
            fontSize=6,
            textColor=colors.black,
            alignment=1
        )

        ticket_text = ParagraphStyle(
            'TicketText',
            parent=styles['Normal'],
            fontSize=7,
            textColor=colors.black,
            alignment=0
        )

        # 1. HEADER
        elements.append(Paragraph("════════════════", ticket_title))
        elements.append(Paragraph("<b>🧾 TICKET VENTA</b>", ticket_title))
        elements.append(Paragraph("════════════════", ticket_title))
        elements.append(Spacer(1, 1.5*mm))

        # Datos del negocio
        elements.append(Paragraph("<b>BAR D'PAUL</b>", ticket_title))
        elements.append(Paragraph("RUC: XXXXXXXXX", ticket_small))
        elements.append(Spacer(1, 1*mm))

        # 2. INFORMACIÓN DE VENTA
        info_data = [
            [f"<b>Ticket:</b> {venta.id}", f"<b>Fecha:</b> {venta.hora.strftime('%d/%m/%Y')}"],
            [f"<b>Hora:</b> {venta.hora.strftime('%H:%M')}", f"<b>Cliente:</b> {venta.cliente[:12]}"],
        ]

        info_table = Table(info_data, colWidths=[35*mm, 35*mm])
        info_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 1*mm))

        # 3. LÍNEA SEPARADORA
        elements.append(Paragraph("─" * 30, ticket_small))
        elements.append(Spacer(1, 0.5*mm))

        # 4. LISTA DE PRODUCTOS
        prod_data = [['Producto', 'Cant', 'Precio', 'Total']]

        for detalle in detalles:
            subtotal = detalle.cantidad * detalle.precio_unitario
            prod_data.append([
                detalle.producto.nombre[:15],
                str(detalle.cantidad),
                f"${detalle.precio_unitario:.2f}",
                f"${float(subtotal):.2f}"
            ])

        prod_table = Table(prod_data, colWidths=[20*mm, 8*mm, 12*mm, 14*mm])
        prod_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(prod_table)
        elements.append(Spacer(1, 1*mm))

        # 5. LÍNEA SEPARADORA
        elements.append(Paragraph("─" * 30, ticket_small))
        elements.append(Spacer(1, 0.5*mm))

        # 6. TOTALES
        total_data = [
            ['', '', '<b>TOTAL:</b>', f'<b>${float(venta.total):.2f}</b>'],
            ['', '', '<b>Método:</b>', venta.metodo_pago],
        ]

        total_table = Table(total_data, colWidths=[15*mm, 13*mm, 17*mm, 25*mm])
        total_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('FONTNAME', (2, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ]))
        elements.append(total_table)
        elements.append(Spacer(1, 1.5*mm))

        # 7. LÍNEA SEPARADORA
        elements.append(Paragraph("─" * 30, ticket_small))
        elements.append(Spacer(1, 1*mm))

        # 8. PIE DE PÁGINA
        elements.append(Paragraph(f"<b>Vendedor:</b> {venta.vendedor.get_full_name() or venta.vendedor.username}", ticket_small))
        elements.append(Paragraph("¡Gracias por su compra!", ticket_small))
        elements.append(Spacer(1, 0.5*mm))
        elements.append(Paragraph(f"{venta.hora.strftime('%d/%m/%Y %H:%M:%S')}", ticket_small))
        elements.append(Spacer(1, 1*mm))
        elements.append(Paragraph("════════════════", ticket_title))

        # BUILD PDF
        doc.build(elements)

        # Return Response
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="ticket_{venta_id}.pdf"'
        return response

    except Venta.DoesNotExist:
        return JsonResponse({'error': 'Venta no encontrada'}, status=404)
    except Exception as e:
        print(f"Error en ticket_venta_pdf: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# ==================== APIS PARA DASHBOARD ====================

@solo_administrador
def api_dashboard_admin(request):
    """
    GET /sales/api/dashboard/stats/
    
    API que devuelve datos para el dashboard administrativo.
    
    Retorna JSON con:
    - Ventas diarias (últimos 30 días)
    - Top 5 productos
    - Stock bajo alertas
    - Estadísticas por método de pago
    - Totales: ventas, productos, vendedores
    
    Solo accesible por administradores.
    """
    ahora = timezone.now()
    hace_30_dias = ahora - timedelta(days=30)
    
    # 1. VENTAS: últimos 30 días agrupadas por día
    ventas_por_dia = Venta.objects.filter(
        hora__gte=hace_30_dias
    ).values('hora__date').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('hora__date')
    
    # Convertir a formato gráfico
    labels_ventas = [str(v['hora__date']) for v in ventas_por_dia]
    datos_ventas = [float(v['total'] or 0) for v in ventas_por_dia]
    
    # 2. TOP 5 PRODUCTOS
    top_productos = Producto.objects.annotate(
        total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0)
    ).order_by('-total_vendido')[:5]
    
    labels_top = [p.nombre for p in top_productos]
    datos_top = [p.total_vendido for p in top_productos]
    
    # 3. STOCK BAJO (menos de 10 unidades)
    stock_bajo = Producto.objects.filter(stock_actual__lt=10).count()
    stock_ok = Producto.objects.filter(stock_actual__gte=10).count()
    total_productos = stock_bajo + stock_ok
    
    # 4. MÉTODOS DE PAGO
    metodos = Venta.objects.filter(
        hora__gte=hace_30_dias
    ).values('metodo_pago').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    )
    
    labels_metodos = [m['metodo_pago'] for m in metodos]
    datos_metodos_cantidad = [m['cantidad'] for m in metodos]
    datos_metodos_monto = [float(m['total'] or 0) for m in metodos]
    
    # 5. ESTADÍSTICAS GENERALES
    total_ventas_30dias = sum(datos_ventas)
    total_productos_vendidos = sum(datos_top)
    num_vendedores = Caja.objects.filter(
        fecha__gte=hace_30_dias.date()
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
        venta = Venta.objects.select_related('vendedor').prefetch_related(
            'detalles__producto'
        ).get(id=venta_id, vendedor=request.user)
        
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
        venta = Venta.objects.select_for_update().get(
            id=venta_id,
            vendedor=request.user
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

@solo_vendedor
def mis_reportes(request):
    """
    GET /sales/reportes/
    
    Módulo de reportes para vendedores.
    Muestra historial completo de ventas con filtros.
    
    Filtros disponibles:
    - fecha_desde: YYYY-MM-DD
    - fecha_hasta: YYYY-MM-DD
    - cliente: búsqueda por nombre
    - metodo_pago: EFECTIVO o TRANSFERENCIA
    """
    # Obtener todas las ventas del usuario
    ventas = Venta.objects.filter(
        vendedor=request.user
    ).select_related('caja').prefetch_related('detalles__producto').order_by('-hora')

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
    paginator = Paginator(ventas, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Estadísticas
    stats = ventas.aggregate(
        total=Coalesce(Sum('total'), Decimal(0), output_field=DecimalField()),
        num_ventas=Count('id'),
        promedio=Coalesce(Avg('total'), Decimal(0), output_field=DecimalField())
    )

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
            'mensaje': 'No hay caja activa para este usuario.'
        })
    return JsonResponse({
        'activa': True,
        'caja_id': caja.id,
        'estado': caja.estado,
        'monto_inicial': float(caja.monto_inicial),
        'hora_apertura': caja.hora_apertura.strftime('%H:%M') if caja.hora_apertura else 'N/A',
        'responsable': caja.responsable.get_full_name() if hasattr(caja.responsable, 'get_full_name') else str(caja.responsable)
    })