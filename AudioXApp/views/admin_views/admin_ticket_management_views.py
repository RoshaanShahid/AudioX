# AudioXApp/views/admin_views/admin_ticket_management_views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Count, Q 
from django.utils import timezone
from datetime import timedelta
import json
from django.core.paginator import Paginator
from django.contrib import messages
import logging

from ...models import Ticket, Admin, TicketCategory, TicketMessage, User 
from ..utils import _get_full_context
from ..decorators import admin_role_required

logger = logging.getLogger(__name__)

# --- Admin Support Tickets Overview ---

@admin_role_required('manage_support')
def admin_manage_tickets_overview_view(request):
    context = _get_full_context(request) 
    context['page_title'] = "Manage Support Tickets"
    context['active_page'] = "manage_support_overview"

    total_tickets_count = Ticket.objects.count()
    open_statuses = [Ticket.StatusChoices.OPEN, Ticket.StatusChoices.PROCESSING, Ticket.StatusChoices.AWAITING_USER, Ticket.StatusChoices.REOPENED]
    open_tickets_count = Ticket.objects.filter(status__in=open_statuses).count()
    
    closed_statuses = [Ticket.StatusChoices.RESOLVED, Ticket.StatusChoices.CLOSED]
    closed_tickets_count = Ticket.objects.filter(status__in=closed_statuses).count()

    context['total_tickets_count'] = total_tickets_count
    context['open_tickets_count'] = open_tickets_count
    context['closed_tickets_count'] = closed_tickets_count
    
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=6)
    daily_labels = []
    daily_new_tickets_data = []
    daily_closed_tickets_data = []
    daily_open_tickets_snapshot_data = []

    for i in range(7):
        current_date = seven_days_ago + timedelta(days=i)
        daily_labels.append(current_date.strftime("%a, %b %d"))
        daily_new_tickets_data.append(Ticket.objects.filter(created_at__date=current_date).count())
        daily_closed_tickets_data.append(Ticket.objects.filter(Q(status__in=closed_statuses) & (Q(resolved_at__date=current_date) | Q(closed_at__date=current_date))).count())
        daily_open_tickets_snapshot_data.append(
            Ticket.objects.filter(created_at__date__lte=current_date)
                          .exclude(Q(status__in=closed_statuses) & Q(updated_at__date__lt=current_date))
                          .count()
        )

    context['daily_chart_labels_json'] = json.dumps(daily_labels)
    context['daily_new_tickets_data_json'] = json.dumps(daily_new_tickets_data)
    context['daily_closed_tickets_data_json'] = json.dumps(daily_closed_tickets_data)
    context['daily_open_tickets_snapshot_json'] = json.dumps(daily_open_tickets_snapshot_data)

    return render(request, 'admin/manage_support/admin_manage_tickets_overview.html', context)

# --- All Tickets List View ---

