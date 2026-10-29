# J.A.R.V.I.S.

A local-first, always-listening voice assistant for Windows. It waits for a
wake word, transcribes what you say, reasons about it with an LLM that can
call tools to actually control the machine, and speaks the answer back —
with the goal of being hands-free, low-latency, safe to leave running near
real system access, and able to remember things about you across sessions.

## Why

Voice assistants that just answer trivia aren't that useful on a personal
machine. The point of this project is an assistant that can actually *do*
things on the computer it runs on — open apps, check hardware stats, search
the web, manage files, display information on screen — while staying
conversational and fast enough that talking to it doesn't feel like waiting
on a chatbot. The supporting design goals that follow from that:

- **Hands-free first.** Wake word → speak → done, no typing required for the
  common case.
- **Low latency.** Responses are streamed sentence-by-sentence to speech
  rather than waiting for a full LLM response before saying anything.
- **Safe machine control.** Anything that touches the OS (launching apps,
  running scripts, shutting down) goes through an explicit whitelist, not a
  model's unchecked judgment.
- **Memory that persists.** Facts about you accumulate in a local vector
  store and get pulled back into context on later turns, instead of every
  conversation starting from zero.

## How it works

```
 microphone
     │
     ▼
 wake word detection  (openWakeWord, "hey_jarvis" model)
     │  (wake word heard)
     ▼
 VAD / phrase recording  (calibrates ambient noise, records until
     │                     trailing silence or a hard time cap)
     ▼
 speech-to-text  (faster-whisper, CUDA)
     │
     ▼
 memory retrieval  (ChromaDB vector search over past extracted facts)
     │
     ▼
 LLM reasoning + tool calls  (Gemini, streaming; a separate background
     │                         model handles memory extraction off the
     │                         critical path)
     ▼
 sentence-level streaming text-to-speech  (spoken as soon as each
     │                                      sentence is ready, not after
     │                                      the whole reply is generated)
     ▼
 speaker
```

A desktop HUD (PySide6) runs alongside this and shows live status,
conversation history, and system telemetry.

Component by component:

