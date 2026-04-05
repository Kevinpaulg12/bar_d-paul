from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


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
