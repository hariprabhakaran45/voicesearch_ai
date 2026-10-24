# from fastapi import (
#     Depends,
#     FastAPI,
#     File,
#     Header,
#     HTTPException,
#     Request,
#     UploadFile,
# )

# from dotenv import load_dotenv
# from pathlib import Path
# from typing import Optional

# import asyncio
# import contextlib
# import hmac
# import os
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

# API_KEY_ENV_VAR = "VOICE_SEARCH_API_KEY"

# # Try root .env first (Windows dev — shared with React Native app).
# # Fall back to local voicesearch_ai/.env (WSL/Ubuntu — files copied here).
# _root_env  = Path(__file__).parent.parent / ".env"
# _local_env = Path(__file__).with_name(".env")

# if _root_env.exists():
#     load_dotenv(dotenv_path=_root_env, override=True)
# else:
#     load_dotenv(dotenv_path=_local_env, override=True)

# API_KEY = os.getenv(API_KEY_ENV_VAR)


# if not API_KEY:
#     raise RuntimeError(
#         f"{API_KEY_ENV_VAR} is not set. "
#         "Set it to a long random key before starting the server."
#     )


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
# # API Key Validation
# # ============================================================

# def require_api_key(
#     x_api_key: Optional[str] = Header(None, alias="API-Key"),
# ):
#     if not x_api_key:
#         raise HTTPException(
#             status_code=401,
#             detail="Invalid API key",
#         )

#     if not hmac.compare_digest(x_api_key, API_KEY):
#         raise HTTPException(
#             status_code=401,
#             detail="Invalid API key",
#         )

#     return x_api_key


# # ============================================================
# # Voice Search Cancel Exception
# # ============================================================

# class VoiceSearchCancelled(Exception):

#     def __init__(
#         self,
#         stage: str,
#     ):

#         self.stage = stage

#         super().__init__(
#             f"Voice search cancelled at: {stage}"
#         )


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
# # Client Disconnect Watcher
# # ============================================================

# async def watch_client_disconnect(
#     request: Request,
#     cancelled_event: asyncio.Event,
# ):
#     """
#     Continuously monitor whether the React Native HTTP
#     request has been disconnected.

#     This can run while:

#     - FFmpeg is running in asyncio.to_thread()
#     - request waits in ai_queue
#     - IndicConformer runs in asyncio.to_thread()

#     When the client disconnects, cancelled_event becomes set.
#     """

#     try:

#         while not cancelled_event.is_set():

#             disconnected = False

#             try:

#                 disconnected = (
#                     await request.is_disconnected()
#                 )

#             except Exception:

#                 disconnected = False


#             if disconnected:

#                 cancelled_event.set()

#                 print(
#                     "\n========================================",
#                     flush=True,
#                 )

#                 print(
#                     "CLIENT DISCONNECTED",
#                     flush=True,
#                 )

#                 print(
#                     "VOICE SEARCH MARKED CANCELLED",
#                     flush=True,
#                 )

#                 print(
#                     "========================================\n",
#                     flush=True,
#                 )

#                 return


#             await asyncio.sleep(
#                 0.10
#             )


#     except asyncio.CancelledError:

#         raise


# # ============================================================
# # Cancellation Check
# # ============================================================

# def check_voice_search_cancelled(
#     cancelled_event: asyncio.Event,
#     stage: str,
# ):
#     """
#     Stop this request before starting another expensive stage.
#     """

#     if cancelled_event.is_set():

#         print(
#             "\n========================================",
#             flush=True,
#         )

#         print(
#             "VOICE SEARCH CANCELLED BY CUSTOMER",
#             flush=True,
#         )

#         print(
#             f"STAGE: {stage}",
#             flush=True,
#         )

#         print(
#             "========================================\n",
#             flush=True,
#         )

#         raise VoiceSearchCancelled(
#             stage
#         )


# # ============================================================
# # Allow Disconnect Watcher To Run
# # ============================================================

