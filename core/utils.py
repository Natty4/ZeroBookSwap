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



@dataclass
class AbyssiniaReceipt:
    success: bool = False
    
    payer_name: str = ""
    payer_account: str = ""
    amount: Decimal = Decimal('0')
    date: str = ""
    reference: str = ""
    narrative: str = ""
    
    error: Optional[str] = None


class AbyssiniaVerifier:
    """
    Modular Bank of Abyssinia receipt verifier
    Works with: https://cs.bankofabyssinia.com
    """
    RECEIPT_API = "https://cs.bankofabyssinia.com/api/onlineSlip/getDetails/"
    
    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://cs.bankofabyssinia.com/",
            "Origin": "https://cs.bankofabyssinia.com",
            "X-Requested-With": "XMLHttpRequest"
        })

    def verify(self, reference: str, account_suffix: str = "90172") -> Optional[AbyssiniaReceipt]:
        """
        Verify BoA transfer by transaction reference + last 5 digits of recipient account
        Example: reference="FT24129987AB", suffix="90172" → FT24129987AB90172
        """
        if self.mock_mode:
            return self._mock_verify(reference, account_suffix)

        full_ref = f"{reference.strip()}{account_suffix.strip()}"
        logger.info(f"Verifying BoA payment: {full_ref}")

        try:
            url = f"{self.RECEIPT_API}?id={full_ref}"
            response = self.session.get(url, timeout=20)

            if response.status_code != 200:
                logger.warning(f"BoA receipt not found (HTTP {response.status_code}): {full_ref}")
                return AbyssiniaReceipt(success=False, error="Transaction not found")

            data = response.json()

            if data.get("header", {}).get("status", "").lower() != "success":
                error_msg = data.get("header", {}).get("message", "Invalid transaction")
                logger.warning(f"BoA API rejected: {error_msg}")
                return AbyssiniaReceipt(success=False, error=error_msg)

            return self._parse_api_response(data)

        except requests.RequestException as e:
            logger.error(f"Network error verifying BoA {full_ref}: {e}")
            return AbyssiniaReceipt(success=False, error="Network timeout")
        except Exception as e:
            logger.error(f"Unexpected error verifying BoA {full_ref}: {e}", exc_info=True)
            return AbyssiniaReceipt(success=False, error="Verification failed")

    def _parse_api_response(self, data: dict) -> AbyssiniaReceipt:
        """Parse the official JSON response from BoA"""
        try:
            txn = data["body"][0]

            # Extract amount safely
            amount_raw = txn.get("Transferred Amount", "0")
            amount_match = re.search(r'[\d,]+(?:\.\d+)?', amount_raw.replace(',', ''))
            amount = Decimal(amount_match.group().replace(',', '')) if amount_match else Decimal('0')

            receipt = AbyssiniaReceipt(
                success=True,
                payer_name=txn.get("Payer's Name", "").strip(),
                payer_account=txn.get("Source Account", "").strip(),
                amount=amount,
                date=txn.get("Transaction Date", ""),
                reference=txn.get("Transaction Reference", ""),
                narrative=txn.get("Narrative", "").strip(),
            )

            if receipt.payer_name and receipt.amount > 0:
                logger.info(f"BoA Verification SUCCESS: {receipt.payer_name} → {receipt.amount} Birr")
            else:
                receipt.success = False
                receipt.error = "Incomplete receipt data"

            return receipt

        except Exception as e:
            logger.error(f"Failed to parse BoA response: {e}")
            return AbyssiniaReceipt(success=False, error="Invalid receipt format")

    def _is_valid_receipt(self, receipt: AbyssiniaReceipt) -> bool:
        return all([
            receipt.success,
            receipt.payer_name,
            receipt.amount > 0,
            receipt.reference
        ])

    def _mock_verify(self, reference: str, account_suffix: str = "90172") -> AbyssiniaReceipt:
        """For testing without hitting BoA servers"""
        logger.info(f"Mock BoA verification: {reference}{account_suffix}")
        import time; time.sleep(1.2)
        return AbyssiniaReceipt(
            success=True,
            payer_name="Yordanos Tesfaye",
            payer_account="1000****5678",
            amount=Decimal("250.00"),
            date="30-Nov-2025 14:22:18",
            reference=f"{reference.upper()}{account_suffix}",
            narrative="YORDANOS BOOKSWAP"
        )


# @dataclass
# class VerifyResult:
#     success: bool
#     payer: Optional[str] = None
#     payerAccount: Optional[str] = None
#     receiver: Optional[str] = None
#     receiverAccount: Optional[str] = None
#     amount: Optional[float] = None
#     date: Optional[str] = None  # Changed to str for simplicity, can parse to datetime if needed
#     reference: Optional[str] = None
#     reason: Optional[str] = None
#     error: Optional[str] = None  # Added for failure cases

# @dataclass
# class AbyssiniaReceipt:
#     sourceAccountName: str = ""
#     vat: str = ""
#     transferredAmountInWord: str = ""
#     address: str = ""
#     transactionType: str = ""
#     serviceCharge: str = ""
#     sourceAccount: str = ""
#     paymentReference: str = ""
#     tel: str = ""
#     payerName: str = ""
#     narrative: str = ""
#     transferredAmount: str = ""
#     transactionReference: str = ""
#     transactionDate: str = ""
#     totalAmountIncludingVAT: str = ""

# def verify_abyssinia(reference: str, suffix: str) -> VerifyResult:
#     try:
#         logger.info(f"🏦 Starting Abyssinia verification for reference: {reference} with suffix: {suffix}")
        