- **Wake word** — [openWakeWord](https://github.com/dscripka/openWakeWord),
  running the bundled `hey_jarvis` model continuously on microphone input
  captured via `pyaudiowpatch` (WASAPI).
- **Voice activity detection / recording** — a dedicated endpointing step
  that calibrates a noise-floor estimate from the first fraction of a
  second of each recording, rather than using one fixed volume threshold
  for every room and microphone.
- **Speech-to-text** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  running the `large-v3-turbo` model on CUDA (float16), with a CPU fallback.
- **Memory** — [ChromaDB](https://www.trychroma.com/) as a local persistent
  vector store, embedded with `sentence-transformers` (`all-MiniLM-L6-v2`).
  Facts extracted from conversation are categorized (identity, preferences,
  projects, relationships) and retrieved by similarity on later turns.
- **Reasoning** — a "dual-brain" split: a primary model
  ([Gemini](https://ai.google.dev/), `gemini-3.6-flash` by default) handles
  the live conversation and streams its response as it's generated, while a
  separate background model (via [OpenRouter](https://openrouter.ai/),
  defaulting to its free tier) handles memory extraction and other
  non-conversational work off the latency-critical path.
- **Tool execution** — the LLM can call a set of registered functions
  (currently 32) to actually act on the machine: launching applications,
  reading/writing files, searching the web, taking screenshots, checking
  hardware stats, adjusting volume/brightness, browser automation, and
  more. Every call that touches the OS directly is checked against an
  explicit allow-list before it runs.
- **Text-to-speech** — a 3-tier cascade: a cloud neural voice (Fish Audio)
  as the primary engine, a Google Translate TTS endpoint as a fallback, and
  a fully offline local engine ([Piper](https://github.com/rhasspy/piper))
  as the last resort if both network tiers fail.
- **Desktop UI** — a frameless PySide6 HUD with a dashboard view, an
  animated status orb, and a memory browser.
- **External messaging (optional)** — a WebSocket client for OpenClaw, an
  external gateway process (not part of this repo) that can bridge
  messaging platforms. Entirely optional; the assistant runs without it.

## Key design decisions

- **Sentence-level streaming TTS.** The LLM's response is split into
  sentences as it streams in, and each sentence is sent to speech the
  moment it's complete — instead of generating the full reply and only then
  starting to speak, which made early turns feel noticeably slower.
- **A streaming/non-streaming fallback for tool-calling.** The Gemini model
  used for streaming can, under certain conditions, return a response that
  silently combines tool use with streaming in a way that comes back empty.
  When that specific signature is detected, the same request is retried
  non-streaming (which doesn't hit the issue) rather than surfacing a
  generic failure to the user.
- **An explicit safety whitelist for machine control.** Tools that launch
  applications or run scripts check their target against a fixed allow-list
  before executing, rather than trusting whatever the model decides to run.
- **A dual-brain split for latency.** Conversation-critical reasoning and
  background bookkeeping (memory extraction, etc.) run on separate model
  calls so that background work never blocks the next thing you hear.
- **Manual tool dispatch with a dedupe guard.** Tool calls are executed by
  this codebase's own dispatcher rather than relying on the model
  provider's automatic function-calling, which turned out to bypass some of
  the UI feedback this project relies on. Because manual dispatch means
  retrying a failed model call can occasionally re-request a tool that
  already ran, executed tool calls are tracked for the duration of a turn
  and an exact repeat (same tool, same arguments) is served from the first
  result instead of running again.

## Scope and status

**Working today:** the app starts cleanly, binds to the real microphone,
detects the wake word, transcribes speech, retrieves relevant memory,
reasons with tool access, and produces streamed spoken output through the
TTS cascade. A multi-step tool-calling path (the model can call more than
one tool in a single turn) and a duplicate-call guard across model
fallbacks are both implemented and tested.

**In progress:** the voice-activity/endpointing logic (how recording
decides a phrase has ended) has gone through two fix attempts after the
first one didn't hold up under real voice testing. The second attempt is
implemented and has passed code-level checks, but is still awaiting live
voice verification before it's considered resolved.

**Known limitations:**
- Local speech-to-text and the embedding model both run on GPU; on a 4 GB
  VRAM card, GPU memory can get tight if other applications are also using
  the GPU at the same time.
- The default API keys (Gemini, OpenRouter) are free-tier, which carries
  daily/per-minute request quotas — expect fallback behavior or slower
  responses once a quota is hit.
- The optional messaging integration depends on OpenClaw, a separate
  process this repo does not include or launch automatically — it has to
  be installed and started independently for that feature to work.

**Roadmap:**
- An MCP server exposing this assistant's tools.
- A live, audio-reactive version of the status orb (replacing the current
  pre-rendered-animation approach).
- A fullscreen UI overhaul.
- Automatically launching the external OpenClaw process instead of
  requiring it to be started manually.

## Setup

**Requirements**
- Windows 11, bare-metal (not a remote desktop session — remote audio
  redirection breaks microphone capture for wake-word/VAD purposes).
- A CUDA-capable NVIDIA GPU is used for speech-to-text by default (falls
  back to CPU if unavailable).
- Python (developed and tested on 3.14).

**Install**

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**Configure**

Copy `.env.example` to `.env` and fill in values. At minimum:

- `GEMINI_API_KEY` — required for LLM reasoning.
- `OPENROUTER_API_KEY` — required for the background model.

Everything else in `.env.example` (model names, Whisper device/compute
settings, etc.) has a working default and only needs changing if you want
to override it.

**Model and voice files**

- The wake-word model is bundled with the `openwakeword` package; no
  separate download needed for the default `hey_jarvis` model.
- The Piper TTS fallback voice lives under `tts/voices/` (an `.onnx` model
  file plus its config).
- Faster-Whisper downloads its model automatically on first run.

**Run**

```
python main.py
```

On a working setup this loads the speech-to-text model, binds to the
default microphone, and opens the desktop HUD. Say the wake word, then
speak your request.
