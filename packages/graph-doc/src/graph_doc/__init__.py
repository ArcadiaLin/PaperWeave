"""graph_doc：graph-doc（读写同形的 YAML 子图）的解析与求差。见 README。"""

from .document import VERSIONS, DocEdge, DocNode, Document, from_data, is_temp, load, parse
from .errors import DiffError, DocError, GraphDocError
from .fragment import Fragment, FragmentNode, diff

__all__ = [
    "VERSIONS",
    "DiffError",
    "DocEdge",
    "DocError",
    "DocNode",
    "Document",
    "Fragment",
    "FragmentNode",
    "GraphDocError",
    "diff",
    "from_data",
    "is_temp",
    "load",
    "parse",
]
