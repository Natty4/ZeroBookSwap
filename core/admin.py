# admin.py - FINAL VERSION (EVERYTHING INCLUDED)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse, path
from django.shortcuts import render, redirect
from decimal import Decimal
from django import forms
from django.utils.html import format_html
from django.contrib import messages
from django.http import JsonResponse
from .utils.zcoin_calculator import ZCoinCalculator
from .models import (
    UserProfile, Wallet, Book, SwapRequest,
    CoinPackage, Payment, Transaction,
    ZCoinCalculatorSettings, ZCoinCalculationLog,
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
# @admin.register(Book)
# class BookAdmin(admin.ModelAdmin):
#     list_display = ('title', 'author', 'added_by', 'genre', 'condition', 
#                    'zcoin_value', 'price_birr', 'book_type', 'status_colored', 
#                    'is_available', 'status', 'created_at')
#     list_filter = ('book_type', 'genre', 'condition', 'status', 'is_available', 'created_at')
#     search_fields = ('title', 'author', 'added_by__username', 'added_by__email')
#     list_editable = ('status', 'is_available', 'zcoin_value', 'price_birr')
#     readonly_fields = ('created_at', 'updated_at', 'added_by')
#     date_hierarchy = 'created_at'
    
#     # Add status colored display
#     def status_colored(self, obj):
#         colors = {
#             'pending': '#fb923c',  # orange
#             'approved': '#22c55e', # green
#             'rejected': '#ef4444', # red
#         }
#         return format_html(
#             '<span style="background:{}; color:white; padding:2px 8px; border-radius:4px;">{}</span>',
#             colors.get(obj.status, '#666'),
#             obj.status.replace('_', ' ').title()
#         )
#     status_colored.short_description = "Status"
    
#     # Add custom actions for book approval
#     actions = ['approve_books', 'reject_books', 'calculate_and_award_zcoin']
    
#     def approve_books(self, request, queryset):
#         count = 0
#         for book in queryset.filter(status='pending'):
#             # Update book status
#             book.status = 'approved'
#             book.is_available = True
#             book.save()
            
#             # Award ZCoin to user
#             wallet = Wallet.get_or_create_for_user(book.added_by)
            
#             # Calculate ZCoin value (use either existing zcoin_value or calculate)
#             if book.zcoin_value and book.zcoin_value > 0:
#                 award_amount = book.zcoin_value
#             else:
#                 # Calculate based on genre and condition
#                 zcoin_values = {
#                     'category': {
#                         'classics': 30,
#                         'non-fiction': 25,
#                         'fiction': 20,
#                         'contemporary': 15,
#                     },
#                     'condition': {
#                         'excellent': 50,
#                         'good': 35,
#                         'fair': 20,
#                         'poor': 10,
#                     }
#                 }
#                 category_value = zcoin_values['category'].get(book.genre, 15)
#                 condition_value = zcoin_values['condition'].get(book.condition, 20)
#                 award_amount = Decimal(category_value + condition_value)
                
#                 # Update book's zcoin_value for future reference
#                 book.zcoin_value = award_amount
#                 book.save()
            
#             # Add to user's wallet
#             wallet.zcoin_balance += award_amount
#             wallet.save()
            
#             # Create transaction record
#             Transaction.objects.create(
#                 user=book.added_by,
#                 transaction_type='topup',
#                 amount=award_amount,
#                 description=f"Book approved: {book.title}",
#                 related_swap=None
#             )
            
#             count += 1
        
#         self.message_user(request, f"{count} books approved and ZCoin awarded to users.")
#     approve_books.short_description = "Approve books & award ZCoin"
    
#     def reject_books(self, request, queryset):
#         count = queryset.filter(status='pending').update(status='rejected')
#         self.message_user(request, f"{count} books rejected.")
#     reject_books.short_description = "Reject books"
    
#     def calculate_and_award_zcoin(self, request, queryset):
#         # This action recalculates and awards ZCoin for already approved books
#         count = 0
#         for book in queryset.filter(status='approved'):
#             wallet = Wallet.get_or_create_for_user(book.added_by)
            
#             # Recalculate ZCoin value
#             zcoin_values = {
#                 'category': {
#                     'classics': 30,
#                     'non-fiction': 25,
#                     'fiction': 20,
#                     'contemporary': 15,
#                 },
#                 'condition': {
#                     'excellent': 50,
#                     'good': 35,
#                     'fair': 20,
#                     'poor': 10,
#                 }
#             }
#             category_value = zcoin_values['category'].get(book.genre, 15)
#             condition_value = zcoin_values['condition'].get(book.condition, 20)
#             award_amount = Decimal(category_value + condition_value)
            
#             # Award difference if zcoin_value is different
#             difference = award_amount - book.zcoin_value
#             if difference != 0:
#                 wallet.zcoin_balance += difference
#                 wallet.save()
                
#                 book.zcoin_value = award_amount
#                 book.save()
                
#                 Transaction.objects.create(
#                     user=book.added_by,
#                     transaction_type='refund' if difference > 0 else 'topup',
#                     amount=difference,
#                     description=f"ZCoin adjustment for: {book.title}",
#                     related_swap=None
#                 )
#                 count += 1
        
#         self.message_user(request, f"ZCoin recalculated for {count} books.")
#     calculate_and_award_zcoin.short_description = "Recalculate & adjust ZCoin"


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
# ZCOIN CALCULATOR ADMIN INTERFACE
# ===================================================================

class ZCoinCalculatorForm(forms.Form):
    """Form for ZCoin calculation in admin"""
    category = forms.ChoiceField(
        choices=ZCoinCalculatorSettings.CATEGORIES,
        initial='fiction'
    )
    condition = forms.ChoiceField(
        choices=ZCoinCalculatorSettings.CONDITION_MULTIPLIERS,
        initial='good'
    )
    cover_type = forms.ChoiceField(
        choices=ZCoinCalculatorSettings.BOOK_COVERS,
        required=False,
        initial=''
    )
    has_images = forms.BooleanField(required=False, initial=False)
    has_dust_jacket = forms.BooleanField(required=False, initial=False)
    is_first_edition = forms.BooleanField(required=False, initial=False)
    is_signed = forms.BooleanField(required=False, initial=False)
    manual_zcoin = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        help_text="Enter manual ZCoin value to override calculation"
    )

