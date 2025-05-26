# AudioXApp/views/user_views/contactsupport_views.py

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone

import json
import logging

from ...models import Ticket, TicketCategory, User, TicketMessage
# from ...models import Creator # Import Creator if you need to directly query it

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from ..utils import _get_full_context

logger = logging.getLogger(__name__)

@login_required
def create_ticket_view(request):
    context = _get_full_context(request)
    context['page_title'] = _("Submit a Support Ticket")

    is_creator = False
    if hasattr(request.user, 'is_creator'):
        is_creator = request.user.is_creator
    context['is_creator_flag'] = is_creator
    
    ticket_categories = TicketCategory.objects.all()
    context['ticket_categories'] = ticket_categories

    form_data_to_repopulate = {}

    if request.method == 'POST':
        form_data_to_repopulate = request.POST.copy()
        subject = request.POST.get('subject')
        description = request.POST.get('description')
        category_id = request.POST.get('ticket_category')
        
        errors = []
        if not subject: errors.append(_("Subject is required."))
        if not description: errors.append(_("Description is required."))
        if not category_id: errors.append(_("Please select a ticket category."))

        category_instance = None
        if category_id:
            try:
                category_instance = TicketCategory.objects.get(pk=category_id)
            except TicketCategory.DoesNotExist:
                errors.append(_("Invalid ticket category selected."))
        
        if errors:
            for error in errors: messages.error(request, error)
            context['form_data'] = form_data_to_repopulate
            return render(request, 'user/contactsupport.html', context)

        try:
            new_ticket = Ticket(
                user=request.user,
                category=category_instance,
                subject=subject,
                description=description
            )
            new_ticket.save() 

            messages.success(request, _(f"Your support ticket (ID: {new_ticket.ticket_display_id}) has been submitted! We'll get back to you soon."))
            return redirect('AudioXApp:user_ticket_detail', ticket_uuid=new_ticket.id)

        except Exception as e:
            logger.error(f"Error creating ticket for user {request.user.email}: {e}", exc_info=True)
            messages.error(request, _("An unexpected error occurred. Please try again later."))
            context['form_data'] = form_data_to_repopulate
            return render(request, 'user/contactsupport.html', context)

    context['form_data'] = form_data_to_repopulate
    return render(request, 'user/contactsupport.html', context)


