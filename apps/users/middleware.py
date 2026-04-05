from django.contrib.auth import logout
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


def _is_api_request(request):
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.headers.get('Content-Type') == 'application/json' or
        request.path.startswith('/api/') or
        request.path.startswith('/sales/api/')
    )


class ActiveUserRequiredMiddleware:
    """
    Si un usuario autenticado tiene Perfil.is_active=False, se le cierra sesión
    y se le bloquea el acceso a cualquier vista protegida.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            perfil = getattr(request.user, 'perfil', None)
            if perfil is not None and not perfil.is_active:
                logout(request)

                if _is_api_request(request):
                    return JsonResponse(
                        {
                            'success': False,
                            'error': 'Tu cuenta ha sido desactivada. Contacta al administrador.',
                            'code': 'USER_DISABLED',
                        },
                        status=403,
                    )

                # Evitar bucles: si ya está yendo a login/logout, permitir que la vista continúe.
                login_path = reverse('users:login')
                logout_path = reverse('users:logout')
                if request.path_info in (login_path, logout_path):
                    return self.get_response(request)

                messages.error(request, 'Tu cuenta ha sido desactivada. Contacta al administrador.')
                return redirect('users:login')

        return self.get_response(request)