# async def refresh_cancellation_state(
#     cancelled_event: asyncio.Event,
#     stage: str,
# ):
#     """
#     Give the event loop a very small opportunity to process
#     the HTTP disconnect before checking cancellation.

#     This is especially useful immediately after a blocking
#     worker-thread operation returns.
#     """

#     await asyncio.sleep(
#         0.05
#     )

#     check_voice_search_cancelled(
#         cancelled_event,
#         stage,
#     )


# # ============================================================
# # Convert Phone Audio -> 16 kHz Mono WAV
# # ============================================================

# def convert_to_16k_mono_wav(
#     input_path: str,
# ) -> str:

#     temp_file = (
#         tempfile.NamedTemporaryFile(
#             suffix=".wav",
#             delete=False,
#         )
#     )


#     wav_path = (
#         temp_file.name
#     )


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

#         if os.path.exists(
#             wav_path
#         ):

#             try:

#                 os.remove(
#                     wav_path
#                 )

#             except Exception:

#                 pass


#         raise RuntimeError(
#             "Audio conversion failed: "
#             + result.stderr.strip()
#         )


#     if (
#         not os.path.exists(
#             wav_path
#         )
#         or
#         os.path.getsize(
#             wav_path
#         ) == 0
#     ):

#         raise RuntimeError(
#             "Audio conversion produced "
#             "an empty WAV file"
#         )


#     return wav_path


# # ============================================================
# # Voice Search
# # ============================================================

# @app.post("/voice-search")
# async def voice_search(
#     request: Request,
#     api_key: str = Depends(require_api_key),
#     audio: UploadFile = File(...),
# ):

#     input_path = None

#     wav_path = None

#     disconnect_task = None

#     cancelled_event = (
#         asyncio.Event()
#     )


#     try:

#         # ====================================================
#         # Start Disconnect Watcher
#         # ====================================================

#         disconnect_task = (
#             asyncio.create_task(
#                 watch_client_disconnect(
#                     request,
#                     cancelled_event,
#                 )
#             )
#         )


#         # ====================================================
#         # 1. Validate Uploaded Audio
#         # ====================================================

#         original_filename = (
#             audio.filename
#             or "voice.mp4"
#         )


#         extension = (
#             Path(
#                 original_filename
#             )
#             .suffix
#             .lower()
#         )


#         if not extension:

#             extension = ".mp4"


#         if (
#             extension
#             not in
#             ALLOWED_AUDIO_EXTENSIONS
#         ):

#             raise HTTPException(
#                 status_code=400,
#                 detail=(
#                     "Unsupported audio format: "
#                     f"{extension}"
#                 ),
#             )


#         # ====================================================
#         # 2. Save Audio Temporarily
#         # ====================================================

#         with tempfile.NamedTemporaryFile(
#             suffix=extension,
#             delete=False,
#         ) as temp_file:

#             input_path = (
#                 temp_file.name
#             )


#             total_size = 0


#             while True:

#                 check_voice_search_cancelled(
#                     cancelled_event,
#                     "audio upload",
#                 )


#                 chunk = await audio.read(
#                     1024 * 1024
#                 )


#                 if not chunk:

#                     break


#                 total_size += len(
#                     chunk
#                 )


#                 if (
#                     total_size
#                     >
#                     MAX_AUDIO_SIZE_BYTES
#                 ):

#                     raise HTTPException(
#                         status_code=413,
#                         detail=(
#                             "Voice recording is too large. "
#                             "Maximum size is 10 MB."
#                         ),
#                     )


#                 temp_file.write(
#                     chunk
#                 )


#         # ====================================================
#         # Check Cancellation
#         # ====================================================

#         await refresh_cancellation_state(
#             cancelled_event,
#             "after audio upload",
#         )


#         if (
#             not input_path
#             or
#             not os.path.exists(
#                 input_path
#             )
#             or
#             os.path.getsize(
#                 input_path
#             ) == 0
#         ):

