"""PyInstaller entry point for the standalone explncc binary.

Kept outside the package so PyInstaller has a plain script to analyze; it
imports the Typer app exactly the way the console script does.
"""

from explncc.cli import app

if __name__ == "__main__":
    app()
