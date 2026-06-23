"""
audio_pipeline.py

End-to-end real-time voice processing bridge between Twilio and our patient bot.

How it fits into the system
----------------------------
Twilio opens a WebSocket to our server and streams µ-law audio (8 kHz, 8-bit) in
20 ms chunks as it captures audio from the remote party (the Athena AI agent).
This module accepts those raw audio bytes, forwards them to Deepgram's streaming
speech-to-text WebSocket, waits for complete utterances, hands the transcribed
text to the PatientAgent LLM to generate a realistic patient reply, converts that
reply back to µ-law audio via Deepgram's TTS REST API, and streams the audio
chunks back to Twilio so they play on the call in real time.

Why we talk to Deepgram directly instead of using their SDK
------------------------------------------------------------
Deepgram SDK v7 (the version pip resolves to by default) is an auto-generated
client from their OpenAPI spec and no longer exposes the streaming WebSocket
interface.  Rather than pin to an older SDK version, we connect to Deepgram's
WebSocket API directly using the `websockets` library.  The protocol is simple:
send raw audio bytes, receive JSON transcript messages.  This makes the code
independent of SDK releases and easy to understand.

Turn-taking approach
--------------------
Healthcare AI agents always speak first (greeting the caller), so we begin in a
listening state.  Deepgram's endpointing emits a final transcript after 600 ms
of silence — we treat each one as a complete agent turn.  While we are sending
TTS audio back to Twilio we pause forwarding inbound audio to Deepgram so our
own synthesised voice is not transcribed as the agent's speech.

Concurrency model
-----------------
`start()` spawns a background asyncio Task (_process_responses) that drains a
queue fed by the Deepgram listener Task (_listen_deepgram).  The high-frequency
audio-forwarding path (called ~50 times/second) never awaits anything slow; it
just drops bytes into the Deepgram WebSocket send buffer.

Audio format notes
------------------
Twilio Media Streams use µ-law (G.711) at 8 kHz, mono, with each WebSocket
message containing a base64-encoded chunk of 160 bytes (20 ms of audio).
Deepgram's streaming API accepts µ-law at 8 kHz directly, so we forward bytes
as-is.  The TTS REST endpoint is asked to produce µ-law at 8 kHz with no
container header, giving us raw µ-law bytes that chunk straight back to Twilio.
"""

import asyncio
import base64
import json
import logging
import os
from typing import Optional

import httpx
import websockets
from fastapi import WebSocket

from bot.patient_agent import PatientAgent

logger = logging.getLogger(__name__)

DEEPGRAM_STT_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=mulaw"
    "&sample_rate=8000"
    "&model=nova-2"
    "&language=en-US"
    "&smart_format=true"
    "&endpointing=600"
    "&interim_results=false"
)
DEEPGRAM_TTS_URL = "https://api.deepgram.com/v1/speak"

CHUNK_SIZE = 160          # 160 bytes = 20 ms of µ-law 8 kHz audio
INTER_CHUNK_DELAY = 0.02  # 20 ms delay keeps playback at real-time speed


