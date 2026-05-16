import openai
import json
import requests
from django.conf import settings
from django.db.models import Q
from accounts.models import User, TeacherProfile, Subject, TeacherSubject, PreferredLocation
from locations.models import County, SubCounty, Ward
from .models import WhatsAppInteraction, WhatsAppState

client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

def send_whatsapp_message(to_phone, text, is_bulk=False, template_name=None, template_vars=None):
    """Sends a WhatsApp message via the Meta Graph API and logs it."""
    # Normalize phone number
    clean_phone = str(to_phone).strip().replace("+", "").replace(" ", "")
    if clean_phone.startswith('0') and len(clean_phone) == 10:
        clean_phone = "254" + clean_phone[1:]
    
    url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"}
    
    # If it's a template, we try common English codes as Meta can be picky
    language_codes = ['en_GB', 'en', 'en_US'] if (is_bulk and template_name) else [None]
    resp = None
    
    for lang_code in language_codes:
        if is_bulk and template_name:
            components = []
            if template_vars:
                parameters = []
                for v in template_vars:
                    if isinstance(v, dict) and 'name' in v:
                        parameters.append({"type": "text", "text": str(v['value']), "parameter_name": v['name']})
                    else:
                        parameters.append({"type": "text", "text": str(v)})
                components = [{"type": "body", "parameters": parameters}]
                
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": lang_code},
                    "components": components
                }
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "to": clean_phone,
                "type": "text",
                "text": {"body": text}
            }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            # If template exists in this language, we stop
            if resp.status_code < 300:
                break
            # If it's specifically a "template doesn't exist" error, try next language
            error_data = resp.json().get('error', {})
            if error_data.get('code') == 132001:
                continue
            else:
                break
        except Exception:
            if not resp: break # Connection error
            break

    # Log the message
    try:
        from .models import WhatsAppMessageLog
        message_id = None
        status = 'sent'
        log_text = text
        
        if resp and resp.status_code < 300:
            data = resp.json()
            if 'messages' in data and data['messages']:
                message_id = data['messages'][0].get('id')
        else:
            status = 'failed'
            # If it failed, append the error reason to the log text for the admin dashboard
            error_info = resp.text if resp else "Connection Timeout"
            log_text = f"{text}\n\nFAILED ({resp.status_code if resp else '??'}): {error_info}"
            
        WhatsAppMessageLog.objects.create(
            phone_number=clean_phone,
            message_id=message_id,
            message_text=log_text,
            direction='OUT',
            status=status,
            is_bulk=is_bulk
        )
    except Exception as e:
        print(f"Error logging WhatsApp message: {e}")
        
    return resp

# --- TOOLS DEFINITIONS ---

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Updates or creates the user's basic profile information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string", "description": "Official first name as per TSC"},
                    "last_name": {"type": "string", "description": "Official last name as per TSC"},
                    "school_name": {"type": "string", "description": "Full name of the current school"},
                    "level": {"type": "string", "enum": ["PRIMARY", "JSS", "SENIOR"], "description": "Academic level of the school"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_location",
            "description": "Sets the user's current working location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "county_name": {"type": "string"},
                    "sub_county_name": {"type": "string"},
                    "ward_name": {"type": "string"}
                },
                "required": ["county_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_subjects",
            "description": "Sets the subjects the teacher is registered to teach.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of subject names"
                    }
                },
                "required": ["subject_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_preferences",
            "description": "Sets the preferred counties the teacher wants to swap to.",
            "parameters": {
                "type": "object",
                "properties": {
                    "county_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of county names"
                    }
                },
                "required": ["county_names"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_matches",
            "description": "Searches for direct and triangle swap matches. Use 'temporary_counties' for one-time searches without updating permanent profile preferences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "temporary_counties": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of counties to search in for this specific request. Use this for 'Search Other Separately' or 'Search All Together'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_meeting_chat",
            "description": "Creates a virtual chat room for the user and their swap partners. Pass the MATCH_ID numbers shown in the match results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "match_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of MATCH_ID numbers from the get_matches results. Example: [1, 2]"
                    }
                },
                "required": ["match_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_support",
            "description": "Alerts an administrator that the user needs human assistance or customer support.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Specific reason why the user needs human help"}
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_opt_out",
            "description": "Unsubscribes the user from all WhatsApp communications and marks them as opted out.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# --- FUZZY SEARCH HELPERS ---