@admin.register(ZCoinCalculatorSettings)
class ZCoinCalculatorSettingsAdmin(admin.ModelAdmin):
    """Admin for ZCoin calculator settings"""
    list_display = ('updated_at', 'min_zcoin', 'max_zcoin', 'zcoin_to_birr_rate')
    fieldsets = (
        ('Category Base Values', {
            'fields': ('classics_base', 'nonfiction_base', 'fiction_base', 
                      'contemporary_base', 'academic_base', 'children_base', 
                      'reference_base')
        }),
        ('Condition Multipliers', {
            'fields': ('excellent_multiplier', 'good_multiplier', 
                      'fair_multiplier', 'poor_multiplier')
        }),
        ('Cover Bonuses/Penalties', {
            'fields': ('hardcover_bonus', 'dust_jacket_bonus', 'no_cover_penalty')
        }),
        ('Additional Bonuses', {
            'fields': ('has_images_bonus', 'has_original_dust_jacket', 
                      'is_first_edition_bonus', 'is_signed_bonus')
        }),
        ('Limits and Conversion', {
            'fields': ('min_zcoin', 'max_zcoin', 'zcoin_to_birr_rate')
        }),
    )

@admin.register(ZCoinCalculationLog)
class ZCoinCalculationLogAdmin(admin.ModelAdmin):
    """Admin for ZCoin calculation logs"""
    list_display = ('created_at', 'category', 'condition', 'calculated_zcoin', 
                   'final_zcoin', 'manual_override', 'calculated_by')
    list_filter = ('manual_override', 'category', 'condition', 'created_at')
    search_fields = ('category', 'condition', 'notes', 'book__title')
    readonly_fields = ('created_at', 'book', 'calculated_by', 'base_value', 
                      'condition_multiplier', 'bonuses', 'calculated_zcoin', 
                      'final_zcoin', 'manual_override', 'manual_zcoin', 
                      'manual_price_birr', 'notes')
    
    def has_add_permission(self, request):
        return False  # Logs are created automatically

