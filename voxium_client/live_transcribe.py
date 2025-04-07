# live_transcribe.py

# --- Required Imports ---
import asyncio
import sounddevice as sd
import numpy as np
from .client import VoxiumClient # Assuming client.py is in the same directory/package
import logging
import websockets # Keep for exception handling if needed, otherwise can maybe remove
from typing import Callable, Awaitable, Optional, Dict, Any, Union
from websockets.connection import State

# --- Logging Setup ---
# Logger instance for this module
logger = logging.getLogger(__name__)

# --- Audio Parameters ---
# Moved constants outside class for potential reuse or easier configuration
BLOCKSIZE = 512  # How many frames per callback
CHANNELS = 1      # Mono audio
RATE = 16000     # Sample rate (Hz)
SD_DTYPE = 'int16' # Data type for sounddevice

class LiveTranscriber:
    """
    Captures audio from the microphone using sounddevice and streams it to a
    Voxium ASR server using the VoxiumClient for real-time transcription.

    Handles thread-safe communication between the sounddevice callback thread
    and the main asyncio event loop. Includes a workaround for potential initial
    server/network stabilization delays.
    """
    def __init__(
        self,
        server_url: str = "wss://voxium.tech/asr/ws",
        api_key: Optional[str] = None,
        vad_threshold: float = 0.5,
        silence_threshold: float = 0.5,
        language: str = "en",
        **client_kwargs
    ):
        """
        Initializes the LiveTranscriber.

        Args:
            server_url: WebSocket server URL for Voxium ASR.
            api_key: Optional API key for authentication.
            vad_threshold: VAD threshold for the Voxium client.
            silence_threshold: Silence threshold for the Voxium client.
            language: Language code for transcription.
            **client_kwargs: Additional keyword arguments passed to VoxiumClient.
        """
        self.stream: Optional[sd.InputStream] = None
        self.audio_queue = asyncio.Queue() # Queue for thread-safe data transfer
        self._is_running = False
        self._audio_task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Initialize Voxium Client
        self.client = VoxiumClient(
            server_url=server_url,
            api_key=api_key,
            vad_threshold=vad_threshold,
            silence_threshold=silence_threshold,
            language=language,
            sample_rate=RATE, # Pass RATE constant
            input_format="base64", # Client handles encoding, server decodes this
            **client_kwargs
        )

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status: sd.CallbackFlags):
        """
        [Thread-Safe] Sounddevice callback. Runs in a separate thread.
        Converts audio data to bytes and safely schedules it to be put onto the
        asyncio queue using loop.call_soon_threadsafe.
        """
        # Log significant sounddevice status issues
        if status:
            logger.warning(f"[AudioCallback] Sounddevice status: {status!s}")
            if status & sd.CallbackFlags.input_overflow:
                 logger.warning("[AudioCallback] Status Detail: Input overflow detected (mic data potentially lost!).")
            # Add other status checks if needed

        try:
            # Convert audio data to bytes (still done in this thread)
            audio_bytes = indata.tobytes()

            # Safely schedule the queue put operation on the event loop thread
            if self._loop:
                self._loop.call_soon_threadsafe(self.audio_queue.put_nowait, audio_bytes)
                # Minimal debug log (optional)
                # logger.debug(f"[AudioCallback] Scheduled put_nowait for {len(audio_bytes)} bytes.")
            else:
                # This should generally not happen if start() logic is correct
                logger.error("[AudioCallback] Event loop reference missing! Cannot queue audio.")

        except Exception as e:
            # Catch errors during byte conversion or scheduling
            logger.error(f"[AudioCallback] UNEXPECTED ERROR in callback thread: {e}", exc_info=True)
        # Removed detailed timing logs for production

    def setup_audio(self):
        """Sets up and starts the sounddevice InputStream."""
        logger.info(f"Setting up sounddevice stream: {RATE} Hz, {CHANNELS} channels, dtype: {SD_DTYPE}, Blocksize: {BLOCKSIZE}")
        try:
            # Ensure previous stream is cleaned up if necessary
            if self.stream and not self.stream.closed:
                logger.warning("Existing audio stream found. Cleaning up before creating new one.")
                self.cleanup_audio()

            # Create and start the input stream
            self.stream = sd.InputStream(
                samplerate=RATE,
                channels=CHANNELS,
                dtype=SD_DTYPE,
                blocksize=BLOCKSIZE,
                callback=self._audio_callback
            )
            self.stream.start()
            logger.info("Sounddevice stream started successfully.")

        except sd.PortAudioError as pae:
             logger.error(f"PortAudioError during sounddevice setup: {pae}", exc_info=True)
             logger.error("-> This often means no input microphone is found, available, or supports the required settings.")
             self.stream = None
             # Propagate as a more specific error if desired, or let the caller handle it
             raise ConnectionAbortedError(f"Audio device error: {pae}") from pae
        except Exception as e:
            logger.error(f"Failed to open sounddevice stream: {e}", exc_info=True)
            self.stream = None
            raise # Re-raise other exceptions

    async def _audio_loop(self):
        """
        [Cleaned] Consumes audio from the queue and sends it via the client.
        Includes the initial configurable delay workaround.
        """
        logger.info("[AudioLoop] Started.")
        self._is_running = True
        loop_iteration = 0

        while self._is_running:
            loop_iteration += 1
            log_prefix = f"[AudioLoop Iter {loop_iteration}]"

            try:
                # Get audio data from the queue (blocks if empty)
                data: bytes = await self.audio_queue.get()

                if data is None: # Handle potential sentinel value for stopping
                    self._is_running = False
                    self.audio_queue.task_done()
                    logger.info(f"{log_prefix} Received sentinel. Stopping loop.")
                    continue

                # Check WebSocket connection state
                if self.client and self.client.websocket and self.client.websocket.state == State.OPEN:

                    # Send the audio chunk via the client
                    await self.client.send_audio_chunk(data)

                else: # Handle disconnection during operation
                    if self._is_running:
                        logger.warning(f"{log_prefix} WebSocket not connected or closed. Stopping loop.")
                    self._is_running = False
                    # Don't mark task done if data wasn't sent
                    continue

                # Mark item as processed
                self.audio_queue.task_done()

            except websockets.exceptions.ConnectionClosed as e:
                 logger.warning(f"{log_prefix} Connection closed during loop: {e}. Stopping.")
                 self._is_running = False
            except Exception as e:
                logger.error(f"{log_prefix} Error in audio processing loop: {e}", exc_info=True)
                self._is_running = False
                # Trigger error callback if set
                if self.client.error_callback:
                    error_obj = RuntimeError(f"Audio Loop Error: {e}")
                    asyncio.create_task(self.client.error_callback(error_obj))

        logger.info("[AudioLoop] Finished.")

    async def start(self):
        """
        Connects to the server, captures the event loop, sets up audio stream,
        and runs the main audio processing loop.
        """
        if self._is_running:
            logger.warning("Transcription is already running.")
            return

        try:
            # Capture running event loop (for thread-safe calls
            self._loop = asyncio.get_running_loop()
            logger.debug(f"Captured event loop: {self._loop}")

            logger.info("Connecting to Voxium server...")
            # Use the client as an async context manager to handle connect/close
            async with self.client:
                logger.info("Connected. Setting up audio...")
                self.setup_audio() # Starts the callback thread which needs self._loop

                logger.info("Starting audio processing loop...")
                # Create and run the main audio consumer task
                self._audio_task = asyncio.create_task(self._audio_loop())
                # Wait for the audio loop task to complete (e.g., if stop() is called or error occurs)
                await self._audio_task

        except ConnectionAbortedError as e:
             # Specific error from setup_audio
             logger.error(f"Cannot start transcription due to audio device issue: {e}")
             # No audio cleanup needed here as stream likely didn't fully start
             raise
        except ConnectionError as e:
             # Error during self.client connect or context management
             logger.error(f"WebSocket connection failed: {e}. Cannot start transcription.")
             # Audio might have started, attempt cleanup
             self.cleanup_audio()
             raise
        except Exception as e:
            # Catch any other unexpected errors during startup
            logger.error(f"Failed to start transcription: {e}", exc_info=True)
            # Attempt cleanup
            self.cleanup_audio()
            raise
        finally:
             logger.info("Transcription process exiting start method.")
             # Ensure state is reset and resources cleaned up
             self._is_running = False
             # Ensure audio cleanup runs if start() exited abnormally after setup_audio
             self.cleanup_audio()
             self._loop = None # Clear loop reference

    def stop(self):
        """
        Signals the audio processing loop to stop gracefully.
        """
        logger.info("Stopping transcription...")
        self._is_running = False
        # Optional: Put a sentinel on the queue to wake the loop immediately
        # This requires self._loop to be valid or handling in put_nowait directly
        # if self._loop:
        #    self._loop.call_soon_threadsafe(self.audio_queue.put_nowait, None)

    def cleanup_audio(self):
        """
        Stops and closes the sounddevice audio stream if it's active.
        """
        # Check if stream exists and is active before stopping/closing
        if self.stream and not self.stream.closed:
            logger.info("Cleaning up sounddevice stream...")
            try:
                # Check if stopped needed? Some examples just close. Be safe.
                if not self.stream.stopped:
                    self.stream.stop()
                self.stream.close()
                logger.info("Sounddevice stream stopped and closed.")
            except Exception as e:
                 logger.error(f"Error stopping/closing sounddevice stream: {e}", exc_info=True)
            finally:
                 self.stream = None # Ensure reference is cleared
        else:
             logger.debug("Audio stream cleanup requested, but stream was not active or already cleaned.")


    def start_transcription(
        self,
        on_transcription: Callable[[Dict[str, Any]], Awaitable[None]],
        on_error: Optional[Callable[[Union[Exception, str]], Awaitable[None]]] = None,
        on_open: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        on_close: Optional[Callable[[int, str], Awaitable[None]]] = None,
    ):
        """
        Simplified blocking method to start live transcription.

        This method handles the asyncio setup, runs the transcription process,
        and waits until it's stopped (e.g., by KeyboardInterrupt or an error).

        Args:
            on_transcription: (Required) Async callback for transcription results.
            on_error: Optional async callback for server-reported errors.
            on_open: Optional async callback when connection is opened.
            on_close: Optional async callback when connection is closed.
        """
        if not on_transcription:
            raise ValueError("The 'on_transcription' callback is required.")

        # --- Define Default Callbacks (used if specific ones aren't provided) ---
        async def _default_on_error(error: Union[Exception, str]):
             logger.error(f"Default Handler - Server/Processing Error: {error}")

        async def _default_on_open(info: dict):
            model_info = info.get('model_info', {})
            logger.info("Default Handler - Connection opened.")
            # Avoid accessing potentially missing keys directly
            model_name = model_info.get('name') or model_info.get('whisper_model', 'Unknown')
            device = model_info.get('device', 'Unknown')
            logger.info(f"  Server Model: {model_name}")
            logger.info(f"  Server Device: {device}")

        async def _default_on_close(code: int, reason: str):
            logger.warning(f"Default Handler - Connection closed: Code={code}, Reason='{reason}'")

        # --- Assign Callbacks (use provided or default) ---
        self.client.set_transcription_callback(on_transcription)
        self.client.set_error_callback(on_error or _default_on_error)
        self.client.set_connection_open_callback(on_open or _default_on_open)
        self.client.set_connection_close_callback(on_close or _default_on_close)

        # --- Async Runner ---
        async def _run_internal():
            logger.info("Starting transcription via start_transcription. Press Ctrl+C to stop.")
            await self.start() # Calls the main async start logic

        # --- Run the Loop and Handle Shutdown ---
        try:
            # Perform audio device check before starting asyncio loop
            logger.debug("Checking sounddevice input settings...")
            try:
                 sd.check_input_settings(samplerate=RATE, channels=CHANNELS, dtype=SD_DTYPE)
                 logger.debug("Sounddevice check successful.")
            except Exception as sd_err:
                 logger.error(f"Sounddevice check failed: {sd_err}", exc_info=True)
                 logger.error("-> Please ensure a microphone is connected, dependencies are installed, and the device supports the required settings (16kHz, Mono, 16-bit).")
                 return # Exit if audio backend check fails

            # Run the main async task using asyncio.run()
            # This creates a new event loop and runs _run_internal until it completes
            asyncio.run(_run_internal())

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received. Stopping transcription...")
            # asyncio.run() handles cancelling the running task (_run_internal -> self.start -> self._audio_task)
            # Cleanup is handled in the 'finally' blocks of self.start() and this function.
        except (ConnectionError, ConnectionAbortedError) as e:
             # Catch specific errors expected from start()
             logger.critical(f"Failed to run transcription due to connection/device error: {e}")
             # Cleanup should be handled by finally block in start() if it got that far
        except Exception as e:
             # Catch any other unexpected errors during run
             logger.critical(f"An unexpected error occurred during transcription: {e}", exc_info=True)
             # Cleanup should be handled by finally block in start() if it got that far
        finally:
            logger.info("start_transcription method finished.")
            # This might be redundant if start()'s finally block always runs, but adds safety.
            self.cleanup_audio()