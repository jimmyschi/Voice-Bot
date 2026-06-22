"""
audio_pipeline.py

End-to-end real-time voice processing bridge between Twilio and our patient bot.

How it fits into the system
----------------------------
Twilio opens a WebSocket to our server and streams µ-law audio (8 kHz, 8-bit) in
20 ms chunks as it captures audio from the remote party (the Athena AI agent).
This module accepts those raw audio bytes, forwards them to Deepgram's streaming
speech-to-text API, waits for complete utterances, hands the transcribed text to
the PatientAgent LLM to generate a realistic patient reply, converts that reply
back to µ-law audio via Deepgram's TTS API, and streams the audio chunks back to
Twilio so they play on the call in real time.

Turn-taking approach
--------------------
Healthcare AI agents are always the first to speak (greeting the caller), so we
begin in a listening state.  Deepgram signals end-of-utterance via endpointing —
after 600 ms of silence it emits a final transcript.  We treat each final
transcript as one complete agent turn and queue it for processing.  While we are
sending TTS audio back to Twilio we pause forwarding inbound audio to Deepgram so
our own voice is not accidentally transcribed as the agent's speech.

Concurrency model
-----------------
`start()` spawns a background asyncio Task (_process_responses) that drains a
queue fed by Deepgram's transcript callbacks.  This decouples the high-frequency
audio-forwarding path (called ~50 times per second) from the slower LLM + TTS
path (typically 1–3 seconds per turn).  Both paths are async so the FastAPI event
loop is never blocked.

Audio format notes
------------------
Twilio Media Streams use µ-law (G.711) at 8 kHz, mono, with each WebSocket
message containing a base64-encoded chunk of 160 bytes (20 ms of audio).
Deepgram's STT API can consume µ-law directly at 8 kHz, which means we send the
bytes as-is without re-encoding.  Deepgram's TTS API is asked to produce µ-law
at 8 kHz with no container so the response body is raw µ-law bytes that can be
chunked and sent straight back to Twilio.
"""

import asyncio
import base64
import logging
import os
from typing import Optional

import httpx
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)
from fastapi import WebSocket

from bot.patient_agent import PatientAgent

logger = logging.getLogger(__name__)

CHUNK_SIZE = 160          # 160 bytes = 20 ms of µ-law 8 kHz audio; must match Twilio's chunk size
INTER_CHUNK_DELAY = 0.02  # 20 ms delay between sent chunks keeps playback at real-time speed


