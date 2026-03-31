"""
Decoradores para control de acceso basado en roles (RBAC).
Proporciona funcionalidad robusta para restricción de vistas por rol de usuario.
"""

from functools import wraps
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def _is_api_request(request):
    """Determina si la solicitud es una API (espera respuesta JSON)."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type') == 'application/json' or
        request.path.startswith('/api/') or
        request.path.startswith('/sales/api/')
    )


def rol_requerido(*roles_permitidos):
    """
    Decorador que requiere que el usuario tenga uno de los roles especificados.
    
    Uso:
        @rol_requerido('admin')
        def mi_vista(request):
            ...
        
        @rol_requerido('admin', 'vendedor')
        def otra_vista(request):
            ...
    
    Retorna:
    - Para vistas normales: redirige a home si no tiene permiso
    - Para APIs JSON: retorna error 403 JSON
    """
    def decorador(vista_func):
        @wraps(vista_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            # Obtener perfil del usuario
            perfil = getattr(request.user, 'perfil', None)
            if not perfil:
                from apps.users.models import Perfil
                perfil, _ = Perfil.objects.get_or_create(usuario=request.user)
            
            rol_usuario = getattr(perfil, 'rol', None)
            
            # Verificar si el usuario tiene uno de los roles permitidos
            if rol_usuario not in roles_permitidos:
                # Si es una API, devolver JSON
                if _is_api_request(request):
                    return JsonResponse({
                        'success': False,
                        'error': f'Acceso denegado. Se requiere rol: {", ".join(roles_permitidos)}',
                        'code': 'PERMISSION_DENIED'
                    }, status=403)
                
                # Si no, redirigir a home
                raise PermissionDenied(f'Se requiere rol: {", ".join(roles_permitidos)}')
            
            # Pasar información de rol a la vista
            request.rol = rol_usuario
            request.es_admin = rol_usuario == 'admin'
            request.es_vendedor = rol_usuario == 'vendedor'
            
            return vista_func(request, *args, **kwargs)
        
        return wrapper
    return decorador


def solo_administrador(vista_func):
    """
    Alias corto para @rol_requerido('admin')
    
    Uso:
        @solo_administrador
        def dashboard_admin(request):
            ...
    """
    return rol_requerido('admin')(vista_func)


def solo_vendedor(vista_func):
    """
    Alias corto para @rol_requerido('vendedor')
    
    Uso:
        @solo_vendedor
        def punto_venta(request):
            ...
    """
    return rol_requerido('vendedor')(vista_func)


def rol_mixto(*roles):
    """
    Decorador alternativo para permitir múltiples roles.
    
    Uso:
        @rol_mixto('admin', 'supervisor')
        def vista_compartida(request):
            ...
    """
    return rol_requerido(*roles)

