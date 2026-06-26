import re

class DataRedactor:
    """
    DataRedactor provides high-fidelity SQL and text scrubbing/redaction 
    for PII (emails, phone numbers, credit cards) and database credentials 
    to enforce privacy in public-facing or audit logging states.
    """

    # Regular expressions for PII detection
    EMAIL_REGEX = re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b")
    PHONE_REGEX = re.compile(
        r"(?<!\d)(?:\+?86[-.\s]?)?1[3-9]\d{9}(?!\d)"
        r"|(?<!\d)(?:\+?86[-.\s]?)?\d{3,4}[-\s]\d{7,8}(?!\d)"
        r"|(?<![\d-])(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?![\d-])"
    )
    CREDIT_CARD_REGEX = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
    
    # Matches assignment of credential values in SQL (e.g. password = 'value' or SET PASSWORD = 'value')
    # It dynamically captures typical credential keyword names and masks the string literals.
    CREDENTIAL_ASSIGN_REGEX = re.compile(
        r"(?i)\b(password|passwd|secret|token|api_key|apikey|credential|passphrase|private_key|privatekey)\b\s*=\s*'[^']+'"
    )
    CREDENTIAL_DEFAULT_REGEX = re.compile(
        r"(?i)\b(password|passwd|secret|token|api_key|apikey|credential|passphrase|private_key|privatekey)\b"
        r"(\s+[A-Z0-9_()\s]+?\bDEFAULT\s*)'[^']+'"
    )
    AUTHORIZATION_HEADER_REGEX = re.compile(
        r"(?i)\b(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)"
    )
    LOCAL_TOKEN_HEADER_REGEX = re.compile(
        r"(?i)\b(x[-_]?local[-_]?token\s*[:=]\s*)([^\s,;]+)"
    )
    RAW_API_KEY_REGEX = re.compile(
        r"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|LTAI[A-Za-z0-9]{12,})(?![A-Za-z0-9_-])"
    )

    @staticmethod
    def _luhn_valid(digits: str) -> bool:
        if not (13 <= len(digits) <= 19) or len(set(digits)) == 1:
            return False

        total = 0
        double = False
        for char in reversed(digits):
            value = int(char)
            if double:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
            double = not double
        return total % 10 == 0

    @staticmethod
    def redact_sql(sql_str: str) -> str:
        """
        Redacts sensitive PII and database credential assignments in the given SQL string.
        """
        if not sql_str:
            return ""

        # 1. Mask credential assignments like: password = 'abc' => password = '[REDACTED_SECURE]'
        def replace_cred_assign(match: re.Match[str]) -> str:
            keyword = match.group(1)
            return f"{keyword} = '[REDACTED_SECURE]'"

        scrubbed = DataRedactor.CREDENTIAL_ASSIGN_REGEX.sub(replace_cred_assign, sql_str)

        # 2. Mask credential defaults in DDL, e.g. password TEXT DEFAULT 'abc'.
        def replace_cred_default(match: re.Match[str]) -> str:
            return f"{match.group(1)}{match.group(2)}'[REDACTED_SECURE]'"

        scrubbed = DataRedactor.CREDENTIAL_DEFAULT_REGEX.sub(replace_cred_default, scrubbed)

        # 3. Mask header-style bearer tokens and local engine tokens in trace/error text.
        scrubbed = DataRedactor.AUTHORIZATION_HEADER_REGEX.sub(
            lambda match: f"{match.group(1)}{match.group(2) or ''}[REDACTED]",
            scrubbed,
        )
        scrubbed = DataRedactor.LOCAL_TOKEN_HEADER_REGEX.sub(
            lambda match: f"{match.group(1)}[REDACTED]",
            scrubbed,
        )
        scrubbed = DataRedactor.RAW_API_KEY_REGEX.sub("[REDACTED_API_KEY]", scrubbed)

        # 4. Redact Emails
        scrubbed = DataRedactor.EMAIL_REGEX.sub("[REDACTED_EMAIL]", scrubbed)

        # 5. Redact Phone Numbers
        scrubbed = DataRedactor.PHONE_REGEX.sub("[REDACTED_PHONE]", scrubbed)

        # 6. Redact Luhn-valid Credit Cards
        def replace_card(match: re.Match[str]) -> str:
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            return "[REDACTED_CARD]" if DataRedactor._luhn_valid(digits) else candidate

        scrubbed = DataRedactor.CREDIT_CARD_REGEX.sub(replace_card, scrubbed)

        return scrubbed
