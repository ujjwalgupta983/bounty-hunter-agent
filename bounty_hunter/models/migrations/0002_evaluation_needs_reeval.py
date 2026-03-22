from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bounty_models', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='evaluation',
            name='needs_reeval',
            field=models.BooleanField(default=False, help_text='AI analysis failed, using defaults'),
        ),
    ]
