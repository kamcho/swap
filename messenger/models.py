from django.db import models
from django.conf import settings

class Conversation(models.Model):
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='conversations')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation {self.id}"

    class Meta:
        ordering = ['-updated_at']

    def has_unread(self, user):
        return self.messages.filter(is_read=False).exclude(sender=user).exists()

    def unread_count(self, user):
        return self.messages.filter(is_read=False).exclude(sender=user).count()

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    text = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message from {self.sender.phone_number} at {self.created_at}"

    class Meta:
        ordering = ['created_at']


class Block(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocked_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')

    def __str__(self):
        return f"{self.blocker} blocked {self.blocked}"

    @staticmethod
    def is_blocked(user1, user2):
        """Check if either user has blocked the other."""
        return Block.objects.filter(
            models.Q(blocker=user1, blocked=user2) |
            models.Q(blocker=user2, blocked=user1)
        ).exists()


class Report(models.Model):
    REASON_CHOICES = [
        ('SPAM', 'Spam or scam'),
        ('HARASSMENT', 'Harassment or bullying'),
        ('FAKE', 'Fake profile'),
        ('INAPPROPRIATE', 'Inappropriate content'),
        ('OTHER', 'Other'),
    ]

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_made')
    reported_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reports_received')
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    details = models.TextField(blank=True)
    is_reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report: {self.reporter} → {self.reported_user} ({self.get_reason_display()})"

    class Meta:
        ordering = ['-created_at']

class WhatsAppInteraction(models.Model):
    STATUS_CHOICES = (
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    )
    phone_number = models.CharField(max_length=20)
    message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    user_message = models.TextField()
    ai_response = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    expects_reply = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Interaction with {self.phone_number} at {self.created_at} - {self.status}"

class WhatsAppState(models.Model):
    phone_number = models.CharField(max_length=20, unique=True)
    state = models.CharField(max_length=50, default='START') # START, ONBOARDING, IDLE
    is_opted_out = models.BooleanField(default=False)
    expects_reply = models.BooleanField(default=False)
    nudge_count = models.IntegerField(default=0)
    context_data = models.JSONField(default=dict) # To store temporary registration data
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"State of {self.phone_number}: {self.state}"

class WhatsAppMessageLog(models.Model):
    DIRECTION_CHOICES = (
        ('IN', 'Incoming'),
        ('OUT', 'Outgoing'),
    )
    STATUS_CHOICES = (
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    )
    phone_number = models.CharField(max_length=20)
    message_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    message_text = models.TextField()
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    is_bulk = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.direction} msg to/from {self.phone_number} - {self.status}"
    
    class Meta:
        ordering = ['-created_at']
