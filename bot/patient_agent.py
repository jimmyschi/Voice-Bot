import logging
import time
from typing import Optional

import anthropic

from bot.scenarios import Scenario

logger = logging.getLogger(__name__)

END_CALL_SIGNAL = "[END_CALL]"
MAX_TURNS = 20


class PatientAgent:
    """LLM-powered patient persona that drives the conversation."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.client = anthropic.AsyncAnthropic()
        self.conversation_history: list[dict] = []
        self.transcript: list[dict] = []
        self.should_end_call = False
        self._turn_count = 0

    async def respond(self, agent_text: str) -> Optional[str]:
        """Generate a patient response given what the agent just said."""
        if self.should_end_call:
            return None

        self._log_turn("agent", agent_text)

        self.conversation_history.append({
            "role": "user",
            "content": agent_text,
        })

        self._turn_count += 1
        if self._turn_count >= MAX_TURNS:
            logger.info("Max turns reached, ending call.")
            self.should_end_call = True
            return "Thank you, goodbye."

        try:
            response = await self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=120,
                system=self._system_prompt(),
                messages=self.conversation_history[-12:],
            )
        except Exception as exc:
            logger.error(f"LLM API error: {exc}")
            return None

        raw = response.content[0].text.strip()

        if END_CALL_SIGNAL in raw:
            self.should_end_call = True
            patient_text = raw.replace(END_CALL_SIGNAL, "").strip()
        else:
            patient_text = raw

        if not patient_text:
            self.should_end_call = True
            return None

        self.conversation_history.append({
            "role": "assistant",
            "content": patient_text,
        })
        self._log_turn("patient", patient_text)

        return patient_text

    def _system_prompt(self) -> str:
        return f"""You are simulating a real patient calling a medical office AI phone agent for testing purposes.

SCENARIO: {self.scenario.description}
YOUR NAME: {self.scenario.patient_name}
YOUR GOAL: {self.scenario.goal}
YOUR PERSONALITY: {self.scenario.personality}

RULES:
- Stay in character as a real patient at all times.
- Keep responses SHORT — 1 to 3 sentences only.
- Speak naturally. You may say "um" or "uh" occasionally. You don't always speak in perfect sentences.
- Ask follow-up questions if the agent is unclear or vague.
- If your goal is fully accomplished OR the agent clearly cannot help you, respond with {END_CALL_SIGNAL} immediately followed by a brief goodbye. Example: {END_CALL_SIGNAL} Thank you, bye.
- Do NOT invent fictional information beyond what the scenario states.
- Do NOT break character under any circumstances."""

    def _log_turn(self, speaker: str, text: str) -> None:
        self.transcript.append({
            "speaker": speaker,
            "text": text,
            "timestamp": time.time(),
        })
