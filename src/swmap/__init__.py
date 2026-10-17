"""swmap - unpack .swmap custom maps into editable files and pack them back.

The binary format (reading, writing, validation rules) lives in swformats
(https://github.com/xmake-studio/sw-formats); the map model is ``swformats.swmap.SwMap``.
"""
from swformats import FormatError
from swformats.swmap import SwMap

from .fileio import MapFile, load, loads
from .folder import read_folder, write_folder
from .validate import Issue, validate

__version__ = "0.4.0"
__all__ = ["load", "loads", "MapFile", "SwMap", "read_folder", "write_folder", "validate", "Issue", "FormatError"]
