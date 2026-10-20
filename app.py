# from fastapi import FastAPI, UploadFile, File, HTTPException
# from pathlib import Path

# import asyncio
# import os
# import shutil
# import subprocess
# import tempfile
# import traceback

# from speech_service import speech_service
# from grocery_parser import grocery_parser

# from ai_queue import (
#     ai_queue,
#     AIQueueFullError,
# )


# # ============================================================
# # FastAPI
# # ============================================================

# app = FastAPI(
#     title="Yuganchin Voice Search AI",
#     version="1.0.0",
# )


# # ============================================================
# # Configuration
# # ============================================================

# MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# ALLOWED_AUDIO_EXTENSIONS = {
#     ".aac",
#     ".wav",
#     ".m4a",
#     ".mp4",
#     ".mp3",
#     ".ogg",
#     ".webm",
# }


# # ============================================================
# # Health
# # ============================================================

# @app.get("/health")
# def health():
#     return {
#         "status": "ok",
#         "service": "voice-search-ai",
#         "speech_model": "IndicConformer Tamil",
#         "parser_model": "Qwen3-1.7B",
#     }


# # ============================================================
# # Convert phone audio -> 16 kHz mono WAV
# # ============================================================

# def convert_to_16k_mono_wav(
#     input_path: str,
# ) -> str:

#     temp_file = tempfile.NamedTemporaryFile(
#         suffix=".wav",
#         delete=False,
#     )

#     wav_path = temp_file.name
#     temp_file.close()

#     command = [
#         "ffmpeg",
#         "-y",
#         "-loglevel",
#         "error",
#         "-i",
#         input_path,
#         "-ac",
#         "1",
#         "-ar",
#         "16000",
#         "-acodec",
#         "pcm_s16le",
#         wav_path,
#     ]

#     result = subprocess.run(
#         command,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.PIPE,
#         text=True,
#     )

#     if result.returncode != 0:

#         if os.path.exists(wav_path):
#             try:
#                 os.remove(wav_path)
#             except Exception:
#                 pass

#         raise RuntimeError(
#             "Audio conversion failed: "
#             + result.stderr.strip()
#         )

#     if (
#         not os.path.exists(wav_path)
#         or os.path.getsize(wav_path) == 0
#     ):
#         raise RuntimeError(
#             "Audio conversion produced an empty WAV file"
#         )

#     return wav_path


# # ============================================================
# # Voice Search
# # ============================================================

# @app.post("/voice-search")
# async def voice_search(
#     audio: UploadFile = File(...),
# ):

#     input_path = None
#     wav_path = None

#     try:

#         # ----------------------------------------------------
#         # 1. Validate uploaded audio
#         # ----------------------------------------------------

#         original_filename = (
#             audio.filename
#             or "voice.mp4"
#         )

#         extension = (
#             Path(original_filename)
#             .suffix
#             .lower()
#         )

#         if not extension:
#             extension = ".mp4"

#         if extension not in ALLOWED_AUDIO_EXTENSIONS:
#             raise HTTPException(
#                 status_code=400,
#                 detail=(
#                     "Unsupported audio format: "
#                     f"{extension}"
#                 ),
#             )


#         # ----------------------------------------------------
#         # 2. Save phone audio temporarily
#         # ----------------------------------------------------

#         with tempfile.NamedTemporaryFile(
#             suffix=extension,
#             delete=False,
#         ) as temp_file:

#             input_path = temp_file.name

#             total_size = 0

#             while True:

#                 chunk = await audio.read(
#                     1024 * 1024
#                 )

#                 if not chunk:
#                     break

#                 total_size += len(chunk)

#                 if total_size > MAX_AUDIO_SIZE_BYTES:
#                     raise HTTPException(
#                         status_code=413,
#                         detail=(
#                             "Voice recording is too large. "
#                             "Maximum size is 10 MB."
#                         ),
#                     )

#                 temp_file.write(chunk)


#         if (
#             not input_path
#             or not os.path.exists(input_path)
#             or os.path.getsize(input_path) == 0
#         ):
#             raise HTTPException(
#                 status_code=400,
#                 detail="Empty audio recording received",
#             )


#         print(
#             f"Audio received: "
#             f"{original_filename} "
#             f"({total_size} bytes)",
#             flush=True,
#         )


#         # ----------------------------------------------------
#         # 3. Convert to 16kHz mono WAV
#         #
#         # FFmpeg can safely run in a worker thread.
#         # ----------------------------------------------------

#         wav_path = await asyncio.to_thread(
#             convert_to_16k_mono_wav,
#             input_path,
#         )