#             raise HTTPException(
#                 status_code=400,
#                 detail=(
#                     "Empty audio recording received"
#                 ),
#             )


#         print(
#             f"Audio received: "
#             f"{original_filename} "
#             f"({total_size} bytes)",
#             flush=True,
#         )


#         # ====================================================
#         # 3. Convert Audio
#         # ====================================================

#         check_voice_search_cancelled(
#             cancelled_event,
#             "before audio conversion",
#         )


#         wav_path = (
#             await asyncio.to_thread(
#                 convert_to_16k_mono_wav,
#                 input_path,
#             )
#         )


#         await refresh_cancellation_state(
#             cancelled_event,
#             "after audio conversion",
#         )


#         print(
#             f"Converted WAV: "
#             f"{wav_path}",
#             flush=True,
#         )


#         # ====================================================
#         # 4. AI Queue
#         # ====================================================

#         check_voice_search_cancelled(
#             cancelled_event,
#             "before AI queue",
#         )


#         try:

#             async with ai_queue.slot():

#                 # ============================================
#                 # Customer may have closed the mic while
#                 # waiting in AI queue.
#                 # ============================================

#                 check_voice_search_cancelled(
#                     cancelled_event,
#                     "AI queue acquired",
#                 )


#                 # ============================================
#                 # 5. IndicConformer
#                 # ============================================

#                 print(
#                     "\nStarting IndicConformer...",
#                     flush=True,
#                 )


#                 transcript = (
#                     await asyncio.to_thread(
#                         speech_service.transcribe,
#                         wav_path,
#                     )
#                 )


#                 transcript = (
#                     transcript
#                     or ""
#                 ).strip()


#                 # ============================================
#                 # CRITICAL CANCELLATION CHECK
#                 #
#                 # If customer pressed Back while
#                 # IndicConformer was working:
#                 #
#                 # STOP NOW.
#                 #
#                 # Qwen MUST NOT start.
#                 # ============================================

#                 await refresh_cancellation_state(
#                     cancelled_event,
#                     "after IndicConformer",
#                 )


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
#                 # Check Again Immediately Before Qwen
#                 # ============================================

#                 check_voice_search_cancelled(
#                     cancelled_event,
#                     "before Qwen",
#                 )


#                 # ============================================
#                 # 6. Qwen
#                 # ============================================
#                 #
#                 # IMPORTANT:
#                 #
#                 # DO NOT change this to:
#                 #
#                 # await asyncio.to_thread(
#                 #     grocery_parser.parse,
#                 #     transcript,
#                 # )
#                 #
#                 # Your llama_cpp previously caused
#                 # a native Bus Error inside
#                 # ThreadPoolExecutor.
#                 #
#                 # Keep this synchronous.
#                 #
#                 # ============================================

#                 print(
#                     "\nStarting Qwen parser...",
#                     flush=True,
#                 )


#                 parsed_result = (
#                     grocery_parser.parse(
#                         transcript
#                     )
#                 )


#                 # ============================================
#                 # IMPORTANT
#                 #
#                 # Qwen is synchronous.
#                 #
#                 # If customer presses Back AFTER Qwen has
#                 # already started, we cannot safely kill the
#                 # llama_cpp native call.
#                 #
#                 # Let the call finish internally.
#                 #
#                 # Then give the disconnect watcher time to
#                 # run and DISCARD the old result.
#                 # ============================================

#                 await refresh_cancellation_state(
#                     cancelled_event,
#                     "after Qwen",
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


#         # ====================================================
#         # 7. Validate Parser Result
#         # ====================================================

#         check_voice_search_cancelled(
#             cancelled_event,
#             "before result validation",
#         )


#         if not isinstance(
#             parsed_result,
#             dict,
#         ):

#             raise RuntimeError(
#                 "Qwen parser returned "
#                 "an invalid result"
#             )


#         items = (
#             parsed_result.get(
#                 "items"
#             )
#         )


#         if not isinstance(
#             items,
#             list,
#         ):

