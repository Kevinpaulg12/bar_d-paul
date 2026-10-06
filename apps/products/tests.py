from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.db import models
from apps.products.models import Categoria, Producto, SolicitudBaja


class ProductProtectionTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Bebidas", descripcion="Refrescos y aguas")
        self.producto = Producto.objects.create(
            nombre="Coca Cola 500ml",
            code="123456",
            categoria=self.categoria,
            costo_compra=0.80,
            precio_venta=1.20,
            stock_actual=10,
            stock_minimo=3
        )

    def test_category_deletion_is_protected(self):
        # Intentar borrar la categoría que tiene productos asociados debería lanzar ProtectedError
        with self.assertRaises(models.ProtectedError):
            self.categoria.delete()

        # Verificar que el producto sigue existiendo
        self.assertTrue(Producto.objects.filter(id=self.producto.id).exists())


class SolicitudBajaTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Snacks", descripcion="Papas y galletas")
        self.producto = Producto.objects.create(
            nombre="Doritos 150g",
            code="987654",
            categoria=self.categoria,
            costo_compra=1.00,
            precio_venta=1.50,
            stock_actual=20,
            stock_minimo=5
        )
        # Crear usuarios
        self.vendedor = User.objects.create_user(username="pedro_vend", password="Password123!")
        self.vendedor.perfil.rol = "vendedor"
        self.vendedor.perfil.tipo_vendedor = "RESPONSABLE"
        self.vendedor.perfil.save()

        self.admin = User.objects.create_superuser(username="admin_boss", password="Password123!")
        self.admin.perfil.rol = "admin"
        self.admin.perfil.save()

    def test_vendedor_can_solicitar_baja(self):
        self.client.force_login(self.vendedor)
        url = reverse('products:solicitar_baja_api')
        response = self.client.post(
            url,
            data={'producto_id': self.producto.id, 'cantidad': 5, 'motivo': 'Caducado'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        
        # Verificar que se creó la solicitud en estado PENDIENTE y que el stock NO ha cambiado aún
        baja = SolicitudBaja.objects.get(id=data['baja_id'])
        self.assertEqual(baja.estado, 'PENDIENTE')
        self.assertEqual(baja.solicitado_por, self.vendedor)
        self.assertEqual(self.producto.stock_actual, 20)

    def test_admin_can_aprobar_baja(self):
        # Crear la solicitud previamente
        baja = SolicitudBaja.objects.create(
            producto=self.producto,
            cantidad=4,
            motivo="Dañado",
            solicitado_por=self.vendedor,
            estado="PENDIENTE"
        )

        self.client.force_login(self.admin)
        url = reverse('products:aprobar_baja', args=[baja.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['stock_nuevo'], 16)

        # Verificar integridad en DB
        baja.refresh_from_db()
        self.assertEqual(baja.estado, 'APROBADO')
        self.assertEqual(baja.revisado_por, self.admin)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 16)

    def test_admin_can_rechazar_baja(self):
        baja = SolicitudBaja.objects.create(
            producto=self.producto,
            cantidad=3,
            motivo="Equivocado",
            solicitado_por=self.vendedor,
            estado="PENDIENTE"
        )

        self.client.force_login(self.admin)
        url = reverse('products:rechazar_baja', args=[baja.id])
        response = self.client.post(
            url,
            data={'comentario': 'No procede'},
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verificar que el stock NO cambió y la solicitud está rechazada
        baja.refresh_from_db()
        self.assertEqual(baja.estado, 'RECHAZADO')
        self.assertEqual(baja.revisado_por, self.admin)
        self.assertEqual(baja.comentario_admin, 'No procede')
        
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, 20)