def get_best_match(model, field, value, filters=None):
    """Fuzzy search using difflib for handling typos and apostrophes (e.g. Muranga -> Murang'a)."""
    if not value: return None
    value = str(value).strip()
    qs = model.objects.all()
    if filters:
        qs = qs.filter(**filters)
    
    # 1. Try variations (strip 'county', etc.)
    clean_val = value.lower().replace('county', '').strip()
    search_terms = [value, clean_val, clean_val.replace("'", "")]
    
    for term in search_terms:
        # Try exact match first
        exact = qs.filter(**{f"{field}__iexact": term}).first()
        if exact: return exact
    
    # 2. If no exact match, use difflib to find the closest string
    all_names = list(qs.values_list(field, flat=True))
    import difflib
    matches = difflib.get_close_matches(clean_val, all_names, n=1, cutoff=0.6)
    
    if not matches:
        # Try one more time with the original value
        matches = difflib.get_close_matches(value, all_names, n=1, cutoff=0.6)
        
    if matches:
        return qs.filter(**{f"{field}__iexact": matches[0]}).first()
    
    return None

def contains_phone_number(text):
    """
    Detects potential phone numbers in text while avoiding false positives 
    from normal words like 'senior' or 'school'.
    """
    import re
    
    # 1. First, check for obvious digit sequences (with common separators)
    # This matches 07XXXXXXXX, 2547XXXXXXXX, etc.
    obvious_pattern = r'(?:\+?254|0)[17](?:[ \-\.]?\d){8}'
    if re.search(obvious_pattern, text):
        return True

    # 2. Check for hidden numbers (words or symbols)
    # We only normalize if we see a high density of potential number words
    clean = text.lower()
    
    # English/Swahili number words
    words = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'sifuri': '0', 'moja': '1', 'mbili': '2', 'tatu': '3', 'nne': '4',
        'tano': '5', 'sita': '6', 'saba': '7', 'nane': '8', 'tisa': '9'
    }
    
    # Only replace words if they are actually present
    word_count = 0
    for word, digit in words.items():
        if word in clean:
            clean = clean.replace(word, digit)
            word_count += 1
            
    # 3. Look for digit clusters (ignoring small numbers like "level 1")
    # We look for sequences of 8+ digits that might be separated by non-alphanumeric chars
    # We do NOT replace 'o' or 'i' globally anymore as it breaks normal words.
    
    # Extract just the "number-like" parts of the string
    potential_chunks = re.findall(r'(?:[\d\s\-\.\(\)]{8,})', clean)
    for chunk in potential_chunks:
        digits = re.sub(r'\D', '', chunk)
        # Kenyan numbers are typically 10 digits (07...) or 12 digits (2547...)
        if len(digits) >= 9 and len(digits) <= 13:
            # Check if it starts with Kenyan prefixes
            if digits.startswith('07') or digits.startswith('01') or digits.startswith('254'):
                return True
            # If it's just a long string of digits (like 712345678), block it too
            if len(digits) == 9 and (digits.startswith('7') or digits.startswith('1')):
                return True

    return False

# --- TOOL HANDLERS ---

def handle_update_profile(profile, **kwargs):
    user = profile.user
    if 'first_name' in kwargs: user.first_name = kwargs['first_name']
    if 'last_name' in kwargs: user.last_name = kwargs['last_name']
    user.save()
    
    if 'school_name' in kwargs: profile.school_name = kwargs['school_name']
    if 'level' in kwargs: profile.level = kwargs['level']
    profile.save()
    return "Profile updated successfully."

