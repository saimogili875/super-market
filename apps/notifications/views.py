"""Views for administrative operational alerts and notifications."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.permissions import staff_required
from apps.menu.models import MenuItem
from .models import AdminNotification


@staff_required
def notification_list(request):
    """View operational alerts, filter by type, and resolve issues."""
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "mark_all_read":
            AdminNotification.objects.filter(recipient__isnull=True, is_read=False).update(is_read=True)
            messages.success(request, "All notifications marked as read.")
        elif action == "mark_resolved":
            notif_id = request.POST.get("notif_id")
            notif = get_object_or_404(AdminNotification, pk=notif_id, recipient__isnull=True)
            notif.is_resolved = True
            notif.is_read = True
            notif.save()
            messages.success(request, f"Notification '{notif.title}' marked as resolved.")
        return redirect("notifications:list")

    # Filter tab
    filter_type = request.GET.get("filter", "All")
    notifs = AdminNotification.objects.filter(recipient__isnull=True)

    if filter_type == "Unread":
        notifs = notifs.filter(is_read=False)
    elif filter_type == "Low stock":
        notifs = notifs.filter(notification_type="Low stock")
    elif filter_type == "Expiry":
        notifs = notifs.filter(notification_type="Expiry")
    elif filter_type == "Orders":
        notifs = notifs.filter(notification_type__in=["Order", "Delivery"])

    # Selected item for right detail pane
    selected_id = request.GET.get("selected")
    selected_notif = None
    if selected_id:
        selected_notif = AdminNotification.objects.filter(pk=selected_id).first()
    if not selected_notif:
        selected_notif = notifs.first()

    # Associated product info if it's low stock or expiry
    product_item = None
    if selected_notif and selected_notif.reference_id:
        product_item = MenuItem.objects.filter(sku=selected_notif.reference_id).first()

    return render(
        request,
        "admin/notifications.html",
        {
            "notifications": notifs,
            "selected_notif": selected_notif,
            "product_item": product_item,
            "filter_type": filter_type,
            "active_nav": "notifications",
        },
    )
