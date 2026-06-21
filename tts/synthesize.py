"""Stage 1: prove the voice clone, fully offline.

Loads XTTS-v2 once and synthesizes whatever text you pass, cloning the speaker
from bharath_ref.wav. Prints how long synthesis took so we can judge whether
real-time phone use is viable on this hardware before building the VAPI plumbing.

Usage:
    tts/.venv/bin/python tts/synthesize.py "Thanks for calling Northgate Motors."
    # -> writes tts/sample_out.wav

Device: defaults to CPU (most reliable for XTTS on Apple Silicon). Set
TTS_DEVICE=mps to try the GPU path.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")  # accept the XTTS model license

HERE = Path(__file__).resolve().parent
REF = HERE / "bharath_ref.wav"
OUT = HERE / "sample_out.wav"

DEFAULT_TEXT = (
    "Thanks for calling Northgate Motors service. "
    "I can help you book an oil change, tire rotation, or other service. "
    "How can I help you today?"
)


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEXT
    device = os.environ.get("TTS_DEVICE", "cpu")

    print(f"Loading XTTS-v2 on {device} (first run downloads ~1.8 GB)...")
    t0 = time.time()
    from TTS.api import TTS  # heavy import; only here

    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    print(f"  model ready in {time.time() - t0:.1f}s")

    print(f"Synthesizing {len(text)} chars in your cloned voice...")
    t1 = time.time()
    tts.tts_to_file(
        text=text,
        speaker_wav=str(REF),
        language="en",
        file_path=str(OUT),
    )
    synth = time.time() - t1
    print(f"  synthesized in {synth:.1f}s -> {OUT}")
    print(f"\nListen with:  afplay {OUT}")


if __name__ == "__main__":
    main()
