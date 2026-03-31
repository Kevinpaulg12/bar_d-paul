from django.contrib import admin
from .models import Perfil

@admin.register(Perfil)
class PerfilAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'rol', 'tipo_vendedor')
    list_filter = ('rol', 'tipo_vendedor')
