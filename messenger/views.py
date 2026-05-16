import json
import requests
from concurrent.futures import ThreadPoolExecutor
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .utils import process_whatsapp_message, send_whatsapp_message

@csrf_exempt
def whatsapp_webhook(request):
    """
    Official Meta WhatsApp Webhook.
    Handles verification (GET) and incoming messages (POST).
    """
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        if mode == 'subscribe' and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge)
        return HttpResponse("Verification failed", status=403)

    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            entry = data['entry'][0]
            changes = entry['changes'][0]
            value = changes['value']
            
            if 'messages' in value:
                message = value['messages'][0]
                phone_number = message['from']
                message_id = message['id']
                message_text = message.get('text', {}).get('body', '')

                # Extract Profile Name (WhatsApp Username)
                whatsapp_name = ""
                if 'contacts' in value:
                    whatsapp_name = value['contacts'][0].get('profile', {}).get('name', '')
                
                # 1. Mark as Read & Show Typing Indicator
                mark_message_as_read(message_id)
                
                # Process with AI
                reply_text = process_whatsapp_message(phone_number, message_text, whatsapp_name=whatsapp_name)
                
                # 3. Send reply back
                send_whatsapp_message(phone_number, reply_text)
            
        except (KeyError, IndexError):
            pass
            
        return HttpResponse("EVENT_RECEIVED")

def mark_message_as_read(message_id):
    """Sends a read receipt and shows 'typing...' status."""
    url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {
            "type": "text"
        }
    }
    resp = requests.post(url, headers=headers, json=payload)
    print(f"DEBUG: Read receipt & Typing response: {resp.status_code} - {resp.text}")
    return resp


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Conversation, Message, Block, Report
from accounts.models import User

# ... existing webhook views ...

@csrf_exempt
def chat_simulator(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        phone = data.get('phone', '')
        message = data.get('message', '')
        whatsapp_name = data.get('whatsapp_name', 'Test User')
        reply = process_whatsapp_message(phone, message, whatsapp_name=whatsapp_name)
        return JsonResponse({"reply": reply})
    return render(request, 'messenger/simulator.html')

@login_required
def inbox(request):
    conversations = request.user.conversations.all().prefetch_related('messages', 'participants')
    return render(request, 'messenger/inbox.html', {'conversations': conversations})

@login_required
def chat_view(request, conversation_id):
    conversation = get_object_or_404(Conversation, id=conversation_id, participants=request.user)
    
    messages = conversation.messages.all()
    # Mark as read
    messages.exclude(sender=request.user).update(is_read=True)
    
    partners = conversation.participants.exclude(id=request.user.id)
    is_group = partners.count() > 1
    
    # For single partner chats, keep existing logic for blocking/reporting
    partner = partners.first() if not is_group else None
    is_blocked_by_me = False
    is_blocked = False
    
    if partner:
        is_blocked_by_me = Block.objects.filter(blocker=request.user, blocked=partner).exists()
        is_blocked = Block.is_blocked(request.user, partner)

    return render(request, 'messenger/chat.html', {
        'conversation': conversation, 
        'messages': messages,
        'partner': partner,
        'partners': partners,
        'is_group': is_group,
        'is_blocked_by_me': is_blocked_by_me,
        'is_blocked': is_blocked,
    })

@login_required
def start_chat(request, user_id):
    partner = get_object_or_404(User, id=user_id)
    if partner == request.user:
        return redirect('messenger:inbox')

    # Prevent starting chat with blocked users
    if Block.is_blocked(request.user, partner):
        return redirect('messenger:inbox')
        
    # Check if conversation already exists
    conversation = Conversation.objects.filter(participants=request.user).filter(participants=partner).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, partner)
        
    return redirect('messenger:chat_view', conversation_id=conversation.id)

@login_required
def block_user(request, user_id):
    if request.method == 'POST':
        target = get_object_or_404(User, id=user_id)
        block, created = Block.objects.get_or_create(blocker=request.user, blocked=target)
        if not created:
            # Already blocked — unblock
            block.delete()
    # Redirect back to the conversation if possible
    conv = Conversation.objects.filter(participants=request.user).filter(participants__id=user_id).first()
    if conv:
        return redirect('messenger:chat_view', conversation_id=conv.id)
    return redirect('messenger:inbox')

@login_required
def report_user(request, user_id):
    reported_user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        reason = request.POST.get('reason')
        details = request.POST.get('details', '')
        Report.objects.create(reporter=request.user, reported_user=reported_user, reason=reason, details=details)
    return redirect('accounts:teacher_profile', profile_id=reported_user.profile.id)

@login_required
def bulk_onboard(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
        
    results = []
    if request.method == 'POST':
        raw_data = request.POST.get('bulk_data', '')
        from .utils import parse_bulk_onboarding_data, send_whatsapp_message
        from .models import WhatsAppState
        
        parsed_entries = parse_bulk_onboarding_data(raw_data)
        print(f"DEBUG: Parsed {len(parsed_entries)} entries from AI: {parsed_entries}")
        
        def process_entry(entry):
            phone = str(entry.get('phone_number', ''))
            if not phone:
                return None
            
            # 1. Prepare context
            state, _ = WhatsAppState.objects.get_or_create(phone_number=phone)
            state.context_data['pre_parsed'] = {
                'current_location': entry.get('current_location'),
                'preferred_location': entry.get('preferred_location'),
                'subjects': entry.get('subjects'),
            }
            state.save()
            
            # 2. Craft message
            current = entry.get('current_location', 'your current station')
            preferred = entry.get('preferred_location', 'a new location')
            msg = f"Hello! 👋 SwapMate AI noticed you are looking for a swap from *{current}* to *{preferred}*.\n\n"
            msg += "We have many other teachers on our platform looking for similar swaps! I'd love to help you find a match.\n\n"
            msg += "Ready to find your match? (Reply with *START*)"
            
            # 3. Send message
            resp = send_whatsapp_message(phone, msg)
            
            return {
                'phone': phone,
                'status': 'Success' if resp.status_code < 300 else f'Failed ({resp.status_code})',
                'entry': entry,
                'debug_info': resp.text if resp.status_code >= 300 else ""
            }

        # Process in parallel (max 10 threads to avoid hitting Meta rate limits too hard)
        with ThreadPoolExecutor(max_workers=10) as executor:
            task_results = list(executor.map(process_entry, parsed_entries))
            results = [r for r in task_results if r is not None]

    return render(request, 'messenger/bulk_onboard.html', {'results': results})

@login_required
def whatsapp_admin(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
        
    from django.db.models import Max
    from .models import WhatsAppInteraction
    
    # Get all unique contacts, sorted by latest activity
    contacts_raw = WhatsAppInteraction.objects.values('phone_number').annotate(
        latest_activity=Max('created_at')
    ).order_by('-latest_activity')
    
    contacts = []
    for c in contacts_raw:
        last_msg = WhatsAppInteraction.objects.filter(
            phone_number=c['phone_number']
        ).order_by('-created_at').first()
        
        contacts.append({
            'phone': c['phone_number'],
            'latest': c['latest_activity'],
            'preview': last_msg.user_message[:30] + "..." if last_msg and last_msg.user_message else "No message"
        })
    
    selected_phone = request.GET.get('phone')
    messages = []
    if selected_phone:
        messages = WhatsAppInteraction.objects.filter(
            phone_number=selected_phone
        ).order_by('created_at')
        
    context = {
        'contacts': contacts,
        'selected_phone': selected_phone,
        'messages': messages
    }
    return render(request, 'messenger/whatsapp_admin.html', context)