#             raise RuntimeError(
#                 "Qwen parser did not "
#                 "return an items list"
#             )


#         # ====================================================
#         # Final Cancellation Check
#         # ====================================================

#         await refresh_cancellation_state(
#             cancelled_event,
#             "before sending result",
#         )


#         # ====================================================
#         # 8. Success
#         # ====================================================

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
#     # Voice Search Cancelled
#     # ========================================================

#     except VoiceSearchCancelled as cancelled:

#         print(
#             "\n========================================",
#             flush=True,
#         )

#         print(
#             "VOICE SEARCH CANCELLED CLEANLY",
#             flush=True,
#         )

#         print(
#             f"STAGE: {cancelled.stage}",
#             flush=True,
#         )

#         print(
#             "OLD RESULT WILL NOT BE RETURNED",
#             flush=True,
#         )

#         print(
#             "========================================\n",
#             flush=True,
#         )


#         # IMPORTANT:
#         #
#         # Return HTTP 200 instead of HTTP 499.
#         #
#         # This prevents React Native from treating intentional
#         # cancellation as:
#         #
#         # Error: [object Object]
#         #
#         return {
#             "status": "cancelled",
#             "transcript": "",
#             "items": [],
#         }


#     # ========================================================
#     # FastAPI Errors
#     # ========================================================

#     except HTTPException:

#         raise


#     # ========================================================
#     # Async Task Cancelled
#     # ========================================================

#     except asyncio.CancelledError:

#         cancelled_event.set()


#         print(
#             "\n========================================",
#             flush=True,
#         )

#         print(
#             "FASTAPI VOICE REQUEST TASK CANCELLED",
#             flush=True,
#         )

#         print(
#             "========================================\n",
#             flush=True,
#         )


#         raise


#     # ========================================================
#     # Normal Python Errors
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
#     # Cleanup
#     # ========================================================

#     finally:

#         # ----------------------------------------------------
#         # Stop disconnect watcher
#         # ----------------------------------------------------

#         cancelled_event.set()


#         if disconnect_task is not None:

#             disconnect_task.cancel()


#             with contextlib.suppress(
#                 asyncio.CancelledError
#             ):

#                 await disconnect_task


#         # ----------------------------------------------------
#         # Close uploaded audio
#         # ----------------------------------------------------

#         try:

#             await audio.close()

#         except Exception:

#             pass


#         # ----------------------------------------------------
#         # Remove original temporary file
#         # ----------------------------------------------------

#         if (
#             input_path
#             and
#             os.path.exists(
#                 input_path
#             )
#         ):
            
#             try:

#                 os.remove(
#                     input_path
#                 )

#             except Exception:

#                 pass


#         # ----------------------------------------------------
#         # Remove converted WAV
#         # ----------------------------------------------------

#         if (
#             wav_path
#             and
#             os.path.exists(
#                 wav_path
#             )
#         ):

#             try:

#                 os.remove(
#                     wav_path
#                 )

#             except Exception:

#                 pass


# # ============================================================
# # Queue Status
# # ============================================================

# @app.get("/queue-status")
# async def queue_status(
#     api_key: str = Depends(require_api_key),
# ):

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
import base64
import contextlib
import hmac
import json
import os
import subprocess
import tempfile
import traceback

try:
    import httpx
except ImportError:
    httpx = None


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

RUNPOD_API_KEY = (os.getenv("RUNPOD_API_KEY") or "").strip()
RUNPOD_ENDPOINT_ID = (os.getenv("RUNPOD_ENDPOINT_ID") or "").strip()
USE_RUNPOD = bool(RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID)

if USE_RUNPOD:
    print(
        f"[VoiceSearch] Mode: RUNPOD SERVERLESS (Endpoint: {RUNPOD_ENDPOINT_ID})",
        flush=True,
    )