def handle_set_location(profile, county_name, sub_county_name=None, ward_name=None):
    print(f"DEBUG: Setting location for {profile.user.phone_number}: C={county_name}, SC={sub_county_name}, W={ward_name}")
    
    county = get_best_match(County, 'name', county_name)
    if not county: 
        print(f"DEBUG: County '{county_name}' not found.")
        return f"Could not find county named '{county_name}'."
    
    profile.county = county
    
    # 1. Update Sub-County if provided
    if sub_county_name:
        sub = get_best_match(SubCounty, 'name', sub_county_name, {'county': county})
        if sub:
            profile.sub_county = sub
            print(f"DEBUG: Sub-County set to {sub.name}")
        else:
            print(f"DEBUG: Sub-County '{sub_county_name}' not found in {county.name}")
    
    # 2. Update Ward if provided (requires a sub-county to be set on profile)
    if ward_name:
        current_sub = profile.sub_county
        if current_sub:
            ward = get_best_match(Ward, 'name', ward_name, {'subcounty': current_sub})
            if ward: 
                profile.ward = ward
                print(f"DEBUG: Ward set to {ward.name}")
            else:
                print(f"DEBUG: Ward '{ward_name}' not found in {current_sub.name}")
        else:
            print(f"DEBUG: Ward '{ward_name}' provided but no Sub-County is set.")
    
    profile.save()
    return f"Location successfully updated to {profile.county.name}, {profile.sub_county.name if profile.sub_county else 'N/A'}, {profile.ward.name if profile.ward else 'N/A'}."

def handle_set_subjects(profile, subject_names):
    if not profile.level: return "Please set your school level (Primary/JSS/Senior) first."
    
    found_subjects = []
    for name in subject_names:
        sub = get_best_match(Subject, 'name', name, {'level': profile.level} if profile.level != 'PRIMARY' else None)
        if sub: found_subjects.append(sub)
    
    if not found_subjects: return "None of the subjects were found. Please check spellings."
    
    profile.teaching_subjects.all().delete()
    for sub in found_subjects[:2]:
        TeacherSubject.objects.create(profile=profile, subject=sub)
    
    return f"Subjects updated: {', '.join([s.name for s in found_subjects])}"

def handle_set_preferences(profile, county_names):
    found_counties = []
    for name in county_names:
        c = get_best_match(County, 'name', name)
        if c: found_counties.append(c)
    
    if not found_counties: return "None of the counties were found."
    
    profile.preferred_locations.all().delete()
    for c in found_counties:
        PreferredLocation.objects.create(profile=profile, county=c)
    
    return f"Preferences updated: {', '.join([c.name for c in found_counties])}"

def mask_phone(phone):
    if not phone or len(phone) < 5: return phone
    return phone[:4] + "*" * (len(phone) - 5) + phone[-1:]

def handle_get_matches(profile, phone_number, temporary_counties=None):
    from accounts.services import get_potential_matches, get_triangle_matches
    
    # Enforce 3-county limit for searches
    if temporary_counties:
        temporary_counties = temporary_counties[:3]

    direct = get_potential_matches(profile, override_counties=temporary_counties)
    triangles = get_triangle_matches(profile, override_counties=temporary_counties)
    
    if not direct and not triangles:
        return "No matches found for your criteria yet. However, you shouldn't worry as new teachers register each and every day. When a potential swap is found you will be contacted automatically, but you are free to check for new possibilities daily!"
    
    # Build match registry to store server-side (phone numbers never sent to AI)
    match_registry = {}
    match_counter = 1
    
    res = f"Found {len(direct)} direct matches and {len(triangles)} triangle loops.\n\n"
    
    if direct:
        res += "Direct Matches:\n"
        for m in direct[:3]:
            masked = mask_phone(m.user.phone_number)
            match_registry[str(match_counter)] = m.user.phone_number
            res += f"- [MATCH_ID: {match_counter}] {m.user.first_name} at {m.school_name} ({m.county.name}) Phone: {masked}\n"
            match_counter += 1
    
    if triangles:
        res += "\nVerified Triangle Swap Loop Found:\n"
        for t in triangles[:3]:
            p1 = t['partner_1']
            p2 = t['partner_2']
            p1_masked = mask_phone(p1.user.phone_number)
            p2_masked = mask_phone(p2.user.phone_number)
            
            match_registry[str(match_counter)] = p1.user.phone_number
            res += f"- [MATCH_ID: {match_counter}] {p1.user.first_name} at {p1.school_name} ({p1.county.name}) Phone: {p1_masked}\n"
            match_counter += 1
            
            match_registry[str(match_counter)] = p2.user.phone_number
            res += f"- [MATCH_ID: {match_counter}] {p2.user.first_name} at {p2.school_name} ({p2.county.name}) Phone: {p2_masked}\n"
            match_counter += 1
            
            res += f"Loop: You -> {p1.county.name} (replacing {p1.user.first_name}), {p1.user.first_name} -> {p2.county.name} (replacing {p2.user.first_name}), {p2.user.first_name} -> {profile.county.name} (your old station).\n"
            res += f"Result: You end up at your preferred location ({p1.county.name}).\n\n"
    
    # Store match registry server-side so create_meeting_chat can look it up
    state_obj = WhatsAppState.objects.get(phone_number=phone_number)
    state_obj.context_data['match_registry'] = match_registry
    state_obj.save()
    
    res += f"\nTo open a chat with any match, use create_meeting_chat with their MATCH_ID number(s).\n"
    return res

