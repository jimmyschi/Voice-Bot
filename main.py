#!/usr/bin/env python3
"""
main.py — CLI entry point for the PGAI Athena voice bot test system.

Usage
-----
  # Run all 17 scenarios back-to-back:
  python main.py run

  # Run a single scenario by ID:
  python main.py single --scenario weekend_appointment

  # List available scenario IDs:
  python main.py list

  # Analyze all saved transcripts and generate a bug report:
  python main.py analyze

Environment
-----------
Requires a .env file (see .env.example).  If WEBHOOK_URL is not set, the
script automatically starts an ngrok HTTPS tunnel on port 8000 and uses that
URL for Twilio callbacks.  Ensure ngrok is authenticated via `ngrok config
add-authtoken <token>` before running.

Call flow
---------
1. An ngrok tunnel (or WEBHOOK_URL) makes our local FastAPI server reachable.
2. We register the call_manager in server.py and start the FastAPI server in
   a background thread.
3. For each scenario we call CallManager.create_call(), which dials the Athena
   number and passes the scenario_id as a custom parameter so the WebSocket
   handler can look it up when the stream starts.
4. We poll is_active() every 2 seconds and move to the next scenario once the
   call completes (signalled by Twilio's /call-status callback).
5. After all calls finish we optionally run bug analysis.
"""

import argparse
import asyncio
import logging
import os
import threading
import time

import uvicorn
from dotenv import load_dotenv
from pyngrok import ngrok

import server as srv
from bot.call_manager import CallManager
from bot.scenarios import SCENARIOS, get_scenario_by_id, list_scenarios
from analysis.bug_analyzer import BugAnalyzer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

TARGET_NUMBER = os.getenv("TARGET_NUMBER", "+18054398008")
SERVER_PORT = 8000
DELAY_BETWEEN_CALLS = 20  # seconds — gives the previous recording time to upload


def _start_server_thread() -> None:
    """Launch uvicorn in a daemon thread so it runs alongside the async main loop."""
    config = uvicorn.Config(
        app=srv.app,
        host="0.0.0.0",
        port=SERVER_PORT,
        log_level="warning",
    )
    uvicorn_server = uvicorn.Server(config)
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    time.sleep(2)  # Give uvicorn a moment to bind the port
    logger.info(f"FastAPI server listening on port {SERVER_PORT}")


def _get_webhook_url() -> str:
    """Return the public HTTPS URL for our server, starting ngrok if needed."""
    url = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
    if url:
        logger.info(f"Using WEBHOOK_URL from env: {url}")
        return url

    logger.info("WEBHOOK_URL not set — starting ngrok tunnel ...")
    tunnel = ngrok.connect(SERVER_PORT, "http")
    url = tunnel.public_url.replace("http://", "https://")
    logger.info(f"ngrok tunnel active: {url}")
    return url


def run_scenario(call_manager: CallManager, scenario_id: str) -> str:
    """
    Initiate one test call and return the Twilio call SID.

    We register the scenario_id in server.pending_scenarios keyed by call SID
    so the WebSocket handler can retrieve it when the stream starts.  Twilio
    doesn't pass arbitrary data to the TwiML URL until after we know the call
    SID, hence this indirection through a shared dict.
    """
    scenario = get_scenario_by_id(scenario_id)
    if scenario is None:
        raise ValueError(f"Unknown scenario ID: {scenario_id}")

    call_sid = call_manager.create_call(TARGET_NUMBER, scenario.name)
    srv.pending_scenarios[call_sid] = scenario_id
    return call_sid


def wait_for_call(call_manager: CallManager, call_sid: str, timeout: int = 300) -> None:
    """
    Block until the call completes, then poll Twilio for the recording.

    After the call ends we immediately start polling Twilio's REST API for a
    completed recording (up to 90 seconds).  This replaces reliance on the
    /recording-status webhook, which arrives asynchronously and can be missed
    if the process exits before Twilio delivers it.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not call_manager.is_active(call_sid):
            dest = os.path.join("recordings", f"{call_sid}.mp3")
            call_manager.fetch_recording_for_call(call_sid, dest)
            return
        time.sleep(2)
    logger.warning(f"Timed out waiting for call {call_sid} — forcing completion.")
    call_manager.mark_completed(call_sid)


async def run_all(call_manager: CallManager) -> None:
    """Run every scenario sequentially with a short pause between calls."""
    logger.info(f"Starting full run: {len(SCENARIOS)} scenarios → {TARGET_NUMBER}")

    for i, scenario in enumerate(SCENARIOS):
        logger.info(f"\n{'='*60}")
        logger.info(f"Scenario {i+1}/{len(SCENARIOS)}: {scenario.name}")
        logger.info(f"{'='*60}")

        try:
            call_sid = run_scenario(call_manager, scenario.id)
            wait_for_call(call_manager, call_sid)
            logger.info(f"Scenario '{scenario.name}' complete.")
        except Exception as exc:
            logger.error(f"Scenario '{scenario.name}' failed: {exc}", exc_info=True)

        if i < len(SCENARIOS) - 1:
            logger.info(f"Waiting {DELAY_BETWEEN_CALLS}s before next call ...")
            await asyncio.sleep(DELAY_BETWEEN_CALLS)

    logger.info("\nAll scenarios complete.")


async def run_analysis() -> None:
    """Analyze all transcripts in transcripts/ and generate bug_reports/bug_report.md."""
    analyzer = BugAnalyzer()
    bugs = await analyzer.analyze_all()
    if not bugs:
        logger.info("No bugs found — or no transcripts available.")
        return
    report_path = await analyzer.save_report(bugs)
    print(f"\nBug report: {report_path}  ({len(bugs)} issue(s) found)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="PGAI Athena Voice Bot Test System")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="Run all scenarios sequentially")
    sub.add_parser("list", help="List available scenario IDs")
    sub.add_parser("analyze", help="Analyze saved transcripts for bugs")

    single_p = sub.add_parser("single", help="Run one scenario by ID")
    single_p.add_argument("--scenario", required=True, help="Scenario ID (see 'list')")

    args = parser.parse_args()

    if args.command == "list":
        list_scenarios()
        return

    if args.command == "analyze":
        await run_analysis()
        return

    # For run / single we need the server + ngrok
    _start_server_thread()
    webhook_url = _get_webhook_url()

    call_manager = CallManager(webhook_url=webhook_url)
    srv.set_call_manager(call_manager)

    if args.command == "run":
        await run_all(call_manager)
        logger.info("Running post-run bug analysis ...")
        await run_analysis()

    elif args.command == "single":
        scenario = get_scenario_by_id(args.scenario)
        if scenario is None:
            print(f"Unknown scenario '{args.scenario}'.  Use 'list' to see options.")
            return
        logger.info(f"Single run: {scenario.name}")
        call_sid = run_scenario(call_manager, args.scenario)
        wait_for_call(call_manager, call_sid)
        logger.info("Call complete. Running bug analysis ...")
        await run_analysis()


if __name__ == "__main__":
    asyncio.run(main())
