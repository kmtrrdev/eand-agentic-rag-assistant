"""Structured-output schema for the classify node's single LLM call."""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Intent = Literal[
    "greeting",
    "out_of_scope",
    "package_inquiry",
    "price_calculation",
    "activation_code",
    "recommendation",
    "comparison",
    "complaint_or_support",
]


class ClassifyResult(BaseModel):
    language: Literal["ar", "en", "mixed"] = Field(
        description="Language the customer wrote in. 'mixed' if both Arabic and English appear."
    )
    intent: Intent = Field(description="The customer's primary intent for this message.")
    family: Optional[str] = Field(
        default=None,
        description="Product family id the question is about, from the provided list, or null if none/unclear.",
    )
    package_name_raw: Optional[str] = Field(
        default=None,
        description="The exact package/tier name or phrase the customer used, e.g. 'Aqwa Card 19' or 'حكاية مكسات 92', or null.",
    )
    tier_price_egp: Optional[float] = Field(
        default=None, description="The EGP price of the specific tier mentioned, if any, e.g. 19 for 'Aqwa Card 19'."
    )
    budget_egp: Optional[float] = Field(
        default=None, description="The customer's stated budget in EGP, if this is a recommendation request."
    )
    device_type: Optional[Literal["phone", "router"]] = Field(
        default=None, description="'router' if the customer mentions a MiFi/USB modem/router, else 'phone', or null."
    )
    usage_focus: Optional[Literal["minutes", "data", "balanced"]] = Field(
        default=None, description="'minutes' if customer prioritizes calls/minutes, 'data' if data/internet, else null."
    )
    min_price_egp: Optional[float] = Field(
        default=None, description="Minimum tier base price — only for 'show higher tiers' follow-ups; filters out plans at or below this price."
    )
    is_out_of_scope: bool = Field(
        description="True if this is about a competitor, an unrelated topic, or a real e& Egypt service this "
        "assistant doesn't cover (e.g. billing disputes, SIM replacement, technical support)."
    )
    entities: List[str] = Field(
        default_factory=list,
        description="All specific package names or product families referenced in the question and recent conversation history (e.g. ['Emerald 3450', 'Hekaya Mixat 270']). For comparisons or follow-ups, resolve pronouns to the concrete packages.",
    )
    keywords: List[str] = Field(default_factory=list, description="2-5 short keywords capturing the question's topic.")


class QueryRewriteResult(BaseModel):
    standalone_query: str = Field(
        description="The customer's request rewritten as a single, self-contained search query in the customer's "
        "own language, with every pronoun/reference resolved to the concrete package or family name (e.g. "
        "'what are its benefits?' -> 'what are Emerald 1725's benefits?'). Rephrase only — never answer the question "
        "or add facts that weren't asked for."
    )
    bridge_terms: List[str] = Field(
        default_factory=list,
        description="0-5 extra keyword phrases that bridge a language/vocabulary gap between the question and how "
        "the knowledge base is written — e.g. the English family/product name for an Arabic question, or vice versa, "
        "plus close English synonyms for the concept asked about (e.g. an Arabic question about roaming coverage "
        "countries should add English terms like 'roaming countries approved destinations'). Leave empty if the "
        "question's own wording already matches the domain vocabulary well.",
    )
