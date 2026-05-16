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
                reply_text, interaction = process_whatsapp_message(phone_number, message_text, whatsapp_name=whatsapp_name)
                
                # 3. Send reply back
                resp = send_whatsapp_message(phone_number, reply_text)
                if resp and resp.status_code < 300:
                    try:
                        data = resp.json()
                        if 'messages' in data and data['messages']:
                            msg_id = data['messages'][0].get('id')
                            interaction.message_id = msg_id
                            interaction.save()
                    except Exception:
                        pass
                
            elif 'statuses' in value:
                # Handle read receipts / delivery statuses
                status_obj = value['statuses'][0]
                msg_id = status_obj.get('id')
                status = status_obj.get('status') # sent, delivered, read, failed
                if msg_id and status:
                    from .models import WhatsAppMessageLog, WhatsAppInteraction
                    WhatsAppMessageLog.objects.filter(message_id=msg_id).update(status=status)
                    WhatsAppInteraction.objects.filter(message_id=msg_id).update(status=status)
            
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
        reply, _ = process_whatsapp_message(phone, message, whatsapp_name=whatsapp_name)
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
    stats = {}
    if request.method == 'POST':
        raw_data = request.POST.get('bulk_data', '')
        from .utils import parse_bulk_onboarding_data, send_whatsapp_message
        from .models import WhatsAppState
        
        parsed_entries = parse_bulk_onboarding_data(raw_data)
        print(f"DEBUG: Parsed {len(parsed_entries)} entries from AI: {parsed_entries}")
        
        def process_entry(entry):
            phone = str(entry.get('phone_number', '')).strip().replace("+", "").replace(" ", "")
            if phone.startswith('0') and len(phone) == 10:
                phone = "254" + phone[1:]
                
            if not phone:
                return None
            
            from .models import WhatsAppState, WhatsAppInteraction
            
            # 1. Skip if opted out
            state, _ = WhatsAppState.objects.get_or_create(phone_number=phone)
            if state.is_opted_out:
                return {'phone': phone, 'status': 'Skipped (Opted Out)', 'entry': entry}
            
            # 2. Skip if already contacted/onboarded
            if WhatsAppInteraction.objects.filter(phone_number=phone).exists():
                return {'phone': phone, 'status': 'Skipped (Already Contacted)', 'entry': entry}
            
            # 3. Prepare context
            state.context_data['pre_parsed'] = {
                'current_location': entry.get('current_location'),
                'preferred_location': entry.get('preferred_location'),
                'subjects': entry.get('subjects'),
            }
            state.save()
            
            # 4. Craft message
            name = (entry.get('name') or '').strip()
            salutation = f"Hi {name}" if name else "Hi there"
            current = entry.get('current_location') or 'your current station'
            preferred = entry.get('preferred_location') or 'a new location'
            
            msg = f"{salutation} — this is SwapMate. You recently expressed interest in finding a teaching position swap from *{current}* → *{preferred}*.\n\n"
            msg += "We're onboarding teachers now to build match lists. Reply *START* to continue.\n\n"
            msg += "Questions? Reply *HELP*. To stop: *STOP*"
            
            # 5. Send message
            template_vars = [
                {'name': 'name', 'value': name if name else "there"},
                {'name': 'current_location', 'value': current},
                {'name': 'preferred_location', 'value': preferred}
            ]
            resp = send_whatsapp_message(
                phone, 
                msg, 
                is_bulk=True,
                template_name='swapmate_onboard_v1',
                template_vars=template_vars
            )
            
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

        # Compute stats
        stats = {
            'total_parsed': len(parsed_entries),
            'total_processed': len(results),
            'success': sum(1 for r in results if r['status'] == 'Success'),
            'skipped_opted_out': sum(1 for r in results if 'Opted Out' in r['status']),
            'skipped_existing': sum(1 for r in results if 'Already Contacted' in r['status']),
            'failed': sum(1 for r in results if r['status'].startswith('Failed')),
        }

    return render(request, 'messenger/bulk_onboard.html', {'results': results, 'stats': stats})

