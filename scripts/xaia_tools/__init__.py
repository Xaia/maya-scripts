"""Xaia Tools for Maya. Importing is safe in batch and does not launch tools."""
__version__ = "1.0.0"


def show_menu():
    from .menu import install
    return install()
