"""swmap - read, write, unpack and pack .swmap custom map files."""
from .fileio import load, loads, save, dumps
from .model import SwMap, Header, Environment, Terrain, Prop
from .folder import read_folder, write_folder
from .validate import validate
from .binio import FormatError

__version__ = "0.1.0"
__all__ = ["load", "loads", "save", "dumps", "SwMap", "Header", "Environment", "Terrain", "Prop",
           "read_folder", "write_folder", "validate", "FormatError"]
