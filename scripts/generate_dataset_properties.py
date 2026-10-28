"""Generate 10 property JSON specifications for dataset house images."""

import json
from pathlib import Path

HOUSES = [
    {
        "id": 1,
        "name": "Oakwood Manor",
        "location": "Whitefield, Bengaluru",
        "price": "₹1.45 Cr",
        "property_type": "3 BHK Villa",
        "tone": "premium",
        "features": ["Spacious master bedroom", "Modern fitted kitchen", "Spa-style bathroom"],
        "contact": {"name": "Rohan Sharma", "phone": "+91 98450 11223", "email": "rohan@oakwood.in"},
        "cta": "Schedule your private tour",
    },
    {
        "id": 2,
        "name": "Serene Palms",
        "location": "Indiranagar, Bengaluru",
        "price": "₹2.20 Cr",
        "property_type": "4 BHK Luxury Residence",
        "tone": "warm",
        "features": ["Designer modular kitchen", "Sunlit master suite", "Contemporary bathroom fittings"],
        "contact": {"name": "Pooja Reddy", "phone": "+91 98800 22334", "email": "pooja@serenepalms.com"},
        "cta": "Book a site visit today",
    },
    {
        "id": 3,
        "name": "Azure Bay View",
        "location": "Koramangala, Bengaluru",
        "price": "₹1.85 Cr",
        "property_type": "3 BHK Premium Apartment",
        "tone": "energetic",
        "features": ["Gourmet modular kitchen", "Expansive master bedroom", "Premium sanitary fixtures"],
        "contact": {"name": "Vikram Sen", "phone": "+91 97400 33445", "email": "vikram@azurebay.in"},
        "cta": "Contact our sales team",
    },
    {
        "id": 4,
        "name": "Maple Crest",
        "location": "HSR Layout, Bengaluru",
        "price": "₹1.60 Cr",
        "property_type": "3 BHK Independent House",
        "tone": "warm",
        "features": ["Sleek open kitchen", "Warm hardwood-style bedroom", "Modern glass-door bath"],
        "contact": {"name": "Ananya Roy", "phone": "+91 99000 44556", "email": "ananya@maplecrest.in"},
        "cta": "Enquire now for details",
    },
    {
        "id": 5,
        "name": "The Grand Horizon",
        "location": "Jayanagar, Bengaluru",
        "price": "₹3.10 Cr",
        "property_type": "4 BHK Ultra-Luxury Villa",
        "tone": "premium",
        "features": ["Italian-finished kitchen", "Executive master suite", "Ensuite luxury bathroom"],
        "contact": {"name": "Karan Malhotra", "phone": "+91 98111 55667", "email": "karan@grandhorizon.com"},
        "cta": "Request an exclusive preview",
    },
    {
        "id": 6,
        "name": "Greenwood Enclave",
        "location": "Sarjapur Road, Bengaluru",
        "price": "₹95 Lakh",
        "property_type": "2 BHK Contemporary Apartment",
        "tone": "warm",
        "features": ["Efficient compact kitchen", "Cozy well-lit bedroom", "Polished tile bathroom"],
        "contact": {"name": "Deepa Nair", "phone": "+91 97333 66778", "email": "deepa@greenwood.in"},
        "cta": "Visit our model apartment",
    },
    {
        "id": 7,
        "name": "Sunset Ridge",
        "location": "Hebbal, Bengaluru",
        "price": "₹2.45 Cr",
        "property_type": "3 BHK Lakeside Penthouse",
        "tone": "energetic",
        "features": ["Chef-grade modular kitchen", "Scenic master suite", "Spacious bath with vanity"],
        "contact": {"name": "Arjun Varma", "phone": "+91 98444 77889", "email": "arjun@sunsetridge.in"},
        "cta": "Experience luxury living today",
    },
    {
        "id": 8,
        "name": "Silver Birch Residences",
        "location": "JP Nagar, Bengaluru",
        "price": "₹1.75 Cr",
        "property_type": "3 BHK Modern Duplex",
        "tone": "premium",
        "features": ["Custom cabinetry kitchen", "Tranquil master bedroom", "Elegant glass shower bath"],
        "contact": {"name": "Sneha Joshi", "phone": "+91 98888 88990", "email": "sneha@silverbirch.in"},
        "cta": "Book your walkthrough",
    },
    {
        "id": 9,
        "name": "Crestview Heights",
        "location": "Electronic City, Bengaluru",
        "price": "₹85 Lakh",
        "property_type": "2 BHK Urban Living",
        "tone": "warm",
        "features": ["Streamlined modern kitchen", "Sunny master bedroom", "Clean modern bathroom"],
        "contact": {"name": "Aditya Menon", "phone": "+91 99450 99001", "email": "aditya@crestview.in"},
        "cta": "Call now to reserve",
    },
    {
        "id": 10,
        "name": "Royal Palms Estate",
        "location": "Bellary Road, Bengaluru",
        "price": "₹4.50 Cr",
        "property_type": "5 BHK Signature Mansion",
        "tone": "premium",
        "features": ["Island modular kitchen", "Palatial master bedroom", "Five-piece designer bath"],
        "contact": {"name": "Meera Kapoor", "phone": "+91 98100 00112", "email": "meera@royalpalms.com"},
        "cta": "Schedule VIP showing",
    },
]

def main():
    props_dir = Path("dataset/properties")
    props_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir = Path("dataset")

    for h in HOUSES:
        i = h["id"]
        # Images are relative to the property JSON file (which is in dataset/properties/)
        # Path from dataset/properties/ to dataset/home{i}/{i}_frontal.jpg is ../home{i}/{i}_frontal.jpg
        images = [
            {"path": f"../home{i}/{i}_frontal.jpg", "label": "Exterior", "feature": "Stunning architecture"},
            {"path": f"../home{i}/{i}_bedroom.jpg", "label": "Master Bedroom", "feature": h["features"][0]},
            {"path": f"../home{i}/{i}_kitchen.jpg", "label": "Kitchen", "feature": h["features"][1]},
            {"path": f"../home{i}/{i}_bathroom.jpg", "label": "Bathroom", "feature": h["features"][2]},
        ]

        prop_data = {
            "name": h["name"],
            "location": h["location"],
            "price": h["price"],
            "property_type": h["property_type"],
            "tone": h["tone"],
            "features": h["features"],
            "images": images,
            "contact": h["contact"],
            "cta": h["cta"],
        }

        out_file = props_dir / f"house_{i}.json"
        out_file.write_text(json.dumps(prop_data, indent=2), encoding="utf-8")
        print(f"Wrote {out_file}")

if __name__ == "__main__":
    main()