@login_required
def whatsapp_admin(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
        
    from django.db.models import Max
    from .models import WhatsAppInteraction
    from .utils import send_whatsapp_message
    
    selected_phone = request.GET.get('phone')
    
    if request.method == 'POST' and selected_phone:
        reply_text = request.POST.get('reply_text')
        if reply_text:
            # 1. Send via WhatsApp API
            resp = send_whatsapp_message(selected_phone, reply_text)
            
            message_id = None
            if resp and resp.status_code < 300:
                try:
                    data = resp.json()
                    if 'messages' in data and data['messages']:
                        message_id = data['messages'][0].get('id')
                except: pass

            # 2. Log as a manual interaction
            WhatsAppInteraction.objects.create(
                phone_number=selected_phone,
                user_message="[Staff Reply]",
                ai_response=reply_text,
                message_id=message_id,
                status='sent' if message_id else 'failed'
            )
            return redirect(f"{request.path}?phone={selected_phone}")
    
    # Get all unique contacts, sorted by latest activity
    contacts_raw = WhatsAppInteraction.objects.values('phone_number').annotate(
        latest_activity=Max('created_at')
    ).order_by('-latest_activity')
    
    contacts = []
    from accounts.models import User
    from django.db.models import Count
    for c in contacts_raw:
        phone = c['phone_number']
        # Efficiently get last message and total count
        interactions_query = WhatsAppInteraction.objects.filter(phone_number=phone)
        last_msg = interactions_query.order_by('-created_at').first()
        msg_count = interactions_query.count()
        
        # Try to find associated user for completion score
        clean_phone = phone.replace("+", "").replace(" ", "")
        last_9 = clean_phone[-9:]
        user = User.objects.filter(Q(phone_number__contains=last_9)).first()
        
        # Get current state for expects_reply
        from .models import WhatsAppState
        state, _ = WhatsAppState.objects.get_or_create(phone_number=phone)
        
        name = "Unknown Teacher"
        completion = 0
        if user:
            name = f"{user.first_name} {user.last_name}".strip() or "No Name Set"
            if hasattr(user, 'profile'):
                completion = user.profile.get_completion_stats()['percentage']
        
        contacts.append({
            'phone': phone,
            'name': name,
            'completion': completion,
            'msg_count': msg_count,
            'latest': c['latest_activity'],
            'expects_reply': state.expects_reply,
            'preview': last_msg.ai_response[:30] + "..." if last_msg and last_msg.ai_response else "No message"
        })
    
    messages = []
    if selected_phone:
        messages = WhatsAppInteraction.objects.filter(
            phone_number=selected_phone
        ).order_by('created_at')
        
    context = {
        'contacts': contacts,
        'messages': messages,
        'selected_phone': selected_phone
    }
    return render(request, 'messenger/whatsapp_admin.html', context)

@login_required
def bulk_campaign_admin(request):
    if not request.user.is_staff:
        return redirect('accounts:dashboard')
        
    from django.db.models import Max
    from .models import WhatsAppMessageLog
    
    # Get all unique contacts from bulk messages, sorted by latest activity
    contacts_raw = WhatsAppMessageLog.objects.filter(is_bulk=True).values('phone_number').annotate(
        latest_activity=Max('created_at')
    ).order_by('-latest_activity')
    
    contacts = []
    for c in contacts_raw:
        last_msg = WhatsAppMessageLog.objects.filter(
            phone_number=c['phone_number'],
            is_bulk=True
        ).order_by('-created_at').first()
        
        contacts.append({
            'phone': c['phone_number'],
            'latest': c['latest_activity'],
            'preview': last_msg.message_text[:30] + "..." if last_msg and last_msg.message_text else "No message",
            'status': last_msg.status if last_msg else 'unknown'
        })
    
    selected_phone = request.GET.get('phone')
    messages = []
    if selected_phone:
        messages = WhatsAppMessageLog.objects.filter(
            phone_number=selected_phone,
            is_bulk=True
        ).order_by('created_at')
        
    context = {
        'contacts': contacts,
        'selected_phone': selected_phone,
        'messages': messages
    }
    
    return render(request, 'messenger/bulk_campaign_admin.html', context)
