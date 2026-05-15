import openai
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings

def landing_page(request):
    return render(request, 'core/landing.html')

def chatbot(request):
    message = request.GET.get('message', '')
    if not message:
        return JsonResponse({"reply": "How can I help you today?"})

    try:
        client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=30.0
        )
        
        user_context = ""
        if request.user.is_authenticated:
            from accounts.services import get_potential_matches, get_triangle_matches, get_possible_matches
            profile = request.user.profile
            
            # Query REAL match data from the database
            mutual_matches = get_potential_matches(profile)
            triangle_matches = get_triangle_matches(profile)
            possible_matches = get_possible_matches(profile)
            
            # Build match details for mutual matches
            mutual_details = ""
            if mutual_matches:
                for m in mutual_matches[:5]:
                    mutual_details += f"  - {m.user.first_name} {m.user.last_name} at {m.school_name} ({m.county.name if m.county else 'Unknown'})\n"
            
            # Build match details for triangle matches
            triangle_details = ""
            if triangle_matches:
                for t in triangle_matches[:3]:
                    triangle_details += f"  - Loop: {t['partner_1'].user.first_name} ({t['partner_1'].county.name}) ↔ {t['partner_2'].user.first_name} ({t['partner_2'].county.name})\n"
            
            # Build match details for possible matches
            possible_details = ""
            if possible_matches:
                for p in possible_matches[:5]:
                    possible_details += f"  - {p.user.first_name} {p.user.last_name} at {p.school_name} ({p.county.name if p.county else 'Unknown'})\n"
            
            pref_counties = list(profile.preferred_locations.values_list('county__name', flat=True))
            
            user_context = f"""
            The current user is LOGGED IN.
            Name: {request.user.first_name} {request.user.last_name}
            Phone: {request.user.phone_number}
            Station: {profile.school_name} ({profile.county.name if profile.county else 'Unknown'})
            Level: {profile.get_level_display()}
            Preferred Counties: {', '.join(pref_counties) if pref_counties else 'Not set'}
            
            === REAL MATCH DATA FROM DATABASE ===
            Mutual Matches: {len(mutual_matches)} found
            {mutual_details if mutual_details else '  None yet.'}
            
            Triangle Matches: {len(triangle_matches)} found
            {triangle_details if triangle_details else '  None yet.'}
            
            Possible Matches (one-way interest): {len(possible_matches)} found
            {possible_details if possible_details else '  None yet.'}
            ======================================
            
            IMPORTANT: Use ONLY the match data above when answering questions about matches.
            Do NOT make up or guess match information. If the data says 0, say 0. If it says 1, say 1.
            Since they are logged in, do NOT ask them to register. Encourage them to check their dashboard for full details.
            """
        else:
            user_context = "The user is NOT logged in. Encourage them to join/register."

        system_prompt = f"""
        You are the SwapMate Assistant. Your goal is to help Kenyan teachers find swaps.
        Provide helpful, professional, and encouraging advice.
        
        {user_context}
        
        Key Info:
        - SwapMate helps find Mutual and Triangle swaps.
        - Users must register and complete a 4-step profile to see matches.
        - We support Primary, JSS, and Senior School levels across all 47 counties.
        - TSC (Teachers Service Commission) is the final authority for approving swaps.
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ]
        )
        reply = response.choices[0].message.content
        return JsonResponse({"reply": reply})
        
    except Exception as e:
        # Fallback to simple logic if OpenAI fails
        return JsonResponse({"reply": "I'm having trouble connecting to my brain right now, but SwapMate is here to help you find your perfect teaching swap!"})

def privacy_policy(request):
    return render(request, 'core/privacy_policy.html')
