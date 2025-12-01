from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from core.models import ZCoinCalculatorSettings, ZCoinCalculationLog

class ZCoinCalculator:
    """Comprehensive ZCoin calculator with manual override capability"""
    
    @staticmethod
    def calculate_zcoin(
        category,
        condition,
        cover_type=None,
        has_images=False,
        has_dust_jacket=False,
        is_first_edition=False,
        is_signed=False,
        manual_zcoin=None,
        user=None,
        book=None
    ):
        """
        Calculate ZCoin value for a book
        
        Args:
            category: Book category (e.g., 'fiction', 'non-fiction')
            condition: Book condition (e.g., 'excellent', 'good')
            cover_type: Type of cover (optional)
            has_images: Whether book has images/illustrations
            has_dust_jacket: Whether original dust jacket is present
            is_first_edition: Whether it's a first edition
            is_signed: Whether book is signed by author
            manual_zcoin: Manual override value (if provided)
            user: User performing calculation (for logging)
            book: Related book object (for logging)
        
        Returns:
            Dictionary with calculation details
        """
        settings = ZCoinCalculatorSettings.get_active_settings()
        
        # Get base value based on category - ensure Decimal
        base_values = {
            'classics': settings.classics_base,
            'non-fiction': settings.nonfiction_base,
            'fiction': settings.fiction_base,
            'contemporary': settings.contemporary_base,
            'academic': settings.academic_base,
            'children': settings.children_base,
            'reference': settings.reference_base,
        }
        
        base_value = base_values.get(category, settings.contemporary_base)
        
        # Get condition multiplier - ensure Decimal
        condition_multipliers = {
            'excellent': settings.excellent_multiplier,
            'good': settings.good_multiplier,
            'fair': settings.fair_multiplier,
            'poor': settings.poor_multiplier,
        }
        
        condition_multiplier = condition_multipliers.get(condition, settings.good_multiplier)
        
        # Calculate base ZCoin - use Decimal arithmetic
        calculated_zcoin = base_value * condition_multiplier
        
        # Apply bonuses - start with Decimal zero
        bonuses = Decimal('0.00')
        
        # Cover type bonus/penalty
        if cover_type:
            if cover_type == 'hardcover':
                bonuses += settings.hardcover_bonus
            elif cover_type == 'dust_jacket':
                bonuses += settings.dust_jacket_bonus
            elif cover_type == 'no_cover':
                bonuses += settings.no_cover_penalty
        
        # Additional bonuses
        if has_images:
            bonuses += settings.has_images_bonus
        if has_dust_jacket:
            bonuses += settings.has_original_dust_jacket
        if is_first_edition:
            bonuses += settings.is_first_edition_bonus
        if is_signed:
            bonuses += settings.is_signed_bonus
        
        # Apply bonuses
        calculated_zcoin += bonuses
        
        # Apply min/max limits - ensure Decimal comparison
        final_zcoin = max(settings.min_zcoin, min(settings.max_zcoin, calculated_zcoin))
        
        # If manual override is provided, use it
        manual_override = manual_zcoin is not None
        if manual_override:
            # Convert to Decimal if it's a float or string
            if isinstance(manual_zcoin, float):
                final_zcoin = Decimal(str(manual_zcoin))
            else:
                final_zcoin = Decimal(manual_zcoin)
            calculated_zcoin = final_zcoin  # For logging purposes
        
        # Round to 2 decimal places
        final_zcoin = final_zcoin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        calculated_zcoin = calculated_zcoin.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        bonuses = bonuses.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Calculate price in Birr
        price_birr = (final_zcoin * settings.zcoin_to_birr_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # Prepare manual_zcoin for logging
        manual_zcoin_decimal = None
        if manual_override:
            if isinstance(manual_zcoin, float):
                manual_zcoin_decimal = Decimal(str(manual_zcoin))
            else:
                manual_zcoin_decimal = Decimal(manual_zcoin)
        
        # Log the calculation
        log_entry = ZCoinCalculationLog.objects.create(
            book=book,
            calculated_by=user,
            category=category,
            condition=condition,
            cover_type=cover_type,
            has_images=has_images,
            has_dust_jacket=has_dust_jacket,
            is_first_edition=is_first_edition,
            is_signed=is_signed,
            base_value=base_value,
            condition_multiplier=condition_multiplier,
            bonuses=bonuses,
            calculated_zcoin=calculated_zcoin,
            final_zcoin=final_zcoin,
            manual_override=manual_override,
            manual_zcoin=manual_zcoin_decimal,
            manual_price_birr=price_birr if manual_override else None,
            notes=f"Manual override: {manual_zcoin} ZCoin" if manual_override else "Auto-calculated"
        )
        
        # Return float values for JSON serialization (frontend compatibility)
        return {
            'zcoin': float(final_zcoin),
            'price_birr': float(price_birr),
            'base_value': float(base_value),
            'condition_multiplier': float(condition_multiplier),
            'bonuses': float(bonuses),
            'calculated_zcoin': float(calculated_zcoin),
            'is_manual': manual_override,
            'min_zcoin': float(settings.min_zcoin),
            'max_zcoin': float(settings.max_zcoin),
            'calculation_id': log_entry.id,
            'details': {
                'category': category,
                'condition': condition,
                'cover_type': cover_type,
                'has_images': has_images,
                'has_dust_jacket': has_dust_jacket,
                'is_first_edition': is_first_edition,
                'is_signed': is_signed,
            },
            'decimal_values': {
                'zcoin_decimal': str(final_zcoin),
                'price_birr_decimal': str(price_birr),
                'base_value_decimal': str(base_value),
            }
        }