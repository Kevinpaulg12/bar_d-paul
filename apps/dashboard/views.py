from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from apps.sales.models import Caja, Venta, CierreCaja
from apps.products.models import Producto, SolicitudBaja
from django.db.models import Sum, Count, Q, DecimalField, F
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import calendar


@login_required
def home(request):
    """
    Página de inicio simple - redirige según rol
    """
    try:
        if not hasattr(request.user, 'perfil'):
            from apps.users.models import Perfil
            Perfil.objects.get_or_create(usuario=request.user)
        
        if request.user.perfil.rol == 'admin':
            return redirect('dashboard:dashboard_admin')
        else:
            return redirect('dashboard:dashboard_vendedor')
    except Exception as e:
        return render(request, 'registration:login.html', {'error': str(e)})


@login_required
def dashboard_admin(request):
    """
    GET /dashboard/ (Para admin)
    
    Dashboard Pro Administrativo con:
    - Gráficos de ventas (últimos 7 y 30 días)
    - Top 5 productos más vendidos
    - Alertas de stock bajo
    - Solicitudes pendientes de baja
    - Actividad de vendedores
    """
    
    # Requerir rol admin: si no es admin, redirigir al dashboard del vendedor
    try:
        from apps.users.models import Perfil
        if not hasattr(request.user, 'perfil') or request.user.perfil is None:
            Perfil.objects.get_or_create(usuario=request.user)
    except Exception:
        # Si algo falla con el perfil, considerarlo no-admin
        return redirect('/')

    if request.user.perfil.rol != 'admin':
        return redirect('/')

    ahora = timezone.now()
    hace_7_dias = ahora - timedelta(days=7)
    hace_30_dias = ahora - timedelta(days=30)
    hoy = ahora.date()
    
    # ===== VENTAS =====
    # Últimas 7 días
    ventas_7dias = Venta.objects.filter(hora__gte=hace_7_dias).aggregate(
        total=Coalesce(Sum('total'), Decimal(0))
    )['total']
    
    # Últimos 30 días
    ventas_30dias = Venta.objects.filter(hora__gte=hace_30_dias).aggregate(
        total=Coalesce(Sum('total'), Decimal(0))
    )['total']
    
    # Hoy
    ventas_hoy = Venta.objects.filter(hora__date=hoy).aggregate(
        total=Coalesce(Sum('total'), Decimal(0))
    )['total']
    
    # ===== STOCK =====
    stock_bajo = Producto.objects.filter(stock_actual__lt=F('stock_minimo')).count()
    total_productos = Producto.objects.count()
    productos_stock_bajo = Producto.objects.filter(
        stock_actual__lt=F('stock_minimo')
    ).select_related('categoria').order_by('stock_actual')[:20]
    
    # ===== SOLICITUDES DE BAJA =====
    bajas_pendientes = SolicitudBaja.objects.filter(estado='PENDIENTE').count()
    bajas_hoy = SolicitudBaja.objects.filter(
        fecha_solicitud__date=hoy,
        estado='PENDIENTE'
    ).count()
    
    # ===== ACTIVIDAD DE VENDEDORES =====
    vendedores_hoy = Caja.objects.filter(fecha=hoy).count()
    vendedores_activos = Caja.objects.filter(
        fecha__gte=hace_7_dias.date()
    ).values('responsable').distinct().count()
    
    # ===== DATOS PARA GRÁFICOS =====
    # Obtener offset para paginación del gráfico (7 días por bloque)
    offset = int(request.GET.get('offset', 0))
    
    # Calcular rango de fechas para el bloque actual
    fecha_fin = ahora.date() - timedelta(days=offset)
    fecha_inicio = fecha_fin - timedelta(days=6)
    
    ventas_por_dia = Venta.objects.filter(
        hora__date__gte=fecha_inicio,
        hora__date__lte=fecha_fin
    ).values('hora__date').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('hora__date')
    
    ventas_dict = {v['hora__date'].isoformat(): float(v['total'] or 0) for v in ventas_por_dia}
    labels_ventas = []
    datos_ventas = []
    
    dias_semana_es = {
        'Monday': 'Lunes',
        'Tuesday': 'Martes',
        'Wednesday': 'Miércoles',
        'Thursday': 'Jueves',
        'Friday': 'Viernes',
        'Saturday': 'Sábado',
        'Sunday': 'Domingo'
    }

    for i in range(7):
        fecha = fecha_fin - timedelta(days=6-i)
        nombre_dia_en = fecha.strftime('%A')
        nombre_dia_es = dias_semana_es.get(nombre_dia_en, nombre_dia_en)
        labels_ventas.append(nombre_dia_es)
        datos_ventas.append(ventas_dict.get(fecha.isoformat(), 0))
    
    # Top 5 productos
    top_productos = Producto.objects.annotate(
        total_vendido=Coalesce(Sum('detalleventa__cantidad'), 0)
    ).filter(total_vendido__gt=0).order_by('-total_vendido')[:5]
    
    context = {
        'es_admin': True,
        'es_vendedor': False,
        # Totales
        'ventas_7dias': float(ventas_7dias),
        'ventas_30dias': float(ventas_30dias),
        'ventas_hoy': float(ventas_hoy),
        # Stock
        'stock_bajo': stock_bajo,
        'total_productos': total_productos,
        'productos_stock_bajo': productos_stock_bajo,
        # Bajas
        'bajas_pendientes': bajas_pendientes,
        'bajas_hoy': bajas_hoy,
        # Vendedores
        'vendedores_hoy': vendedores_hoy,
        'vendedores_activos': vendedores_activos,
        # Gráficos
        'labels_ventas': labels_ventas,
        'datos_ventas': datos_ventas,
        'top_productos': top_productos,
        # Paginación gráfico
        'chart_offset': offset,
        'chart_offset_next': offset + 7,
        'chart_offset_prev': max(0, offset - 7),
        'chart_fecha_inicio': fecha_inicio.strftime('%d/%m'),
        'chart_fecha_fin': fecha_fin.strftime('%d/%m'),
        'chart_has_prev': offset > 0,
    }
    
    return render(request, 'dashboard_admin.html', context)


