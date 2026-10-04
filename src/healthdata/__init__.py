"""healthdata package

Provides tools to: download, read and preprocess health datasets.
It is specific to open health datasets.
Dataset implementations are under separate modules, such as ``healthdata.nhanes``
"""

from . import nhanes

__all__ = ["nhanes"]
