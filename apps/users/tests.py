from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.core.cache import cache


class DisabledUserLoginTests(TestCase):
    def test_disabled_user_cannot_login_with_correct_password(self):
        user = User.objects.create_user(username='juan', password='Password123!')
        user.perfil.is_active = False
        user.perfil.save()

        response = self.client.post(
            reverse('users:login'),
            {'username': 'juan', 'password': 'Password123!'},
            follow=True,
        )

        self.assertContains(response, 'Tu cuenta ha sido desactivada', status_code=200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_disabled_user_is_logged_out_by_middleware(self):
        user = User.objects.create_user(username='maria', password='Password123!')
        self.client.force_login(user)

        user.perfil.is_active = False
        user.perfil.save()

        response = self.client.get(reverse('dashboard:panel'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('users:login'), response['Location'])
        self.assertNotIn('_auth_user_id', self.client.session)


class UserCacheMiddlewareTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='pedro', password='Password123!')

    def tearDown(self):
        cache.clear()

    def test_user_activity_status_is_cached(self):
        self.client.force_login(self.user)
        
        # Al hacer un request por primera vez, se debería crear la caché
        cache_key = f"user_active_{self.user.id}"
        self.assertIsNone(cache.get(cache_key))
        
        response = self.client.get(reverse('dashboard:panel'))
        self.assertEqual(response.status_code, 302)
        
        # Validamos que se haya cacheado correctamente
        self.assertTrue(cache.get(cache_key))

    def test_cache_invalidation_on_profile_save(self):
        self.client.force_login(self.user)
        
        # Hacemos una petición para popular la caché
        self.client.get(reverse('dashboard:panel'))
        cache_key = f"user_active_{self.user.id}"
        self.assertTrue(cache.get(cache_key))

        # Modificamos el perfil para desactivar al usuario
        perfil = self.user.perfil
        perfil.is_active = False
        perfil.save()

        # Validamos que la señal post_save haya invalidado la caché inmediatamente
        self.assertIsNone(cache.get(cache_key))

        # El siguiente request del usuario debería ser capturado por el middleware
        response = self.client.get(reverse('dashboard:panel'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

