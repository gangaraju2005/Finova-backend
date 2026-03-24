import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth import get_user_model
from users.models import UserProfile

User = get_user_model()

def check_users():
    users = User.objects.all().order_by('-date_joined')[:5]
    result = []
    for u in users:
        p = getattr(u, 'profile', None)
        result.append({
            'email': u.email,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'is_verified': u.is_verified,
            'username': p.username if p else 'N/A',
            'phone_number': p.phone_number if p else 'N/A',
            'date_joined': u.date_joined.isoformat()
        })
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    check_users()