#         print(
#             f"Converted WAV: {wav_path}",
#             flush=True,
#         )


#         # ----------------------------------------------------
#         # 4. Enter AI queue
#         #
#         # Only ONE customer uses the AI models at a time.
#         # ----------------------------------------------------

#         try:

#             async with ai_queue.slot():

#                 # ============================================
#                 # IndicConformer
#                 # ============================================

#                 print(
#                     "Starting IndicConformer...",
#                     flush=True,
#                 )

#                 transcript = await asyncio.to_thread(
#                     speech_service.transcribe,
#                     wav_path,
#                 )

#                 transcript = (
#                     transcript
#                     or ""
#                 ).strip()


#                 if not transcript:
#                     raise HTTPException(
#                         status_code=422,
#                         detail=(
#                             "No speech detected. "
#                             "Please try again."
#                         ),
#                     )


#                 print(
#                     "\nTRANSCRIPT:",
#                     transcript,
#                     flush=True,
#                 )


#                 # ============================================
#                 # Qwen
#                 # ============================================
#                 #
#                 # IMPORTANT:
#                 #
#                 # DO NOT use:
#                 #
#                 # await asyncio.to_thread(
#                 #     grocery_parser.parse,
#                 #     transcript
#                 # )
#                 #
#                 # llama_cpp produced a native Bus Error while
#                 # running inside ThreadPoolExecutor.
#                 #
#                 # The queue already guarantees that only one
#                 # request enters Qwen at a time.
#                 # ============================================

#                 print(
#                     "\nStarting Qwen parser...",
#                     flush=True,
#                 )

#                 parsed_result = grocery_parser.parse(
#                     transcript
#                 )


#                 print(
#                     "Qwen parsing completed.",
#                     flush=True,
#                 )


#         except AIQueueFullError:

#             raise HTTPException(
#                 status_code=503,
#                 detail=(
#                     "Voice search is currently busy. "
#                     "Please try again shortly."
#                 ),
#             )


#         # ----------------------------------------------------
#         # 5. Validate parser result
#         # ----------------------------------------------------

#         if not isinstance(
#             parsed_result,
#             dict,
#         ):
#             raise RuntimeError(
#                 "Qwen parser returned an invalid result"
#             )


#         items = parsed_result.get(
#             "items"
#         )


#         if not isinstance(
#             items,
#             list,
#         ):
#             raise RuntimeError(
#                 "Qwen parser did not return an items list"
#             )


#         # ----------------------------------------------------
#         # 6. Return result
#         # ----------------------------------------------------

#         result = {
#             "status": "success",
#             "transcript": transcript,
#             "items": items,
#         }


#         print(
#             "\nVOICE SEARCH SUCCESS:",
#             result,
#             flush=True,
#         )


#         return result


#     # ========================================================
#     # FastAPI / validation errors
#     # ========================================================

#     except HTTPException:
#         raise


#     # ========================================================
#     # Normal Python errors
#     # ========================================================

#     except Exception as error:

#         print(
#             "\nVOICE SEARCH ERROR:",
#             repr(error),
#             flush=True,
#         )

#         traceback.print_exc()

#         raise HTTPException(
#             status_code=500,
#             detail=str(error),
#         )


#     # ========================================================
#     # Cleanup temporary audio
#     # ========================================================

#     finally:

#         try:
#             await audio.close()
#         except Exception:
#             pass


#         if (
#             input_path
#             and os.path.exists(input_path)
#         ):
#             try:
#                 os.remove(input_path)
#             except Exception:
#                 pass


#         if (
#             wav_path
#             and os.path.exists(wav_path)
#         ):
#             try:
#                 os.remove(wav_path)
#             except Exception:
#                 pass


# # ============================================================
# # Queue Status
# # ============================================================

# @app.get("/queue-status")
# async def queue_status():

#     return await ai_queue.status()












from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)

from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

import asyncio
import contextlib
import hmac
import os
import subprocess
import tempfile
import traceback


from speech_service import speech_service
from grocery_parser import grocery_parser

from ai_queue import (
    ai_queue,
    AIQueueFullError,
)


# ============================================================
# FastAPI
# ============================================================

app = FastAPI(
    title="Yuganchin Voice Search AI",
    version="1.0.0",
)


# ============================================================
# Configuration
# ============================================================

API_KEY_ENV_VAR = "VOICE_SEARCH_API_KEY"

