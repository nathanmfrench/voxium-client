# Voxium Real-Time Transcription Client

This project provides a Python client library for interacting with the Voxium real-time speech-to-text (ASR) WebSocket service. It captures audio from the microphone, streams it to the Voxium server, and processes the received transcriptions via callbacks.

**Key Features:**

* **Real-time Audio Streaming:** Captures microphone audio using `sounddevice`.
* **WebSocket Communication:** Connects to and communicates with the Voxium ASR WebSocket endpoint using `websockets`.
* **Asynchronous Operation:** Built using `asyncio` for efficient non-blocking I/O.
* **Thread-Safe Audio Handling:** Safely transfers audio data from the `sounddevice` callback thread to the main `asyncio` event loop using `asyncio.Queue`.
* **Configurable Parameters:** Allows setting language, VAD thresholds, API keys, and other parameters for the Voxium service.
* **Callback-Based API:** Provides asynchronous callbacks for handling transcription results, errors, connection events (open/close).
* **Simplified Usage:** Offers a high-level `LiveTranscriber` class with a blocking `start_transcription` method for easy integration.

## Table of Contents

* [Prerequisites](#prerequisites)
* [Installation](#installation)
* [Configuration](#configuration)
* [Usage](#usage)
* [Core Components](#core-components)
    * [VoxiumClient (`client.py`)](#voxiumclient-clientpy)
    * [LiveTranscriber (`live_transcribe.py`)](#livetranscriber-live_transcribepy)
* [Callbacks](#callbacks)
* [Logging](#logging)
* [How it Works](#how-it-works)
* [Dependencies](#dependencies)
* [Troubleshooting](#troubleshooting)

## Prerequisites

* **Python:** Version 3.7+ (due to `asyncio` usage)
* **Microphone:** A working microphone connected to your system and recognized by `sounddevice`.
* **PortAudio:** The `sounddevice` library depends on the PortAudio library. Installation varies by OS:
    * **macOS:** `brew install portaudio`
    * **Debian/Ubuntu:** `sudo apt-get install libportaudio2 libportaudiocpp0 portaudio19-dev`
    * **Windows:** Often included with Python distributions or audio drivers. Check the [sounddevice documentation](https://python-sounddevice.readthedocs.io/en/latest/installation.html) for details.
* **Voxium API Key:** You will need an API key from Voxium to authenticate with the service.

## Installation

1.  **Clone Repo** Obtain the source files (`client.py`, `live_transcribe.py`, `example_usage.py`). Place them in your project directory, maintaining the relative import structure (e.g., keep `client.py` and `live_transcribe.py` together if `live_transcribe.py` uses `from .client import VoxiumClient`).
2.  **Install Dependencies:** Install the required Python libraries using pip:

    ```bash
    pip install websockets numpy sounddevice
    ```
    You can also create a `requirements.txt` file:

    ```text
    # requirements.txt
    websockets>=10.0  # Specify versions as needed
    numpy>=1.18
    sounddevice>=0.4
    ```
    And install using:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

Configuration is primarily done within your Python script (like `example_usage.py`):

* **`VOXIUM_API_KEY`**: **Required.** Replace the placeholder `"YOUR_API_KEY_HERE"` with your actual Voxium API key. This is sent as a query parameter (`apiKey`) for authentication.
* **`VOXIUM_SERVER_URL`**: The WebSocket endpoint URL for the Voxium ASR service. Defaults to `"wss://voxium.tech/asr/ws"`.
* **`VOXIUM_LANGUAGE`**: The language code for transcription (e.g., `"en"`, `"es"`, `"fr"`). Defaults to `"en"`.
* **Other Parameters:** You can customize other parameters when initializing `LiveTranscriber` or `VoxiumClient`:
    * `vad_threshold` (float): Voice Activity Detection threshold (client-side hint for server).
    * `silence_threshold` (float): Server-side silence duration parameter.
    * `sample_rate` (int): Audio sample rate (hardcoded to 16000 Hz in `live_transcribe.py`).
    * `input_format` (str): Expected audio format on the server *after* base64 decoding (hardcoded to `"base64"` in `live_transcribe.py` as the client sends base64).
    * `beam_size`, `batch_size` (int): Hints for the server's transcription process.

## Usage

The `example_usage.py` script demonstrates how to use the `LiveTranscriber`.

1.  **Import:** Import the necessary classes and modules.
2.  **Configure Logging:** Set up Python's `logging` module (the example provides a basic console logger).
3.  **Define Transcription Handler:** Create an `async` function that will receive transcription results (dictionaries). This is where you integrate the text into your application logic.
4.  **Set Parameters:** Define your API key, server URL, and language.
5.  **Initialize `LiveTranscriber`:** Create an instance, passing the configuration parameters.
6.  **Start Transcription:** Call the `start_transcription` method, providing your handler function. This method is **blocking** and will run until interrupted (e.g., Ctrl+C) or a critical error occurs.

```python
# example_usage.py (Simplified)
import logging
import asyncio
# Assuming live_transcribe.py is in a package named 'voxium_client'
from voxium_client import LiveTranscriber # Adjust import based on your structure

# --- 1. Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("MyExample")

# --- 2. Define Your Transcription Handler ---
async def handle_transcription(result: dict):
    """Processes transcription results."""
    try:
        text = result.get('transcription', '')
        is_final = result.get('is_final', False) # Check if result is final
        if text:
            print(f"Transcription ({'Final' if is_final else 'Partial'}): {text}")
        # Add your application logic here
    except Exception as e:
        logger.error(f"Error in handle_transcription: {e}", exc_info=True)

# --- 3. Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Voxium LiveTranscriber Example...")

    # --- Configuration ---
    VOXIUM_API_KEY = "YOUR_API_KEY_HERE" # <<< REPLACE THIS!
    VOXIUM_SERVER_URL = "wss://voxium.tech/asr/ws"
    VOXIUM_LANGUAGE = "en"

    if VOXIUM_API_KEY == "YOUR_API_KEY_HERE":
        logger.warning("Using placeholder API Key. Please set correctly.")
        # Consider exiting if the key is required:
        # import sys
        # sys.exit("API Key not configured.")

    # --- Initialize ---
    transcriber = LiveTranscriber(
        server_url=VOXIUM_SERVER_URL,
        language=VOXIUM_LANGUAGE,
        api_key=VOXIUM_API_KEY
    )

    # --- Start (Blocking Call) ---
    logger.info("Starting transcription. Press Ctrl+C to stop.")
    try:
        transcriber.start_transcription(
            on_transcription=handle_transcription
            # Optional: Add other callbacks like on_error, on_open, on_close
        )
    except Exception as e:
         logger.critical(f"Failed to run transcription: {e}", exc_info=True)

    logger.info("Transcription process finished.")