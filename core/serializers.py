from rest_framework import serializers
from decimal import Decimal
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import UserProfile, Wallet, Book, SwapRequest, CoinPackage, Payment, Transaction

# serializers.py
class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)
    full_name = serializers.CharField(write_only=True)
    phone_number = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'full_name', 'phone_number', 'password', 'password_confirm')

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match")
        return data

    def create(self, validated_data):
        password = validated_data.pop('password')
        validated_data.pop('password_confirm')
        phone_number = validated_data.pop('phone_number', None)
        full_name = validated_data.pop('full_name', '')

        # Create the User
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'] or '',
            password=password,
            first_name=full_name
        )

        # Create Profile
        UserProfile.objects.create(
            user=user,
            phone_number=phone_number or ''
        )

        wallet = Wallet.get_or_create_for_user(user)

        return user

class UserLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        username = data.get('username')
        password = data.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if user:
                if user.is_active:
                    data['user'] = user
                else:
                    raise serializers.ValidationError("User account is disabled.")
            else:
                raise serializers.ValidationError("Unable to log in with provided credentials.")
        else:
            raise serializers.ValidationError("Must include username and password.")
        
        return data

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ('zcoin_balance',)

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.first_name')
    username = serializers.CharField(source='user.username')
    email = serializers.CharField(source='user.email')
    wallet = WalletSerializer(source='user.wallet')
    
    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'email', 'full_name', 'phone_number', 'wallet')

class UserProfileDetailSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source='user.first_name')
    username = serializers.CharField(source='user.username')
    email = serializers.CharField(source='user.email')
    zcoin_balance = serializers.DecimalField(source='user.wallet.zcoin_balance', max_digits=15, decimal_places=2, read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ('id', 'username', 'email', 'full_name', 'phone_number', 'zcoin_balance')

class BookSerializer(serializers.ModelSerializer):
    added_by = serializers.PrimaryKeyRelatedField(read_only=True)
    
    class Meta:
        model = Book
        fields = '__all__'
        read_only_fields = ('added_by', 'is_available', 'created_at')

class SwapRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    requested_book_title = serializers.CharField(source='requested_book.title', read_only=True)
    requested_book_author = serializers.CharField(source='requested_book.author', read_only=True)
    requested_book_cover = serializers.CharField(source='requested_book.cover_image_url', read_only=True)
    requested_book_zcoin = serializers.DecimalField(source='requested_book.zcoin_value', read_only=True, max_digits=15, decimal_places=2)

    class Meta:
        model = SwapRequest
        fields = '__all__'
        read_only_fields = ('user', 'calculated_zcoin', 'status')

        

class CoinPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoinPackage
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    package_name = serializers.CharField(source='coin_package.name', read_only=True)

    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('user', 'zcoin_amount', 'status', 'verified_at')

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'

class ZCoinCalculatorSerializer(serializers.Serializer):
    genre = serializers.ChoiceField(choices=Book.BOOK_GENRES)
    condition = serializers.ChoiceField(choices=Book.BOOK_CONDITIONS)
    
    def calculate_zcoin(self):
        genre = self.validated_data['genre']
        condition = self.validated_data['condition']
        
        # ZCoin calculation logic (same as frontend)
        zcoin_values = {
            'category': {
                'classics': 30,
                'non-fiction': 25,
                'fiction': 20,
                'contemporary': 15,
            },
            'condition': {
                'excellent': 50,
                'good': 35,
                'fair': 20,
                'poor': 10,
            }
        }
        
        category_value = zcoin_values['category'].get(genre, 15)
        condition_value = zcoin_values['condition'].get(condition, 20)
        
        return category_value + condition_value