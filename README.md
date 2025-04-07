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
* **Voxium API Key:** You need an API key from Voxium to authenticate with the service.

## Installation

1.  **Clone Repo** 

```
git clone https://github.com/nathanmfrench/voxium-client
```

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
```
Run script from your terminal with

```
python3 example_usage.py
```

## Core Components

### VoxiumClient (`client.py`)

* Manages the low-level WebSocket connection lifecycle (`connect`, `close`).
* Handles URL construction with query parameters (including the API key).
* Formats outgoing audio messages (encodes audio bytes to Base64 JSON).
* Runs a persistent `_receiver` task to listen for incoming messages (transcriptions, status, errors) from the server.
* Parses incoming JSON messages and routes them to the appropriate asynchronous callbacks.
* Provides setter methods (`set_transcription_callback`, `set_error_callback`, etc.) for registering custom handlers.
* Implements `async` context manager protocols (`__aenter__`, `__aexit__`) for automatic connection setup and teardown.
* Handles WebSocket connection errors and state changes.

### LiveTranscriber (`live_transcribe.py`)

* Acts as the primary interface for users.
* Initializes and manages the `VoxiumClient`.
* Uses `sounddevice.InputStream` to capture audio from the default microphone in a separate thread.
* The `_audio_callback` function (running in the `sounddevice` thread) converts audio chunks (`numpy.ndarray`) to bytes.
* Uses `loop.call_soon_threadsafe` to safely put the audio bytes onto an `asyncio.Queue` from the `sounddevice` thread.
* An `_audio_loop` `async` task runs in the main event loop, consuming audio bytes from the queue.
* Sends audio chunks to the server via the `VoxiumClient.send_audio_chunk` method.
* Manages the starting (`start`) and stopping (`stop`, `cleanup_audio`) of the audio stream and processing loop.
* Provides the simplified, blocking `start_transcription` method which:
    * Sets up default callbacks if user doesn't provide them.
    * Assigns user-provided callbacks to the underlying `VoxiumClient`.
    * Checks basic `sounddevice` settings before starting.
    * Uses `asyncio.run()` to manage the event loop and run the main `start` coroutine.
    * Handles `KeyboardInterrupt` for graceful shutdown.

## Callbacks

The `LiveTranscriber.start_transcription` method accepts several optional `async` callback functions:

* **`on_transcription(result: dict)`**: *(Required)* Called whenever a transcription message (partial or final) is received from the server. The `result` dictionary typically contains keys like `"transcription"` (the text) and `"is_final"` (boolean).
* **`on_error(error: Union[Exception, str])`**: Called when the server sends an error status message or when certain client-side processing errors occur (like in the audio loop or message handling).
* **`on_open(info: dict)`**: Called once after the WebSocket connection is successfully established and the initial server handshake is complete. The `info` dictionary contains details sent by the server (e.g., model info).
* **`on_close(code: int, reason: str)`**: Called when the WebSocket connection is closed, either cleanly or due to an error detected by the underlying `websockets` library *within the receiver task*. Provides the close code and reason.

If you don't provide `on_error`, `on_open`, or `on_close`, default handlers that log the event will be used.

*Note:* The underlying `VoxiumClient` also has a `connection_error_callback` specifically for errors during the connection phase or WebSocket-level close errors not caught by the receiver loop's `ConnectionClosed...` exceptions. This isn't directly exposed via `start_transcription` but is used internally and logs errors.

## Logging

The code uses Python's standard `logging` module.

* `example_usage.py` sets up a basic configuration that logs `INFO` level messages and above to the console.
* `client.py` and `live_transcribe.py` obtain their own loggers (`logging.getLogger(__name__)`).
* You can customize the logging level and format in `example_usage.py` (e.g., set `level=logging.DEBUG` for verbose output, or add file handlers).

## How it Works

1.  `LiveTranscriber.start_transcription` is called.
2.  It configures callbacks on the `VoxiumClient` instance.
3.  It runs `asyncio.run(_run_internal)`, which calls `LiveTranscriber.start`.
4.  `LiveTranscriber.start` gets the current event loop.
5.  It enters the `VoxiumClient` async context (`__aenter__`), which calls `client.connect`.
6.  `client.connect` establishes the WebSocket connection, handles authentication, receives initial info, and starts the `client._receiver` task in the background.
7.  `LiveTranscriber.start` calls `setup_audio`, which creates and starts `sounddevice.InputStream`. The `_audio_callback` begins running in a separate thread.
8.  `_audio_callback` captures audio chunks, converts them to bytes, and uses `loop.call_soon_threadsafe` to put them on the `audio_queue`.
9.  `LiveTranscriber.start` starts the `_audio_loop` task.
10. `_audio_loop` waits for audio bytes from the `audio_queue`.
11. When audio arrives, `_audio_loop` calls `client.send_audio_chunk`.
12. `client.send_audio_chunk` base64 encodes the audio and sends it as a JSON message over the WebSocket.
13. Concurrently, `client._receiver` listens for messages from the server.
14. When a transcription message arrives, `_receiver` parses it and calls the registered `on_transcription` callback (your `handle_transcription` function).
15. This continues until `start_transcription` is interrupted (`Ctrl+C`) or a fatal error occurs.
16. On exit (interrupt or completion/error of `start`), `asyncio.run` handles task cancellation. The `finally` blocks in `start` and the client's `__aexit__` method (`close`) ensure the audio stream and WebSocket connection are cleaned up.

## Dependencies

* **`websockets`**: For WebSocket client implementation.
* **`numpy`**: For handling audio data arrays from `sounddevice`.
* **`sounddevice`**: For accessing the microphone and capturing audio streams.
* **`typing`**: For type checking
## Troubleshooting

* **`PortAudioError` / No Sound / "Invalid input device":**
    * Ensure a microphone is plugged in and enabled in your system settings.
    * Verify PortAudio is installed correctly (`brew install portaudio`, `apt-get install ...`).
    * Check if another application is exclusively using the microphone.
    * Try specifying a device ID in `sd.InputStream(device=...)` if the default is wrong. Use `python -m sounddevice` to list devices.
    * Ensure the microphone supports the required settings (16000 Hz, Mono, 16-bit Integer - `RATE`, `CHANNELS`, `SD_DTYPE`).
* **Connection Refused / Invalid Status Code / Timeout:**
    * Double-check the `VOXIUM_SERVER_URL`.
    * Verify your `VOXIUM_API_KEY` is correct and valid.
    * Check your internet connection and any firewall/proxy settings that might block WebSocket connections (port 443 for `wss://`).
* **Authentication Errors:**
    * Ensure the `apiKey` query parameter is being sent correctly (check logs if `DEBUG` level enabled) and matches what Voxium expects.
* **No Transcriptions Received:**
    * Check if the microphone is picking up sound (enable `DEBUG` logging to see audio chunk scheduling/sending).
    * Verify the correct `VOXIUM_LANGUAGE` is set.
    * Look for error messages in the logs from the client or server.
* **Import Errors:**
    * Ensure the Python files (`client.py`, `live_transcribe.py`) are located where Python can find them (e.g., same directory as your main script, or installed as part of a package). Adjust import statements (`from .client ...` vs `from voxium_client ...`) as needed based on your project structure.