"""One-shot VAPI setup: register the tools + create the assistant via the API.

This does the fiddly dashboard work for you. Given a filled-in .env, it:
  1. Creates the four Custom Tools from vapi/tools.json, pointing each at your
     tunnel URL and baking in the x-vapi-secret so the webhook trusts the calls.
  2. Creates an assistant wired to those tools, with the ElevenLabs voice and the
     system prompt from vapi/assistant_system_prompt.md.

It prints the assistant id at the end. Then you just buy a phone number in the
VAPI dashboard and assign this assistant to it.

Usage:
    cp .env.example .env        # then fill in the values
    python scripts/setup_vapi.py            # create tools + assistant
    python scripts/setup_vapi.py --dry-run  # show what would be sent, call nothing

Re-running creates NEW tools/assistant each time (the VAPI API doesn't dedupe by
name). For a second run, delete the old ones in the dashboard first, or just keep
the newest assistant id this prints.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
VAPI_BASE = "https://api.vapi.ai"


def load_dotenv(path: Path) -> None:
    """Tiny .env loader so we don't add a dependency. Existing env wins."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        sys.exit(f"Missing required value: {name}. Fill it in your .env (see .env.example).")
    return val


def main() -> None:
    ap = argparse.ArgumentParser(description="Register VAPI tools + assistant.")
    ap.add_argument("--dry-run", action="store_true", help="Print payloads, make no API calls.")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")

    api_key = require("VAPI_API_KEY")
    public_url = require("PUBLIC_URL").rstrip("/")
    secret = require("VAPI_SERVER_SECRET")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
    llm_provider = os.environ.get("LLM_PROVIDER", "openai").strip()
    llm_model = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()

    webhook = f"{public_url}/vapi/tool-calls"
    tools_spec = json.loads((ROOT / "vapi" / "tools.json").read_text())
    system_prompt = (ROOT / "vapi" / "assistant_system_prompt.md").read_text()

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    client = httpx.Client(base_url=VAPI_BASE, headers=headers, timeout=30.0)

    def post(path: str, payload: dict) -> dict:
        if args.dry_run:
            print(f"\n[dry-run] POST {path}\n{json.dumps(payload, indent=2)}")
            return {"id": f"dryrun_{path.strip('/')}"}
        r = client.post(path, json=payload)
        if r.status_code >= 300:
            sys.exit(f"VAPI error on POST {path}: {r.status_code}\n{r.text}")
        return r.json()

    # 1. Create the tools, pointing each at our tunnel + secret.
    print(f"Registering tools -> {webhook}")
    tool_ids: list[str] = []
    for spec in tools_spec["tools"]:
        payload = {
            "type": "function",
            "function": spec["function"],
            "server": {"url": webhook, "secret": secret},
        }
        created = post("/tool", payload)
        tool_ids.append(created["id"])
        print(f"  + {spec['function']['name']} -> {created['id']}")

    # 2. Create the assistant wired to those tools, ElevenLabs voice, our prompt.
    assistant_payload = {
        "name": "Northgate Motors Service",
        "firstMessage": "Thanks for calling Northgate Motors service. How can I help you today?",
        "model": {
            "provider": llm_provider,
            "model": llm_model,
            "messages": [{"role": "system", "content": system_prompt}],
            "toolIds": tool_ids,
        },
        "voice": {"provider": "11labs", "voiceId": voice_id},
    }
    assistant = post("/assistant", assistant_payload)

    print("\nDone.")
    print(f"  Assistant id: {assistant['id']}")
    print(f"  Voice: ElevenLabs ({voice_id})   Model: {llm_provider}/{llm_model}")
    print("\nNext: VAPI Dashboard -> Phone Numbers -> buy/import a number ->")
    print("      set its assistant to the id above -> call it.")


if __name__ == "__main__":
    main()
