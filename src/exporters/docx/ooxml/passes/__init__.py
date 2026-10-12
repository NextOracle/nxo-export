"""The post-processing passes, one concern each."""

from .base import DocumentPass
from .bookmarks import BookmarkPass
from .chapters import ChapterBreakPass
from .figures import FigurePass
from .lists import ListSpacingPass
from .properties import CorePropertiesPass
from .tables import TableLayoutPass
from .text_diagrams import TextDiagramPass
from .toc import TocPass

__all__ = [
    "BookmarkPass", "ChapterBreakPass", "CorePropertiesPass", "DocumentPass", "FigurePass", "ListSpacingPass",
    "TableLayoutPass", "TextDiagramPass", "TocPass",
]
