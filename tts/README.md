# Offline voice clone (XTTS-v2)

A self-hosted, $0 voice clone using Coqui XTTS-v2. It clones a speaker from a
short reference clip and synthesizes arbitrary text in that voice.

**Use it for offline audio** — greetings, IVR prompts, voicemail, marketing.
It is **not wired into live phone calls**: on an 8 GB M1 it synthesizes at
~1.5x real-time (warm), so audio is generated slower than it plays and would
stutter in a live conversation. Live calls use a managed real-time voice in
VAPI instead (see the project root README). Faster hardware or a cloud GPU
would make real-time viable without code changes.

## Setup (one time)

```bash
/opt/homebrew/bin/python3.12 -m venv tts/.venv        # Python 3.12, not 3.13
tts/.venv/bin/pip install -r tts/requirements.txt
```

## Generate audio in the cloned voice

```bash
# Reference clip -> tts/bharath_ref.wav (mono, 22.05 kHz). Regenerate from any sample:
ffmpeg -y -i /path/to/voice.mp3 -ac 1 -ar 22050 tts/bharath_ref.wav

# Synthesize (first run downloads the ~1.8 GB model, then caches it):
COQUI_TOS_AGREED=1 tts/.venv/bin/python tts/synthesize.py "Your text here"
afplay tts/sample_out.wav
```

`bench_warm.py` measures cold vs warm real-time factor on this machine — rerun it
if you move to faster hardware to re-check whether real-time calls become viable.

## Files

- `synthesize.py` — text -> `sample_out.wav` in the cloned voice.
- `bench_warm.py` — cold/warm RTF benchmark (the real-time viability check).
- `requirements.txt` — pinned deps (note the transformers<5 / torchcodec gotchas).
- `bharath_ref.wav`, `*.wav`, `.venv/` — gitignored (personal voice data + heavy).