@login_required

def dashboard_vendedor(request):
    """
    GET /dashboard/vendedor/

    `templates/dashboard_vendedor.html` muestra el estado de caja y métricas del día.
    Si estas keys no están en el context, la UI asume "caja cerrada" y ofrece abrir caja.
    """
    ahora = timezone.now()

    caja = Caja.objects.filter(
        abierta=True,
        estado='Abierta',
    ).order_by('-fecha', '-id').first()

    caja_abierta = bool(caja and caja.abierta and caja.estado == 'Abierta')

    inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_dia = ahora.replace(hour=23, minute=59, second=59, microsecond=999999)

    if caja_abierta:
        ventas_qs = caja.ventas.filter(
            vendedor=request.user,
            hora__range=(inicio_dia, fin_dia),
        )
    else:
        ventas_qs = Venta.objects.none()

    stats = ventas_qs.aggregate(
        total_dia=Coalesce(Sum('total'), Decimal(0), output_field=DecimalField()),
        num_ventas=Count('id'),
        total_efectivo=Coalesce(
            Sum('total', filter=Q(metodo_pago='EFECTIVO')),
            Decimal(0),
            output_field=DecimalField(),
        ),
        total_transferencias=Coalesce(
            Sum('total', filter=Q(metodo_pago='TRANSFERENCIA')),
            Decimal(0),
            output_field=DecimalField(),
        ),
    )

    total_dia = stats['total_dia']
    num_ventas = stats['num_ventas']
    ticket_promedio = (total_dia / num_ventas) if num_ventas else Decimal(0)

    context = {
        'caja_abierta': caja_abierta,
        'hora_apertura': timezone.localtime(caja.hora_apertura).strftime('%H:%M') if caja_abierta and caja.hora_apertura else 'N/A',
        'monto_inicial': caja.monto_inicial if caja_abierta else Decimal(0),
        'ventas_hoy': total_dia,
        'num_ventas': num_ventas,
        'total_efectivo': stats['total_efectivo'],
        'total_transferencias': stats['total_transferencias'],
        'ticket_promedio': ticket_promedio,
    }

    return render(request, 'dashboard_vendedor.html', context)


@login_required
def api_reporte_mensual(request):
    """
    GET /dashboard/api/reporte-mensual/?año=2026&mes=4
    
    API que devuelve datos para el reporte mensual.
    Incluye resumen general y rendimiento por vendedor activo en el mes.
    """
    try:
        año = int(request.GET.get('año', timezone.now().year))
        mes = int(request.GET.get('mes', timezone.now().month))
    except (ValueError, TypeError):
        año = timezone.now().year
        mes = timezone.now().month
    
    inicio_mes = timezone.make_aware(timezone.datetime(año, mes, 1))
    ultimo_dia = calendar.monthrange(año, mes)[1]
    fin_mes = timezone.make_aware(timezone.datetime(año, mes, ultimo_dia, 23, 59, 59))
    
    ventas_mes = Venta.objects.filter(
        hora__gte=inicio_mes,
        hora__lte=fin_mes
    ).select_related('vendedor').prefetch_related('detalles__producto')
    
    total_mes = sum(float(v.total) for v in ventas_mes)
    num_ventas = ventas_mes.count()
    
    nombre_mes = calendar.month_name[mes]
    
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
    
    return JsonResponse({
        'año': año,
        'mes': mes,
        'nombre_mes': nombre_mes,
        'total_mes': total_mes,
        'num_ventas': num_ventas,
        'vendedores': vendedores_list
    })