def handle_create_meeting_chat(profile, phone_number, **kwargs):
    from accounts.models import User
    from .models import Conversation, Message
    
    match_ids = kwargs.get('match_ids')
    if not match_ids:
        return "Error: No match_ids provided. Pass the MATCH_ID numbers from the get_matches results."
    
    # Look up actual phone numbers from server-side stored registry
    state_obj = WhatsAppState.objects.get(phone_number=phone_number)
    match_registry = state_obj.context_data.get('match_registry', {})
    
    if not match_registry:
        return "Error: No match results found. Please run get_matches first to search for swap partners."
    
    participants = [profile.user]
    errors = []
    for mid in match_ids:
        partner_phone = match_registry.get(str(mid))
        if not partner_phone:
            errors.append(f"MATCH_ID {mid} not found. Valid IDs are: {', '.join(match_registry.keys())}")
            continue
        
        last_9 = partner_phone[-9:]
        u = User.objects.filter(phone_number__icontains=last_9).first()
        if u:
            participants.append(u)
        else:
            errors.append(f"User for MATCH_ID {mid} not found in database.")
    
    if errors:
        return f"Error: {' | '.join(errors)}"
    
    if len(participants) < 2:
        return "Could not find swap partners. Please run get_matches first."
    
    conv = Conversation.objects.create()
    conv.participants.add(*participants)
    
    welcome_msg = "Hello! 👋 SwapMate AI has identified a potential swap match between you.\n\n"
    welcome_msg += "Feel free to introduce yourselves and discuss the swap — talk about your schools, locations, subjects, and anything else that matters to you.\n\n"
    welcome_msg += "⚠️ **SECURITY WARNING:** Do NOT share your mobile number or personal contact info here. Sharing of numbers is strictly prohibited to avoid scams. Accounts may be **burned (permanently banned)** for asking or sharing phone numbers.\n\n"
    welcome_msg += "Once you are both comfortable and ready to proceed, the SwapMate team will arrange a virtual meeting to verify your details before you head to the official TSC portal."
    
    Message.objects.create(conversation=conv, sender=profile.user, text=welcome_msg)
    
    return f"Meeting chat created successfully with {len(participants)-1} partners. The user can now see it in their inbox."

def handle_request_human_support(profile, reason):
    admin_phone = "254742134431"
    user_name = f"{profile.user.first_name} {profile.user.last_name}" if profile.user.first_name else "New User"
    user_phone = profile.user.phone_number
    
    admin_msg = f"🆘 *Human Support Requested!*\n\n"
    admin_msg += f"User: {user_name}\n"
    admin_msg += f"Phone: {user_phone}\n"
    admin_msg += f"Reason: {reason}\n"
    
    send_whatsapp_message(admin_phone, admin_msg)
    
def handle_opt_out(state_obj):
    state_obj.is_opted_out = True
    state_obj.save()
    return "You have been successfully unsubscribed. You will no longer receive match notifications or onboarding messages from SwapMate. To re-subscribe, simply send any message to this number."

