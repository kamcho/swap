from django import template

register = template.Library()

@register.filter
def has_unread(conversation, user):
    return conversation.has_unread(user)

@register.filter
def unread_count(conversation, user):
    return conversation.unread_count(user)

@register.filter
def get_partners(conversation, user):
    return conversation.participants.exclude(id=user.id)
