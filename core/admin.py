# admin.py - UPDATED VERSION WITH COMMODITY AND PURCHASE MODELS

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from decimal import Decimal
from django import forms
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html
from django.contrib import messages
from django.http import JsonResponse
from .utils.zcoin_calculator import ZCoinCalculator
from .models import (
    UserProfile, Wallet, Book, SwapRequest,
    CoinPackage, Payment, Transaction,
    ZCoinCalculatorSettings, ZCoinCalculationLog,
    Commodity, CommodityPurchase  # ADDED THESE
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
    """Book admin with review workflow"""
    list_display = ('title', 'author', 'genre', 'status_badge', 
                   'zcoin_value', 'price_birr', 'added_by', 
                   'reviewed_by', 'created_at')
    list_filter = ('status', 'genre', 'created_at')
    search_fields = ('title', 'author', 'added_by__username')
    readonly_fields = ('created_at', 'updated_at', 'reviewed_at', 
                      'approved_at', 'reviewed_by', 'approved_by', 'added_by',
                      'zcoin_calculator')
    actions = ['approve_books', 'reject_books', 'calculate_zcoin']
    
    def status_badge(self, obj):
        """Display status with color"""
        colors = {
            'pending': 'orange',
            'reviewed': 'blue',
            'approved': 'green',
            'rejected': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; border-radius:10px; font-size:12px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def zcoin_calculator(self, obj):
        """Display calculator button"""
        return format_html(
            '<a href="calculate/" class="button" style="background:#4CAF50; color:white; padding:8px 16px; border-radius:4px; text-decoration:none;">'
            'Calculate ZCoin</a>'
        )
    zcoin_calculator.short_description = 'Calculator'
    
    def approve_books(self, request, queryset):
        """Approve books and award ZCoin (superuser only)"""
        if not request.user.is_superuser:
            messages.error(request, 'Only superusers can approve books')
            return
        
        count = 0
        for book in queryset.filter(status='reviewed'):
            # Award ZCoin
            wallet = Wallet.get_or_create_for_user(book.added_by)
            wallet.zcoin_balance += book.zcoin_value
            wallet.save()
            
            # Update book
            book.status = 'approved'
            book.is_available = True
            book.approved_by = request.user
            book.approved_at = timezone.now()
            book.save()
            
            # Record transaction
            Transaction.objects.create(
                user=book.added_by,
                transaction_type='topup',
                amount=book.zcoin_value,
                description=f'Book approved: {book.title}'
            )
            
            count += 1
        
        self.message_user(request, f'{count} books approved and ZCoin awarded')
    approve_books.short_description = 'Approve books & award ZCoin'
    
    def reject_books(self, request, queryset):
        """Reject books (superuser only)"""
        if not request.user.is_superuser:
            messages.error(request, 'Only superusers can reject books')
            return
        
        count = queryset.update(status='rejected', is_available=False)
        self.message_user(request, f'{count} books rejected')
    reject_books.short_description = 'Reject books'
    
    def calculate_zcoin(self, request, queryset):
        """Calculate ZCoin for selected books"""
        count = 0
        for book in queryset:
            result = ZCoinCalculator.calculate_zcoin(
                category=book.genre,
                condition=book.assessed_condition or book.condition,
                cover_type=book.cover_type,
                has_images=book.has_images,
                has_dust_jacket=book.has_dust_jacket,
                is_first_edition=book.is_first_edition,
                is_signed=book.is_signed,
                user=request.user,
                book=book
            )
            book.zcoin_value = Decimal(str(result['zcoin']))
            book.price_birr = Decimal(str(result['price_birr']))
            book.save()
            count += 1
        
        self.message_user(request, f'ZCoin calculated for {count} books')
    calculate_zcoin.short_description = 'Calculate ZCoin'

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
# 6. COMMODITY ADMIN
# ===================================================================

@admin.register(Commodity)
class CommodityAdmin(admin.ModelAdmin):
    """Admin interface for Commodity items"""
    list_display = ('name', 'commodity_type_display', 'price_birr', 'zcoin_value', 
                    'stock_status', 'is_available', 'created_at')
    list_filter = ('commodity_type', 'is_available', 'created_at')
    search_fields = ('name', 'description')
    list_editable = ('is_available', 'price_birr', 'zcoin_value')
    readonly_fields = ('created_at', 'updated_at', 'stock_status_display')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'commodity_type', 'image_url')
        }),
        ('Pricing & Inventory', {
            'fields': ('price_birr', 'zcoin_value', 'stock_quantity', 'is_available')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at', 'stock_status_display')
        }),
    )
    actions = ['restock_items', 'toggle_availability', 'update_zcoin_from_price']
    
    def commodity_type_display(self, obj):
        """Display commodity type with icon"""
        icons = {
            'stationery': '📝',
            'book_accessory': '🎀',
            'reading_aid': '🔍',
            'gift': '🎁',
        }
        icon = icons.get(obj.commodity_type, '📦')
        return format_html(
            '<span style="display: flex; align-items: center; gap: 5px;">'
            '{} {}</span>',
            icon, obj.get_commodity_type_display()
        )
    commodity_type_display.short_description = 'Type'
    
    def stock_status(self, obj):
        """Display stock status with color coding"""
        if obj.stock_quantity == 0:
            return format_html(
                '<span style="background:#ef4444; color:white; padding:2px 8px; border-radius:10px; font-size:11px;">'
                'OUT OF STOCK</span>'
            )
        elif obj.stock_quantity <= 10:
            return format_html(
                '<span style="background:#fb923c; color:white; padding:2px 8px; border-radius:10px; font-size:11px;">'
                'LOW-<strong>{}</strong></span>', obj.stock_quantity
            )
        else:
            return format_html(
                '<span style="background:#22c55e; color:white; padding:2px 8px; border-radius:10px; font-size:11px;">'
                'INSTOCK-<strong>{}</strong></span>', obj.stock_quantity
            )
    stock_status.short_description = 'Stock'
    
    def stock_status_display(self, obj):
        """Detailed stock status for readonly field"""
        if obj.stock_quantity == 0:
            return "❌ Out of Stock"
        elif obj.stock_quantity <= 5:
            return f"⚠️ Low Stock: {obj.stock_quantity} units remaining"
        elif obj.stock_quantity <= 10:
            return f"📦 Moderate Stock: {obj.stock_quantity} units"
        else:
            return f"✅ Good Stock: {obj.stock_quantity} units"
    stock_status_display.short_description = 'Current Stock Status'
    
    def restock_items(self, request, queryset):
        """Restock selected commodities"""
        for commodity in queryset:
            commodity.stock_quantity += 10  # Add 10 units
            commodity.is_available = True
            commodity.save()
        
        self.message_user(request, f"Restocked {queryset.count()} commodities (+10 units each)")
    restock_items.short_description = "Restock (+10 units)"
    
    def toggle_availability(self, request, queryset):
        """Toggle availability of selected commodities"""
        for commodity in queryset:
            commodity.is_available = not commodity.is_available
            commodity.save()
        
        self.message_user(request, f"Toggled availability for {queryset.count()} commodities")
    toggle_availability.short_description = "Toggle Availability"
    
    def update_zcoin_from_price(self, request, queryset):
        """Update ZCoin values based on price (100 ZCoin = 1 Birr)"""
        updated = 0
        for commodity in queryset:
            # Convert price_birr to ZCoin (100 ZCoin per 1 Birr)
            new_zcoin = commodity.price_birr * 100
            if commodity.zcoin_value != new_zcoin:
                commodity.zcoin_value = new_zcoin
                commodity.save()
                updated += 1
        
        if updated:
            self.message_user(request, f"Updated ZCoin values for {updated} commodities")
        else:
            self.message_user(request, "No ZCoin values needed updating")
    update_zcoin_from_price.short_description = "Update ZCoin from Price"