# --- MAIN LOGIC ---

SYSTEM_PROMPT = """
You are the SwapMate Advanced Assistant. Your goal is to onboard Kenyan teachers and help them find swaps.

ONBOARDING FLOW:
If a user's profile is incomplete, guide them through these steps one-by-one:
1. Official names (First and Last).
2. School Name and Level (Primary, JSS, or Senior).
3. School Location (County, Sub-County, and Ward).
4. Subjects they teach (max 2). **SKIP THIS STEP if the school level is PRIMARY.**
5. Preferred counties for swap.

BEHAVIOR:
- Be professional, polite, and encouraging.
- Ask questions in SMALL STEPS. Do not ask for everything at once.
- If the user provides info, use the tools to save it immediately.
- Use 'fuzzy search' context: if a user mispells a school or location, confirm it with them.
- **PRIVACY REASSURANCE**: When asking for the **School Name**, if the user seems hesitant or paranoid, explicitly reassure them: "Your school information is kept strictly private and is never shared with other teachers. We only use it for internal verification to protect the platform from scams and ensure all users are genuine teachers."
- **ONCE COMPLETE**: Show them a clear summary of their information (from CURRENT PROFILE below) and ask if they want to edit anything.
- If they want to edit, simply ask what they want to change and use the tools.

MATCHING:
- Intent 'find_swaps': 
    - **MANDATORY STOP**: If the user's profile is COMPLETE, you **MUST NOT** call `get_matches` yet.
    - First, list their currently saved 'Preferences' (counties).
    - **Always ask** the user to choose their search strategy:
        1. **Use Default**: Search using only their saved preferred locations.
        2. **Search Other Separately**: Provide new counties and search ONLY in those. (Use `temporary_counties` tool parameter).
        3. **Search All Together**: Combine saved locations with new ones for a broader search. (Use `temporary_counties` tool parameter).
    - **WAIT** for the user's explicit choice.
    - **SEARCH LIMITS**: Explicitly tell the user that **search is limited to a maximum of 3 counties** (either their saved ones or new temporary ones). If they provide more than 3, inform them you will only search the first 3. Do **NOT** perform a search on all counties even if the user asks.
    - **ACTION**: Once they choose, **CALL the `get_matches` tool immediately**. DO NOT say "One moment" or "Searching..." without calling the tool. 
    - **PERMANENCE**: Do **NOT** use `handle_set_preferences` unless the user explicitly says "Update my saved preferences" or "Save these for future searches". For one-time explorations, use the `temporary_counties` parameter in `get_matches`.
- MATCH SELECTION: If matches are found, present them clearly with their MATCH_ID numbers. **Ask which ones they are interested in pursuing.** They can choose multiple.
- CONFIRMATION: If a user expresses interest in one or more matches:
    1. **CALL the `create_meeting_chat` tool** with the MATCH_ID numbers of the selected partners.
    2. Tell the user: "We have successfully opened a chat for you with your potential swap partners. You can now discuss the swap details here: https://tscswap.com/messenger/inbox/\n\nOnce you are both ready, the SwapMate team will invite you to a virtual meeting to verify all information before you proceed to the official TSC portal."
- LEGAL/PROCEDURAL: **NEVER** tell a user they are 'relocating' or that the swap is 'finalized'. We do NOT process transfers; only the **TSC (Teachers Service Commission)** does that. 
- PRIVACY: Phone numbers are already masked in match results. Just display them as shown. **STRICT RULE:** Do NOT share your own phone number and do NOT ask users for theirs. Sharing of phone numbers is strictly prohibited to avoid scams. If a user tries to share a number, warn them that their account may be burned (permanently banned).
- MINIMALISM: Keep responses short and to the point. **DO NOT use asterisks (*) for bold or italic emphasis in text.** Only use asterisks for masking phone numbers as required. Keep text clean and plain.
- TRIANGLE SWAPS: Use the `get_matches` tool and follow its destination logic exactly.
- SUPPORT: If the user explicitly asks for a human, admin, customer support, or is clearly frustrated and needs 'special help', call the `request_human_support` tool immediately.
- UNSUBSCRIBE/STOP: If the user says 'STOP', 'UNSUBSCRIBE', or 'QUIT', call the `handle_opt_out` tool immediately and confirm that they have been unsubscribed.

PRE-PARSED INFO:
- If a 'PRE-PARSED INFO' section is provided below, it means the SwapMate team already found some details about the user.
- **DO NOT** ask for these details again. Instead, start by confirming them. 
- Example: "I see you're looking for a swap from [Location] to [Preferred]. Is that correct? And are you still teaching [Subjects]?"
- Once confirmed, use the appropriate tools to save them to the profile.

CRITICAL RULE FOR create_meeting_chat:
- Use the MATCH_ID numbers (integers like 1, 2, 3) from the get_matches results.
- Example: create_meeting_chat(match_ids=[1, 2])
- NEVER pass phone numbers, names, or usernames. Only MATCH_ID integers.

WHATSAPP NAME:
- If 'WhatsApp Name' is provided and the official name is NOT set, address the user as that name until they provide their official name.

- RESPONSE FORMAT: Your final response to the user must always be preceded by a status flag indicating if you are waiting for an answer. 
  - Format: [EXPECTS_REPLY: TRUE] your message here (if you asked a question or need info).
  - Format: [EXPECTS_REPLY: FALSE] your message here (if you are just being polite, ending a task, or closing the conversation).
"""

