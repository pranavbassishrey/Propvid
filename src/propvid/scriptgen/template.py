"""Deterministic template script generator."""

from typing import List

from propvid.schema import PropertyInput, SceneSpec, Script

DIRECTION_MAP = {
    "warm": "warm",
    "premium": "calm",
    "energetic": "excited",
}

TITLE_TEMPLATES = {
    "warm": "Welcome to {name}, a {property_type} in {location}, offered at {price}.",
    "premium": "Presenting {name}, a {property_type} in {location}, priced at {price}.",
    "energetic": "Discover {name}! A {property_type} in {location}, available at {price}.",
}

FEATURE_TEMPLATES = {
    "warm": [
        "This home includes {feature}.",
        "The property provides {feature}.",
        "You will find {feature} here.",
        "Included with this home is {feature}.",
        "The residence offers {feature}.",
    ],
    "premium": [
        "The residence includes {feature}.",
        "The property provides {feature}.",
        "Amenities include {feature}.",
        "The layout includes {feature}.",
        "Key features include {feature}.",
    ],
    "energetic": [
        "Take a look at the {feature}!",
        "The home includes {feature}!",
        "This property features {feature}!",
        "Check out the {feature}!",
        "Highlights include {feature}!",
    ],
}


def format_feature_for_mid_sentence(feature: str) -> str:
    """Format feature string for mid-sentence placement without lowercasing acronyms."""
    words = feature.split()
    if not words:
        return feature

    first_word = words[0]
    # If the first word is all-uppercase (e.g. CCTV, AC, EV, BHK) or has digits (e.g. 24x7), keep it
    if first_word.isupper() or any(char.isdigit() for char in first_word):
        return feature

    formatted_first = first_word[0].lower() + first_word[1:]
    return " ".join([formatted_first] + words[1:])


def build_template_script(prop: PropertyInput) -> Script:
    """Generate a 100% deterministic, fact-verified script with zero LLM dependency.

    Ensures that every word and claim is directly drawn from the input property fields.
    """
    tone = prop.tone if prop.tone in DIRECTION_MAP else "warm"
    direction = DIRECTION_MAP[tone]
    scenes: List[SceneSpec] = []

    # 1. Title Scene
    title_narration = TITLE_TEMPLATES[tone].format(
        name=prop.name,
        property_type=prop.property_type,
        location=prop.location,
        price=prop.price,
    )
    scenes.append(
        SceneSpec(
            id="title_0",
            kind="title",
            image_index=0,
            headline=prop.name,
            caption=f"{prop.location} • {prop.price}",
            narration=title_narration,
            direction=direction,
        )
    )

    # 2. Feature Scenes (up to 5) or Highlight Scene
    if prop.features:
        selected_features = prop.features[:5]
        templates = FEATURE_TEMPLATES[tone]
        for idx, feat in enumerate(selected_features):
            tmpl = templates[idx % len(templates)]
            mid_feat = format_feature_for_mid_sentence(feat)
            feat_narration = tmpl.format(feature=mid_feat)
            scenes.append(
                SceneSpec(
                    id=f"feature_{idx + 1}",
                    kind="feature",
                    image_index=idx + 1,
                    headline=feat,
                    caption=feat,
                    narration=feat_narration,
                    direction=direction,
                )
            )
    else:
        # No features provided: construct single highlight scene
        highlight_narration = f"This {prop.property_type} is located in {prop.location}."
        scenes.append(
            SceneSpec(
                id="highlight_1",
                kind="highlight",
                image_index=1,
                headline=prop.property_type,
                caption=prop.location,
                narration=highlight_narration,
                direction=direction,
            )
        )

    # 3. CTA Scene
    cta_headline = prop.cta
    cta_caption = prop.cta
    cta_narration = f"{prop.cta} for {prop.name}."

    if prop.contact:
        contact_items = []
        if prop.contact.name:
            contact_items.append(prop.contact.name)
        if prop.contact.phone:
            contact_items.append(prop.contact.phone)
        if prop.contact.email:
            contact_items.append(prop.contact.email)

        if contact_items:
            cta_caption = " • ".join(contact_items)

        if prop.contact.name and prop.contact.phone:
            cta_narration = f"{prop.cta}. Contact {prop.contact.name} at {prop.contact.phone}."
        elif prop.contact.phone:
            cta_narration = f"{prop.cta}. Call {prop.contact.phone} for details."
        elif prop.contact.email:
            cta_narration = f"{prop.cta}. Email {prop.contact.email}."

    scenes.append(
        SceneSpec(
            id="cta_final",
            kind="cta",
            image_index=len(scenes),
            headline=cta_headline,
            caption=cta_caption,
            narration=cta_narration,
            direction=direction,
        )
    )

    return Script(scenes=scenes, source="template")
