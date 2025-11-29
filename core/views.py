from django.contrib.auth import login as auth_login
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from rest_framework import status, viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from django.middleware.csrf import get_token, rotate_token
from django.http import JsonResponse
from django.db import transaction
from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt, csrf_protect

from decimal import Decimal
import logging
import re

from .models import UserProfile, Wallet, Book, SwapRequest, CoinPackage, Payment, Transaction
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer, UserProfileDetailSerializer,
    BookSerializer, SwapRequestSerializer, 
    CoinPackageSerializer, PaymentSerializer, TransactionSerializer, 
    ZCoinCalculatorSerializer
)
from .utils import TelebirrVerifier

logger = logging.getLogger(__name__)



# Add this decorator to views that need CSRF protection
class CSRFView(APIView):
    permission_classes = [permissions.AllowAny]
    
    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return JsonResponse({'CSRFToken': get_token(request)})

class UserRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Return user data with profile
            profile_serializer = UserProfileSerializer(user.profile)
            return Response({
                'message': 'User registered successfully',
                'user': profile_serializer.data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Enhanced UserLoginView with better session handling
class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Log the user in (create session)
            auth_login(request, user)
            
            # Update last login
            user.last_login = timezone.now()
            user.save()
            
            # Return user data with profile
            profile_serializer = UserProfileSerializer(user.profile)
            
            response_data = {
                'message': 'Login successful',
                'user': profile_serializer.data,
                'session_expiry': settings.SESSION_COOKIE_AGE
            }
            
            response = Response(response_data)
            
            # Set custom header for session management
            response['X-Session-Expiry'] = settings.SESSION_COOKIE_AGE
            
            return response
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Enhanced UserLogoutView
class UserLogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Clear the session
        request.session.flush()
        
        # Logout the user
        from django.contrib.auth import logout
        logout(request)
        
        response = Response({'message': 'Logout successful'})
        
        # Clear session cookie on client side
        response.delete_cookie('sessionid')
        response.delete_cookie('csrftoken')
        
        return response


@method_decorator(csrf_protect, name='dispatch')
class CreatePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        coin_package_id = request.data.get('coin_package_id')
        custom_amount = request.data.get('custom_amount')

        if not coin_package_id and not custom_amount:
            return Response(
                {'error': 'Either coin_package_id or custom_amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            if coin_package_id:
                coin_package = CoinPackage.objects.get(id=coin_package_id, is_active=True)
                amount_birr = coin_package.price_birr
                zcoin_amount = coin_package.zcoin_amount
                package_name = coin_package.name
            else:
                amount_birr = Decimal(custom_amount)
                if amount_birr < 10:
                    return Response({'error': 'Minimum payment amount is 10 Birr'}, status=400)
                zcoin_amount = amount_birr * Decimal('100')
                package_name = f"Custom {amount_birr} Birr"

            return Response({
                'success': True,
                'amount_birr': float(amount_birr),
                'zcoin_amount': float(zcoin_amount),
                'package_name': package_name,
                'payment_instructions': {
                    'telebirr_number': '+251901758052',
                    'amount': float(amount_birr),
                    'note_instructions': f"Include your username '{request.user.username}' in the note",
                    'steps': [
                        "Open Telebirr app",
                        f"Send exactly {amount_birr} Birr to +251901758052",
                        f"Write your username '{request.user.username}' in the note",
                        "Copy the reference number",
                        "Come back here and paste it"
                    ]
                }
            })

        except Exception as e:
            return Response({'error': str(e)}, status=400)



@method_decorator(csrf_protect, name='dispatch')
class PaymentVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        reference_number = request.data.get('reference_number', '').strip()
        coin_package_id = request.data.get('coin_package_id')
        custom_amount = request.data.get('custom_amount')

        if not reference_number:
            return Response({'error': 'Reference number is required'}, status=400)

        # Prevent duplicate use
        if Payment.objects.filter(reference_number=reference_number).exists():
            return Response({
                'error': 'This reference number has already been used.'
            }, status=400)

        # === Determine expected amount & ZCoin reward ===
        if coin_package_id:
            try:
                package = CoinPackage.objects.get(id=coin_package_id, is_active=True)
                expected_amount = package.price_birr
                zcoin_to_add = package.zcoin_amount
            except CoinPackage.DoesNotExist:
                return Response({'error': 'Invalid or inactive package'}, status=400)

        elif custom_amount:
            try:
                expected_amount = Decimal(str(custom_amount))
                if expected_amount < Decimal('10'):
                    return Response({'error': 'Minimum top-up is 10 Birr'}, status=400)
                zcoin_to_add = expected_amount * settings.ZCOIN_PRICE_PER_BIRR
            except (ValueError, TypeError, Decimal.InvalidOperation):
                return Response({'error': 'Invalid custom amount'}, status=400)

        else:
            return Response({'error': 'Either coin_package_id or custom_amount is required'}, status=400)

        
        verifier = TelebirrVerifier(mock_mode=True)  # Set True only in dev
        receipt = verifier.verify(reference_number)

        if not receipt:
            return Response({
                'error': 'Payment not found or invalid reference.',
                'suggestions': [
                    'Double-check the reference number',
                    'Wait 2–3 minutes after payment',
                    'For testing: use any reference starting with "TEST"'
                ]
            }, status=400)

        
        amount_str = receipt.settled_amount or receipt.total_paid_amount or ""
        try:
            paid_amount = Decimal(re.search(r'([\d.]+)', amount_str.replace(',', '')).group(1))
        except (AttributeError, Decimal.InvalidOperation):
            return Response({'error': 'Could not read payment amount from receipt'}, status=400)

        # === Amount tolerance: allow ±0.50 Birr difference due to service fee rounding ===
        tolerance = Decimal('0.50')
        if not (expected_amount - tolerance <= paid_amount <= expected_amount + tolerance):
            return Response({
                'error': f'Amount mismatch. Expected ~{expected_amount} Birr, received {paid_amount} Birr.',
                'received_amount': str(paid_amount),
                'expected_amount': str(expected_amount)
            }, status=400)

        # === SUCCESS: Create payment & credit ZCoin ===
        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    user=request.user,
                    coin_package_id=coin_package_id or None,
                    amount_birr=expected_amount,
                    actual_amount_birr=paid_amount,
                    zcoin_amount=zcoin_to_add,
                    payment_method='telebirr',
                    reference_number=reference_number,
                    receipt_no=receipt.receipt_no,
                    payer_name=receipt.payer_name,
                    payer_phone=receipt.payer_telebirr_no,
                    status='verified',
                    verified_at=timezone.now()
                )

                wallet = Wallet.get_or_create_for_user(request.user)
                wallet.zcoin_balance += zcoin_to_add
                wallet.save()

                Transaction.objects.create(
                    user=request.user,
                    transaction_type='topup',
                    amount=zcoin_to_add,
                    description=f"Telebirr top-up • {reference_number} • {paid_amount} Birr",
                    related_payment=payment
                )

        except Exception as e:
            logger.error(f"Failed to save payment for {reference_number}: {e}")
            return Response({'error': 'Payment verified but failed to credit ZCoin. Contact support.'}, status=500)

        # Optional: rotate_token(request)  # if you use token rotation

        return Response({
            'message': 'Payment verified successfully!',
            'zcoin_added': float(zcoin_to_add),
            'amount_paid_birr': str(paid_amount),
            'new_balance': float(wallet.zcoin_balance),
            'receipt_no': receipt.receipt_no,
            'payer': receipt.payer_name,
            'reference': reference_number
        }, status=200)

@method_decorator(csrf_protect, name='dispatch')
class SessionCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rotate_token(request)
        return Response({
            'is_authenticated': True,
            'user': UserProfileSerializer(request.user.profile).data
        })

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserProfileDetailSerializer(request.user.profile)
        return Response(serializer.data)

class UserBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        wallet = Wallet.get_or_create_for_user(request.user)
        return Response({
            'zcoin_balance': wallet.zcoin_balance,
            'username': request.user.username,
            'full_name': request.user.first_name
        })

class BookViewSet(viewsets.ModelViewSet):
    serializer_class = BookSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]      

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and self.request.query_params.get('my_books'):
            return Book.objects.filter(added_by=user)  # Show all, even unavailable
        
        queryset = Book.objects.filter(is_available=True)
        book_type = self.request.query_params.get('type', None)
        genre = self.request.query_params.get('genre', None)
        
        if book_type:
            queryset = queryset.filter(book_type=book_type)
        if genre:
            queryset = queryset.filter(genre=genre)
            
        return queryset

    def perform_create(self, serializer):
        title = serializer.validated_data['title']
        user = self.request.user

        # Prevent user from submitting the same book twice (even if pending)
        if Book.objects.filter(
            added_by=user,
            title__iexact=title
        ).exists():
            raise ValidationError("You have already submitted this book for review.")

        serializer.save(
            added_by=self.request.user,
            is_available=False,
            book_type='swap',
            price_birr=25
        )


class SwapRequestViewSet(viewsets.ModelViewSet):
    serializer_class = SwapRequestSerializer
    permission_classes = [permissions.IsAuthenticated]  # This is correct for POST

    def get_queryset(self):
        # Only return user's own requests — but safely handle unauthenticated
        if self.request.user.is_authenticated:
            return SwapRequest.objects.filter(user=self.request.user)
        return SwapRequest.objects.none()  # Return empty queryset if not logged in

    def perform_create(self, serializer):
        with transaction.atomic():
            user_wallet = Wallet.get_or_create_for_user(self.request.user)
            # Use the same fields for calculation — no duplication!
            calculator_data = {
                'genre': self.request.data.get('user_book_genre'),
                'condition': self.request.data.get('user_book_condition')
            }

            calculator = ZCoinCalculatorSerializer(data=calculator_data)
            if not calculator.is_valid():
                raise ValidationError({
                    "detail": "Please select valid genre and condition.",
                    "errors": calculator.errors
                })


            try:
                requested_book = Book.objects.get(
                    id=self.request.data['requested_book'],
                    is_available=True,
                    book_type='swap'
                )
            except Book.DoesNotExist:
                raise ValidationError("Book not available for swap.")

            required_zcoin = requested_book.zcoin_value
            calculated_zcoin = requested_book.zcoin_value or calculator.calculate_zcoin()
            
            zcoin_difference = max(0, user_wallet.zcoin_balance - calculated_zcoin)

            if zcoin_difference > 0 and user_wallet.zcoin_balance < zcoin_difference:
                raise ValidationError(f"Insufficient ZCoin. Need {zcoin_difference} more.")

            
            serializer.save(
                user=self.request.user,
                requested_book=requested_book,
                calculated_zcoin=calculated_zcoin,

            )

            if zcoin_difference >= 0:
                user_wallet.zcoin_balance -= calculated_zcoin
                user_wallet.save()

                Transaction.objects.create(
                    user=self.request.user,
                    transaction_type='swap',
                    amount=-calculated_zcoin,
                    description=f"Swap: {requested_book.title}",
                    related_swap=serializer.instance
                )
                requested_book.is_available = False
                requested_book.save(update_fields=['is_available'])

class CoinPackageViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CoinPackageSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        return CoinPackage.objects.filter(is_active=True)

class PaymentViewSet(viewsets.ModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        coin_package = CoinPackage.objects.get(id=self.request.data['coin_package'])
        
        payment = serializer.save(
            user=self.request.user,
            amount_birr=coin_package.price_birr,
            zcoin_amount=coin_package.zcoin_amount
        )


class ZCoinCalculatorView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = ZCoinCalculatorSerializer(data=request.data)
        if serializer.is_valid():
            zcoin_value = serializer.calculate_zcoin()
            return Response({'zcoin_value': zcoin_value})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TransactionHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        transactions = Transaction.objects.filter(user=request.user)
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)