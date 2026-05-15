from django.utils import timezone
from accounts.models import User

class LastSeenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Update last_seen only if it was more than 1 minute ago to save DB hits
            now = timezone.now()
            last_seen = request.user.last_seen
            
            if not last_seen or (now - last_seen).total_seconds() > 60:
                User.objects.filter(id=request.user.id).update(last_seen=now)
        
        response = self.get_response(request)
        return response
