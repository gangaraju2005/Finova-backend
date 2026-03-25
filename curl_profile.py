import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.test import RequestFactory
from users.views import ProfileView
from django.contrib.auth import get_user_model

User = get_user_model()
try:
    user = User.objects.get(email='karthikbisai003@gmail.com')
    from rest_framework.request import Request
    from rest_framework.test import force_authenticate

    factory = RequestFactory()
    django_request = factory.get('/api/auth/profile/')
    force_authenticate(django_request, user=user)
    
    view = ProfileView.as_view()
    response = view(django_request)
    print(json.dumps(response.data, indent=2))
except User.DoesNotExist:
    print("User not found")
except Exception as e:
    print(f"Error: {e}")
