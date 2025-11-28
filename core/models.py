from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from decimal import Decimal

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    zcoin_balance = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet - {self.zcoin_balance} ZCoin"
    
    @classmethod
    def get_or_create_for_user(cls, user):
        wallet, created = cls.objects.get_or_create(user=user, defaults={'zcoin_balance': Decimal('0.00')})
        return wallet

class Book(models.Model):
    BOOK_CONDITIONS = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]
    
    BOOK_GENRES = [
        ('fiction', 'Fiction'),
        ('non-fiction', 'Non-Fiction'),
        ('classics', 'Classics'),
        ('contemporary', 'Contemporary'),
    ]
    
    BOOK_TYPES = [
        ('swap', 'For Swap'),
        ('new', 'New Book'),
    ]
    
    title = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, null=True, blank=True)
    author = models.CharField(max_length=255)
    genre = models.CharField(max_length=50, choices=BOOK_GENRES)
    description = models.TextField(blank=True)
    cover_image_url = models.CharField(max_length=999, null=True, blank=True)
    condition = models.CharField(max_length=20, choices=BOOK_CONDITIONS, default='good')
    zcoin_value = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    price_birr = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    book_type = models.CharField(max_length=10, choices=BOOK_TYPES)
    is_available = models.BooleanField(default=True)
    added_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='books_added')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['added_by', 'title'],
                name='unique_user_book_title'
            )
        ]

    def __str__(self):
        return f"{self.title} by {self.author}"

class SwapRequest(models.Model):
    SWAP_STATUS = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='swap_requests')
    requested_book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='swap_requests')
    user_book_title = models.CharField(max_length=255)
    user_book_author = models.CharField(max_length=255)
    user_book_genre = models.CharField(max_length=50, choices=Book.BOOK_GENRES)
    user_book_condition = models.CharField(max_length=20, choices=Book.BOOK_CONDITIONS)
    calculated_zcoin = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    status = models.CharField(max_length=20, choices=SWAP_STATUS, default='pending')
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Swap: {self.user_book_title} for {self.requested_book.title}"

class CoinPackage(models.Model):
    name = models.CharField(max_length=100)
    zcoin_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    price_birr = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.zcoin_amount} ZCoin"

class Payment(models.Model):
    PAYMENT_METHODS = [
        ('telebirr', 'Telebirr'),
        ('bank', 'Bank Transfer'),
        ('cash', 'Cash'),
    ]
    
    PAYMENT_STATUS = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    coin_package = models.ForeignKey(CoinPackage, on_delete=models.CASCADE, null=True, blank=True)
    amount_birr = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    zcoin_amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    receipt_no = models.CharField(max_length=50, blank=True, null=True)
    payer_name = models.CharField(max_length=100, blank=True)
    payer_phone = models.CharField(max_length=20, blank=True)
    actual_amount_birr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='telebirr')
    reference_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment {self.reference_number} - {self.amount_birr} Birr"

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('topup', 'Top Up'),
        ('swap', 'Book Swap'),
        ('purchase', 'Book Purchase'),
        ('refund', 'Refund'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2
    )
    description = models.TextField()
    related_swap = models.ForeignKey(SwapRequest, on_delete=models.SET_NULL, null=True, blank=True)
    related_payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} - {self.amount} ZCoin"