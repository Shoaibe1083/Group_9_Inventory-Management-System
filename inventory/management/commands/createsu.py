from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create the default superuser (admin/admin123) if it does not exist.'

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username='admin').exists():
            self.stdout.write('Superuser "admin" already exists — skipping.')
            return
        User.objects.create_superuser(username='admin', email='admin@example.com', password='admin123')
        self.stdout.write(self.style.SUCCESS('Superuser created — username: admin, password: admin123'))
