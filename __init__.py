"""Top-level package for quiz_parser."""

__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]

__author__ = """quiz-parser"""
__email__ = "feishengfei@126.com"
__version__ = "0.0.1"

from .src.quiz_parser.nodes import NODE_CLASS_MAPPINGS
from .src.quiz_parser.nodes import NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"
