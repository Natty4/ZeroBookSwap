# admin.py - FINAL VERSION (EVERYTHING INCLUDED)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import csv
from django.http import HttpResponse

from .models import (
    UserProfile, Wallet, Book, SwapRequest,
    CoinPackage, Payment, Transaction
)

# ===================================================================
# 1. USER + PROFILE + WALLET - FULLY INTEGRATED
# ===================================================================
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    fields = ('phone_number',)
    extra = 0

class WalletInline(admin.StackedInline):
    model = Wallet
    can_delete = False
    readonly_fields = ('zcoin_balance', 'created_at', 'updated_at')
    verbose_name_plural = "Wallet"
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False  # Wallet is auto-created

class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline, WalletInline)
    list_display = ('username', 'email', 'get_full_name', 'get_phone', 'get_zcoin', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'profile__phone_number')
    ordering = ('-date_joined',)

    def get_full_name(self, obj):
        return obj.get_full_name() or "-"
    get_full_name.short_description = "Name"

    def get_phone(self, obj):
        return obj.profile.phone_number or "-"
    get_phone.short_description = "Phone"

    def get_zcoin(self, obj):
        try:
            return f"Ⓩ {obj.wallet.zcoin_balance}"
        except (Wallet.DoesNotExist, AttributeError):
            return "Ⓩ 0.00 (no wallet)"
    get_zcoin.short_description = "ZCoin Balance"
    get_zcoin.admin_order_field = 'wallet__zcoin_balance'

# Unregister old, register new
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ===================================================================
# 2. WALLET - STANDALONE (for direct access)
# ===================================================================
@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'zcoin_balance', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'zcoin_balance', 'created_at', 'updated_at')
    actions = ['add_zcoin', 'deduct_zcoin']

    def user_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}"><strong>{}</strong></a>', url, obj.user.username)
    user_link.short_description = "User"

    def add_zcoin(self, request, queryset, amount=100):
        updated = 0
        for wallet in queryset:
            wallet.zcoin_balance += Decimal(str(amount))
            wallet.save()
            Transaction.objects.create(
                user=wallet.user,
                transaction_type='topup',
                amount=amount,
                description=f"Admin added {amount} ZCoin"
            )
            updated += 1
        self.message_user(request, f"Added {amount} ZCoin to {updated} wallets.")
    add_zcoin.short_description = "Add 100 ZCoin (admin bonus)"

    def deduct_zcoin(self, request, queryset, amount=50):
        updated = 0
        for wallet in queryset:
            if wallet.zcoin_balance >= Decimal(str(amount)):
                wallet.zcoin_balance -= Decimal(str(amount))
                wallet.save()
                Transaction.objects.create(
                    user=wallet.user,
                    transaction_type='refund',
                    amount=-amount,
                    description=f"Admin deducted {amount} ZCoin"
                )
                updated += 1
        self.message_user(request, f"Deducted {amount} ZCoin from {updated} wallets.")
    deduct_zcoin.short_description = "Deduct 50 ZCoin"


# ===================================================================
# 3. BOOK - FULLY FEATURED
# ===================================================================
@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'added_by_link', 'genre', 'condition', 'zcoin_value', 'price_birr', 'book_type', 'is_available', 'created_at')
    list_filter = ('book_type', 'genre', 'condition', 'is_available', 'created_at')
    search_fields = ('title', 'author', 'added_by__username', 'added_by__email')
    list_editable = ('is_available', 'zcoin_value', 'price_birr')
    readonly_fields = ('created_at', 'updated_at', 'added_by')
    date_hierarchy = 'created_at'

    def added_by_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.added_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.added_by.username)
    added_by_link.short_description = "Added By"


# ===================================================================
# 4. SWAP REQUEST - PROFESSIONAL WITH ZCOIN LOGIC
# ===================================================================
@admin.register(SwapRequest)
class SwapRequestAdmin(admin.ModelAdmin):
    list_display = ('user_link', 'requested_book_link', 'user_book_title', 'calculated_zcoin', 'required_zcoin', 'status_colored', 'created_at')
    list_filter = ('status', 'created_at', 'user_book_genre')
    search_fields = ('user__username', 'user_book_title', 'requested_book__title')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['approve_swaps', 'reject_swaps', 'complete_swaps']

    def user_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User"

    def requested_book_link(self, obj):
        url = reverse("admin:core_book_change", args=[obj.requested_book.id])
        return format_html('<a href="{}">{}</a>', url, obj.requested_book.title)
    requested_book_link.short_description = "Requested"

    def required_zcoin(self, obj):
        return f"Ⓩ {obj.requested_book.zcoin_value}"
    required_zcoin.short_description = "Required"

    def status_colored(self, obj):
        colors = {'pending': '#fb923c', 'approved': '#22c55e', 'rejected': '#ef4444', 'completed': '#8b5cf6'}
        return format_html('<span style="background:{}; color:white; padding:2px 8px; border-radius:4px;">{}</span>', 
                          colors.get(obj.status, '#666'), obj.status.upper())
    status_colored.short_description = "Status"

    def approve_swaps(self, request, queryset):
        count = 0
        for swap in queryset.filter(status='pending'):
            swap.status = 'approved'
            swap.save()
            diff = swap.calculated_zcoin - swap.requested_book.zcoin_value
            if diff > 0:
                wallet = swap.user.wallet
                wallet.zcoin_balance += diff
                wallet.save()
                Transaction.objects.create(
                    user=swap.user,
                    transaction_type='refund',
                    amount=diff,
                    description=f"Swap refund: {swap.requested_book.title}",
                    related_swap=swap
                )
            count += 1
        self.message_user(request, f"{count} swaps approved.")
    approve_swaps.short_description = "Approve & refund extra ZCoin"


# ===================================================================
# 5. COIN PACKAGE, PAYMENT, TRANSACTION - FULLY COVERED
# ===================================================================
@admin.register(CoinPackage)
class CoinPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'zcoin_amount', 'price_birr', 'price_per_zcoin', 'is_active')
    list_editable = ('is_active', 'price_birr')
    def price_per_zcoin(self, obj):
        return f"{obj.price_birr / obj.zcoin_amount:.4f} Birr/Z" if obj.zcoin_amount else "-"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference_number', 'user', 'amount_birr', 'zcoin_amount', 'status', 'payment_method', 'created_at')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('reference_number', 'user__username', 'receipt_no')
    readonly_fields = ('created_at', 'verified_at', 'reference_number')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction_type', 'amount', 'description', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('user__username', 'description')


# ===================================================================
# ADMIN SITE CUSTOMIZATION
# ===================================================================
admin.site.site_header = "Zero Book Swap - Admin Panel"
admin.site.site_title = "Zero Admin"
admin.site.index_title = "Welcome to Zero Book Swap Management"