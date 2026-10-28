"""Fact verification and safety auditing for script scenes."""

import re
from typing import List, Set

from propvid.schema import PropertyInput, SceneSpec

BANNED_PHRASES = [
    "guaranteed",
    "best",
    "cheapest",
    "lowest price",
    "number one",
    "#1",
    "limited offer",
    "rera",
    "near",
    "minutes from",
    "walking distance",
    "ready to move",
]

COMMON_ALLOWLIST = {
    "a", "an", "the", "this", "that", "these", "those",
    "is", "are", "was", "were", "be", "been", "being",
    "in", "at", "on", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "in", "out", "over", "under", "again",
    "further", "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "welcome", "presenting", "discover", "features", "feature", "highlights",
    "enjoy", "experience", "check", "take", "crafted", "designed", "offering",
    "distinguished", "residence", "home", "living", "access", "convenience",
    "call", "email", "contact", "book", "enquire", "today", "now", "details",
    "site", "visit", "key", "luxury", "lifestyle", "and", "or", "exclusive",
}


def _extract_all_text_from_facts(facts: PropertyInput) -> str:
    """Concatenate all text from input property specification."""
    parts = [
        facts.name,
        facts.location,
        facts.price,
        facts.property_type,
        facts.cta,
        facts.tone,
        " ".join(facts.features),
    ]
    if facts.contact:
        if facts.contact.name:
            parts.append(facts.contact.name)
        if facts.contact.phone:
            parts.append(facts.contact.phone)
        if facts.contact.email:
            parts.append(facts.contact.email)
    for img in facts.images:
        if img.feature:
            parts.append(img.feature)
        if img.label:
            parts.append(img.label)
    return " ".join(parts)


def _extract_numbers(text: str) -> Set[str]:
    """Extract all numerical tokens (e.g. 1, 1.25, 90000, 24x7)."""
    # Match sequences of digits optionally separated by commas, dots, or 'x'
    matches = re.findall(r"\b\d+(?:[.,x]\d+)*\b", text.lower())
    return set(matches)


def _extract_words(text: str) -> Set[str]:
    """Extract individual alphanumeric word tokens lowercased."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def verify_scene(spec: SceneSpec, facts: PropertyInput) -> List[str]:
    """Verify that a scene strictly conforms to ground truth facts.

    Returns a list of violation descriptions. If empty, the scene is verified.
    """
    violations: List[str] = []
    facts_text = _extract_all_text_from_facts(facts)
    facts_numbers = _extract_numbers(facts_text)
    facts_words = _extract_words(facts_text)

    # 1. Length constraints
    narration_words = spec.narration.split()
    if len(narration_words) > 22:
        violations.append(
            f"Narration exceeds 22 words ({len(narration_words)} words): '{spec.narration}'"
        )

    # For captions, allow slightly longer if displaying full contact info in CTA
    caption_words = spec.caption.split()
    max_caption_len = 12 if spec.kind == "cta" else 8
    if len(caption_words) > max_caption_len:
        violations.append(
            f"Caption exceeds {max_caption_len} words ({len(caption_words)} words): '{spec.caption}'"
        )

    combined_scene_text = f"{spec.headline} {spec.caption} {spec.narration}"

    # 2. Number verification: every number in scene must exist in facts
    scene_numbers = _extract_numbers(combined_scene_text)
    for num in scene_numbers:
        if num not in facts_numbers:
            violations.append(f"Invented number not present in facts: '{num}'")

    # 3. Banned phrases check with strict word boundaries
    for phrase in BANNED_PHRASES:
        # Build pattern using word boundaries
        if phrase.startswith("#"):
            pattern = re.compile(r"(?:^|\s)" + re.escape(phrase) + r"(?:\b|\s|[.,!?]|$)", re.IGNORECASE)
        else:
            pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)

        if pattern.search(combined_scene_text):
            # Only allowed if the exact banned phrase was explicitly in the input facts
            if not pattern.search(facts_text):
                violations.append(f"Contains unverified banned phrase: '{phrase}'")

    # 4. Capitalized words check (excluding first word of sentences)
    # Split into sentences
    sentences = re.split(r"[.!?]\s*", spec.narration)
    for sent in sentences:
        tokens = sent.strip().split()
        if len(tokens) <= 1:
            continue
        # Check non-initial tokens for proper nouns / invented claims
        for token in tokens[1:]:
            # Split hyphenated or compound words (e.g. East-facing -> East, facing)
            subtokens = [re.sub(r"[^\w]", "", t) for t in re.split(r"[\s\-]+", token)]
            for sub in subtokens:
                if sub and sub[0].isupper():
                    lower_sub = sub.lower()
                    if lower_sub not in facts_words and lower_sub not in COMMON_ALLOWLIST:
                        violations.append(f"Invented entity or proper noun not in facts: '{sub}'")

    return violations


def verify_share_copy(text: str, facts: PropertyInput) -> List[str]:
    """Verify that social share copy and hashtags strictly adhere to input facts."""
    violations: List[str] = []
    facts_text = _extract_all_text_from_facts(facts)
    facts_numbers = _extract_numbers(facts_text)
    facts_words = _extract_words(facts_text)

    # 1. Number verification
    copy_numbers = _extract_numbers(text)
    for num in copy_numbers:
        if num not in facts_numbers:
            violations.append(f"Invented number in share copy: '{num}'")

    # 2. Banned phrases verification
    for phrase in BANNED_PHRASES:
        if phrase.startswith("#"):
            pattern = re.compile(r"(?:^|\s)" + re.escape(phrase) + r"(?:\b|\s|[.,!?]|$)", re.IGNORECASE)
        else:
            pattern = re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE)
        if pattern.search(text) and not pattern.search(facts_text):
            violations.append(f"Banned phrase in share copy: '{phrase}'")

    # 3. Hashtag checking: each hashtag must stem from facts or standard safe real-estate terms
    hashtags = re.findall(r"#(\w+)", text)
    safe_hashtag_terms = {
        "realestate", "propertyforsale", "hometour", "property", "realty",
        "apartment", "house", "villa", "penthouse", "sale", "home", "residence"
    }
    for tag in hashtags:
        tag_lower = tag.lower()
        if tag_lower not in facts_words and tag_lower not in safe_hashtag_terms:
            # Check if composite of known fact words (e.g. 2BHKApartment or Whitefield)
            if not any(w in tag_lower for w in facts_words if len(w) > 2):
                violations.append(f"Unverified hashtag claim in share copy: '#{tag}'")

    return violations