# ===================================================================
# 7. COMMODITY PURCHASE ADMIN
# ===================================================================

class CommodityPurchaseStatusFilter(admin.SimpleListFilter):
    """Custom filter for purchase status"""
    title = 'Purchase Status'
    parameter_name = 'status_group'
    
    def lookups(self, request, model_admin):
        return (
            ('active', 'Active Orders'),
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        )
    
    def queryset(self, request, queryset):
        if self.value() == 'active':
            return queryset.filter(status__in=['pending', 'processing'])
        elif self.value():
            return queryset.filter(status=self.value())
        return queryset

@admin.register(CommodityPurchase)
class CommodityPurchaseAdmin(admin.ModelAdmin):
    """Admin interface for Commodity Purchases"""
    list_display = ('purchase_id', 'user_link', 'commodity_link', 'quantity', 
                    'total_zcoin_display', 'status_badge', 'created_at', 'delivery_info')
    list_filter = (CommodityPurchaseStatusFilter, 'created_at', 'commodity__commodity_type')
    search_fields = ('user__username', 'commodity__name', 'contact_phone')
    readonly_fields = ('user', 'commodity', 'total_zcoin', 'status', 'created_at', 
                      'updated_at', 'purchase_summary')
    fieldsets = (
        ('Purchase Details', {
            'fields': ('purchase_summary', 'user', 'commodity', 'quantity', 'total_zcoin')
        }),
        ('Delivery Information', {
            'fields': ('delivery_address', 'contact_phone', 'special_instructions')
        }),
        ('Order Management', {
            'fields': ('status',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    actions = ['mark_as_processing', 'mark_as_shipped', 'mark_as_delivered', 
               'mark_as_cancelled', 'refund_purchase']
    
    def purchase_id(self, obj):
        """Display purchase ID"""
        return f"PUR-{obj.id:06d}"
    purchase_id.short_description = 'Purchase ID'
    
    def user_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User"
    
    def commodity_link(self, obj):
        url = reverse("admin:core_commodity_change", args=[obj.commodity.id])
        return format_html('<a href="{}">{}</a>', url, obj.commodity.name)
    commodity_link.short_description = "Commodity"
    
    def total_zcoin_display(self, obj):
        """Display total ZCoin spent"""
        return format_html(
            '<span style="font-weight: bold; color: #22c55e;">Ⓩ {}</span>',
            format(obj.total_zcoin, ',').rstrip('0').rstrip('.')
        )
    total_zcoin_display.short_description = 'Total ZCoin'
    
    def status_badge(self, obj):
        """Display status with color-coded badge"""
        colors = {
            'pending': '#fb923c',     # orange
            'processing': '#3b82f6',  # blue
            'shipped': '#8b5cf6',     # purple
            'delivered': '#22c55e',   # green
            'cancelled': '#ef4444',   # red
        }
        icons = {
            'pending': '⏳',
            'processing': '⚙️',
            'shipped': '🚚',
            'delivered': '✅',
            'cancelled': '❌',
        }
        color = colors.get(obj.status, '#666')
        icon = icons.get(obj.status, '❓')
        
        return format_html(
            '<span style="background:{}; color:white; padding:4px 10px; border-radius:12px; '
            'font-size:12px; display:inline-flex; align-items:center; gap:5px;">'
            '{} {}</span>',
            color, icon, obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def delivery_info(self, obj):
        """Display delivery information"""
        if obj.delivery_address:
            return format_html(
                '<div style="max-width: 200px;">'
                '<div><strong>📞</strong> {}</div>'
                '<div style="font-size: 11px; color: #666; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">'
                '{}</div>'
                '</div>',
                obj.contact_phone or 'Not provided',
                obj.delivery_address[:50] + '...' if len(obj.delivery_address) > 50 else obj.delivery_address
            )
        return "No delivery info"
    delivery_info.short_description = 'Delivery Info'
    
    def purchase_summary(self, obj):
        """Display purchase summary for readonly field"""
        return format_html(
            '<div style="background: rgba(7, 40, 92, 0.2); padding: 15px; border-radius: 8px; border: 1px solid #ddd;">'
            '<h4 style="margin-top: 0;">📦 Purchase Summary</h4>'
            '<div><strong>Item:</strong> {}</div>'
            '<div><strong>Type:</strong> {}</div>'
            '<div><strong>Quantity:</strong> {}</div>'
            '<div><strong>Unit Price:</strong> Ⓩ {}</div>'
            '<div><strong>Total Cost:</strong> Ⓩ {}</div>'
            '<div><strong>Purchased On:</strong> {}</div>'
            '</div>',
            obj.commodity.name,
            obj.commodity.get_commodity_type_display(),
            obj.quantity,
            format(obj.commodity.zcoin_value, ',').rstrip('0').rstrip('.'),
            format(obj.total_zcoin, ',').rstrip('0').rstrip('.'),
            obj.created_at.strftime('%Y-%m-%d %H:%M')
        )
    purchase_summary.short_description = 'Summary'
    
    def mark_as_processing(self, request, queryset):
        """Mark purchases as processing"""
        count = queryset.filter(status='pending').update(status='processing')
        self.message_user(request, f"{count} purchases marked as processing")
    mark_as_processing.short_description = "Mark as Processing"
    
    def mark_as_shipped(self, request, queryset):
        """Mark purchases as shipped"""
        count = queryset.filter(status='processing').update(status='shipped')
        self.message_user(request, f"{count} purchases marked as shipped")
    mark_as_shipped.short_description = "Mark as Shipped"
    
    def mark_as_delivered(self, request, queryset):
        """Mark purchases as delivered"""
        count = queryset.filter(status='shipped').update(status='delivered')
        self.message_user(request, f"{count} purchases marked as delivered")
    mark_as_delivered.short_description = "Mark as Delivered"
    
    def mark_as_cancelled(self, request, queryset):
        """Cancel purchases and refund ZCoin"""
        with transaction.atomic():
            count = 0
            for purchase in queryset.filter(status__in=['pending', 'processing']):
                # Refund ZCoin to user
                wallet = Wallet.get_or_create_for_user(purchase.user)
                wallet.zcoin_balance += purchase.total_zcoin
                wallet.save()
                
                # Restock the commodity
                commodity = purchase.commodity
                commodity.stock_quantity += purchase.quantity
                commodity.save()
                
                # Update purchase status
                purchase.status = 'cancelled'
                purchase.save()
                
                # Record refund transaction
                Transaction.objects.create(
                    user=purchase.user,
                    transaction_type='refund',
                    amount=purchase.total_zcoin,
                    description=f"Commodity purchase cancelled: {purchase.commodity.name} x{purchase.quantity}"
                )
                
                count += 1
            
            self.message_user(
                request, 
                f"{count} purchases cancelled. ZCoin refunded and items restocked."
            )
    mark_as_cancelled.short_description = "Cancel & Refund"
    
    def refund_purchase(self, request, queryset):
        """Refund ZCoin for already delivered/cancelled purchases"""
        with transaction.atomic():
            count = 0
            for purchase in queryset.filter(status__in=['delivered', 'cancelled']):
                # Check if already refunded
                existing_refunds = Transaction.objects.filter(
                    user=purchase.user,
                    description__contains=f"Commodity refund: {purchase.commodity.name}"
                ).count()
                
                if existing_refunds == 0:
                    # Refund ZCoin
                    wallet = Wallet.get_or_create_for_user(purchase.user)
                    wallet.zcoin_balance += purchase.total_zcoin
                    wallet.save()
                    
                    # Record refund transaction
                    Transaction.objects.create(
                        user=purchase.user,
                        transaction_type='refund',
                        amount=purchase.total_zcoin,
                        description=f"Commodity refund: {purchase.commodity.name} x{purchase.quantity}"
                    )
                    
                    count += 1
            
            self.message_user(request, f"{count} purchases refunded.")
    refund_purchase.short_description = "Refund ZCoin"
    
    def save_model(self, request, obj, form, change):
        """Handle status changes"""
        if change and 'status' in form.changed_data:
            old_status = Book.objects.get(pk=obj.pk).status if obj.pk else None
            new_status = obj.status
            
            # If changing from delivered to cancelled, restock items
            if old_status == 'delivered' and new_status == 'cancelled':
                # Restock the commodity
                commodity = obj.commodity
                commodity.stock_quantity += obj.quantity
                commodity.save()
                
                # Refund ZCoin
                wallet = Wallet.get_or_create_for_user(obj.user)
                wallet.zcoin_balance += obj.total_zcoin
                wallet.save()
                
                Transaction.objects.create(
                    user=obj.user,
                    transaction_type='refund',
                    amount=obj.total_zcoin,
                    description=f"Commodity order cancelled: {obj.commodity.name}"
                )
                
                messages.success(request, 
                    f"Order cancelled. {obj.quantity} units restocked and Ⓩ{obj.total_zcoin} refunded."
                )
        
        super().save_model(request, obj, form, change)

# ===================================================================
# 8. ZCOIN CALCULATOR SETTINGS ADMIN
# ===================================================================

@admin.register(ZCoinCalculatorSettings)
class ZCoinCalculatorSettingsAdmin(admin.ModelAdmin):
    """Admin for calculator settings"""
    list_display = ('updated_at',)
    
    fieldsets = (
        ('Category Base Values', {
            'fields': (
                ('classics_base', 'nonfiction_base'),
                ('fiction_base', 'contemporary_base'),
                ('academic_base', 'children_base'),
                ('reference_base',)
            )
        }),
        ('Condition Multipliers', {
            'fields': (
                ('excellent_multiplier', 'good_multiplier'),
                ('fair_multiplier', 'poor_multiplier')
            )
        }),
        ('Cover Bonuses', {
            'fields': ('hardcover_bonus', 'dust_jacket_bonus', 'no_cover_penalty')
        }),
        ('Feature Bonuses', {
            'fields': ('has_images_bonus', 'is_first_edition_bonus', 'is_signed_bonus')
        }),
        ('Limits & Conversion', {
            'fields': ('min_zcoin', 'max_zcoin', 'zcoin_to_birr_rate')
        }),
    )

# ===================================================================
# 9. ZCOIN CALCULATION LOG ADMIN
# ===================================================================

@admin.register(ZCoinCalculationLog)
class ZCoinCalculationLogAdmin(admin.ModelAdmin):
    """Admin for ZCoin calculation logs"""
    list_display = ('id', 'book_link', 'category', 'condition', 'calculated_zcoin', 
                    'final_zcoin', 'calculated_by', 'created_at')
    list_filter = ('category', 'condition', 'created_at')
    search_fields = ('book__title', 'book__author', 'calculated_by__username')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    
    def book_link(self, obj):
        if obj.book:
            url = reverse("admin:core_book_change", args=[obj.book.id])
            return format_html('<a href="{}">{}</a>', url, obj.book.title)
        return "Standalone Calculation"
    book_link.short_description = "Book"

# ===================================================================
# ADMIN SITE CUSTOMIZATION
# ===================================================================
admin.site.site_header = "Zero Book Swap - Admin Panel"
admin.site.site_title = "Zero Admin"
admin.site.index_title = "Welcome to Zero Book Swap Management"

# Optional: Reorder admin index to group related models
def get_app_list(self, request):
    """
    Reorder the admin index to group related models
    """
    app_dict = self._build_app_dict(request)
    
    # Reorder apps
    app_order = ['auth', 'core']
    
    app_list = []
    for app in app_order:
        if app in app_dict:
            app_list.append(app_dict[app])
    
    # Add any remaining apps
    for app in app_dict:
        if app not in app_order:
            app_list.append(app_dict[app])
    
    # Reorder models within core app
    for app in app_list:
        if app['app_label'] == 'core':
            model_order = [
                'user',
                'wallet',
                'book',
                'swaprequest',
                'commodity',
                'commoditypurchase',
                'coinpackage',
                'payment',
                'transaction',
                'zcoincalculationsettings',
                'zcoincalculationlog',
            ]
            
            ordered_models = []
            for model_name in model_order:
                for model in app['models']:
                    if model['object_name'].lower() == model_name:
                        ordered_models.append(model)
                        break
            
            # Add any remaining models
            for model in app['models']:
                if model not in ordered_models:
                    ordered_models.append(model)
            
            app['models'] = ordered_models
    
    return app_list

admin.AdminSite.get_app_list = get_app_list