from django.shortcuts import redirect, render
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.contrib.auth.hashers import check_password, make_password
from django.urls import reverse_lazy
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from .decorators import solo_administrador


class LoginView(auth_views.LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('dashboard:panel')

    def form_valid(self, form):
        user = form.get_user()

        # Bloquear login si el perfil está desactivado (Perfil.is_active).
        # Django por defecto valida User.is_active, pero aquí el estado vive en Perfil.
        perfil = getattr(user, 'perfil', None)
        if perfil is not None and not perfil.is_active:
            form.add_error(None, 'Tu cuenta ha sido desactivada. Contacta al administrador.')
            return self.form_invalid(form)

        return super().form_valid(form)
    
    def form_invalid(self, form):
        # Verificar si el usuario existe pero está desactivado
        username = form.cleaned_data.get('username')
        if username:
            try:
                user = User.objects.get(username=username)
                if hasattr(user, 'perfil') and not user.perfil.is_active:
                    return self.render_to_response(self.get_context_data(
                        form=form,
                        error='Tu cuenta ha sido desactivada. Contacta al administrador.'
                    ))
            except User.DoesNotExist:
                pass
        return super().form_invalid(form)

@login_required
def logout_view(request):
    auth_logout(request)
    return redirect('users:login')


@login_required
def perfil_view(request):
    """
    GET/POST /cuentas/perfil/
    Muestra y edita el perfil del usuario actual, incluyendo cambio de contraseña.
    """
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'cambiar_password':
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')
            
            if not check_password(current_password, user.password):
                messages.error(request, 'La contraseña actual es incorrecta.')
            elif len(new_password) < 8:
                messages.error(request, 'La nueva contraseña debe tener al menos 8 caracteres.')
            elif new_password != confirm_password:
                messages.error(request, 'Las contraseñas nuevas no coinciden.')
            else:
                user.password = make_password(new_password)
                user.save()
                messages.success(request, 'Contraseña cambiada exitosamente.')
                return redirect('users:perfil')
        
        elif action == 'actualizar_perfil':
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            user.email = request.POST.get('email', '')
            user.save()
            messages.success(request, 'Perfil actualizado exitosamente.')
            return redirect('users:perfil')
    
    return render(request, 'users/perfil.html', {
        'user': user,
    })


@solo_administrador
def listar_usuarios(request):
    """
    GET /admin/usuarios/
    Lista todos los usuarios del sistema con sus perfiles.
    """
    usuarios = User.objects.select_related('perfil').order_by('-date_joined')
    total_usuarios = usuarios.count()
    total_admins = usuarios.filter(perfil__rol='admin').count()
    total_vendedores = usuarios.filter(perfil__rol='vendedor').count()
    usuarios_activos = usuarios.filter(perfil__is_active=True).count()
    
    return render(request, 'users/list_users.html', {
        'usuarios': usuarios,
        'total_usuarios': total_usuarios,
        'total_admins': total_admins,
        'total_vendedores': total_vendedores,
        'usuarios_activos': usuarios_activos,
    })


@solo_administrador
def crear_usuario(request):
    """
    GET/POST /admin/usuarios/crear/
    Crea un nuevo usuario con perfil.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        rol = request.POST.get('rol', 'vendedor')
        tipo_vendedor = request.POST.get('tipo_vendedor', 'RESPONSABLE')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya existe.')
            return redirect('users:crear_usuario')
        
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            user.perfil.rol = rol
            if rol == 'vendedor':
                user.perfil.tipo_vendedor = tipo_vendedor
            user.perfil.save()
        
        messages.success(request, f'Usuario {username} creado exitosamente.')
        return redirect('users:listar_usuarios')
    
    return render(request, 'users/create_users.html')


@solo_administrador
@require_http_methods(["POST"])
def toggle_usuario(request, user_id):
    """
    POST /admin/usuarios/<id>/toggle/
    Activa o desactiva un usuario.
    """
    try:
        user = User.objects.get(id=user_id)
        
        # No permitir desactivar a sí mismo
        if user == request.user:
            return JsonResponse({
                'success': False,
                'error': 'No puedes desactivar tu propia cuenta'
            }, status=400)
        
        # No permitir desactivar al último admin
        if user.perfil.rol == 'admin':
            admin_count = User.objects.filter(perfil__rol='admin', perfil__is_active=True).count()
            if admin_count <= 1:
                return JsonResponse({
                    'success': False,
                    'error': 'No puedes desactivar al último administrador'
                }, status=400)
        
        # Toggle estado
        user.perfil.is_active = not user.perfil.is_active
        user.perfil.save()
        
        # Si se desactivó, cerrar sesión si está activo
        if not user.perfil.is_active and user == request.user:
            auth_logout(request)
        
        return JsonResponse({
            'success': True,
            'is_active': user.perfil.is_active,
            'mensaje': f'Usuario {"activado" if user.perfil.is_active else "desactivado"} correctamente'
        })
        
    except User.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Usuario no encontrado'
        }, status=404)
