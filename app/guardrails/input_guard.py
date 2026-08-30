from typing import Optional
from app.config import settings
from app.guardrails.policies import GuardrailCategory, GuardrailResult
from app.guardrails.garak_guard import GarakInputGuard
from app.guardrails.security_utils import (
    ARABIC_INJECTION_PATTERNS,
    PROMPT_INJECTION_PATTERNS,
    SECRET_REQUEST_PATTERNS,
    SYSTEM_PROMPT_PATTERNS,
    is_arabic_text,
)


def get_safe_refusal_message(category: GuardrailCategory, is_arabic: bool) -> str:
    """Generate a polite, secure customer-facing refusal based on violation category."""
    if is_arabic:
        if category == GuardrailCategory.SECRET_REQUEST:
            return "عذراً، لا يمكنني مشاركة أي مفاتيح تشغيل أو بيانات سرية أو إعدادات داخلية. أنا هنا لمساعدتك في باقات وخدمات اتصالات مصر فقط."
        if category == GuardrailCategory.SYSTEM_PROMPT_REQUEST:
            return "عذراً، تعليمات النظام والإعدادات الداخلية محمية ولا يمكن عرضها. يسعدني مساعدتك في أي استفسار يخص باقات وخدمات اتصالات مصر."
        if category == GuardrailCategory.PROMPT_INJECTION or category == GuardrailCategory.MALICIOUS_INPUT:
            return "عذراً، لا يمكن معالجة هذا الطلب لأسباب أمنية. يرجى كتابة استفسارك حول باقات وعروض اتصالات مصر وسأكون سعيداً بمساعدتك."
        if category == GuardrailCategory.INVALID_INPUT:
            return "عذراً، نص السؤال غير صالح أو يتجاوز الحد المسموح به. يرجى كتابة سؤال محدد وموجز."
        return "عذراً، لا يمكن إتمام هذا الطلب. كيف يمكنني مساعدتك في باقات اتصالات مصر؟"
    else:
        if category == GuardrailCategory.SECRET_REQUEST:
            return "I cannot share API keys, credentials, or internal configuration. I am here to help you with e& Egypt telecom plans and services."
        if category == GuardrailCategory.SYSTEM_PROMPT_REQUEST:
            return "Internal system instructions and configurations cannot be displayed. I am happy to assist you with any questions regarding e& Egypt packages and services."
        if category == GuardrailCategory.PROMPT_INJECTION or category == GuardrailCategory.MALICIOUS_INPUT:
            return "This request cannot be processed for security reasons. Please ask a question related to e& Egypt packages and services."
        if category == GuardrailCategory.INVALID_INPUT:
            return "The provided query is invalid or exceeds the maximum allowed length. Please provide a concise telecom question."
        return "I cannot fulfill this request. How may I assist you with e& Egypt services?"


def validate_input(text: Optional[str]) -> GuardrailResult:
    """
    Validate user input using Garak probe analytics before retrieval.
    Protects against prompt injection, DAN jailbreaks, obfuscated base64 attacks,
    secret extraction, system prompt theft, oversized inputs, and malicious payloads.
    """
    if not text or not str(text).strip():
        return GuardrailResult(
            allowed=False,
            category=GuardrailCategory.INVALID_INPUT,
            reason="Empty query received",
            safe_message="يرجى إدخال استفسارك لمساعدتك."
        )

    raw_text = str(text).strip()
    is_ar = is_arabic_text(raw_text)

    # 1. Length check
    if len(raw_text) > settings.MAX_QUERY_LENGTH:
        return GuardrailResult(
            allowed=False,
            category=GuardrailCategory.INVALID_INPUT,
            reason=f"Query length ({len(raw_text)}) exceeds limit of {settings.MAX_QUERY_LENGTH}",
            safe_message=get_safe_refusal_message(GuardrailCategory.INVALID_INPUT, is_ar)
        )

    # 2. Garak-Powered Input Security Engine (DAN, Goodside, Base64/Obfuscation, SysPrompt, APIKey)
    garak_res = GarakInputGuard.evaluate(raw_text)
    if not garak_res["allowed"]:
        cat_str = garak_res.get("category", "PROMPT_INJECTION")
        if cat_str == "SECRET_REQUEST":
            cat_enum = GuardrailCategory.SECRET_REQUEST
        elif cat_str == "SYSTEM_PROMPT_REQUEST":
            cat_enum = GuardrailCategory.SYSTEM_PROMPT_REQUEST
        elif cat_str == "INVALID_INPUT":
            cat_enum = GuardrailCategory.INVALID_INPUT
        else:
            cat_enum = GuardrailCategory.PROMPT_INJECTION

        return GuardrailResult(
            allowed=False,
            category=cat_enum,
            reason=garak_res.get("reason", "Garak security probe triggered"),
            safe_message=get_safe_refusal_message(cat_enum, is_ar)
        )

    # 3. Secondary regex fallback patterns
    for pattern in SECRET_REQUEST_PATTERNS:
        if pattern.search(raw_text):
            return GuardrailResult(
                allowed=False,
                category=GuardrailCategory.SECRET_REQUEST,
                reason="Attempted secret or API key extraction",
                safe_message=get_safe_refusal_message(GuardrailCategory.SECRET_REQUEST, is_ar)
            )

    for pattern in SYSTEM_PROMPT_PATTERNS:
        if pattern.search(raw_text):
            return GuardrailResult(
                allowed=False,
                category=GuardrailCategory.SYSTEM_PROMPT_REQUEST,
                reason="Attempted system prompt extraction",
                safe_message=get_safe_refusal_message(GuardrailCategory.SYSTEM_PROMPT_REQUEST, is_ar)
            )

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(raw_text):
            return GuardrailResult(
                allowed=False,
                category=GuardrailCategory.PROMPT_INJECTION,
                reason="Prompt injection pattern detected",
                safe_message=get_safe_refusal_message(GuardrailCategory.PROMPT_INJECTION, is_ar)
            )

    for pattern in ARABIC_INJECTION_PATTERNS:
        if pattern.search(raw_text):
            return GuardrailResult(
                allowed=False,
                category=GuardrailCategory.PROMPT_INJECTION,
                reason="Arabic prompt injection pattern detected",
                safe_message=get_safe_refusal_message(GuardrailCategory.PROMPT_INJECTION, is_ar)
            )

    return GuardrailResult(
        allowed=True,
        category=GuardrailCategory.SAFE,
        reason="Input passed all Garak security checks",
        safe_message=None
    )

