"""Admin interface for Table and TableSession management."""
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .models import Table, TableSession
from .services import make_qr_png


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    """Admin configuration for restaurant dining tables."""

    list_display = ("number", "is_active", "qr_token", "download_qr_link")
    list_filter = ("is_active",)
    search_fields = ("number", "qr_token")
    readonly_fields = ("qr_token", "created_at", "updated_at")

    def get_urls(self):
        """Register custom URL for downloading table QR code."""
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:table_id>/qr.png",
                self.admin_site.admin_view(self.download_qr_view),
                name="tables_table_download_qr",
            ),
        ]
        return custom_urls + urls

    def download_qr_link(self, obj: Table):
        """Render a clickable link in the list display to download the QR code."""
        if not obj.pk:
            return "-"
        url = reverse("admin:tables_table_download_qr", args=[obj.pk])
        return format_html('<a href="{}" download="table_{}.png">Download QR</a>', url, obj.number)

    download_qr_link.short_description = "QR Code"

    def download_qr_view(self, request, table_id: int):
        """Return the PNG image bytes for a table's QR code."""
        table = self.get_object(request, table_id)
        if table is None:
            return HttpResponse("Table not found", status=404)
        png_bytes = make_qr_png(table, request=request)
        response = HttpResponse(png_bytes, content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="table_{table.number}_qr.png"'
        return response


@admin.register(TableSession)
class TableSessionAdmin(admin.ModelAdmin):
    """Admin configuration for tracking active dining tabs."""

    list_display = ("id", "table", "opened_at", "closed_at", "is_open")
    list_filter = ("table",)
    list_select_related = ("table",)
    list_per_page = 50
    readonly_fields = ("opened_at", "closed_at", "created_at", "updated_at")

    def is_open(self, obj: TableSession) -> bool:
        """Return whether the session is currently open."""
        return obj.closed_at is None

    is_open.boolean = True
