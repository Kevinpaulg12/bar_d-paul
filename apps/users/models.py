from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class Perfil(models.Model):
    # Opciones de roles
    ROLES = (
        ('admin', 'Administrador'),
        ('vendedor', 'Vendedor'),
    )

    TIPOS_VENDEDOR = (
        ('RESPONSABLE', 'Vendedor Responsable'),
        ('APOYO', 'Vendedor de Apoyo'),
    )
    
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    rol = models.CharField(max_length=20, choices=ROLES, default='vendedor')
    # Sub-rol dentro de "vendedor": define permisos operativos (POS vs. solo impresión/consulta).
    tipo_vendedor = models.CharField(max_length=20, choices=TIPOS_VENDEDOR, default='RESPONSABLE')
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    def __str__(self):
        estado = "Activo" if self.is_active else "Desactivado"
        return f"{self.usuario.username} - {self.rol} ({estado})"

@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    """
    Signal que crea o actualiza el perfil cuando se guarda un usuario.
    Si es superuser o staff, asigna rol 'admin', sino 'vendedor'.
    """
    if created:
        # Determinar rol según si es admin o no
        rol = 'admin' if (instance.is_superuser or instance.is_staff) else 'vendedor'
        Perfil.objects.create(usuario=instance, rol=rol)
    else:
        # También actualizar si el usuario existente cambia su estado de admin
        if hasattr(instance, 'perfil'):
            nuevo_rol = 'admin' if (instance.is_superuser or instance.is_staff) else 'vendedor'
            if instance.perfil.rol != nuevo_rol:
                instance.perfil.rol = nuevo_rol
                instance.perfil.save()