# Try root .env first (Windows dev — shared with React Native app).
# Fall back to local voicesearch_ai/.env (WSL/Ubuntu — files copied here).
_root_env  = Path(__file__).parent.parent / ".env"
_local_env = Path(__file__).with_name(".env")

if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=True)
else:
    load_dotenv(dotenv_path=_local_env, override=True)

API_KEY = os.getenv(API_KEY_ENV_VAR)


if not API_KEY:
    raise RuntimeError(
        f"{API_KEY_ENV_VAR} is not set. "
        "Set it to a long random key before starting the server."
    )


MAX_AUDIO_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


ALLOWED_AUDIO_EXTENSIONS = {
    ".aac",
    ".wav",
    ".m4a",
    ".mp4",
    ".mp3",
    ".ogg",
    ".webm",
}


# ============================================================
# API Key Validation
# ============================================================

def require_api_key(
    x_api_key: Optional[str] = Header(None, alias="API-Key"),
):
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    if not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )

    return x_api_key


# ============================================================
# Voice Search Cancel Exception
# ============================================================

class VoiceSearchCancelled(Exception):

    def __init__(
        self,
        stage: str,
    ):

        self.stage = stage

        super().__init__(
            f"Voice search cancelled at: {stage}"
        )


# ============================================================
# Health
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "voice-search-ai",
        "speech_model": "IndicConformer Tamil",
        "parser_model": "Qwen3-1.7B",
    }


# ============================================================
# Client Disconnect Watcher
# ============================================================

async def watch_client_disconnect(
    request: Request,
    cancelled_event: asyncio.Event,
):
    """
    Continuously monitor whether the React Native HTTP
    request has been disconnected.

    This can run while:

    - FFmpeg is running in asyncio.to_thread()
    - request waits in ai_queue
    - IndicConformer runs in asyncio.to_thread()

    When the client disconnects, cancelled_event becomes set.
    """

    try:

        while not cancelled_event.is_set():

            disconnected = False

            try:

                disconnected = (
                    await request.is_disconnected()
                )

            except Exception:

                disconnected = False


            if disconnected:

                cancelled_event.set()

                print(
                    "\n========================================",
                    flush=True,
                )

                print(
                    "CLIENT DISCONNECTED",
                    flush=True,
                )

                print(
                    "VOICE SEARCH MARKED CANCELLED",
                    flush=True,
                )

                print(
                    "========================================\n",
                    flush=True,
                )

                return


            await asyncio.sleep(
                0.10
            )


    except asyncio.CancelledError:

        raise


# ============================================================
# Cancellation Check
# ============================================================

def check_voice_search_cancelled(
    cancelled_event: asyncio.Event,
    stage: str,
):
    """
    Stop this request before starting another expensive stage.
    """

    if cancelled_event.is_set():

        print(
            "\n========================================",
            flush=True,
        )

        print(
            "VOICE SEARCH CANCELLED BY CUSTOMER",
            flush=True,
        )

        print(
            f"STAGE: {stage}",
            flush=True,
        )

        print(
            "========================================\n",
            flush=True,
        )

        raise VoiceSearchCancelled(
            stage
        )


# ============================================================
# Allow Disconnect Watcher To Run
# ============================================================

async def refresh_cancellation_state(
    cancelled_event: asyncio.Event,
    stage: str,
):
    """
    Give the event loop a very small opportunity to process
    the HTTP disconnect before checking cancellation.

    This is especially useful immediately after a blocking
    worker-thread operation returns.
    """

    await asyncio.sleep(
        0.05
    )

    check_voice_search_cancelled(
        cancelled_event,
        stage,
    )


# ============================================================
# Convert Phone Audio -> 16 kHz Mono WAV
# ============================================================

def convert_to_16k_mono_wav(
    input_path: str,
) -> str:

    temp_file = (
        tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )
    )


    wav_path = (
        temp_file.name
    )


    temp_file.close()


    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "16000",
        "-acodec",
        "pcm_s16le",
        wav_path,
    ]


    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


    if result.returncode != 0:

        if os.path.exists(
            wav_path
        ):

            try:

                os.remove(
                    wav_path
                )

            except Exception:

                pass


        raise RuntimeError(
            "Audio conversion failed: "
            + result.stderr.strip()
        )


    if (
        not os.path.exists(
            wav_path
        )
        or
        os.path.getsize(
            wav_path
        ) == 0
    ):

        raise RuntimeError(
            "Audio conversion produced "
            "an empty WAV file"
        )


    return wav_path


# ============================================================
# Voice Search
# ============================================================

