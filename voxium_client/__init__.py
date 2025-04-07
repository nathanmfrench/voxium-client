# voxium_client/__init__.py

# Import the main classes to make them available directly at the package level
from .client import VoxiumClient
from .live_transcribe import LiveTranscriber

# Define package version (good practice)
__version__ = '0.1.0'

# Control what 'from voxium_client import *' does (optional but good practice)
__all__ = ['VoxiumClient', 'LiveTranscriber']

print(f"Voxium Client Library v{__version__} loaded.") # Optional: confirmation message