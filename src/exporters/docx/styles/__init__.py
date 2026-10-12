"""Word styles: declared by the catalogue, written by StyleWriter, packaged as reference.docx."""

from .catalogue import WritersideStyleCatalogue
from .reference import ReferenceDocBuilder

__all__ = ["ReferenceDocBuilder", "WritersideStyleCatalogue"]