#         # Construct the API URL
#         api_url = f"https://cs.bankofabyssinia.com/api/onlineSlip/getDetails/?id={reference}{suffix}"
#         logger.info(f"📡 Fetching from URL: {api_url}")
        
#         # Fetch JSON data from the API
#         response = requests.get(api_url, timeout=30, headers={
#             'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
#             'Accept': 'application/json, text/plain, */*',
#             'Accept-Language': 'en-US,en;q=0.9',
#             'Cache-Control': 'no-cache',
#             'Pragma': 'no-cache'
#         })
        
#         logger.info(f"✅ Successfully fetched response with status: {response.status_code}")
        
#         # Debug log response headers
#         logger.debug(f"📋 Response headers: {response.headers}")
        
#         # Debug log complete response structure
#         logger.debug(f"📄 Complete response data: {response.text}")
        
#         # Debug log response size and content type
#         logger.debug(f"📊 Response size: {len(response.text)} characters")
#         logger.debug(f"📝 Content-Type: {response.headers.get('content-type', 'unknown')}")
        
#         # Parse the JSON response
#         json_data: Dict = response.json()
        
#         # Check if the response has the expected structure
#         if not json_data or 'header' not in json_data or 'body' not in json_data or not isinstance(json_data['body'], list):
#             logger.error('❌ Invalid response structure from Abyssinia API')
#             return VerifyResult(success=False, error='Invalid response structure from Abyssinia API')
        
#         # Check if the request was successful
#         if json_data['header'].get('status') != 'success':
#             logger.error(f"❌ API returned error status: {json_data['header'].get('status')}")
#             return VerifyResult(success=False, error=f"API returned error status: {json_data['header'].get('status')}")
        
#         # Check if there's data in the body
#         if len(json_data['body']) == 0:
#             logger.error('❌ No transaction data found in response body')
#             return VerifyResult(success=False, error='No transaction data found in response body')
        
#         # Extract the first (and typically only) transaction record
#         transaction_data = json_data['body'][0]
#         logger.debug(f"📋 Raw transaction data from API: {transaction_data}")
#         logger.debug(f"🔍 Available fields in transaction data: {list(transaction_data.keys())}")
#         logger.debug(f"📊 Number of fields in transaction: {len(transaction_data)}")
        
#         # Map the response fields to standardized VerifyResult structure with detailed field-by-field logging
#         logger.debug("🔄 Starting field mapping process...")
        
#         # Extract and parse the amount
#         transferred_amount_str = transaction_data.get('Transferred Amount', '')
#         amount_match = re.search(r'[\d.]+', transferred_amount_str.replace(',', ''))
#         amount = float(amount_match.group(0)) if amount_match else None
        
#         # Parse the date (keep as str for now)
#         transaction_date_str = transaction_data.get('Transaction Date', '')
        
#         result = VerifyResult(
#             success=True,
#             payer=transaction_data.get("Payer's Name"),
#             payerAccount=transaction_data.get('Source Account'),
#             receiver=transaction_data.get('Source Account Name'),
#             amount=amount,
#             date=transaction_date_str if transaction_date_str else None,
#             reference=transaction_data.get('Transaction Reference'),
#             reason=transaction_data.get('Narrative') or None
#         )
        
#         # Debug log each field mapping
#         logger.debug("🏷️ Field mappings:")
#         logger.debug(f" payer: \"{transaction_data.get('Payer\'s Name')}\" -> \"{result.payer}\"")
#         logger.debug(f" payerAccount: \"{transaction_data.get('Source Account')}\" -> \"{result.payerAccount}\"")
#         logger.debug(f" receiver: \"{transaction_data.get('Source Account Name')}\" -> \"{result.receiver}\"")
#         logger.debug(f" amount: \"{transaction_data.get('Transferred Amount')}\" -> {result.amount}")
#         logger.debug(f" date: \"{transaction_data.get('Transaction Date')}\" -> {result.date}")
#         logger.debug(f" reference: \"{transaction_data.get('Transaction Reference')}\" -> \"{result.reference}\"")
#         logger.debug(f" reason: \"{transaction_data.get('Narrative')}\" -> \"{result.reason}\"")
        
#         logger.debug(f"✅ Field mapping completed. Mapped {len(vars(result))} fields.")
        
#         logger.debug(f"📋 Final mapped result object: {result}")
#         logger.info(f"✅ Successfully parsed Abyssinia receipt for reference: {result.reference}")
#         logger.debug(f"💰 Key transaction details - Amount: {result.amount}, Payer: {result.payer}, Date: {result.date}")
        
#         # Validate that we have essential fields
#         if not result.reference or result.amount is None or not result.payer:
#             logger.error('❌ Missing essential fields in transaction data')
#             return VerifyResult(success=False, error='Missing essential fields in transaction data')
        
#         return result
        
#     except requests.RequestException as e:
#         logger.error(f"❌ HTTP Error fetching Abyssinia receipt: {str(e)}")
#         if e.response:
#             logger.error(f"📊 Response status: {e.response.status_code}")
#             logger.error(f"📄 Response data: {e.response.text}")
#         return VerifyResult(success=False, error='Failed to verify Abyssinia transaction')
#     except Exception as e:
#         logger.error(f"❌ Unexpected error in verify_abyssinia: {str(e)}")
#         return VerifyResult(success=False, error='Failed to verify Abyssinia transaction')
    
    
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