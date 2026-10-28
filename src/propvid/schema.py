"""Data models and schemas for propvid."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Contact(BaseModel):
    """Contact information for property enquiries."""
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class ImageRef(BaseModel):
    """Reference to an image file with optional feature association."""
    model_config = ConfigDict(extra="ignore")

    path: str
    feature: Optional[str] = None
    label: Optional[str] = None


class PropertyInput(BaseModel):
    """Raw validated input specification for a property."""
    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Property name")
    location: str = Field(..., description="Property location")
    price: str = Field(..., description="Property price string exactly as given")
    property_type: str = Field(..., description="Property type (e.g. 2-BHK Apartment)")
    features: List[str] = Field(default_factory=list, max_length=12)
    contact: Optional[Contact] = None
    cta: str = Field(default="Enquire today")
    tone: Literal["warm", "premium", "energetic"] = "warm"
    images: List[ImageRef] = Field(default_factory=list)


class SceneSpec(BaseModel):
    """Specification of an individual scene content."""
    model_config = ConfigDict(extra="ignore")

    id: str
    kind: Literal["title", "feature", "cta", "highlight"]
    image_index: int = 0
    headline: str
    caption: str
    narration: str
    direction: str = "warm"


class Script(BaseModel):
    """Collection of scenes forming the narrative script."""
    model_config = ConfigDict(extra="ignore")

    scenes: List[SceneSpec]
    source: Literal["template", "llm", "mixed"] = "template"


@dataclass
class PlannedScene:
    """Timeline-planned scene with timing, assigned image, and visual motion."""
    spec: SceneSpec
    image_path: Path
    start: float
    duration: float
    motion: str


@dataclass
class VideoPlan:
    """Overall timeline plan for the video."""
    scenes: List[PlannedScene]
    total_duration: float
    resolution: tuple[int, int]
    fps: int

    def __iter__(self):
        return iter(self.scenes)

    def __len__(self) -> int:
        return len(self.scenes)

    def __getitem__(self, index):
        return self.scenes[index]