def process_whatsapp_message(phone_number, message_text, whatsapp_name=""):
    # 0. Security Filter: Block phone numbers (DISABLED AS REQUESTED)
    # if contains_phone_number(message_text):
    #     return "Message blocked! Sharing phone numbers is strictly prohibited to avoid scams. A repeat violation will have your account burned (permanently banned) from our platform."

    # 1. Get or Create User & Profile
    clean_whatsapp = phone_number.replace("+", "").replace(" ", "")
    last_9 = clean_whatsapp[-9:]
    variations = [clean_whatsapp, f"0{last_9}", last_9]
    
    user = User.objects.filter(Q(phone_number__in=variations)).first()
    if not user:
        # Create new user with phone number as default password
        phone_for_db = f"254{last_9}"
        user = User.objects.create_user(phone_number=phone_for_db, password=phone_for_db)
        TeacherProfile.objects.create(user=user)
    
    profile = user.profile
    state_obj, _ = WhatsAppState.objects.get_or_create(phone_number=phone_number)
    
    # 2. Check Opt-out Status
    if state_obj.is_opted_out:
        # If they send "START" or something similar, maybe we re-subscribe them?
        # For now, let's just re-subscribe them on ANY message as per the handle_opt_out message promise
        state_obj.is_opted_out = False
        state_obj.save()
        # Continue to process normally
    
    # 3. Prepare Context for AI
    pre_parsed = state_obj.context_data.get('pre_parsed', {})
    completion = profile.get_completion_stats()
    
    profile_summary = f"""
    User: {user.first_name} {user.last_name}
    WhatsApp Name: {whatsapp_name}
    School: {profile.school_name if profile.school_name else 'Not Set'} ({profile.get_level_display() if profile.level else 'Not Set'})
    Location: {profile.county.name if profile.county else 'N/A'}, {profile.sub_county.name if profile.sub_county else 'N/A'}
    Subjects: {', '.join([ts.subject.name for ts in profile.teaching_subjects.all()])}
    Preferences: {', '.join([pl.county.name for pl in profile.preferred_locations.all()])}
    Profile Complete: {completion['is_complete']}
    Missing Steps: {', '.join([k for k,v in completion['steps'].items() if not v])}
    """
    
    if pre_parsed:
        profile_summary += f"\nPRE-PARSED INFO (Confirm with user instead of asking):\n{json.dumps(pre_parsed)}\n"

    # 3. Get Conversation History
    history = WhatsAppInteraction.objects.filter(phone_number=phone_number).order_by('-created_at')[:5]
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\nCURRENT PROFILE:\n" + profile_summary}]
    
    for h in reversed(history):
        messages.append({"role": "user", "content": h.user_message})
        messages.append({"role": "assistant", "content": h.ai_response})
    
    messages.append({"role": "user", "content": message_text})

    # 4. AI Call
    try:
        # Re-init client with a longer timeout to prevent APITimeoutError
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=60.0  # Increased to 60 seconds
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Faster and more reliable for tool calling
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        
        # 5. Handle Tool Calls
        if assistant_message.tool_calls:
            messages.append(assistant_message) # Append assistant message ONCE
            
            for tool_call in assistant_message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                print(f"DEBUG: Executing tool {func_name} with args {args}")
                
                tool_result = ""
                try:
                    if func_name == "update_profile":
                        tool_result = handle_update_profile(profile, **args)
                    elif func_name == "set_location":
                        tool_result = handle_set_location(profile, **args)
                    elif func_name == "set_subjects":
                        tool_result = handle_set_subjects(profile, **args)
                    elif func_name == "set_preferences":
                        tool_result = handle_set_preferences(profile, **args)
                    elif func_name == "get_matches":
                        tool_result = handle_get_matches(profile, phone_number, **args)
                    elif func_name == "create_meeting_chat":
                        tool_result = handle_create_meeting_chat(profile, phone_number, **args)
                    elif func_name == "request_human_support":
                        tool_result = handle_request_human_support(profile, **args)
                    elif func_name == "handle_opt_out":
                        tool_result = handle_opt_out(state_obj)
                except Exception as te:
                    tool_result = f"Error executing tool: {str(te)}"
                
                print(f"DEBUG: Tool {func_name} result: {tool_result}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": tool_result
                })
            
            # Second call to get final response
            final_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            reply_text = final_response.choices[0].message.content
        else:
            reply_text = assistant_message.content

    except Exception as e:
        import traceback
        print(f"AI Error Traceback: {traceback.format_exc()}")
        reply_text = f"I'm having a bit of trouble processing that. (Error: {str(e)[:50]}...)"

    # 5.5 Parse Expects Reply Flag
    expects_reply = True # Default
    if "[EXPECTS_REPLY:" in reply_text:
        if "[EXPECTS_REPLY: FALSE]" in reply_text:
            expects_reply = False
        reply_text = reply_text.replace("[EXPECTS_REPLY: TRUE]", "").replace("[EXPECTS_REPLY: FALSE]", "").strip()

    # 6. Save Interaction & State
    interaction = WhatsAppInteraction.objects.create(
        phone_number=phone_number,
        user_message=message_text,
        ai_response=reply_text,
        expects_reply=expects_reply
    )
    
    # Update State
    state_obj.expects_reply = expects_reply
    state_obj.save()
    
    return reply_text, interaction

