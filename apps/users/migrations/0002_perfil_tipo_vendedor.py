
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfil',
            name='tipo_vendedor',
            field=models.CharField(
                choices=[('RESPONSABLE', 'Vendedor Responsable'), ('APOYO', 'Vendedor de Apoyo')],
                default='RESPONSABLE',
                max_length=20,
            ),
        ),
    ]

