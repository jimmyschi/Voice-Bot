"""
analysis/bug_analyzer.py

Post-call transcript analysis that identifies quality issues in the Athena AI
agent's responses.

How it works
------------
After all calls are complete, the analyzer reads each saved transcript JSON and
sends the full conversation to the LLM with a structured prompt asking it to act
as a QA reviewer.  The model is instructed to look for a specific set of failure
categories (wrong office hours, unsafe scheduling, missed urgency signals, etc.)
and return a JSON array of bugs with severity, location, and recommended fix.

We use the larger Sonnet model here (not Haiku) because bug analysis is a
one-time offline task where quality matters more than latency.

Output format
-------------
Each run appends findings to `bug_reports/bug_report.md`.  This is a Markdown
file designed to be included directly in the GitHub submission.  Each bug entry
includes the call SID, timestamp reference, severity badge, and a diff-style
comparison of actual vs expected behaviour.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

BUG_REPORTS_DIR = "bug_reports"


class BugAnalyzer:

    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic()

    async def analyze_transcript(self, payload: dict) -> list[dict]:
        """
        Ask the LLM to review one call transcript for agent quality issues.

        Parameters
        ----------
        payload   The dict loaded from a transcript JSON file (as saved by
                  TranscriptManager).  Must contain 'turns', 'scenario_name',
                  and 'patient_name' keys.

        Returns
        -------
        List of bug dicts.  Each dict has keys: title, severity, timestamp_ref,
        agent_quote, expected_behaviour, description.  Empty list if no bugs found.
        """
        transcript_text = self._format_for_analysis(payload)
        scenario_name = payload.get("scenario_name", "Unknown")
        scenario_id = payload.get("scenario_id", "")

        prompt = f"""You are a QA analyst evaluating an AI-powered medical office phone agent called Athena.
A patient-simulation bot made a test call and the conversation is transcribed below.

Scenario: {scenario_name}

Transcript:
{transcript_text}

Review the AGENT's responses (not the patient's) for the following categories of issues:

1. SCHEDULING ERRORS — booking appointments on closed days (weekends, holidays), outside office hours,
   or double-booking without checking availability.
2. FACTUAL ERRORS — wrong office hours, wrong address, wrong insurance information, wrong medication
   instructions, or any other incorrect factual claim.
3. SAFETY / URGENCY FAILURES — not recognising and escalating urgent medical symptoms (chest pain,
   difficulty breathing, severe pain, etc.) to a live person or advising 911.
4. UNHELPFULNESS — failing to address the patient's stated request, giving a non-answer, or
   repeatedly asking the same question without progressing.
5. CONVERSATIONAL QUALITY — talking over the patient, not maintaining context across turns,
   misidentifying what the patient said, or responding to a different question than asked.
6. MISSING INFORMATION COLLECTION — for scheduling tasks, not collecting required fields like
   patient name, date of birth, or reason for visit.
7. INAPPROPRIATE TONE OR RESPONSE — too casual, dismissive, overly clinical, or otherwise
   inappropriate for a healthcare context.

Return ONLY a JSON array.  If no bugs found, return [].
Each bug object must have exactly these fields:
{{
  "title": "short bug title",
  "severity": "critical" | "high" | "medium" | "low",
  "timestamp_ref": "MM:SS from transcript where the issue occurs, or empty string",
  "agent_quote": "verbatim quote from the agent that demonstrates the issue",
  "expected_behaviour": "what the agent should have said or done instead",
  "description": "2-3 sentence explanation of why this is a problem"
}}