@admin_role_required('manage_support')
def admin_all_tickets_list_view(request):
    context = _get_full_context(request)
    context['page_title'] = "All Support Tickets"
    context['active_page'] = "manage_support_all_tickets" 
    context['list_title'] = "All Tickets"

    ticket_list = Ticket.objects.select_related('user', 'category').order_by('-updated_at')
    
    status_filter = request.GET.get('status')
    category_filter = request.GET.get('category_id')
    search_query = request.GET.get('search_query', '').strip()

    if status_filter:
        ticket_list = ticket_list.filter(status=status_filter)
    if category_filter:
        ticket_list = ticket_list.filter(category_id=category_filter)
    
    if search_query:
        ticket_list = ticket_list.filter(
            Q(ticket_display_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(subject__icontains=search_query)
        )

    context['categories'] = TicketCategory.objects.all()
    context['statuses'] = Ticket.StatusChoices.choices
    context['current_status_filter'] = status_filter
    context['current_category_filter'] = int(category_filter) if category_filter and category_filter.isdigit() else None
    context['current_search_query'] = search_query

    paginator = Paginator(ticket_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context['page_obj'] = page_obj
    context['is_paginated'] = page_obj.has_other_pages()
    
    return render(request, 'admin/manage_support/admin_ticket_list_template.html', context)

# --- Open Tickets List View ---

@admin_role_required('manage_support')
def admin_open_tickets_list_view(request):
    context = _get_full_context(request)
    context['page_title'] = "Open Support Tickets"
    context['active_page'] = "manage_support_open_tickets"
    context['list_title'] = "Open & Active Tickets"

    open_statuses = [Ticket.StatusChoices.OPEN, Ticket.StatusChoices.PROCESSING, Ticket.StatusChoices.AWAITING_USER, Ticket.StatusChoices.REOPENED]
    ticket_list = Ticket.objects.filter(status__in=open_statuses).select_related('user', 'category').order_by('updated_at')
    
    status_filter = request.GET.get('status')
    category_filter = request.GET.get('category_id')
    search_query = request.GET.get('search_query', '').strip()

    if status_filter and status_filter in open_statuses:
        ticket_list = ticket_list.filter(status=status_filter)
    elif status_filter: 
        ticket_list = ticket_list.none()

    if category_filter:
        ticket_list = ticket_list.filter(category_id=category_filter)

    if search_query:
        ticket_list = ticket_list.filter(
            Q(ticket_display_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(subject__icontains=search_query)
        )

    context['categories'] = TicketCategory.objects.all()
    context['statuses'] = [(s[0], s[1]) for s in Ticket.StatusChoices.choices if s[0] in open_statuses]
    context['current_status_filter'] = status_filter
    context['current_category_filter'] = int(category_filter) if category_filter and category_filter.isdigit() else None
    context['current_search_query'] = search_query

    paginator = Paginator(ticket_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context['page_obj'] = page_obj
    context['is_paginated'] = page_obj.has_other_pages()
    
    return render(request, 'admin/manage_support/admin_ticket_list_template.html', context)

# --- Closed Tickets List View ---

@admin_role_required('manage_support')
def admin_closed_tickets_list_view(request):
    context = _get_full_context(request)
    context['page_title'] = "Closed & Resolved Tickets"
    context['active_page'] = "manage_support_closed_tickets"
    context['list_title'] = "Closed & Resolved Tickets"

    closed_statuses = [Ticket.StatusChoices.RESOLVED, Ticket.StatusChoices.CLOSED]
    ticket_list = Ticket.objects.filter(status__in=closed_statuses).select_related('user', 'category').order_by('-updated_at')
    
    status_filter = request.GET.get('status')
    category_filter = request.GET.get('category_id')
    search_query = request.GET.get('search_query', '').strip()
        
    if status_filter and status_filter in closed_statuses:
        ticket_list = ticket_list.filter(status=status_filter)
    elif status_filter: 
        ticket_list = ticket_list.none()
        
    if category_filter:
        ticket_list = ticket_list.filter(category_id=category_filter)

    if search_query:
        ticket_list = ticket_list.filter(
            Q(ticket_display_id__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(subject__icontains=search_query)
        )

    context['categories'] = TicketCategory.objects.all()
    context['statuses'] = [(s[0], s[1]) for s in Ticket.StatusChoices.choices if s[0] in closed_statuses]
    context['current_status_filter'] = status_filter
    context['current_category_filter'] = int(category_filter) if category_filter and category_filter.isdigit() else None
    context['current_search_query'] = search_query

    paginator = Paginator(ticket_list, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context['page_obj'] = page_obj
    context['is_paginated'] = page_obj.has_other_pages()
    
    return render(request, 'admin/manage_support/admin_ticket_list_template.html', context)

# --- Ticket Detail View ---

@admin_role_required('manage_support')
def admin_ticket_detail_view(request, ticket_uuid):
    context = _get_full_context(request)
    ticket = get_object_or_404(Ticket.objects.select_related('user', 'category', 'creator_profile__user')
                                            .prefetch_related('messages__user'), id=ticket_uuid)

    context['page_title'] = f"Ticket {ticket.ticket_display_id} - {ticket.subject[:50]}"
    context['active_page'] = "manage_support_detail"
    context['ticket'] = ticket
    context['ticket_statuses'] = Ticket.StatusChoices.choices

    if request.method == 'POST':
        action = request.POST.get('action')
        admin_user_obj = context.get('admin_user') 
        admin_user_identifier = admin_user_obj.username if admin_user_obj else "System"

        if action == 'add_reply':
            message_content = request.POST.get('message_content')
            if not message_content:
                messages.error(request, "Reply message cannot be empty.")
            else:
                TicketMessage.objects.create(
                    ticket=ticket,
                    user=None,
                    message=message_content,
                    is_admin_reply=True
                )
                if ticket.status == Ticket.StatusChoices.AWAITING_USER or ticket.status == Ticket.StatusChoices.OPEN:
                    ticket.status = Ticket.StatusChoices.PROCESSING
                
                ticket.assigned_admin_identifier = admin_user_identifier
                ticket.updated_at = timezone.now()
                ticket.save()
                messages.success(request, "Your reply has been added successfully.")
            return redirect('AudioXApp:admin_ticket_detail', ticket_uuid=ticket.id)

        elif action == 'update_status':
            new_status = request.POST.get('new_status')

            if new_status and new_status in Ticket.StatusChoices.values:
                ticket.status = new_status
                ticket.assigned_admin_identifier = admin_user_identifier

                if new_status == Ticket.StatusChoices.RESOLVED and not ticket.resolved_at:
                    ticket.resolved_at = timezone.now()
                elif new_status == Ticket.StatusChoices.CLOSED and not ticket.closed_at:
                    ticket.closed_at = timezone.now()
                
                ticket.updated_at = timezone.now()
                ticket.save()
                messages.success(request, f"Ticket status updated to '{ticket.get_status_display()}'.")
            else:
                messages.error(request, "Invalid status selected.")
            return redirect('AudioXApp:admin_ticket_detail', ticket_uuid=ticket.id)
    
    return render(request, 'admin/manage_support/admin_ticket_detail.html', context)