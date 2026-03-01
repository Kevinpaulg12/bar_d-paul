from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required

@login_required
def logout_view(request):
    """
    Vista personalizada para cerrar sesión.
    Simplifica el logout y evita problemas de CSRF.
    """
    auth_logout(request)
    return redirect('users:login')
