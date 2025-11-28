# telebirr_verifier.py
import re
import logging
import requests
from decimal import Decimal
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class TelebirrReceipt:
    payer_name: str = ""
    payer_telebirr_no: str = ""
    credited_party_name: str = ""
    credited_party_account_no: str = ""
    transaction_status: str = ""
    receipt_no: str = ""
    payment_date: str = ""
    settled_amount: str = ""
    service_fee: str = ""
    service_fee_vat: str = ""
    total_paid_amount: str = ""
    bank_name: str = ""

class TelebirrVerifier:
    RECEIPT_URL = "https://transactioninfo.ethiotelecom.et/receipt/"

    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def verify(self, reference: str) -> Optional[TelebirrReceipt]:
        """
        Verify Telebirr payment by reference number
        Returns full receipt data or None if failed/invalid
        """
        if self.mock_mode:
            return self._mock_verify(reference)

        logger.info(f"Verifying Telebirr payment: {reference}")

        try:
            response = self.session.get(f"{self.RECEIPT_URL}{reference}", timeout=15)
            if response.status_code != 200:
                logger.warning(f"Receipt not found (HTTP {response.status_code}): {reference}")
                return None

            receipt = self._scrape_receipt_html(response.text)
            
            if receipt and self._is_valid_receipt(receipt):
                logger.info(f"Verification SUCCESS: {receipt.payer_name} → {receipt.settled_amount}")
                return receipt
            else:
                logger.warning(f"Invalid or incomplete receipt data for: {reference}")
                return None

        except requests.RequestException as e:
            logger.error(f"Network error verifying {reference}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error verifying {reference}: {e}", exc_info=True)
            return None

    def _scrape_receipt_html(self, html: str) -> TelebirrReceipt:
        soup = BeautifulSoup(html, 'html.parser')
        text = html

        def regex_find(pattern: str, group: int = 1) -> str:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            return match.group(group).strip() if match else ""

        def find_next_td(label_text: str) -> str:
            td = soup.find("td", string=re.compile(label_text, re.I))
            if td and td.find_next_sibling("td"):
                return td.find_next_sibling("td").get_text(strip=True)
            return ""

        receipt = TelebirrReceipt()

        # === CRITICAL FIELDS WITH MULTIPLE FALLBACKS ===
        receipt.payer_name = (
            find_next_td("Payer Name|የከፋይ ስም") or
            regex_find(r"የከፋይ\s+ስም.*?([A-Za-z\s]+?)(?=<|የከፋይ)")
        )

        receipt.settled_amount = (
            find_next_td("Settled Amount|የተከፈለው መጠን") or
            regex_find(r"የተከፈለው\s+መጠን.*?(\d+(?:\.\d{2})?\s*Birr)") or
            regex_find(r"Settled\s+Amount.*?(\d+(?:\.\d{2})?\s*Birr)")
        )

        receipt.service_fee = (
            find_next_td("Service fee|የአገልግሎት ክፍያ") or
            regex_find(r"የአገልግሎት\s+ክፍያ(?!\s*VAT).*?(\d+(?:\.\d{2})?\s*Birr)") or
            regex_find(r"Service\s+fee(?!\s*VAT).*?(\d+(?:\.\d{2})?\s*Birr)")
        )

        receipt.receipt_no = (
            regex_find(r"receipttableTd2[^>]*>\s*([A-Z0-9]+)\s*<") or
            soup.find(string=re.compile(r"[A-Z0-9]{10,}")).strip() if soup.find(string=re.compile(r"[A-Z0-9]{10,}")) else ""
        )

        receipt.payment_date = regex_find(r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})")

        receipt.transaction_status = (
            find_next_td("transaction status|የክፍያው ሁኔታ") or
            regex_find(r"transaction status.*?([A-Za-z]+)")
        )

        receipt.service_fee_vat = find_next_td("Service fee VAT|ተ\.እ\.ታ")
        receipt.total_paid_amount = find_next_td("Total Paid Amount|ጠቅላላ የተከፈለ")

        receipt.payer_telebirr_no = find_next_td("Payer telebirr no|የከፋይ ቴሌብር")

        # === Credited Party vs Bank Logic ===
        credited_name = find_next_td("Credited Party name|የገንዘብ ተቀባይ ስም")
        credited_no = find_next_td("Credited party account no|የገንዘብ ተቀባይ ቴሌብር")
        bank_account = find_next_td("Bank account number|የባንክ አካውንት")

        if bank_account:
            receipt.bank_name = credited_name
            match = re.search(r"(\d+)\s+(.*)", bank_account)
            if match:
                receipt.credited_party_account_no = match.group(1)
                receipt.credited_party_name = match.group(2)
            else:
                receipt.credited_party_name = credited_name
        else:
            receipt.credited_party_name = credited_name
            receipt.credited_party_account_no = credited_no

        return receipt

    def _is_valid_receipt(self, receipt: TelebirrReceipt) -> bool:
        return all([
            receipt.receipt_no,
            receipt.payer_name,
            receipt.settled_amount or receipt.total_paid_amount,
            receipt.transaction_status
        ])

    def _mock_verify(self, reference: str) -> TelebirrReceipt:
        logger.info(f"Mock verification: {reference}")
        import time; time.sleep(1)
        return TelebirrReceipt(
            payer_name="Abebe Kebede",
            payer_telebirr_no="0912345678",
            credited_party_name="BookSwap Ethiopia",
            credited_party_account_no="1000123456",
            transaction_status="Completed",
            receipt_no=reference.upper(),
            payment_date="29-04-2025 10:30:45",
            settled_amount="150.00 Birr",
            service_fee="3.00 Birr",
            service_fee_vat="0.45 Birr",
            total_paid_amount="153.45 Birr",
            bank_name=""
        )




