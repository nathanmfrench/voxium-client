import asyncio
import json
import websockets
import base64
import numpy as np
from typing import Optional, Dict, Any, Union, Callable, Awaitable
import logging
from websockets.connection import State

logger = logging.getLogger(__name__)

class VoxiumClient:
    """
    A client SDK for connecting to the Voxium WebSocket server for real-time speech transcription.
    Handles WebSocket connection, message formatting, sending/receiving, and callbacks.
    """
    def __init__(
        self,
        server_url: str = "wss://voxium.tech/asr/ws",
        vad_threshold: float = 0.5,
        silence_threshold: float = 0.5,
        language: Optional[str] = None,
        batch_size: int = 4,
        beam_size: int = 2,
        input_format: str = "base64",
        sample_rate: int = 16000,
        api_key: Optional[str] = None
    ):
        """
        Initialize the VoxiumClient.

        Args:
            server_url: WebSocket server URL.
            vad_threshold: Voice Activity Detection threshold (0.0 to 1.0).
            silence_threshold: Server-side silence duration parameter (float, e.g., seconds).
                               Check server documentation for exact meaning and units.
            language: Language code (e.g., "en", "es", "fr").
            batch_size: Batch size hint for server (might be ignored in streaming).
            beam_size: Beam size for transcription.
            input_format: Expected format of audio *after* base64 decoding by server.
            sample_rate: Input audio sample rate of the *original* audio before encoding.
            api_key: Optional API key for authentication via query parameter.
        """

        self.api_key = api_key
        self.server_url = server_url
        self.params = {
            "vad_threshold": vad_threshold,
            "silence_threshold": silence_threshold,
            "language": language,
            "batch_size": batch_size,
            "beam_size": beam_size,
            "input_format": input_format,
            "sample_rate": sample_rate
        }
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._is_connecting: bool = False
        self._connection_lock = asyncio.Lock()

        # Callbacks initialized to None
        self.transcription_callback = None
        self.error_callback = None
        self.connection_open_callback = None
        self.connection_close_callback = None
        self.connection_error_callback = None


    # --- Callback Setter Methods ---
    def set_transcription_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        self.transcription_callback = callback

    def set_error_callback(self, callback: Callable[[Union[Exception, str]], Awaitable[None]]):
        self.error_callback = callback

    def set_connection_open_callback(self, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        self.connection_open_callback = callback

    def set_connection_close_callback(self, callback: Callable[[int, str], Awaitable[None]]):
        self.connection_close_callback = callback

    def set_connection_error_callback(self, callback: Callable[[Exception], Awaitable[None]]):
         self.connection_error_callback = callback

    # --- Core WebSocket Logic ---
    async def _receiver(self):
        """Internal task to continuously receive messages from the WebSocket."""
        logger.info("Receiver task started.")
        while self.websocket and self.websocket.state == State.OPEN:
            try:
                message = await self.websocket.recv()
                try:
                    data = json.loads(message)
                    if isinstance(data, dict):
                        if "transcription" in data:
                            if self.transcription_callback:
                                await self.transcription_callback(data)
                        elif data.get("status") == "error":
                            error_msg = data.get("message", "Unknown server error")
                            logger.warning(f"Server reported error: {error_msg}")
                            if self.error_callback:
                                await self.error_callback(error_msg)
                        # Optionally log other status messages at INFO level
                        elif "status" in data and data["status"] not in ["connected", "partial", "final"]: # Avoid logging common statuses
                             logger.info(f"Received server status/message: {data}")
                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {message}")
                except Exception as e: # Catch errors during message processing/callback execution
                    logger.error(f"Error processing received message or in callback: {e}", exc_info=True)
                    if self.error_callback:
                         await self.error_callback(RuntimeError(f"Callback/Processing Error: {e}"))

            # handling for connection closed events
            except websockets.exceptions.ConnectionClosedOK as e:
                logger.info(f"WebSocket connection closed cleanly (OK): {e.code} {e.reason}")
                if self.connection_close_callback:
                    await self.connection_close_callback(e.code, e.reason)
                break
            except websockets.exceptions.ConnectionClosedError as e:
                logger.error(f"WebSocket connection closed with error: {e.code} {e.reason}")
                if self.connection_error_callback:
                     await self.connection_error_callback(e)
                break
            except Exception as e: 
                logger.error(f"Error during WebSocket receive: {e}", exc_info=True)
                if self.connection_error_callback:
                     await self.connection_error_callback(e)
                break

        logger.info("Receiver task finished.")
        # Attempt to clean up connection if task exits unexpectedly
        if self.websocket and self.websocket.state == State.OPEN:
             logger.warning("Receiver task exited unexpectedly, attempting to close connection.")
             # Use create_task as we are likely already in the event loop here, but await might not work
             asyncio.create_task(self.close())


    async def connect(self):
        """
        Connects to the WebSocket server, handles authentication, receives initial info,
        and starts the receiver task.
        """

        async with self._connection_lock: # Prevent concurrent connect/close operations
            if self.websocket and self.websocket.state == State.OPEN:
                logger.warning("Already connected.")
                return
            if self._is_connecting:
                logger.warning("Connection attempt already in progress.")
                return

            self._is_connecting = True
            logger.info("Attempting to connect...")

            try:
                # Construct URL with query parameters
                param_list = [f"{k}={v}" for k, v in self.params.items()]
                if self.api_key:
                    param_list.append(f"apiKey={self.api_key}")
                    # logger.info("Adding 'apiKey' to query parameters.") # Reduce noise
                else:
                    logger.info("No API key provided.")

                query_string = "&".join(param_list)
                url = f"{self.server_url}?{query_string}" if param_list else self.server_url
                logger.info(f"Connecting to: {url}")

                # Establish WebSocket connection
                # Consider adding connect_timeout if needed: await asyncio.wait_for(websockets.connect(url), timeout=10.0)
                self.websocket = await websockets.connect(url)
                logger.info("WebSocket connection established.")

                # Receive and process initial server information
                try:
                    # Added timeout to prevent indefinite wait
                    initial_info_raw = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                    initial_info = json.loads(initial_info_raw)
                    logger.info(f"Server connection ready. Info: {initial_info}") # Log useful info
                    # Trigger the open callback if set
                    if self.connection_open_callback:
                        await self.connection_open_callback(initial_info)
                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for initial server info after connection.")
                    # Attempt to close cleanly if possible
                    if self.websocket and self.websocket.state == State.OPEN: await self.websocket.close(code=1008, reason="Timeout waiting initial info")
                    self.websocket = None
                    raise ConnectionError("Did not receive initial server info in time.")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Failed to parse initial server info as JSON: {e}")
                    if self.websocket and self.websocket.state == State.OPEN: await self.websocket.close(code=1007, reason="Invalid JSON received")
                    self.websocket = None
                    raise ConnectionError(f"Failed to parse initial server info: {e}")
                except websockets.exceptions.ConnectionClosed as e:
                    logger.error(f"Connection closed unexpectedly after opening, before receiving info: {e.code} {e.reason}")
                    self.websocket = None
                    raise ConnectionError(f"Connection closed prematurely: {e.code} {e.reason}")

                # Start the background receiver task if connection is successful
                if self._receive_task and not self._receive_task.done():
                    logger.warning("Receiver task already exists. Cancelling old one.")
                    self._receive_task.cancel()
                    try: await self._receive_task
                    except asyncio.CancelledError: pass # Expected

                self._receive_task = asyncio.create_task(self._receiver())
                logger.info("Connection successful and receiver task started.")

            # error handling for connection attempt failures
            except websockets.exceptions.InvalidStatusCode as e: # ... (keep logging and raise)
                 logger.error(f"Server rejected connection (Status {e.status_code}). Check URL/API Key/Params.")
                 self.websocket = None
                 conn_error = ConnectionRefusedError(f"Server rejected connection: Status {e.status_code}")
                 if self.connection_error_callback: await self.connection_error_callback(conn_error)
                 raise conn_error
            except (websockets.exceptions.WebSocketException, OSError, ConnectionError) as e: # Group common connection errors
                 logger.error(f"WebSocket connection failed: {e}")
                 self.websocket = None
                 conn_error = ConnectionError(f"WebSocket connection failed: {e}")
                 if self.connection_error_callback: await self.connection_error_callback(conn_error)
                 raise conn_error
            except Exception as e: 
                 logger.error(f"An unexpected error occurred during connection: {e}", exc_info=True)
                 self.websocket = None
                 conn_error = ConnectionError(f"Unexpected connection error: {e}")
                 if self.connection_error_callback: await self.connection_error_callback(conn_error)
                 raise conn_error
            finally:
                self._is_connecting = False


    async def send_audio_chunk(self, audio_data: Union[bytes, np.ndarray]):
        """
        Encodes and sends a single audio chunk over the WebSocket.
        """
        if not self.websocket or self.websocket.state != State.OPEN:
             logger.error("[SendChunk] Cannot send: Not connected.")
             raise ConnectionError("WebSocket is not connected.")

        try:
            # --- Convert to bytes if necessary ---
            if isinstance(audio_data, np.ndarray):
                audio_bytes = audio_data.tobytes()
            elif isinstance(audio_data, bytes):
                 audio_bytes = audio_data
            else:
                 raise TypeError("audio_data must be bytes or numpy.ndarray")

            # --- Encode and Format ---
            base64_audio = base64.b64encode(audio_bytes).decode('utf-8')
            message = json.dumps({"audio_data": base64_audio})

            # --- Send bytes through the websocket ---
            await self.websocket.send(message)

        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"[SendChunk] Connection closed while sending: {e}")
            if self.connection_error_callback:
                asyncio.create_task(self.connection_error_callback(e))
            # await self.close() # May cause issues if called concurrently
            raise # Re-raise so the caller (_audio_loop) knows
        except Exception as e:
            logger.error(f"[SendChunk] Error sending audio chunk: {e}", exc_info=True)
            if self.error_callback:
                 asyncio.create_task(self.error_callback(RuntimeError(f"Send Error: {e}")))
            raise # Re-raise

    async def close(self):
        """Closes the WebSocket connection and cleans up related tasks."""
        # Use lock to prevent race conditions if close is called concurrently
        async with self._connection_lock:
            # Cancel receiver task safely
            if self._receive_task and not self._receive_task.done():
                logger.info("Cancelling receiver task...")
                self._receive_task.cancel()
                try:
                    await self._receive_task # Allow task to process cancellation
                except asyncio.CancelledError:
                    logger.info("Receiver task successfully cancelled.")
                except Exception as e: # Log errors during cancellation itself
                     logger.error(f"Error awaiting cancelled receiver task: {e}", exc_info=True)
                self._receive_task = None

            # Close WebSocket connection if open
            if self.websocket and self.websocket.state == State.OPEN:
                logger.info("Closing WebSocket connection...")
                try:
                    await self.websocket.close(code=1000, reason="Client closing normally")
                    logger.info("WebSocket connection closed.")
                    # Trigger callback if it exists and wasn't triggered by receiver
                    if not self._receive_task and self.connection_close_callback:
                         await self.connection_close_callback(1000, "Closed manually")
                except Exception as e:
                     logger.error(f"Error closing websocket: {e}", exc_info=True)
                     # Trigger error callback for close errors
                     if self.connection_error_callback:
                         await self.connection_error_callback(e)

            # Ensure state is fully reset
            self.websocket = None
            logger.debug("WebSocket client state cleared.")


    # --- Async Context Manager ---
    async def __aenter__(self):
        """Enters the async context, connecting the client."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exits the async context, closing the client connection."""
        await self.close()