@login_required
@require_POST
def ajax_ai_generate_ticket_details_view(request):
    if not genai:
        logger.error("Google Generative AI library (genai) not imported/installed.")
        return JsonResponse({'error': _('AI service is currently unavailable. Please try again later.')}, status=503)

    try:
        data = json.loads(request.body)
        user_prompt = data.get('prompt')
        ticket_context_type = data.get('ticket_context_type', 'user') 
    except json.JSONDecodeError:
        return JsonResponse({'error': _('Invalid JSON data in request.')}, status=400)
    except Exception as e:
        logger.error(f"Error decoding request body for AI prompt: {e}")
        return JsonResponse({'error': _('Invalid request format.')}, status=400)

    if not user_prompt:
        return JsonResponse({'error': _('Prompt is missing.')}, status=400)

    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured in settings.")
        return JsonResponse({'error': _('AI service configuration error. Cannot proceed.')}, status=500)

    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        # --- MODIFIED Category Filtering for AI Prompt ---
        categories_qs = TicketCategory.objects.all()
        relevant_categories_for_ai = []
        context_info_for_ai = ""

        if ticket_context_type == 'creator':
            relevant_categories_for_ai = [cat for cat in categories_qs if cat.is_creator_specific]
            context_info_for_ai = "The user is submitting this ticket in the context of their 'Creator Profile & Activities'."
        else: # 'user' context (default)
            relevant_categories_for_ai = [cat for cat in categories_qs if not cat.is_creator_specific]
            context_info_for_ai = "The user is submitting this ticket in the context of their 'General User Account'."
        
        # Fallback if filtering results in no categories (e.g., no categories match the criteria)
        if not relevant_categories_for_ai and categories_qs.exists():
            logger.warning(f"No categories found for AI prompt with context '{ticket_context_type}'. Falling back to all categories.")
            relevant_categories_for_ai = list(categories_qs) # Or a sensible default list
        elif not categories_qs.exists():
             logger.error("No TicketCategory instances found in the database.")
             return JsonResponse({'error': _('Ticket categories not set up.')}, status=500)


        category_names_for_ai_prompt = [category.name for category in relevant_categories_for_ai]
        # If, after filtering, no category names are available (should be rare if categories exist and filtering is correct)
        if not category_names_for_ai_prompt:
            # This case should ideally not be hit if categories exist.
            # If it is, it means either no categories match the filter or all categories were filtered out.
            # Provide a very generic list or handle error.
            all_category_names = [cat.name for cat in categories_qs]
            category_list_str = ", ".join(f"'{name}'" for name in all_category_names) if all_category_names else "'General Inquiry'"
            logger.warning(f"No relevant categories for AI prompt context '{ticket_context_type}'. Using full list or default for AI prompt.")
        else:
            category_list_str = ", ".join(f"'{name}'" for name in category_names_for_ai_prompt)
        # --- END OF MODIFIED Category Filtering ---

        full_prompt = (
            f"You are an assistant for a support ticketing system for an audiobook platform called 'AudioX'.\n"
            f"{context_info_for_ai}\n"
            f"Based on the user's problem description below, please act as a helpful assistant to pre-fill a support ticket. "
            f"Generate a concise ticket 'subject' (max 70 characters), a detailed 'description' (elaborate on the user's prompt if needed, maintaining a helpful tone), "
            f"and suggest the most relevant 'category'. The category MUST be chosen EXACTLY from the following list: [{category_list_str}]. Do not invent new categories.\n"
            f"Ensure your ENTIRE output is ONLY a single, valid JSON object with three keys: \"subject\", \"description\", and \"category\". "
            f"Do not include any other text, greetings, or explanations outside of this JSON object.\n\n"
            f"User's problem: \"{user_prompt}\""
        )
        
        model_name = 'gemini-1.5-flash-latest'
        model = genai.GenerativeModel(model_name)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

        response = model.generate_content(full_prompt, safety_settings=safety_settings)
        ai_response_text = response.text.strip()

        if ai_response_text.startswith("```json"): ai_response_text = ai_response_text[7:]
        if ai_response_text.endswith("```"): ai_response_text = ai_response_text[:-3]
        ai_response_text = ai_response_text.strip()

        try:
            ai_data = json.loads(ai_response_text)
            if not all(k in ai_data for k in ("subject", "description", "category")):
                logger.warning(f"AI response missing expected keys. Context: {ticket_context_type}. Raw text: {response.text}")
                raise ValueError("Missing keys in AI JSON response")
            
            suggested_category_name = ai_data.get('category')
            # Validate against the list of names provided to the AI
            if suggested_category_name not in category_names_for_ai_prompt:
                logger.warning(f"AI suggested category '{suggested_category_name}' which was NOT in the filtered list for context '{ticket_context_type}'. AI Prompt List: [{category_list_str}] Raw response: {response.text}")
                found_match_in_relevant_list = False
                for cat_name in category_names_for_ai_prompt:
                    if cat_name.lower() == suggested_category_name.lower():
                        ai_data['category'] = cat_name 
                        found_match_in_relevant_list = True
                        break
                if not found_match_in_relevant_list:
                    ai_data['category_warning'] = f"AI suggested an unsuitable category ('{suggested_category_name}') for the selected context. Please select manually."
                    ai_data['category'] = "" # Clear category, force user to choose

            return JsonResponse(ai_data)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode AI JSON. Context: {ticket_context_type}. Error: {e}. Raw: {response.text}", exc_info=True)
            return JsonResponse({'error': _('AI response format error.'), 'ai_raw_response': response.text}, status=200)
        except ValueError as e: # Catches the "Missing keys" error too
             logger.error(f"ValueError processing AI response. Context: {ticket_context_type}. Error: {e}. Raw: {response.text}", exc_info=True)
             return JsonResponse({'error': str(e), 'ai_raw_response': response.text}, status=200)

    except Exception as e:
        logger.error(f"Error in AI generation. Context: {ticket_context_type}. Prompt: '{user_prompt[:100]}...': {e}", exc_info=True)
        return JsonResponse({'error': _('Unexpected AI error. Please fill manually.')}, status=500)


# Keep your user_ticket_list_view and user_ticket_detail_view functions as they were
@login_required
def user_ticket_list_view(request):
    context = _get_full_context(request)
    context['page_title'] = _("My Support Tickets")
    user_tickets = Ticket.objects.filter(user=request.user).order_by('-updated_at', '-created_at')
    context['user_tickets'] = user_tickets
    return render(request, 'user/user_ticket_list.html', context)

@login_required
def user_ticket_detail_view(request, ticket_uuid):
    context = _get_full_context(request)
    try:
        ticket = Ticket.objects.prefetch_related('messages__user').get(id=ticket_uuid, user=request.user)
    except Ticket.DoesNotExist:
        messages.error(request, _("Support ticket not found or you do not have permission to view it."))
        return redirect('AudioXApp:user_ticket_list')

    context['page_title'] = _(f"Ticket Details - {ticket.ticket_display_id}")
    context['ticket'] = ticket

    if request.method == 'POST':
        message_content = request.POST.get('message_content')
        if not message_content:
            messages.error(request, _("Your reply cannot be empty."))
        else:
            try:
                TicketMessage.objects.create(
                    ticket=ticket,
                    user=request.user,
                    message=message_content,
                    is_admin_reply=False
                )
                ticket.updated_at = timezone.now()
                if ticket.status == Ticket.StatusChoices.AWAITING_USER:
                    ticket.status = Ticket.StatusChoices.OPEN 
                ticket.save(update_fields=['updated_at', 'status'])
                messages.success(request, _("Your reply has been added."))
                return redirect('AudioXApp:user_ticket_detail', ticket_uuid=ticket.id)
            except Exception as e:
                logger.error(f"Error adding reply to ticket {ticket.id} by user {request.user.email}: {e}", exc_info=True)
                messages.error(request, _("An error occurred while adding your reply."))
    
    return render(request, 'user/user_ticket_detail.html', context)