"""
mothersauce: the base recipes of production Python, typed, tested and served to your AI agent.

Importing the package costs almost nothing: the version is read only when someone asks for
``mothersauce.__version__``, through a module level ``__getattr__`` (PEP 562), from the ``_version.py`` that
setuptools_scm writes at install time.
"""

__all__ = ["__version__"]


def __getattr__(name: str) -> str:
    """
    Compute ``__version__`` on first use, so ``import mothersauce`` never reads package metadata.

    :param name: The attribute asked for
    :returns: The version string
    :raises AttributeError: For any other name
    """
    if name != "__version__":
        raise AttributeError(f"module 'mothersauce' has no attribute {name!r}")
    import importlib

    try:
        return str(importlib.import_module("mothersauce._version").version)  # written by setuptools_scm
    except ImportError:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("mothersauce")
        except PackageNotFoundError:  # a source tree that was never installed
            return "0.0.0"
