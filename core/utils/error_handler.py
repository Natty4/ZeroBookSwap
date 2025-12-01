# core/utils/error_handler.py

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import IntegrityError
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

class UserFriendlyError(APIException):
    """Custom exception for user-friendly error messages"""
    status_code = 400
    default_detail = 'An error occurred. Please try again.'
    default_code = 'error'

    def __init__(self, detail=None, code=None, friendly_message=None):
        if detail is None:
            detail = self.default_detail
        if code is None:
            code = self.default_code
        
        self.friendly_message = friendly_message or detail
        super().__init__(detail, code)

class ValidationErrorHandler(UserFriendlyError):
    """Handle validation errors with friendly messages"""
    default_detail = 'Please check your input and try again.'
    status_code = 400

class AuthenticationErrorHandler(UserFriendlyError):
    """Handle authentication errors with friendly messages"""
    default_detail = 'Authentication failed. Please check your credentials.'
    status_code = 401

class PermissionErrorHandler(UserFriendlyError):
    """Handle permission errors with friendly messages"""
    default_detail = 'You do not have permission to perform this action.'
    status_code = 403

class NotFoundErrorHandler(UserFriendlyError):
    """Handle not found errors with friendly messages"""
    default_detail = 'The requested resource was not found.'
    status_code = 404

class ServerErrorHandler(UserFriendlyError):
    """Handle server errors with friendly messages"""
    default_detail = 'Something went wrong on our end. Please try again later.'
    status_code = 500

def get_friendly_error_message(exception):
    """Map various exceptions to user-friendly messages"""
    
    # Django validation errors
    if isinstance(exception, ValidationError):
        if hasattr(exception, 'message_dict'):
            # Field-specific errors
            messages = []
            for field, errors in exception.message_dict.items():
                field_name = field.replace('_', ' ').title()
                for error in errors:
                    if 'already exists' in error.lower():
                        messages.append(f"{field_name} is already taken.")
                    elif 'required' in error.lower():
                        messages.append(f"{field_name} is required.")
                    elif 'invalid' in error.lower():
                        messages.append(f"Please enter a valid {field_name.lower()}.")
                    else:
                        messages.append(f"{field_name}: {error}")
            return ' '.join(messages) if messages else "Please check your input."
        else:
            return str(exception)
    
    # Integrity errors (duplicate entries, etc.)
    elif isinstance(exception, IntegrityError):
        if 'unique' in str(exception).lower():
            return "This information is already registered. Please use different details."
        return "Database error. Please try again with different information."
    
    # Custom user-friendly errors
    elif isinstance(exception, UserFriendlyError):
        return exception.friendly_message
    
    # Default messages for common errors
    error_str = str(exception).lower()
    
    if 'password' in error_str:
        if 'too short' in error_str:
            return "Password is too short. Please use at least 8 characters."
        elif 'too common' in error_str:
            return "Password is too common. Please choose a stronger password."
        elif 'similar' in error_str:
            return "Password is too similar to your personal information."
        elif 'match' in error_str:
            return "Passwords do not match. Please try again."
        else:
            return "Invalid password. Please check and try again."
    
    elif 'username' in error_str:
        if 'already exists' in error_str:
            return "Username is already taken. Please choose another one."
        elif 'invalid' in error_str:
            return "Username can only contain letters, numbers, and underscores."
        else:
            return "Please enter a valid username."
    
    elif 'email' in error_str:
        if 'already exists' in error_str:
            return "Email is already registered. Please use a different email or login."
        elif 'invalid' in error_str:
            return "Please enter a valid email address."
        else:
            return "Email error. Please check your email address."
    
    elif 'login' in error_str or 'authentication' in error_str or 'credentials' in error_str:
        return "Invalid username or password. Please try again."
    
    elif 'not found' in error_str:
        return "The requested item was not found. It may have been removed or is unavailable."
    
    elif 'permission' in error_str or 'not allowed' in error_str:
        return "You don't have permission to perform this action."
    
    elif 'required' in error_str:
        return "Please fill in all required fields."
    
    elif 'network' in error_str or 'connection' in error_str:
        return "Network error. Please check your internet connection and try again."
    
    elif 'timeout' in error_str:
        return "Request timed out. Please try again."
    
    elif 'server' in error_str or 'internal' in error_str:
        return "Server error. Our team has been notified. Please try again later."
    
    # Generic fallback
    return "An error occurred. Please try again."

def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns user-friendly error messages.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Get the original error message
        original_error = response.data
        
        # Generate user-friendly message
        friendly_message = get_friendly_error_message(exc)
        
        # Create a clean response structure
        error_data = {
            'success': False,
            'error': {
                'code': response.status_code,
                'message': friendly_message,
                'type': exc.__class__.__name__,
                'timestamp': timezone.now().isoformat()
            }
        }
        
        # Only include detailed info in debug mode
        from django.conf import settings
        if settings.DEBUG:
            error_data['error']['details'] = str(original_error)
            error_data['error']['original'] = original_error
        
        response.data = error_data
    
    # Log the error for debugging
    logger.error(f"Error: {exc}", exc_info=True)
    
    return response