def parse_bulk_onboarding_data(text):
    """Uses GPT to parse unstructured text into a list of structured user data."""
    prompt = f"""
    You are an expert data extractor. Parse the following unstructured teacher swap requests into a clean JSON list.
    
    RULES:
    1. Extract 'phone_number': Format as 254XXXXXXXXX (must be 12 digits, no plus sign).
    2. Extract 'name': The teacher's name if mentioned (e.g. "Jane Doe").
    3. Extract 'current_location': String describing where they are now.
    4. Extract 'preferred_location': String describing where they want to go.
    5. Extract 'subjects': A string list of teaching subjects mentioned.
    6. Extract 'raw_text': The original line for reference.
    
    Data to parse:
    {text}
    
    Return ONLY a JSON list of objects.
    """
    
    try:
        print(f"DEBUG: Calling GPT (4o-mini) to parse text: {text[:100]}...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a data extraction assistant."},
                      {"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
            timeout=120  # Increased timeout
        )
        raw_content = response.choices[0].message.content
        print(f"DEBUG: GPT Raw Content: {raw_content}")
        data = json.loads(raw_content)
        # Extract the list regardless of what key GPT used
        for key in data:
            if isinstance(data[key], list):
                return data[key]
        return []
    except Exception as e:
        print(f"Error parsing bulk data: {e}")
        import traceback
        print(traceback.format_exc())
        return []
