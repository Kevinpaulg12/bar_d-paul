from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from apps.sales.models import Caja, Venta, CierreCaja
from apps.products.models import Producto, SolicitudBaja
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal


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
    stock_bajo = Producto.objects.filter(stock_actual__lt=10).count()
    total_productos = Producto.objects.count()
    
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
    ventas_por_dia = Venta.objects.filter(
        hora__gte=hace_7_dias
    ).values('hora__date').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('hora__date')
    
    labels_ventas = [str(v['hora__date']) for v in ventas_por_dia]
    datos_ventas = [float(v['total'] or 0) for v in ventas_por_dia]
    
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
    }
    
    return render(request, 'dashboard_admin.html', context)


@login_required

def dashboard_vendedor(request):
    hoy = timezone.now().date()
    
    ventas_hoy = Venta.objects.filter(
        vendedor=request.user, 
        hora__date=hoy # Nota: Cambié 'fecha' por 'hora' ya que así se llama en tu modelo
    )
    
    # IMPORTANTE: Cambia 'suma_total' por algo único
    resultado = ventas_hoy.aggregate(valor_acumulado=Sum('total'))
    
    # Extraemos usando el nuevo nombre
    total_dia = resultado['valor_acumulado'] or 0
    
    context = {
        'total_dia': total_dia,
        'ventas_recientes': ventas_hoy.order_by('-hora')[:5],
    }
    
    return render(request, 'dashboard_vendedor.html', context)