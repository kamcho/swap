import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from messenger.models import WhatsAppState, WhatsAppInteraction
from messenger.utils import send_whatsapp_message, client
from django.conf import settings

class Command(BaseCommand):
    help = 'Sends automated follow-up messages (nudges) to teachers who haven\'t responded to the bot.'

    def handle(self, *args, **options):
        # Configuration
        HOURS_THRESHOLD = 6
        MAX_NUDGES = 2
        
        threshold_time = timezone.now() - timedelta(hours=HOURS_THRESHOLD)
        
        # 1. Find users who are stuck
        stuck_users = WhatsAppState.objects.filter(
            expects_reply=True,
            updated_at__lte=threshold_time,
            nudge_count__lt=MAX_NUDGES,
            is_opted_out=False
        )
        
        self.stdout.write(f"Found {stuck_users.count()} users needing a nudge.")
        
        for state in stuck_users:
            phone = state.phone_number
            
            # 2. Get context of the last interaction
            last_interaction = WhatsAppInteraction.objects.filter(phone_number=phone).order_by('-created_at').first()
            if not last_interaction:
                continue
            
            self.stdout.write(f"Nudging {phone} (Nudge #{state.nudge_count + 1})...")
            
            # 3. Ask AI to generate a GENTLE nudge based on the last thing it said
            try:
                nudge_prompt = f"""
                You are the SwapMate Assistant. You previously asked a teacher a question, but they haven't replied in over {HOURS_THRESHOLD} hours.
                
                YOUR LAST MESSAGE:
                "{last_interaction.ai_response}"
                
                TASK:
                Generate a very short, gentle, and professional nudge (max 2 sentences). 
                Do NOT apologize. Just ask if they are still interested or if they saw your previous question.
                Keep it helpful and friendly.
                
                IMPORTANT: Do NOT include any [EXPECTS_REPLY] tags here.
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "system", "content": nudge_prompt}],
                    temperature=0.7,
                    max_tokens=100
                )
                
                nudge_text = response.choices[0].message.content.strip()
                
                # 4. Send the message
                resp = send_whatsapp_message(phone, nudge_text)
                
                if resp and resp.status_code < 300:
                    # 5. Log the nudge as a bot response
                    WhatsAppInteraction.objects.create(
                        phone_number=phone,
                        user_message="[AUTOMATED NUDGE]",
                        ai_response=nudge_text,
                        expects_reply=True # We are still waiting
                    )
                    
                    # 6. Update state
                    state.nudge_count += 1
                    state.save()
                    self.stdout.write(self.style.SUCCESS(f"Successfully nudged {phone}"))
                else:
                    self.stdout.write(self.style.ERROR(f"Failed to nudge {phone}: {resp.text if resp else 'No response'}"))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error nudging {phone}: {str(e)}"))

        # 7. Clean up: If users reached MAX_NUDGES, mark as not expecting reply to stop future nudges
        # We also move them to a 'STALLED' state so admin can see
        final_stalled = WhatsAppState.objects.filter(
            expects_reply=True,
            nudge_count__gte=MAX_NUDGES
        )
        for state in final_stalled:
            state.expects_reply = False
            state.state = 'STALLED'
            state.save()
            self.stdout.write(self.style.WARNING(f"User {state.phone_number} reached max nudges. Marked as STALLED."))
