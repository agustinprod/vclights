"""Control de lamparas LED VC-BLELIGHT (DoHome) sin la app oficial."""
from .lamp import Found, Group, Lamp, discover
from .protocol import MODES

__all__ = ["Lamp", "Group", "Found", "discover", "MODES"]
__version__ = "0.1.0"
