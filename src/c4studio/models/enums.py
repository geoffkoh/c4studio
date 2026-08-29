"""Enumerations used throughout the Structurizr metamodel."""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Element classification
# ---------------------------------------------------------------------------


class ElementType(str, Enum):
    PERSON = "person"
    SOFTWARE_SYSTEM = "softwareSystem"
    CONTAINER = "container"
    COMPONENT = "component"


class ViewType(str, Enum):
    SYSTEM_LANDSCAPE = "systemLandscape"
    SYSTEM_CONTEXT = "systemContext"
    CONTAINER = "container"
    COMPONENT = "component"
    DYNAMIC = "dynamic"
    DEPLOYMENT = "deployment"
    CUSTOM = "custom"
    IMAGE = "image"
    FILTERED = "filtered"


class Location(str, Enum):
    """Whether a Person or SoftwareSystem is internal or external to the enterprise."""

    INTERNAL = "Internal"
    EXTERNAL = "External"
    UNSPECIFIED = "Unspecified"


class InteractionStyle(str, Enum):
    SYNCHRONOUS = "Synchronous"
    ASYNCHRONOUS = "Asynchronous"


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class RankDirection(str, Enum):
    TOP_BOTTOM = "TopBottom"
    BOTTOM_TOP = "BottomTop"
    LEFT_RIGHT = "LeftRight"
    RIGHT_LEFT = "RightLeft"


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------


class Shape(str, Enum):
    BOX = "Box"
    ROUNDED_BOX = "RoundedBox"
    CIRCLE = "Circle"
    ELLIPSE = "Ellipse"
    HEXAGON = "Hexagon"
    DIAMOND = "Diamond"
    CYLINDER = "Cylinder"
    BUCKET = "Bucket"
    PIPE = "Pipe"
    PERSON = "Person"
    ROBOT = "Robot"
    FOLDER = "Folder"
    WEB_BROWSER = "WebBrowser"
    WINDOW = "Window"
    TERMINAL = "Terminal"
    SHELL = "Shell"
    MOBILE_DEVICE_PORTRAIT = "MobileDevicePortrait"
    MOBILE_DEVICE_LANDSCAPE = "MobileDeviceLandscape"
    COMPONENT = "Component"


class Routing(str, Enum):
    DIRECT = "Direct"
    CURVED = "Curved"
    ORTHOGONAL = "Orthogonal"


class LineStyle(str, Enum):
    DASHED = "Dashed"
    DOTTED = "Dotted"
    SOLID = "Solid"


class Border(str, Enum):
    SOLID = "Solid"
    DASHED = "Dashed"
    DOTTED = "Dotted"


class FilterMode(str, Enum):
    INCLUDE = "Include"
    EXCLUDE = "Exclude"


class ColorScheme(str, Enum):
    LIGHT = "Light"
    DARK = "Dark"


class IconPosition(str, Enum):
    TOP = "Top"
    BOTTOM = "Bottom"
    LEFT = "Left"


class ViewSortOrder(str, Enum):
    DEFAULT = "Default"
    TYPE = "Type"
    KEY = "Key"


class PaperSize(str, Enum):
    A6_PORTRAIT = "A6_Portrait"
    A6_LANDSCAPE = "A6_Landscape"
    A5_PORTRAIT = "A5_Portrait"
    A5_LANDSCAPE = "A5_Landscape"
    A4_PORTRAIT = "A4_Portrait"
    A4_LANDSCAPE = "A4_Landscape"
    A3_PORTRAIT = "A3_Portrait"
    A3_LANDSCAPE = "A3_Landscape"
    A2_PORTRAIT = "A2_Portrait"
    A2_LANDSCAPE = "A2_Landscape"
    A1_PORTRAIT = "A1_Portrait"
    A1_LANDSCAPE = "A1_Landscape"
    A0_PORTRAIT = "A0_Portrait"
    A0_LANDSCAPE = "A0_Landscape"
    LETTER_PORTRAIT = "Letter_Portrait"
    LETTER_LANDSCAPE = "Letter_Landscape"
    LEGAL_PORTRAIT = "Legal_Portrait"
    LEGAL_LANDSCAPE = "Legal_Landscape"
    SLIDE_4_3 = "Slide_4_3"
    SLIDE_16_9 = "Slide_16_9"
    SLIDE_16_10 = "Slide_16_10"


class Format(str, Enum):
    """Markup format for documentation sections and decisions."""

    MARKDOWN = "Markdown"
    ASCIIDOC = "AsciiDoc"