else:
    print(
        "[VoiceSearch] Mode: LOCAL MODELS (speech_service + grocery_parser)",
        flush=True,
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
# RunPod Serverless Client
# ============================================================

async def call_runpod_serverless(
    wav_path: str,
    cancelled_event: asyncio.Event,
) -> dict:
    """
    Sends 16kHz mono WAV to the RunPod Serverless endpoint.
    Handles runsync synchronous response as well as status polling.
    Respects client cancellation.
    """
    with open(wav_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    check_voice_search_cancelled(cancelled_event, "before RunPod request")

    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/run"
    headers = {
        "Authorization": f"Bearer {RUNPOD_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "input": {
            "audio_b64": audio_b64,
            "language_id": "ta",
        }
    }

    print(
        f"\n[RunPod] Submitting voice search to endpoint {RUNPOD_ENDPOINT_ID}...",
        flush=True,
    )

    if httpx is not None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code not in (200, 201):
                raise RuntimeError(
                    f"RunPod HTTP error {resp.status_code}: {resp.text}"
                )
            data = resp.json()
    else:
        import urllib.request
        def _sync_post():
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        data = await asyncio.to_thread(_sync_post)

    check_voice_search_cancelled(cancelled_event, "after RunPod job submit")

    job_id = data.get("id")
    job_status = data.get("status")

    if not job_id:
        raise RuntimeError(f"RunPod did not return a job ID: {data}")

    print(f"[RunPod] Job ID: {job_id} (Status: {job_status})", flush=True)

    status_url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/status/{job_id}"

    # Poll status for up to 180s (handles initial cold-start image pull/model load gracefully)
    for i in range(400):
        await asyncio.sleep(1.5)
        check_voice_search_cancelled(cancelled_event, "polling RunPod")

        if httpx is not None:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(status_url, headers=headers)
                poll_data = resp.json()
        else:
            import urllib.request
            def _sync_get():
                req = urllib.request.Request(status_url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as r:
                    return json.loads(r.read().decode("utf-8"))
            poll_data = await asyncio.to_thread(_sync_get)

        status = poll_data.get("status")

        if status == "COMPLETED":
            output = poll_data.get("output", {})
            if "error" in output:
                raise RuntimeError(output["error"])
            print(
                f"[RunPod] Completed in execution time: {poll_data.get('executionTime', 'N/A')}ms",
                flush=True,
            )
            return output

        elif status in ("FAILED", "CANCELLED", "TIMED_OUT"):
            raise RuntimeError(
                f"RunPod job {status}: {poll_data.get('error', 'Unknown error')}"
            )

        if i % 5 == 0:
            print(f"[RunPod] Waiting for GPU worker... (status: {status})", flush=True)

    raise TimeoutError("RunPod voice search timed out after 600 seconds.")


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
        # 4. Speech Recognition & Grocery Parsing
        # ====================================================

        check_voice_search_cancelled(
            cancelled_event,
            "before AI inference",
        )

        if USE_RUNPOD:
            # ------------------------------------------------
            # Offloaded to RunPod Serverless GPU
            # ------------------------------------------------
            runpod_output = await call_runpod_serverless(
                wav_path,
                cancelled_event,
            )
            transcript = (runpod_output.get("transcript") or "").strip()
            parsed_result = {"items": runpod_output.get("items", [])}
        else:
            # ------------------------------------------------
            # Local Execution via ai_queue
            # ------------------------------------------------
            try:
                async with ai_queue.slot():

                    # Customer may have closed the mic while waiting
                    check_voice_search_cancelled(
                        cancelled_event,
                        "AI queue acquired",
                    )

                    # ----------------------------------------
                    # 5. IndicConformer
                    # ----------------------------------------
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

                    check_voice_search_cancelled(
                        cancelled_event,
                        "before Qwen",
                    )

                    # ----------------------------------------
                    # 6. Qwen
                    # ----------------------------------------
                    print(
                        "\nStarting Qwen parser...",
                        flush=True,
                    )

                    parsed_result = (
                        grocery_parser.parse(
                            transcript
                        )
                    )

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