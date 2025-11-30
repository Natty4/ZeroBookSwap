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
from .utils import TelebirrVerifier, AbyssiniaVerifier

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
            wallet = Wallet.get_or_create_for_user(user)
            wallet.zcoin_balance += 10
            wallet.save()
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


class CreatePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        coin_package_id = request.data.get('coin_package_id')
        custom_amount = request.data.get('custom_amount')
        payment_method = request.data.get('payment_method', 'telebirr')

        if payment_method not in ['telebirr', 'abyssinia']:
            return Response({'error': 'Invalid payment method'}, status=400)

        if not coin_package_id and not custom_amount:
            return Response({'error': 'Package or amount required'}, status=400)

        try:
            if coin_package_id:
                package = CoinPackage.objects.get(id=coin_package_id, is_active=True)
                amount_birr = package.price_birr
                zcoin_amount = package.zcoin_amount
                name = package.name
            else:
                amount_birr = Decimal(custom_amount)
                if amount_birr < 10:
                    return Response({'error': 'Minimum 10 Birr'}, status=400)
                zcoin_amount = amount_birr * Decimal('100')
                name = f"Custom {amount_birr} Birr"

            instructions = {
                    'telebirr': {
                        'number': '+251901758052',
                        'amount': 'amount_birr', # For clarity, keep amount separate if possible
                        'note_info': 'request.user.username',
                        'steps': [
                            f"Send {amount_birr} Birr to +251901758052.",
                            f"Write your username '{request.user.username}' in the note.",
                            "Copy & paste the reference number below."
                        ]
                    },
                    'abyssinia': {
                        'account_name': 'Zero Book Swap PLC',
                        'source_account_suffix': '12345', # Renamed key for clarity
                        'amount': 'amount_birr',
                        'narrative_info': 'request.user.username.upper()',
                        'steps': [
                            f"Transfer {amount_birr} Birr to Zero Book Swap PLC.",
                            f"Use '{request.user.username.upper()}' as the narrative/reason.",
                            "Copy & paste the transaction reference + the last 5 digits of your source account (****12345) below."
                        ]
                    }
                }

            return Response({
                'success': True,
                'amount_birr': float(amount_birr),
                'zcoin_amount': float(zcoin_amount),
                'package_name': name,
                'payment_method': payment_method,
                'instructions': instructions[payment_method]
            })

        except Exception as e:
            return Response({'error': str(e)}, status=400)


class PaymentVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ref = request.data.get('reference_number', '').strip()
        suffix = request.data.get('account_suffix', '').strip()
        method = request.data.get('payment_method', 'telebirr')
        coin_package_id = request.data.get('coin_package_id')
        custom_amount = request.data.get('custom_amount')

        if not ref:
            return Response({'error': 'Reference required'}, status=400)

        full_ref = f"{ref}{suffix}" if method == 'abyssinia' else ref
        if Payment.objects.filter(reference_number=full_ref).exists():
            return Response({'error': 'Already used'}, status=400)

        # Determine expected amount
        if coin_package_id:
            package = CoinPackage.objects.get(id=coin_package_id)
            expected = package.price_birr
            zcoin = package.zcoin_amount
        else:
            expected = Decimal(custom_amount or '0')
            zcoin = expected * Decimal('100')

        paid_amount = None
        payer_name = None

        if method == 'telebirr':
            verifier = TelebirrVerifier(mock_mode=True)
            receipt = verifier.verify(ref)
            if not receipt:
                return Response({'error': 'Telebirr payment not found'}, status=400)
            amount_str = receipt.settled_amount or receipt.total_paid_amount
            match = re.search(r'[\d.]+', amount_str.replace(',', ''))
            paid_amount = Decimal(match.group()) if match else None
            payer_name = receipt.payer_name

        elif method == 'abyssinia':
            if not suffix or len(suffix) != 5 or not suffix.isdigit():
                return Response({'error': 'Enter last 5 digits (e.g. 90172)'}, status=400)
            
            verifier = AbyssiniaVerifier(mock_mode=True)  # ← Clean & reusable
            receipt = verifier.verify(ref, suffix)
            
            if not receipt or not receipt.success:
                return Response({'error': receipt.error or 'Invalid BoA reference'}, status=400)
            
            paid_amount = receipt.amount
            payer_name = receipt.payer_name or "BoA Customer"

        # Amount tolerance ±0.50
        # if abs(paid_amount - expected) > Decimal('0.50'):
        #     return Response({
        #         'error': f'Amount mismatch: Expected {expected}, got {paid_amount}',
        #         'expected': str(expected),
        #         'received': str(paid_amount)
        #     }, status=400)

        # Success: Credit ZCoin
        with transaction.atomic():
            payment = Payment.objects.create(
                user=request.user,
                coin_package_id=coin_package_id or None,
                amount_birr=expected,
                actual_amount_birr=paid_amount,
                zcoin_amount=zcoin,
                payment_method=method,
                reference_number=full_ref,
                receipt_no=ref,
                payer_name=payer_name,
                status='verified',
                verified_at=timezone.now()
            )
            wallet = Wallet.get_or_create_for_user(request.user)
            wallet.zcoin_balance += zcoin
            wallet.save()

        return Response({
            'message': 'Success!',
            'zcoin_added': float(zcoin),
            'amount_paid_birr': str(paid_amount),
            'new_balance': float(wallet.zcoin_balance),
            'method': 'Telebirr' if method == 'telebirr' else 'Bank of Abyssinia'
        })
        
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

class SessionCheckView(APIView):
    permission_classes = [permissions.AllowAny]  # Change to AllowAny
    
    def get(self, request):
        if request.user.is_authenticated:
            return Response({
                'is_authenticated': True,
                'user': UserProfileSerializer(request.user.profile).data
            })
        else:
            return Response({
                'is_authenticated': False
            })
            
# @method_decorator(csrf_protect, name='dispatch')
# class SessionCheckView(APIView):
#     permission_classes = [permissions.AllowAny]

#     def get(self, request):
#         rotate_token(request)
#         return Response({
#             'is_authenticated': True,
#             'user': UserProfileSerializer(request.user.profile).data
#         })

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