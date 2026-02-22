"""
Vani Web Demo — FastAPI WebSocket server.

Bridges browser mic audio → Vani Gateway → browser playback.

Usage:
    export SARVAM_API_KEY=your-key
    cd webapp
    pip install fastapi uvicorn
    uvicorn server:app --reload --port 8000
    # Open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys

# Add parent dir to path so we can import vani
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from vani.session import SessionConfig
from vani.backends.sarvam import (
    SarvamSTTBackend,
    SarvamLLMBackend,
    SarvamTTSBackend,
)
from vani.gateway.stub import VaniGatewayStub, GatewayEvent, TurnState

app = FastAPI(title="Vani Web Demo")

# Serve static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/languages")
async def get_languages():
    return [
        {"code": "hi-IN", "name": "Hindi (हिन्दी)", "flag": "🇮🇳"},
        {"code": "te-IN", "name": "Telugu (తెలుగు)", "flag": "🇮🇳"},
        {"code": "ta-IN", "name": "Tamil (தமிழ்)", "flag": "🇮🇳"},
        {"code": "bn-IN", "name": "Bengali (বাংলা)", "flag": "🇮🇳"},
        {"code": "mr-IN", "name": "Marathi (मराठी)", "flag": "🇮🇳"},
        {"code": "kn-IN", "name": "Kannada (ಕನ್ನಡ)", "flag": "🇮🇳"},
        {"code": "ml-IN", "name": "Malayalam (മലയാളം)", "flag": "🇮🇳"},
        {"code": "gu-IN", "name": "Gujarati (ગુજરાતી)", "flag": "🇮🇳"},
        {"code": "en-IN", "name": "English (India)", "flag": "🇮🇳"},
    ]


# ── Tool implementations for demo ────────────────────────────────────────────

async def handle_tool(tool_name: str, args: dict) -> str:
    """Demo tool handler — same as CLI demo."""
    if tool_name == "enam_mandi_price":
        crop = args.get("crop", "unknown")
        mandi = args.get("mandi", "unknown")
        await asyncio.sleep(0.3)
        prices = {
            "tomato":  {"min": 800,  "max": 1200, "modal": 1000},
            "onion":   {"min": 400,  "max": 600,  "modal": 500},
            "rice":    {"min": 2200, "max": 2500, "modal": 2350},
            "wheat":   {"min": 1800, "max": 2100, "modal": 1950},
            "cotton":  {"min": 5500, "max": 6000, "modal": 5750},
            "potato":  {"min": 600,  "max": 900,  "modal": 750},
        }
        data = prices.get(crop.lower(), {"min": 500, "max": 800, "modal": 650})
        return json.dumps({
            "crop": crop, "mandi": mandi,
            "min_price_per_quintal_inr": data["min"],
            "max_price_per_quintal_inr": data["max"],
            "modal_price_per_quintal_inr": data["modal"],
            "date": "2026-02-22", "source": "eNAM (demo)",
        })

    if tool_name == "pan_validate":
        import re
        pan = args.get("pan_number", "")
        valid = bool(re.match(r"[A-Z]{5}[0-9]{4}[A-Z]$", pan))
        return json.dumps({
            "pan_number": pan,
            "is_valid_format": valid,
            "message": "Valid PAN format" if valid else "Invalid PAN format",
        })

    return json.dumps({"error": f"Tool not available: {tool_name}"})


# ── WebSocket handler ─────────────────────────────────────────────────────────

@app.websocket("/ws/audio")
async def audio_ws(websocket: WebSocket):
    await websocket.accept()

    api_key = os.environ.get("SARVAM_API_KEY", "")
    if not api_key:
        await websocket.send_json({"type": "error", "message": "SARVAM_API_KEY not set on server"})
        await websocket.close()
        return

    # Wait for config message from client
    try:
        config_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
    except Exception:
        await websocket.close()
        return

    language = config_msg.get("language", "hi-IN")

    # Build Vani pipeline
    config = SessionConfig.for_language(language, caller_id="web-demo")
    gateway = VaniGatewayStub(
        config=config,
        stt=SarvamSTTBackend(api_key=api_key),
        llm=SarvamLLMBackend(api_key=api_key),
        tts=SarvamTTSBackend(api_key=api_key),
        system_prompt=(
            "You are a helpful Indian voice assistant named Vani (वाणी). "
            "Respond concisely in the same language the user speaks. "
            "If they speak Hindi, respond in Hindi. If Telugu, respond in Telugu. "
            "Keep responses under 3 sentences."
        ),
        action_callback=handle_tool,
        max_history_turns=6,
    )

    await websocket.send_json({"type": "ready", "session_id": config.session_id[:8]})

    try:
        while True:
            # Wait for "start" signal from client
            msg = await websocket.receive_json()
            if msg.get("type") == "start_turn":
                await _handle_turn(websocket, gateway)
            elif msg.get("type") == "reset":
                gateway.reset()
                await websocket.send_json({"type": "reset_ack"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def _handle_turn(websocket: WebSocket, gateway: VaniGatewayStub):
    """Handle one voice turn: receive audio chunks, process through Vani, send back events."""

    # Audio queue: browser sends PCM chunks, we yield them to the gateway
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

    async def audio_iter():
        """Yield audio chunks from the WebSocket."""
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            yield chunk

    # Receive audio in background while processing events
    async def receive_audio():
        """Read audio messages from the WebSocket and put them in the queue."""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.receive":
                    if "bytes" in msg and msg["bytes"]:
                        await audio_queue.put(msg["bytes"])
                    elif "text" in msg:
                        data = json.loads(msg["text"])
                        if data.get("type") == "audio_chunk":
                            # Base64-encoded PCM from browser
                            pcm = base64.b64decode(data["data"])
                            await audio_queue.put(pcm)
                        elif data.get("type") == "end_audio":
                            await audio_queue.put(None)
                            return
                        elif data.get("type") == "cancel":
                            await audio_queue.put(None)
                            return
        except WebSocketDisconnect:
            await audio_queue.put(None)
        except Exception:
            await audio_queue.put(None)

    # Start receiving audio in background
    recv_task = asyncio.create_task(receive_audio())

    try:
        async for event in gateway.process_audio(audio_iter()):
            await _send_event(websocket, event)

        await websocket.send_json({"type": "turn_complete"})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        recv_task.cancel()
        try:
            await recv_task
        except asyncio.CancelledError:
            pass


async def _send_event(websocket: WebSocket, event: GatewayEvent):
    """Convert a GatewayEvent to JSON and send over WebSocket."""

    if event.turn_signal:
        await websocket.send_json({
            "type": "turn_signal",
            "state": event.turn_signal.event.value,
        })

    if event.transcript:
        t = event.transcript
        await websocket.send_json({
            "type": "transcript",
            "text": t.text,
            "is_final": t.is_final,
            "language": t.language_bcp47,
            "confidence": t.confidence,
            "dialect_tag": t.dialect_tag or None,
            "code_switch_spans": [
                {
                    "start": s.start_char,
                    "end": s.end_char,
                    "language": s.language_bcp47,
                    "confidence": s.confidence,
                }
                for s in (t.code_switch_spans or [])
            ],
        })

    if event.synthesis_chunk:
        chunk = event.synthesis_chunk
        if chunk.audio_bytes:
            # Send audio as base64 JSON (simpler than binary frames for demo)
            await websocket.send_json({
                "type": "tts_audio",
                "data": base64.b64encode(chunk.audio_bytes).decode(),
                "is_final": chunk.is_final,
                "chunk_index": chunk.chunk_index,
            })

    if event.error:
        await websocket.send_json({
            "type": "error",
            "message": event.error,
        })

    if event.llm_text:
        await websocket.send_json({
            "type": "llm_text",
            "text": event.llm_text,
        })


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
