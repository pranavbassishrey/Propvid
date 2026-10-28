"""Script to generate elegant placeholder images for real-estate demos."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

IMAGES = [
    ("01_exterior.jpg", "Green Valley Heights", "Modern Luxury Architectural Exterior", (24, 43, 73), (70, 130, 180)),
    ("02_living_room.jpg", "Spacious Living Room", "Sunlit Open-Concept Living & Dining Area", (45, 35, 30), (140, 110, 90)),
    ("03_kitchen.jpg", "Modular Kitchen", "Contemporary Quartz Countertops & Cabinetry", (30, 45, 40), (80, 130, 115)),
    ("04_balcony.jpg", "East-Facing Balcony", "Panoramic City Skyline View with Morning Sun", (35, 45, 60), (100, 135, 175)),
    ("05_bedroom.jpg", "Master Bedroom Suite", "Spacious Hardwood Flooring & Full Wardrobes", (40, 30, 45), (120, 95, 135)),
    ("06_clubhouse.jpg", "Clubhouse & Amenities", "Fully-Equipped Fitness Gym & Community Lounge", (30, 50, 45), (75, 140, 120)),
]


def create_gradient(width: int, height: int, start_color: tuple, end_color: tuple) -> Image.Image:
    """Create a subtle horizontal and vertical color gradient."""
    base = Image.new("RGB", (width, height), start_color)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        ratio = y / height
        r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return base


def generate_images(out_dir: Path) -> None:
    """Generate all demo images."""
    out_dir.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720

    for filename, title, subtitle, c1, c2 in IMAGES:
        img = create_gradient(width, height, c1, c2)
        draw = ImageDraw.Draw(img)

        # Draw architectural grid/geometry overlay
        for x in range(80, width, 160):
            draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 15), width=1)
        for y in range(60, height, 120):
            draw.line([(0, y), (width, y)], fill=(255, 255, 255, 15), width=1)

        # Draw a central showcase card
        card_w, card_h = 760, 220
        card_x = (width - card_w) // 2
        card_y = (height - card_h) // 2
        draw.rectangle(
            [card_x, card_y, card_x + card_w, card_y + card_h],
            fill=(10, 15, 25),
            outline=(212, 175, 55),
            width=2,
        )

        # Text labels
        draw.text((card_x + 40, card_y + 45), title.upper(), fill=(255, 255, 255))
        draw.text((card_x + 40, card_y + 90), subtitle, fill=(200, 210, 225))
        draw.text((card_x + 40, card_y + 150), "DEMO PROPERTY ASSET • PROPVID", fill=(212, 175, 55))

        target_file = out_dir / filename
        img.save(target_file, "JPEG", quality=95)
        print(f"Generated {target_file}")


if __name__ == "__main__":
    examples_img_dir = Path(__file__).resolve().parent.parent / "examples" / "images"
    generate_images(examples_img_dir)
