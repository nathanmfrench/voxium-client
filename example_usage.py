import logging
from voxium_client import LiveTranscriber 

# --- 1. Configure Logging  ---
# This basic setup logs WARNING level messages and above to the console.
# It's sufficient for most examples (you can implement more complex logging if needed).
# Set level=logging.DEBUG for debugging logs, and level=logging.INFO for normal logs.

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("MyVoiceAgentExample")


# --- 2. Define Your Transcription Handler (Required) ---
# This asynchronous function will receive transcription results.
async def handle_transcription(result: dict):
    """
    Callback function to process transcription results from Voxium.
    'result' is a dictionary.
    """
    try:
        text = result.get('transcription', '')
        print("Transcription: ", text)
        print("Language: ", result.get('language', ''), "with probability: ", result.get('language_probability', ''))

        # Now, you can ntegrate the transcription text into your voice agent's pipeline. For example:
            # await send_to_my_agent_logic(text)

    except Exception as e:
        logger.error(f"Error within handle_transcription callback: {e}", exc_info=True)


# --- 3. Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Voxium LiveTranscriber Integration Example...")

    # --- Configuration Parameters ---
    VOXIUM_API_KEY = "YOUR_API_KEY_HERE"

    if VOXIUM_API_KEY == "YOUR_API_KEY_HERE":
        logger.warning("Using placeholder API Key. Please set the VOXIUM_API_KEY environment variable or replace the placeholder.")

    VOXIUM_SERVER_URL = "wss://voxium.tech/asr/ws"
    LANGUAGE = None

    # --- Initialize the Transcriber ---
    logger.info(f"Initializing LiveTranscriber for {LANGUAGE}...")
    transcriber = LiveTranscriber(
        server_url=VOXIUM_SERVER_URL,
        language=LANGUAGE,
        api_key=VOXIUM_API_KEY
        # Add/override other parameters if needed:
        # vad_threshold=0.5,
        # silence_threshold=0.5,
    )

    # --- Start the Transcription Process ---
    # This is a blocking call that runs the transcriber until stopped (Ctrl+C or error).
    # It requires your 'on_transcription' callback function.
    logger.info("Starting transcription. Press Ctrl+C to stop.")
    try:
        transcriber.start_transcription(
            on_transcription=handle_transcription
            # --- Optional Callbacks ---
            # You can provide your own async functions for other events:
            # on_error=my_async_error_handler,
            # on_open=my_async_open_handler,
            # on_close=my_async_close_handler
        )
    except Exception as e:
         logger.critical(f"Failed to run transcription: {e}", exc_info=True)

    logger.info("Transcription process finished.")