class AudioPipeline:
    """
    Manages the full audio round-trip for one active call.

    Attributes
    ----------
    websocket       The FastAPI WebSocket connected to Twilio's media stream.
    stream_sid      Twilio stream identifier — required in every outbound message.
    agent           The PatientAgent instance that owns the conversation state for
                    this call (conversation history, transcript, end-call flag).
    _dg_connection  Live Deepgram WebSocket connection for streaming STT.
    _response_queue asyncio.Queue that the Deepgram callback pushes final
                    transcript strings into and _process_responses drains.
    _bot_speaking   True while TTS audio is being sent to Twilio.  Used to pause
                    forwarding inbound audio to Deepgram so we don't accidentally
                    transcribe our own voice as the agent's speech.
    """

    def __init__(self, websocket: WebSocket, stream_sid: str, agent: PatientAgent) -> None:
        self.websocket = websocket
        self.stream_sid = stream_sid
        self.agent = agent
        self._dg_connection = None
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._processor_task: Optional[asyncio.Task] = None
        self._bot_speaking = False

    async def start(self) -> None:
        """Open the Deepgram streaming connection and launch the response processor."""
        self._dg_connection = await self._init_deepgram()
        self._processor_task = asyncio.create_task(self._process_responses())

    async def stop(self) -> None:
        """Gracefully shut down the processor task and close the Deepgram connection."""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        if self._dg_connection:
            try:
                await self._dg_connection.finish()
            except Exception:
                pass

    async def process_audio(self, audio_data: bytes) -> None:
        """
        Forward one µ-law audio chunk from Twilio to the Deepgram streaming API.

        We skip forwarding when the bot is currently speaking to avoid feeding our
        own TTS output into the transcription pipeline.  Twilio only sends the
        remote party's audio on the inbound track, but there can be acoustic
        bleed-through if the far end doesn't mute properly.
        """
        if self._dg_connection and not self._bot_speaking:
            try:
                await self._dg_connection.send(audio_data)
            except Exception as exc:
                logger.warning(f"Deepgram send error: {exc}")

    async def _init_deepgram(self):
        """
        Open an authenticated Deepgram WebSocket and register the transcript callback.

        We configure the connection for µ-law at 8 kHz to match Twilio's format
        exactly — no transcoding needed.  `endpointing=600` tells Deepgram to emit
        a final transcript after 600 ms of silence, which gives the agent enough
        time to finish a sentence before we respond.  `interim_results=False`
        suppresses partial transcripts so our queue only receives stable final
        utterances.
        """
        api_key = os.environ["DEEPGRAM_API_KEY"]
        config = DeepgramClientOptions(options={"keepalive": "true"})
        client = DeepgramClient(api_key, config)
        conn = client.listen.asyncwebsocket.v("1")

        async def _on_transcript(_, result, **__):
            # Deepgram fires this callback for every transcript event; we only act
            # on final results that contain non-empty text.
            try:
                transcript = result.channel.alternatives[0].transcript
                if result.is_final and transcript.strip():
                    await self._response_queue.put(transcript)
            except Exception as exc:
                logger.warning(f"Transcript handler error: {exc}")

        conn.on(LiveTranscriptionEvents.Transcript, _on_transcript)

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            encoding="mulaw",
            channels=1,
            sample_rate=8000,
            endpointing=600,
            interim_results=False,
        )

        started = await conn.start(options)
        if not started:
            raise RuntimeError("Failed to start Deepgram connection")

        return conn

    async def _process_responses(self) -> None:
        """
        Drain the transcript queue one utterance at a time.

        Each item in the queue is a string containing what the Athena agent said.
        We pass it to the PatientAgent to generate a reply, then speak that reply
        aloud.  If the agent signals that the conversation goal has been met (or
        the max-turn limit is hit) we hang up.

        Running this in a dedicated task means audio forwarding is never delayed
        by LLM or TTS latency — they operate on separate coroutine "threads".
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
                logger.info("Patient agent signaled end of call — hanging up.")
                await self._request_hang_up()
                break

    async def _tts(self, text: str) -> bytes:
        """
        Convert text to raw µ-law audio using Deepgram's Aura TTS REST API.

        We request `encoding=mulaw`, `sample_rate=8000`, and `container=none`
        so the response body is a bare byte stream of µ-law samples — exactly
        the format Twilio's media stream expects, with no WAV/OGG header overhead
        to strip.  This lets us pipe the response bytes directly into _speak()
        without any audio conversion step.
        """
        api_key = os.environ["DEEPGRAM_API_KEY"]
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/speak",
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
        Synthesize speech for the given text and stream the audio back to Twilio.

        Audio is sent in 160-byte chunks with a 20 ms sleep between each chunk.
        This pacing mirrors Twilio's own inbound audio rate and prevents buffer
        overruns on the Twilio side.  The _bot_speaking flag is raised for the
        entire duration so that the audio forwarding path pauses during playback.
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

        We can't issue a Twilio REST API call from inside the pipeline directly
        (it doesn't hold a reference to the Twilio client), so we push a sentinel
        onto the queue.  The server's media-stream handler watches for this
        sentinel and issues the REST termination request.
        """
        await self._response_queue.put(_HANG_UP_SENTINEL)


# Sentinel used to propagate a hang-up request from _process_responses back to
# the WebSocket handler in server.py without raising an exception.
_HANG_UP_SENTINEL = object()