@app.post("/voice-search")
async def voice_search(
    request: Request,
    api_key: str = Depends(require_api_key),
    audio: UploadFile = File(...),
):

    input_path = None

    wav_path = None

    disconnect_task = None

    cancelled_event = (
        asyncio.Event()
    )


    try:

        # ====================================================
        # Start Disconnect Watcher
        # ====================================================

        disconnect_task = (
            asyncio.create_task(
                watch_client_disconnect(
                    request,
                    cancelled_event,
                )
            )
        )


        # ====================================================
        # 1. Validate Uploaded Audio
        # ====================================================

        original_filename = (
            audio.filename
            or "voice.mp4"
        )


        extension = (
            Path(
                original_filename
            )
            .suffix
            .lower()
        )


        if not extension:

            extension = ".mp4"


        if (
            extension
            not in
            ALLOWED_AUDIO_EXTENSIONS
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported audio format: "
                    f"{extension}"
                ),
            )


        # ====================================================
        # 2. Save Audio Temporarily
        # ====================================================

        with tempfile.NamedTemporaryFile(
            suffix=extension,
            delete=False,
        ) as temp_file:

            input_path = (
                temp_file.name
            )


            total_size = 0


            while True:

                check_voice_search_cancelled(
                    cancelled_event,
                    "audio upload",
                )


                chunk = await audio.read(
                    1024 * 1024
                )


                if not chunk:

                    break


                total_size += len(
                    chunk
                )


                if (
                    total_size
                    >
                    MAX_AUDIO_SIZE_BYTES
                ):

                    raise HTTPException(
                        status_code=413,
                        detail=(
                            "Voice recording is too large. "
                            "Maximum size is 10 MB."
                        ),
                    )


                temp_file.write(
                    chunk
                )


        # ====================================================
        # Check Cancellation
        # ====================================================

        await refresh_cancellation_state(
            cancelled_event,
            "after audio upload",
        )


        if (
            not input_path
            or
            not os.path.exists(
                input_path
            )
            or
            os.path.getsize(
                input_path
            ) == 0
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    "Empty audio recording received"
                ),
            )


        print(
            f"Audio received: "
            f"{original_filename} "
            f"({total_size} bytes)",
            flush=True,
        )


        # ====================================================
        # 3. Convert Audio
        # ====================================================

        check_voice_search_cancelled(
            cancelled_event,
            "before audio conversion",
        )


        wav_path = (
            await asyncio.to_thread(
                convert_to_16k_mono_wav,
                input_path,
            )
        )


        await refresh_cancellation_state(
            cancelled_event,
            "after audio conversion",
        )


        print(
            f"Converted WAV: "
            f"{wav_path}",
            flush=True,
        )


        # ====================================================
        # 4. AI Queue
        # ====================================================

        check_voice_search_cancelled(
            cancelled_event,
            "before AI queue",
        )


        try:

            async with ai_queue.slot():

                # ============================================
                # Customer may have closed the mic while
                # waiting in AI queue.
                # ============================================

                check_voice_search_cancelled(
                    cancelled_event,
                    "AI queue acquired",
                )


                # ============================================
                # 5. IndicConformer
                # ============================================

                print(
                    "\nStarting IndicConformer...",
                    flush=True,
                )


                transcript = (
                    await asyncio.to_thread(
                        speech_service.transcribe,
                        wav_path,
                    )
                )


                transcript = (
                    transcript
                    or ""
                ).strip()


                # ============================================
                # CRITICAL CANCELLATION CHECK
                #
                # If customer pressed Back while
                # IndicConformer was working:
                #
                # STOP NOW.
                #
                # Qwen MUST NOT start.
                # ============================================

                await refresh_cancellation_state(
                    cancelled_event,
                    "after IndicConformer",
                )


                if not transcript:

                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "No speech detected. "
                            "Please try again."
                        ),
                    )


                print(
                    "\nTRANSCRIPT:",
                    transcript,
                    flush=True,
                )


                # ============================================
                # Check Again Immediately Before Qwen
                # ============================================

                check_voice_search_cancelled(
                    cancelled_event,
                    "before Qwen",
                )


                # ============================================
                # 6. Qwen
                # ============================================
                #
                # IMPORTANT:
                #
                # DO NOT change this to:
                #
                # await asyncio.to_thread(
                #     grocery_parser.parse,
                #     transcript,
                # )
                #
                # Your llama_cpp previously caused
                # a native Bus Error inside
                # ThreadPoolExecutor.
                #
                # Keep this synchronous.
                #
                # ============================================

                print(
                    "\nStarting Qwen parser...",
                    flush=True,
                )


                parsed_result = (
                    grocery_parser.parse(
                        transcript
                    )
                )


                # ============================================
                # IMPORTANT
                #
                # Qwen is synchronous.
                #
                # If customer presses Back AFTER Qwen has
                # already started, we cannot safely kill the
                # llama_cpp native call.
                #
                # Let the call finish internally.
                #
                # Then give the disconnect watcher time to
                # run and DISCARD the old result.
                # ============================================

                await refresh_cancellation_state(
                    cancelled_event,
                    "after Qwen",
                )


                print(
                    "Qwen parsing completed.",
                    flush=True,
                )


        except AIQueueFullError:

            raise HTTPException(
                status_code=503,
                detail=(
                    "Voice search is currently busy. "
                    "Please try again shortly."
                ),
            )


        # ====================================================
        # 7. Validate Parser Result
        # ====================================================

        check_voice_search_cancelled(
            cancelled_event,
            "before result validation",
        )


        if not isinstance(
            parsed_result,
            dict,
        ):

            raise RuntimeError(
                "Qwen parser returned "
                "an invalid result"
            )


        items = (
            parsed_result.get(
                "items"
            )
        )


        if not isinstance(
            items,
            list,
        ):

            raise RuntimeError(
                "Qwen parser did not "
                "return an items list"
            )


        # ====================================================
        # Final Cancellation Check
        # ====================================================

        await refresh_cancellation_state(
            cancelled_event,
            "before sending result",
        )


        # ====================================================
        # 8. Success
        # ====================================================

        result = {
            "status": "success",
            "transcript": transcript,
            "items": items,
        }


        print(
            "\nVOICE SEARCH SUCCESS:",
            result,
            flush=True,
        )


        return result


    # ========================================================
    # Voice Search Cancelled
    # ========================================================

    except VoiceSearchCancelled as cancelled:

        print(
            "\n========================================",
            flush=True,
        )

        print(
            "VOICE SEARCH CANCELLED CLEANLY",
            flush=True,
        )

        print(
            f"STAGE: {cancelled.stage}",
            flush=True,
        )

        print(
            "OLD RESULT WILL NOT BE RETURNED",
            flush=True,
        )

        print(
            "========================================\n",
            flush=True,
        )


        # IMPORTANT:
        #
        # Return HTTP 200 instead of HTTP 499.
        #
        # This prevents React Native from treating intentional
        # cancellation as:
        #
        # Error: [object Object]
        #
        return {
            "status": "cancelled",
            "transcript": "",
            "items": [],
        }


    # ========================================================
    # FastAPI Errors
    # ========================================================

    except HTTPException:

        raise


    # ========================================================
    # Async Task Cancelled
    # ========================================================

    except asyncio.CancelledError:

        cancelled_event.set()


        print(
            "\n========================================",
            flush=True,
        )

        print(
            "FASTAPI VOICE REQUEST TASK CANCELLED",
            flush=True,
        )

        print(
            "========================================\n",
            flush=True,
        )


        raise


    # ========================================================
    # Normal Python Errors
    # ========================================================

    except Exception as error:

        print(
            "\nVOICE SEARCH ERROR:",
            repr(error),
            flush=True,
        )


        traceback.print_exc()


        raise HTTPException(
            status_code=500,
            detail=str(error),
        )


    # ========================================================
    # Cleanup
    # ========================================================

    finally:

        # ----------------------------------------------------
        # Stop disconnect watcher
        # ----------------------------------------------------

        cancelled_event.set()


        if disconnect_task is not None:

            disconnect_task.cancel()


            with contextlib.suppress(
                asyncio.CancelledError
            ):

                await disconnect_task


        # ----------------------------------------------------
        # Close uploaded audio
        # ----------------------------------------------------

        try:

            await audio.close()

        except Exception:

            pass


        # ----------------------------------------------------
        # Remove original temporary file
        # ----------------------------------------------------

        if (
            input_path
            and
            os.path.exists(
                input_path
            )
        ):
            
            try:

                os.remove(
                    input_path
                )

            except Exception:

                pass


        # ----------------------------------------------------
        # Remove converted WAV
        # ----------------------------------------------------

        if (
            wav_path
            and
            os.path.exists(
                wav_path
            )
        ):

            try:

                os.remove(
                    wav_path
                )

            except Exception:

                pass


# ============================================================
# Queue Status
# ============================================================

@app.get("/queue-status")
async def queue_status(
    api_key: str = Depends(require_api_key),
):

    return await ai_queue.status()