"""
Health check endpoint for ALB / Target Group.
"""
from django.http import JsonResponse


def health_check(request):
    """Returns 200 OK — used by ALB target group health checks."""
    return JsonResponse({"status": "ok"})
