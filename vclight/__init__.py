"""Control VC-BLELIGHT (DoHome) LED lamps without the official app."""
from .lamp import Found, Group, Lamp, discover
from .protocol import MODES

__all__ = ["Lamp", "Group", "Found", "discover", "MODES"]
__version__ = "0.2.0"
