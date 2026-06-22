"""
call_manager.py

Wraps the Twilio REST API for outbound call creation and call termination.

Responsibilities
----------------
- Initiate an outbound call to the target number, pointing Twilio's TwiML
  webhook at our FastAPI server so the call connects to the media stream.
- Enable call recording so that a full-fidelity MP3 of both sides is
  available for download after the call ends.
- Terminate an active call early when the PatientAgent signals end-of-call
  (rather than waiting for the natural PSTN disconnect).
- Track which call SIDs are currently active so the main loop can poll for
  completion without blocking.

Twilio call lifecycle
---------------------
1. create_call()  → Twilio dials the number; call SID is returned immediately.
2. Twilio answers → fetches TwiML from POST /twiml on our server.
3. TwiML contains a <Connect><Stream> element that opens a WebSocket to /media-stream.
4. Media stream runs until the PatientAgent ends the call or the remote hangs up.
5. Twilio POSTs to /call-status with CallStatus=completed when the call ends.
6. Twilio POSTs to /recording-status with the recording URL when encoding finishes.
"""

import logging
import os
from typing import Optional

from twilio.rest import Client

logger = logging.getLogger(__name__)


class CallManager:
    """Thin wrapper around the Twilio REST client for outbound call management."""

    def __init__(self, webhook_url: str) -> None:
        """
        Parameters
        ----------
        webhook_url
            Publicly reachable HTTPS base URL for our FastAPI server (e.g. the
            ngrok tunnel URL).  Twilio will POST TwiML requests and status
            callbacks to paths under this URL.
        """
        self.webhook_url = webhook_url.rstrip("/")
        self._client = Client(
            os.environ["TWILIO_ACCOUNT_SID"],
            os.environ["TWILIO_AUTH_TOKEN"],
        )
        self._active_calls: set[str] = set()

    def create_call(self, to: str, scenario_label: str) -> str:
        """
        Dial `to` and return the Twilio call SID.

        The call is configured with:
        - `url`                        → POST /twiml returns the <Connect><Stream> TwiML.
        - `status_callback`            → POST /call-status receives lifecycle events.
        - `record=True`                → Twilio records both legs and mixes them into one MP3.
        - `recording_status_callback`  → POST /recording-status delivers the recording URL.

        Parameters
        ----------
        to             Destination E.164 phone number.
        scenario_label Human-readable label attached to the call SID in our
                       active set — not sent to Twilio, used only for logging.
        """
        call = self._client.calls.create(
            to=to,
            from_=os.environ["TWILIO_PHONE_NUMBER"],
            url=f"{self.webhook_url}/twiml",
            status_callback=f"{self.webhook_url}/call-status",
            status_callback_event=["completed", "failed", "no-answer", "busy"],
            record=True,
            recording_status_callback=f"{self.webhook_url}/recording-status",
            recording_status_callback_method="POST",
        )

        self._active_calls.add(call.sid)
        logger.info(f"Initiated call {call.sid} → {to}  [{scenario_label}]")
        return call.sid

    def terminate_call(self, call_sid: str) -> None:
        """
        Hang up an active call by updating its status to 'completed' via REST.

        Twilio accepts a status update of 'completed' on in-progress calls, which
        causes an immediate disconnect.  This is the correct way to end a call
        programmatically when we don't want to wait for the remote to hang up.
        """
        try:
            self._client.calls(call_sid).update(status="completed")
            logger.info(f"Terminated call {call_sid}")
        except Exception as exc:
            logger.warning(f"Failed to terminate call {call_sid}: {exc}")
        finally:
            self._active_calls.discard(call_sid)

    def download_recording(self, recording_url: str, dest_path: str) -> None:
        """
        Download a completed Twilio recording to `dest_path` as an MP3.

        Twilio recording URLs require HTTP Basic Auth with account SID and auth
        token.  The URL already points to the MP3 resource; we append `.mp3`
        only if it isn't already present in the URL.
        """
        import requests  # local import keeps top-level imports minimal

        mp3_url = recording_url if recording_url.endswith(".mp3") else recording_url + ".mp3"
        response = requests.get(
            mp3_url,
            auth=(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]),
            timeout=60,
        )
        response.raise_for_status()

        with open(dest_path, "wb") as fh:
            fh.write(response.content)

        logger.info(f"Recording saved to {dest_path}")

    def is_active(self, call_sid: str) -> bool:
        return call_sid in self._active_calls

    def mark_completed(self, call_sid: str) -> None:
        self._active_calls.discard(call_sid)

    @property
    def active_call_count(self) -> int:
        return len(self._active_calls)
