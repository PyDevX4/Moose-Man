"""
Where things live, whether the game runs from source or from the .exe.

PyInstaller's one-file build unpacks into a temp folder that is deleted on
exit, so anything the game writes must go next to the .exe the player
actually double-clicked, never into that temp folder.
"""

import os
import sys

FROZEN = getattr(sys, "frozen", False)


def app_dir():
    """The folder the game lives in, from the player's point of view."""
    if FROZEN:
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))
