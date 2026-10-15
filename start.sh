#!/bin/sh
set -e
echo "Running database migrations..."
python manage.py migrate --noinput

echo "Creating superuser if it does not exist..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = 'admin'
password = 'admin123'
if not User.objects.filter(username=username).exists():
    user = User.objects.create_superuser(username=username, email='admin@example.com', password=password)
    if hasattr(user, 'role'):
        user.role = 'ADMIN'
        user.save()
    print('Superuser created successfully!')
"

echo "Starting server..."
exec uvicorn config.asgi:application --host 0.0.0.0 --port "${PORT:-8000}"