Do not include any text outside the JSON array."""

        try:
            response = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            logger.error(f"Bug analysis API error: {exc}")
            return []

        raw = response.content[0].text.strip()
        return self._parse_json_array(raw)

    async def analyze_file(self, transcript_path: Path) -> list[dict]:
        """Load a transcript JSON file and return its bugs, enriched with call metadata."""
        with open(transcript_path, encoding="utf-8") as fh:
            payload = json.load(fh)

        bugs = await self.analyze_transcript(payload)
        for bug in bugs:
            bug["call_sid"] = payload.get("call_sid", "")
            bug["scenario_id"] = payload.get("scenario_id", "")
            bug["scenario_name"] = payload.get("scenario_name", "")
        return bugs

    async def analyze_all(self, transcripts_dir: str = "transcripts") -> list[dict]:
        """Analyze every transcript in the given directory and return all bugs found."""
        all_bugs: list[dict] = []
        transcript_files = sorted(Path(transcripts_dir).glob("*.json"))

        if not transcript_files:
            logger.warning(f"No transcript files found in {transcripts_dir}/")
            return []

        for path in transcript_files:
            logger.info(f"Analyzing {path.name} ...")
            bugs = await self.analyze_file(path)
            logger.info(f"  → {len(bugs)} issue(s) found")
            all_bugs.extend(bugs)

        return all_bugs

    async def save_report(self, bugs: list[dict], output_path: Optional[str] = None) -> str:
        """
        Write a Markdown bug report and return the path.

        The report is structured for inclusion in a GitHub repository:
        a header section with summary stats, then one entry per bug sorted by
        severity (critical first).
        """
        os.makedirs(BUG_REPORTS_DIR, exist_ok=True)
        if output_path is None:
            output_path = os.path.join(BUG_REPORTS_DIR, "bug_report.md")

        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_bugs = sorted(bugs, key=lambda b: severity_order.get(b.get("severity", "low"), 4))

        counts = {s: sum(1 for b in bugs if b.get("severity") == s) for s in severity_order}

        lines = [
            "# Athena Agent Bug Report",
            "",
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            f"Total calls analyzed: (see transcripts/)",
            f"Total issues found: **{len(bugs)}**",
            "",
            "| Severity | Count |",
            "|----------|-------|",
        ]
        for s in ["critical", "high", "medium", "low"]:
            lines.append(f"| {s.capitalize()} | {counts[s]} |")

        lines += ["", "---", ""]

        for i, bug in enumerate(sorted_bugs, start=1):
            sev = bug.get("severity", "low").upper()
            lines += [
                f"## Bug {i}: {bug.get('title', 'Untitled')}",
                "",
                f"**Severity:** {sev}  ",
                f"**Call:** {bug.get('call_sid', 'N/A')} — scenario `{bug.get('scenario_id', '')}`  ",
                f"**Location:** `{bug.get('timestamp_ref', 'N/A')}` in transcript",
                "",
                f"**Agent said:**",
                f"> {bug.get('agent_quote', '')}",
                "",
                f"**Expected behaviour:**",
                f"{bug.get('expected_behaviour', '')}",
                "",
                f"**Details:**",
                f"{bug.get('description', '')}",
                "",
                "---",
                "",
            ]

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        logger.info(f"Bug report written to {output_path}")
        return output_path

    @staticmethod
    def _format_for_analysis(payload: dict) -> str:
        """Render transcript turns into the text format used in the analysis prompt."""
        start_ts: Optional[float] = None
        lines = []
        for turn in payload.get("turns", []):
            ts = turn.get("timestamp", 0)
            if start_ts is None:
                start_ts = ts
            elapsed = ts - start_ts
            mm = int(elapsed) // 60
            ss = int(elapsed) % 60
            speaker = turn["speaker"].upper()
            lines.append(f"[{mm:02d}:{ss:02d}] {speaker}: {turn['text']}")
        return "\n".join(lines)

    @staticmethod
    def _parse_json_array(text: str) -> list[dict]:
        """
        Extract a JSON array from LLM output, tolerating markdown code fences.

        The model sometimes wraps its JSON in ```json ... ``` blocks even when
        instructed not to.  We strip those fences before parsing.
        """
        # Strip markdown fences
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`")
        try:
            result = json.loads(text)
            return result if isinstance(result, list) else []
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to parse bug analysis JSON: {exc}\nRaw: {text[:500]}")
            return []