class AudioPipeline:
    """
    Manages the full audio round-trip for one active call.

    Attributes
    ----------
    websocket       The FastAPI WebSocket connected to Twilio's media stream.
    stream_sid      Twilio stream identifier — required in every outbound message.
    agent           The PatientAgent instance owning conversation state for this
                    call (history, transcript, end-call flag).
    _dg_ws          The raw `websockets` connection to Deepgram's streaming STT.
    _response_queue asyncio.Queue that the Deepgram listener pushes final
                    transcript strings into and _process_responses drains.
    _bot_speaking   True while TTS audio is being sent to Twilio.  Pauses inbound
                    audio forwarding so we don't transcribe our own voice.
    """

    def __init__(self, websocket: WebSocket, stream_sid: str, agent: PatientAgent) -> None:
        self.websocket = websocket
        self.stream_sid = stream_sid
        self.agent = agent
        self._dg_ws = None
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._listener_task: Optional[asyncio.Task] = None
        self._processor_task: Optional[asyncio.Task] = None
        self._bot_speaking = False

    async def start(self) -> None:
        """Open the Deepgram WebSocket and launch the listener and response-processor tasks."""
        api_key = os.environ["DEEPGRAM_API_KEY"]
        self._dg_ws = await websockets.connect(
            DEEPGRAM_STT_URL,
            additional_headers={"Authorization": f"Token {api_key}"},
        )
        self._listener_task = asyncio.create_task(self._listen_deepgram())
        self._processor_task = asyncio.create_task(self._process_responses())

    async def stop(self) -> None:
        """Gracefully cancel background tasks and close the Deepgram WebSocket."""
        for task in (self._listener_task, self._processor_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._dg_ws:
            try:
                await self._dg_ws.close()
            except Exception:
                pass

    async def process_audio(self, audio_data: bytes) -> None:
        """
        Forward one µ-law audio chunk from Twilio to Deepgram.

        Skips forwarding while the bot is speaking to prevent our TTS audio
        from being transcribed back as the agent's speech.
        """
        if self._dg_ws and not self._bot_speaking:
            try:
                await self._dg_ws.send(audio_data)
            except Exception as exc:
                logger.warning(f"Deepgram audio send error: {exc}")

    async def _listen_deepgram(self) -> None:
        """
        Continuously read JSON messages from Deepgram and enqueue final transcripts.

        Deepgram emits transcript messages with type "Results".  We only act on
        messages where `is_final=True` and the transcript string is non-empty —
        these represent a complete, stable utterance after the 600 ms silence
        endpointing window has closed.
        """
        try:
            async for raw in self._dg_ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if msg.get("type") != "Results":
                    continue

                is_final = msg.get("is_final", False)
                try:
                    transcript = msg["channel"]["alternatives"][0]["transcript"]
                except (KeyError, IndexError):
                    continue

                if is_final and transcript.strip():
                    await self._response_queue.put(transcript)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Deepgram listener error: {exc}")

    async def _process_responses(self) -> None:
        """
        Drain the transcript queue one utterance at a time.

        Each item is the agent's complete spoken turn.  We pass it to
        PatientAgent to generate a reply, speak that reply aloud, then check
        whether the agent has signalled end-of-call.  Running this in a
        dedicated task means audio forwarding is never delayed by LLM or TTS
        latency — they operate on separate coroutine "threads".
        """
        while True:
            try:
                agent_text = await self._response_queue.get()
            except asyncio.CancelledError:
                break

            logger.info(f"[AGENT]   {agent_text}")

            patient_text = await self.agent.respond(agent_text)

            if patient_text:
                logger.info(f"[PATIENT] {patient_text}")
                await self._speak(patient_text)

            if self.agent.should_end_call:
                logger.info("Patient agent signalled end of call — hanging up.")
                await self._request_hang_up()
                break

    async def _tts(self, text: str) -> bytes:
        """
        Convert text to raw µ-law audio using Deepgram's Aura TTS REST API.

        We request `encoding=mulaw`, `sample_rate=8000`, and `container=none`
        so the response body is bare µ-law samples — no WAV/OGG header to strip.
        This lets us pipe the bytes directly into _speak() without any conversion.
        """
        api_key = os.environ["DEEPGRAM_API_KEY"]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                DEEPGRAM_TTS_URL,
                params={
                    "model": "aura-asteria-en",
                    "encoding": "mulaw",
                    "sample_rate": "8000",
                    "container": "none",
                },
                headers={
                    "Authorization": f"Token {api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )
            resp.raise_for_status()
            return resp.content

    async def _speak(self, text: str) -> None:
        """
        Synthesise speech for the given text and stream the audio back to Twilio.

        Audio is sent in 160-byte chunks with a 20 ms sleep between each chunk.
        This pacing mirrors Twilio's own inbound audio rate and prevents buffer
        overruns.  The _bot_speaking flag is raised for the entire duration so
        the audio-forwarding path pauses during playback.
        """
        try:
            audio = await self._tts(text)
        except Exception as exc:
            logger.error(f"TTS synthesis failed: {exc}")
            return

        self._bot_speaking = True
        try:
            for i in range(0, len(audio), CHUNK_SIZE):
                chunk = audio[i : i + CHUNK_SIZE]
                await self.websocket.send_json({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": base64.b64encode(chunk).decode()},
                })
                await asyncio.sleep(INTER_CHUNK_DELAY)
        except Exception as exc:
            logger.error(f"Audio stream send error: {exc}")
        finally:
            self._bot_speaking = False

    async def _request_hang_up(self) -> None:
        """
        Signal the outer server layer to terminate the Twilio call via REST.

        We push a sentinel onto the queue.  The server's media-stream handler
        watches for agent.should_end_call after each audio event and issues
        the REST termination request itself.
        """
        await self._response_queue.put(_HANG_UP_SENTINEL)


# Sentinel used to propagate a hang-up request back to the WebSocket handler.
_HANG_UP_SENTINEL = object()
