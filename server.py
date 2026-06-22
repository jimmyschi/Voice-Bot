"""
server.py

FastAPI application that handles all inbound requests from Twilio during a call.

Endpoints
---------
POST /twiml
    Called by Twilio when the outbound call is answered.  Returns TwiML XML
    that instructs Twilio to open a WebSocket media stream back to this server.
    The <Connect><Stream> verb is what triggers the /media-stream WebSocket
    upgrade.  Without it the call would connect but there would be no audio
    path to our bot.

WS /media-stream
    Twilio sends µ-law 8 kHz audio frames here in real time.  We route each
    frame to the AudioPipeline for STT processing, and send synthesized
    patient-voice audio back on the same socket.

POST /call-status
    Twilio lifecycle callback (completed, failed, no-answer, busy, canceled).
    When a call ends we save the transcript to disk and clean up in-memory
    session state.

POST /recording-status
    Fired when Twilio finishes encoding the dual-channel recording.  The POST
    body contains the recording URL; we download the MP3 and store it in the
    recordings/ directory alongside the transcript.

Session state
-------------
active_sessions maps call_sid → session dict.  The dict is created in the
/twiml handler (where we have the call SID from Twilio's POST body) and
populated with a running transcript reference once the WebSocket connect
event arrives with the stream SID.  The /call-status and /recording-status
handlers look up sessions by call SID to finalise and persist data.

Concurrency
-----------
FastAPI runs on a single-thread asyncio event loop (uvicorn default).  All I/O
in this file is async so the event loop is never blocked.  AudioPipeline
internally spawns one asyncio Task per call to process LLM+TTS responses
concurrently with the audio-forwarding hot path.
"""

import base64
import json
import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from bot.audio_pipeline import AudioPipeline, _HANG_UP_SENTINEL
from bot.call_manager import CallManager
from bot.patient_agent import PatientAgent
from bot.scenarios import get_scenario_by_id
from utils.transcript_manager import TranscriptManager

logger = logging.getLogger(__name__)

app = FastAPI(title="PGAI Voice Bot")

# Populated by main.py after ngrok/server start; used by /twiml to set the
# WebSocket URL host header fallback.
_call_manager: Optional[CallManager] = None

# call_sid → {scenario, agent, pipeline, transcript}
active_sessions: dict[str, dict] = {}

# call_sid → scenario_id, set by main.py before each call so that /twiml can
# look up the right scenario when Twilio POSTs to it.
pending_scenarios: dict[str, str] = {}


def set_call_manager(cm: CallManager) -> None:
    global _call_manager
    _call_manager = cm


@app.post("/twiml")
async def twiml_handler(request: Request) -> Response:
    """
    Return TwiML that wires this call into our real-time media stream.

    Twilio POSTs form data including CallSid when it fetches the TwiML URL.
    We build a response that opens a WebSocket stream back to /media-stream on
    this same server.  The wss:// URL uses the request's Host header so it works
    with any tunnel URL (ngrok, Render, etc.) without configuration.

    The streamSid/callSid are passed as custom parameters so the WebSocket
    handler can correlate the stream with the call and look up the correct
    patient scenario.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    host = request.headers.get("host", "")

    response = VoiceResponse()
    connect = Connect()
    stream = Stream(url=f"wss://{host}/media-stream")
    stream.parameter(name="callSid", value=call_sid)
    connect.append(stream)
    response.append(connect)

    logger.info(f"TwiML served for call {call_sid}")
    return Response(content=str(response), media_type="application/xml")


@app.post("/call-status")
async def call_status_handler(request: Request) -> Response:
    """
    Handle Twilio call lifecycle callbacks.

    When a call reaches a terminal state we save the transcript to disk and
    remove the session from memory.  The recording download happens separately
    in /recording-status because the recording is not always available at the
    same moment the call ends.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status = form.get("CallStatus", "")
    logger.info(f"Call {call_sid} status → {status}")

    terminal_statuses = {"completed", "failed", "no-answer", "busy", "canceled"}
    if status in terminal_statuses and call_sid in active_sessions:
        session = active_sessions.pop(call_sid, {})
        agent: Optional[PatientAgent] = session.get("agent")
        scenario_id: str = session.get("scenario_id", "unknown")
        if agent and agent.transcript:
            await TranscriptManager.save(call_sid, agent.transcript, scenario_id)

        if _call_manager:
            _call_manager.mark_completed(call_sid)

    return Response(status_code=200)


