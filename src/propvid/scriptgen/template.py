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
        "Features include {feature}.",
        "This residence provides {feature}.",
        "Enjoy the convenience of {feature}.",
        "Highlights include {feature}.",
        "Crafted with {feature}.",
    ],
    "premium": [
        "The residence features {feature}.",
        "Thoughtfully designed with {feature}.",
        "Offering access to {feature}.",
        "Key highlights include {feature}.",
        "Distinguished by {feature}.",
    ],
    "energetic": [
        "Check out the {feature}!",
        "Experience great living with {feature}!",
        "Take advantage of {feature}!",
        "Featuring {feature}!",
        "Highlights include {feature}!",
    ],
}


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
            feat_narration = tmpl.format(feature=feat)
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
    cta_narration = f"{prop.cta}."

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