# ===================================================================
# ENHANCED BOOK ADMIN WITH ZCOIN CALCULATOR
# ===================================================================

class BookAdminForm(forms.ModelForm):
    """Enhanced form for Book admin with ZCoin calculator"""
    class Meta:
        model = Book
        fields = '__all__'
    
    # Add manual override fields
    manual_zcoin_override = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        help_text="Override calculated ZCoin value"
    )
    manual_price_override = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        help_text="Override calculated price in Birr"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # If instance exists, show current values
        if self.instance and self.instance.pk:
            self.fields['manual_zcoin_override'].initial = self.instance.zcoin_value
            self.fields['manual_price_override'].initial = self.instance.price_birr

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    """Enhanced Book admin with ZCoin calculator integration"""
    form = BookAdminForm
    change_form_template = 'admin/core/book/change_form.html'
    
    list_display = ('title', 'author', 'added_by_link', 'genre', 'condition', 
                   'zcoin_value', 'price_birr', 'book_type', 'status_colored', 
                   'is_available', 'status', 'created_at')
    list_filter = ('book_type', 'genre', 'condition', 'status', 'is_available', 'created_at')
    search_fields = ('title', 'author', 'added_by__username', 'added_by__email')
    list_editable = ('status', 'is_available', 'zcoin_value', 'price_birr')
    readonly_fields = ('created_at', 'updated_at', 'added_by')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Book Information', {
            'fields': ('title', 'author', 'genre', 'description', 'cover_image_url')
        }),
        ('Physical Details', {
            'fields': ('condition', 'book_type')
        }),
        ('ZCoin Calculator', {
            'fields': ('manual_zcoin_override', 'manual_price_override'),
            'classes': ('collapse',),
            'description': 'Use calculator or enter manual values'
        }),
        ('Pricing & Status', {
            'fields': ('zcoin_value', 'price_birr', 'status', 'is_available')
        }),
        ('Additional Info', {
            'fields': ('added_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('calculate-zcoin/', self.admin_site.admin_view(self.calculate_zcoin_view), 
                 name='book_calculate_zcoin'),
            path('<int:book_id>/calculate/', self.admin_site.admin_view(self.calculate_book_zcoin), 
                 name='book_calculate_book_zcoin'),
        ]
        return custom_urls + urls
    
    def calculate_zcoin_view(self, request):
        """Standalone ZCoin calculator view"""
        if request.method == 'POST':
            form = ZCoinCalculatorForm(request.POST)
            if form.is_valid():
                result = ZCoinCalculator.calculate_zcoin(
                    category=form.cleaned_data['category'],
                    condition=form.cleaned_data['condition'],
                    cover_type=form.cleaned_data['cover_type'] or None,
                    has_images=form.cleaned_data['has_images'],
                    has_dust_jacket=form.cleaned_data['has_dust_jacket'],
                    is_first_edition=form.cleaned_data['is_first_edition'],
                    is_signed=form.cleaned_data['is_signed'],
                    manual_zcoin=form.cleaned_data['manual_zcoin'],
                    user=request.user
                )
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse(result)
                
                return render(request, 'admin/core/book/calculator_result.html', {
                    'result': result,
                    'form': form,
                    'title': 'ZCoin Calculator Result',
                })
        else:
            form = ZCoinCalculatorForm()
        
        return render(request, 'admin/core/book/calculator.html', {
            'form': form,
            'title': 'ZCoin Calculator',
            'opts': self.model._meta,
        })
    
    def calculate_book_zcoin(self, request, book_id):
        """Calculate ZCoin for a specific book"""
        try:
            book = Book.objects.get(id=book_id)
            
            # Auto-calculate based on book attributes
            result = ZCoinCalculator.calculate_zcoin(
                category=book.genre,
                condition=book.condition,
                book=book,
                user=request.user
            )
            
            # Update book with calculated values
            book.zcoin_value = result['zcoin']
            book.price_birr = result['price_birr']
            book.save()
            
            messages.success(request, f"Calculated ZCoin: {result['zcoin']} (Price: {result['price_birr']} Birr)")
            
        except Book.DoesNotExist:
            messages.error(request, "Book not found")
        
        return redirect(f'../{book_id}/change/')
    
    def save_model(self, request, obj, form, change):
        """Override save to handle manual overrides"""
        from decimal import Decimal
        from .models import ZCoinCalculatorSettings
        
        manual_zcoin = form.cleaned_data.get('manual_zcoin_override')
        manual_price = form.cleaned_data.get('manual_price_override')
        
        # If manual values are provided, use them
        if manual_zcoin is not None:
            # Ensure manual_zcoin is Decimal
            if isinstance(manual_zcoin, float):
                manual_zcoin_decimal = Decimal(str(manual_zcoin))
            else:
                manual_zcoin_decimal = Decimal(manual_zcoin)
                
            obj.zcoin_value = manual_zcoin_decimal
            
            # If manual price is also provided, use it, otherwise calculate from ZCoin
            if manual_price is not None:
                if isinstance(manual_price, float):
                    obj.price_birr = Decimal(str(manual_price))
                else:
                    obj.price_birr = Decimal(manual_price)
            else:
                settings = ZCoinCalculatorSettings.get_active_settings()
                obj.price_birr = manual_zcoin_decimal * settings.zcoin_to_birr_rate
            
            # Log manual override
            ZCoinCalculationLog.objects.create(
                book=obj,
                calculated_by=request.user,
                category=obj.genre,
                condition=obj.condition,
                base_value=Decimal('0.00'),
                condition_multiplier=Decimal('0.00'),
                bonuses=Decimal('0.00'),
                calculated_zcoin=manual_zcoin_decimal,
                final_zcoin=manual_zcoin_decimal,
                manual_override=True,
                manual_zcoin=manual_zcoin_decimal,
                manual_price_birr=obj.price_birr,
                notes="Manual override in admin"
            )
        
        super().save_model(request, obj, form, change)
    
    def added_by_link(self, obj):
        url = reverse("admin:auth_user_change", args=[obj.added_by.id])
        return format_html('<a href="{}">{}</a>', url, obj.added_by.username)
    added_by_link.short_description = "Added By"
    
    def status_colored(self, obj):
        colors = {
            'pending': '#fb923c',
            'approved': '#22c55e',
            'rejected': '#ef4444',
        }
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; border-radius:4px;">{}</span>',
            colors.get(obj.status, '#666'),
            obj.status.replace('_', ' ').title()
        )
    status_colored.short_description = "Status"
    
    # Add custom actions
    actions = ['approve_books', 'reject_books', 'calculate_zcoin_for_books', 
               'apply_manual_zcoin', 'recalculate_all_zcoin']
    
    def approve_books(self, request, queryset):
        """Approve books and award ZCoin to uploaders"""
        from decimal import Decimal
        from .utils.zcoin_calculator import ZCoinCalculator
        
        count = 0
        for book in queryset.filter(status='pending'):
            try:
                # Update book status
                book.status = 'approved'
                book.is_available = True
                
                # Calculate ZCoin value for this book
                result = ZCoinCalculator.calculate_zcoin(
                    category=book.genre,
                    condition=book.condition,
                    book=book,
                    user=request.user
                )
                
                # Update book with calculated values
                book.zcoin_value = Decimal(str(result['zcoin']))  # Convert back to Decimal
                book.price_birr = Decimal(str(result['price_birr']))  # Convert back to Decimal
                book.save()
                
                # Award ZCoin to user
                wallet = Wallet.get_or_create_for_user(book.added_by)
                award_amount = Decimal(str(result['zcoin']))
                
                wallet.zcoin_balance += award_amount
                wallet.save()
                
                # Record transaction
                Transaction.objects.create(
                    user=book.added_by,
                    transaction_type='topup',
                    amount=award_amount,
                    description=f"Book upload approved: {book.title}",
                    related_swap=None
                )
                
                count += 1
                
            except Exception as e:
                self.message_user(request, f"Error approving book '{book.title}': {str(e)}", messages.ERROR)
        
        self.message_user(request, f"{count} books approved and ZCoin awarded to users.")
    approve_books.short_description = "Approve books & award ZCoin"

    def calculate_zcoin_for_books(self, request, queryset):
        """Calculate ZCoin for selected books"""
        from decimal import Decimal
        from .utils.zcoin_calculator import ZCoinCalculator
        
        count = 0
        for book in queryset:
            try:
                result = ZCoinCalculator.calculate_zcoin(
                    category=book.genre,
                    condition=book.condition,
                    book=book,
                    user=request.user
                )
                book.zcoin_value = Decimal(str(result['zcoin']))
                book.price_birr = Decimal(str(result['price_birr']))
                book.save()
                count += 1
            except Exception as e:
                self.message_user(request, f"Error calculating for '{book.title}': {str(e)}", messages.ERROR)
        
        self.message_user(request, f"ZCoin calculated for {count} books.")
    calculate_zcoin_for_books.short_description = "Calculate ZCoin for books"

    def apply_manual_zcoin(self, request, queryset):
        """Apply manual ZCoin value to selected books"""
        from decimal import Decimal
        from .models import ZCoinCalculatorSettings
        
        # You could add a form here for manual input
        # For now, we'll apply a fixed value
        manual_value = Decimal('50.00')  # Default value
        count = 0
        
        for book in queryset:
            try:
                book.zcoin_value = manual_value
                settings = ZCoinCalculatorSettings.get_active_settings()
                book.price_birr = manual_value * settings.zcoin_to_birr_rate
                book.save()
                
                # Log the manual override
                ZCoinCalculationLog.objects.create(
                    book=book,
                    calculated_by=request.user,
                    category=book.genre,
                    condition=book.condition,
                    base_value=Decimal('0.00'),
                    condition_multiplier=Decimal('0.00'),
                    bonuses=Decimal('0.00'),
                    calculated_zcoin=manual_value,
                    final_zcoin=manual_value,
                    manual_override=True,
                    manual_zcoin=manual_value,
                    manual_price_birr=book.price_birr,
                    notes=f"Batch manual override: {manual_value} ZCoin"
                )
                count += 1
            except Exception as e:
                self.message_user(request, f"Error applying to '{book.title}': {str(e)}", messages.ERROR)
        
        self.message_user(request, f"Applied manual ZCoin ({manual_value}) to {count} books.")
    apply_manual_zcoin.short_description = "Apply manual ZCoin value"
    
    def recalculate_all_zcoin(self, request, queryset):
        """Recalculate ZCoin using latest calculator settings"""
        count = 0
        for book in queryset:
            result = ZCoinCalculator.calculate_zcoin(
                category=book.genre,
                condition=book.condition,
                book=book,
                user=request.user
            )
            book.zcoin_value = result['zcoin']
            book.price_birr = result['price_birr']
            book.save()
            count += 1
        self.message_user(request, f"ZCoin recalculated for {count} books using latest settings.")
    recalculate_all_zcoin.short_description = "Recalculate ZCoin with current settings"
    
    
# ===================================================================
# ADMIN SITE CUSTOMIZATION
# ===================================================================
admin.site.site_header = "Zero Book Swap - Admin Panel"
admin.site.site_title = "Zero Admin"
admin.site.index_title = "Welcome to Zero Book Swap Management"