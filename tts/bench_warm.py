"""Measure WARM synthesis speed: load once, synthesize several times.

The cold first call includes lazy init/warmup; a long-running TTS server only
pays that once. This reports the real-time factor (RTF = synth_time / audio_len)
for warm calls, which is what governs whether streaming live calls are viable.
RTF < ~0.6 = streaming viable; RTF > ~1.0 = not real-time on this box.
"""

from __future__ import annotations

import os
import time
import wave
from pathlib import Path

os.environ.setdefault("COQUI_TOS_AGREED", "1")
HERE = Path(__file__).resolve().parent
REF = HERE / "bharath_ref.wav"
DEVICE = os.environ.get("TTS_DEVICE", "cpu")

PHRASES = [
    "How can I help you today?",
    "I have Monday at ten A M or eleven A M. Which works best?",
    "You're booked for an oil change Monday at ten. Your code is C W C two.",
]


def audio_len(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    from TTS.api import TTS

    t0 = time.time()
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(DEVICE)
    print(f"model loaded in {time.time() - t0:.1f}s on {DEVICE}\n")

    out = HERE / "_bench.wav"
    for i, text in enumerate(PHRASES):
        t = time.time()
        tts.tts_to_file(text=text, speaker_wav=str(REF), language="en", file_path=str(out))
        synth = time.time() - t
        alen = audio_len(out)
        tag = "COLD" if i == 0 else "warm"
        print(f"[{tag}] {synth:5.1f}s synth / {alen:4.1f}s audio  -> RTF {synth/alen:.2f}x  | {text[:40]!r}")


if __name__ == "__main__":
    main()
