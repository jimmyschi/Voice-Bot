"""
transcript_manager.py

Persists call transcripts to disk in two formats:

1. JSON  (.json) — machine-readable, includes per-turn timestamps; used by
   the bug analyzer and any downstream tooling.

2. Text  (.txt)  — human-readable formatted transcript; included in the
   GitHub submission so reviewers can read calls without running the code.

Naming convention
-----------------
Files are written to the `transcripts/` directory and named
`<call_sid>.json` / `<call_sid>.txt`.  The call SID (CA...) is unique per
call so there is never a collision even when running many scenarios in the
same session.
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional

from bot.scenarios import get_scenario_by_id

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = "transcripts"


class TranscriptManager:

    @staticmethod
    async def save(
        call_sid: str,
        transcript: list[dict],
        scenario_id: str,
    ) -> tuple[str, str]:
        """
        Write transcript to disk in JSON and plain-text formats.

        Parameters
        ----------
        call_sid     Twilio call SID (used as filename base).
        transcript   List of dicts with keys: speaker, text, timestamp.
        scenario_id  Scenario ID string used to look up the scenario object.

        Returns
        -------
        Tuple of (json_path, txt_path).
        """
        os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

        scenario = get_scenario_by_id(scenario_id)
        scenario_name = scenario.name if scenario else scenario_id
        patient_name = scenario.patient_name if scenario else "Unknown"

        json_path = os.path.join(TRANSCRIPTS_DIR, f"{call_sid}.json")
        txt_path = os.path.join(TRANSCRIPTS_DIR, f"{call_sid}.txt")

        payload = {
            "call_sid": call_sid,
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "patient_name": patient_name,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "turns": transcript,
        }

        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

        with open(txt_path, "w", encoding="utf-8") as fh:
            fh.write(TranscriptManager._format_text(payload))

        logger.info(f"Transcript saved: {txt_path}")
        return json_path, txt_path

    @staticmethod
    def _format_text(payload: dict) -> str:
        """Render a human-readable transcript from the payload dict."""
        lines = [
            "CALL TRANSCRIPT",
            "=" * 60,
            f"Call ID  : {payload['call_sid']}",
            f"Date     : {payload['recorded_at']}",
            f"Scenario : {payload['scenario_name']}",
            f"Patient  : {payload['patient_name']}",
            "=" * 60,
            "",
        ]

        start_ts: Optional[float] = None
        for turn in payload.get("turns", []):
            ts = turn.get("timestamp", 0)
            if start_ts is None:
                start_ts = ts
            elapsed = ts - start_ts
            mm = int(elapsed) // 60
            ss = int(elapsed) % 60
            speaker = turn["speaker"].upper().ljust(8)
            lines.append(f"[{mm:02d}:{ss:02d}] {speaker} {turn['text']}")

        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def load(call_sid: str) -> Optional[dict]:
        """Load a previously saved transcript JSON by call SID."""
        path = os.path.join(TRANSCRIPTS_DIR, f"{call_sid}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def list_all() -> list[str]:
        """Return all call SIDs that have saved transcripts."""
        if not os.path.isdir(TRANSCRIPTS_DIR):
            return []
        return [
            f[:-5]  # strip .json
            for f in os.listdir(TRANSCRIPTS_DIR)
            if f.endswith(".json")
        ]