@app.post("/recording-status")
async def recording_status_handler(request: Request) -> Response:
    """
    Receive the Twilio recording URL and download the MP3 to recordings/.

    Twilio fires this after it finishes encoding the dual-channel recording.
    We download immediately so the file is available locally before the run
    completes.  The filename mirrors the transcript filename so they can be
    paired by call SID.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    recording_url = form.get("RecordingUrl", "")
    recording_status = form.get("RecordingStatus", "")

    if recording_status == "completed" and recording_url and _call_manager:
        dest = os.path.join("recordings", f"{call_sid}.mp3")
        os.makedirs("recordings", exist_ok=True)
        try:
            _call_manager.download_recording(recording_url, dest)
        except Exception as exc:
            logger.error(f"Recording download failed for {call_sid}: {exc}")

    return Response(status_code=200)


@app.websocket("/media-stream")
async def media_stream_handler(websocket: WebSocket) -> None:
    """
    Handle the Twilio Media Stream WebSocket for one call.

    Message protocol (Twilio → server)
    ------------------------------------
    connected   Confirmation that the WebSocket handshake succeeded.
    start       Contains stream SID, call SID, and custom parameters.  This is
                where we look up the scenario and initialise AudioPipeline.
    media       Contains a base64-encoded µ-law audio chunk from the agent.
    stop        The stream has ended (call hung up or TwiML exhausted).

    Message protocol (server → Twilio)
    ------------------------------------
    media       Base64-encoded µ-law audio chunk to play to the caller.
    clear       Discard Twilio's playback buffer (used for barge-in).

    The AudioPipeline owns the STT ↔ LLM ↔ TTS loop.  When its internal
    _process_responses task puts _HANG_UP_SENTINEL in the queue, the pipeline
    signals end-of-call.  We detect this by inspecting agent.should_end_call
    after each respond() cycle and terminate the Twilio call via REST.
    """
    await websocket.accept()

    stream_sid: Optional[str] = None
    call_sid: Optional[str] = None
    pipeline: Optional[AudioPipeline] = None
    agent: Optional[PatientAgent] = None

    try:
        async for raw in websocket.iter_text():
            msg = json.loads(raw)
            event = msg.get("event")

            if event == "connected":
                logger.info("Media stream WebSocket connected")

            elif event == "start":
                stream_sid = msg["start"]["streamSid"]
                call_sid = msg["start"]["callSid"]
                custom = msg["start"].get("customParameters", {})

                # Recover scenario_id from pending_scenarios (set by main.py)
                scenario_id = pending_scenarios.pop(call_sid, None) or custom.get("scenarioId", "simple_scheduling")
                scenario = get_scenario_by_id(scenario_id)

                if scenario is None:
                    logger.error(f"Unknown scenario '{scenario_id}' for call {call_sid}")
                    break

                agent = PatientAgent(scenario)
                pipeline = AudioPipeline(
                    websocket=websocket,
                    stream_sid=stream_sid,
                    agent=agent,
                )
                await pipeline.start()

                active_sessions[call_sid] = {
                    "stream_sid": stream_sid,
                    "scenario_id": scenario_id,
                    "agent": agent,
                    "pipeline": pipeline,
                }
                logger.info(f"Stream {stream_sid} started for call {call_sid} — scenario: {scenario_id}")

            elif event == "media":
                if pipeline:
                    audio = base64.b64decode(msg["media"]["payload"])
                    await pipeline.process_audio(audio)

                    # Check for hang-up signal without consuming the queue
                    if agent and agent.should_end_call and _call_manager and call_sid:
                        _call_manager.terminate_call(call_sid)

            elif event == "stop":
                logger.info(f"Stream {stream_sid} stopped")
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for stream {stream_sid}")
    except Exception as exc:
        logger.error(f"Unhandled error in media stream handler: {exc}", exc_info=True)
    finally:
        if pipeline:
            await pipeline.stop()


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")