# import requests
# import re
# import logging
# from datetime import datetime
# from decimal import Decimal
# from django.utils import timezone

# logger = logging.getLogger(__name__)

# class PaymentVerificationResult:
#     def __init__(self, success=False, payer_name=None, amount=None, reference=None, error=None):
#         self.success = success
#         self.payer_name = payer_name
#         self.amount = amount
#         self.reference = reference
#         self.error = error

# class TelebirrVerifier:
#     """
#     Enhanced Telebirr verification with mock mode for development
#     """
    
#     def __init__(self, mock_mode=True):
#         self.mock_mode = mock_mode
#         self.mock_payments = {
#             'TEST123': PaymentVerificationResult(
#                 success=True,
#                 payer_name='Test User',
#                 amount=Decimal('100.00'),
#                 reference='TEST123'
#             ),
#             'TEST456': PaymentVerificationResult(
#                 success=True,
#                 payer_name='John Doe',
#                 amount=Decimal('50.00'),
#                 reference='TEST456'
#             )
#         }
    
#     def verify(self, reference: str) -> PaymentVerificationResult:
#         """
#         Verify Telebirr transaction with mock support for development
#         """
#         if self.mock_mode:
#             return self._mock_verify(reference)
        
#         try:
#             logger.info(f"📱 Verifying Telebirr transaction: {reference}")
            
#             # Primary source - This would be the actual Telebirr API
#             url = f"https://transactioninfo.ethiotelecom.et/receipt/{reference}"
            
#             response = requests.get(url, timeout=15)
            
#             if response.status_code != 200:
#                 return PaymentVerificationResult(error="Failed to fetch Telebirr receipt")
            
#             html_content = response.text
            
#             # Simple regex extraction for key fields
#             payer_name = self._extract_field(html_content, "የከፋይ ስም/Payer Name")
#             amount_str = self._extract_field(html_content, "የተከፈለው መጠን/Settled Amount")
            
#             # Extract amount
#             amount = None
#             if amount_str:
#                 try:
#                     amount_match = re.search(r'(\d+\.?\d*)', amount_str.replace(',', ''))
#                     if amount_match:
#                         amount = Decimal(amount_match.group(1))
#                 except:
#                     pass
            
#             if not payer_name or not amount:
#                 return PaymentVerificationResult(error="Could not extract payment details")
            
#             result = PaymentVerificationResult(
#                 success=True,
#                 payer_name=payer_name,
#                 amount=amount,
#                 reference=reference
#             )
            
#             logger.info(f"✅ Telebirr verification successful: {result.payer_name}, {result.amount}")
#             return result
            
#         except Exception as e:
#             logger.error(f"❌ Telebirr verification error: {str(e)}")
#             return PaymentVerificationResult(error=str(e))
    
#     def _mock_verify(self, reference: str) -> PaymentVerificationResult:
#         """Mock verification for development"""
#         logger.info(f"🔧 Mock verification for reference: {reference}")
        
#         # Simulate API delay
#         import time
#         time.sleep(1)
        
#         if reference in self.mock_payments:
#             result = self.mock_payments[reference]
#             logger.info(f"✅ Mock verification successful: {result.payer_name}, {result.amount}")
#             return result
#         else:
#             # For any other reference starting with 'TEST', create a successful mock
#             if reference.startswith('TEST'):
#                 result = PaymentVerificationResult(
#                     success=True,
#                     payer_name='Mock User',
#                     amount=Decimal('100.00'),
#                     reference=reference
#                 )
#                 logger.info(f"✅ Mock verification successful: {result.payer_name}, {result.amount}")
#                 return result
#             else:
#                 error_msg = "Mock payment not found. Use TEST123, TEST456, or any reference starting with 'TEST'"
#                 logger.warning(f"❌ {error_msg}")
#                 return PaymentVerificationResult(error=error_msg)
    
#     @staticmethod
#     def _extract_field(html: str, field_name: str) -> str:
#         """Extract field value from HTML using regex"""
#         # Look for field name followed by value in table structure
#         pattern = f'{re.escape(field_name)}.*?</td>\\s*<td[^>]*>\\s*([^<]+)'
#         match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
#         return match.group(1).strip() if match else ""