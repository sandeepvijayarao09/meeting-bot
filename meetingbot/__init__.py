"""Local-first AI meeting notetaker for macOS."""

import logging

__version__ = "0.1.0"

# Library convention (PEP 282): never configure logging on import — attach a
# NullHandler so importing the package is silent. The CLI installs real handlers.
logging.getLogger(__name__).addHandler(logging.NullHandler())
