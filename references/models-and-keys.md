# Models and keys for media (STT, TTS, image generation)

Read when setting `stt_model`, `tts_model`, `image_generation_model`, or when a media step fails with a key, 404 or modality error.

## 1. Each model uses its own provider's key

The agent's chat `provider` is not used for media when a model is set. `handlers/media.py::_resolve_model_provider` takes the AI Model's
own `provider`, reads that AI Provider's `api_key`, and normalises the LiteLLM name. The agent's provider is used only when the model
is not a known AI Model, or for the provider default when the field is empty.
Consequences:
- An Anthropic agent can speak with a Google TTS model and transcribe with a Google STT model, provided an AI Provider "Google" has a key.
- Missing key error names the media provider: "API key is not configured for TTS provider 'Google'. Please add it to the AI Provider document."
- Anthropic has no STT/TTS/image models; set all three fields explicitly on Anthropic agents.
Same for STT (`audio_service.resolve_stt_config`: tool param > `Agent.stt_model` > Transcription model of the agent's provider > provider default),
OCR and video. Never put keys in seed files; use `<GOOGLE_API_KEY>` style placeholders and enter keys on the AI Provider doc.

Source: huf/ai/handlers/media.py (_resolve_model_provider, _resolve_image_config, _resolve_tts_config); huf/ai/audio_service.py; huf/ai/tests/test_media_model_provider.py

## 2. Fields and required modality

| Agent field | Type | Link target | Required modality on the AI Model |
|---|---|---|---|
| `stt_model` | Link | AI Model | `Transcription` |
| `tts_model` | Link | AI Model | `Text-to-Speech` |
| `tts_voice` | Data | - | (voice id, e.g. `alloy`; Gemini voices e.g. `Puck`) |
| `image_generation_model` | Link | AI Model | `Image` |
| `enable_ocr` | Check | - | agent `model` needs `OCR` |

AI Model `modalities` options: Text, Image, Text-to-Speech, Transcription, Embeddings, Vision, OCR, Speech-to-Speech, Video.
Saving an agent with a mismatch throws, e.g. "Selected STT Model does not support modality: Transcription" (also
"...TTS Model does not support modality: Text-to-Speech", "...Image Generation Model does not support modality: Image").
Fix: pick another model, or add the modality on the AI Model row.

Choosing: pick an AI Model row whose `provider` has a key and whose modalities match; set the field to the AI Model name.
Defaults when a field is empty (`_get_default_*`): TTS google/gemini `gemini/gemini-3.8-flash-tts`, openai `gpt-4o-mini-tts`;
STT google/gemini `gemini/gemini-flash-latest`; image openai `gpt-image-2`, google `gemini/gemini-3.1-flash-image`.

Source: huf/huf/doctype/agent/agent.json, agent.py (_validate_advanced_models); huf/huf/doctype/ai_model/ai_model.json; huf/ai/audio_service.py

## 3. Alias vs pinned models

`AI Model.is_latest_alias` (read-only Check) marks moving aliases, e.g. `gemini-flash-latest`, `gemini-pro-latest`,
`gemini-flash-lite-latest`, `chat-latest`, `mistral-large-latest`, OpenRouter `~google/gemini-flash-latest`.
Prefer an alias for Google defaults: pinned ids get closed (Google closed `gemini-2.5-pro/-flash/-flash-lite` to new users on
2026-09-18; calls 404). Anthropic has no `-latest` aliases: use the dashed id (e.g. `claude-sonnet-5-5`, not dotted ids).
`gemini-flash-latest` carries `Transcription` because Gemini audio is transcribed through a multimodal completion
(`audio_service.MULTIMODAL_STT_PROVIDERS = google, gemini, vertex_ai`), not `litellm.transcription`.
Trade-off: aliases follow Google's re-routing silently; pin when you need reproducible output.

Source: huf/ai/model_catalogue.py; huf/ai/audio_service.py; MODEL_REFRESH_NOTES.md (gap2)

## 4. How the catalogue is seeded and refreshed

- `huf/ai/model_catalogue.py` (generated, 254 models, do not hand-edit; generator `scripts/gen_model_catalogue.py`) holds `MODELS` and `RETIRED`.
- Every `after_migrate` calls `model_catalogue_sync.upsert_models`: adds missing models, fills blank metadata, adds missing modalities,
  syncs `is_latest_alias`. It never deletes or repoints.
- Patch `huf.patches.v1.refresh_model_catalogue` applies `RETIRED` (`model_name -> (provider, replacement)`, confirmed shutdowns only): repoints
  agent/automation/conversation config to the same-provider replacement, writes an Info Comment on each affected Agent, deletes the old row
  only if no history references it. Example: `gemini-2.5-flash` -> `gemini-flash-latest`.
- Softened models stay on existing sites but are not seeded for new ones. Admin-created rows survive migrate.
After upgrading Huf run `bench migrate`, then re-check an agent's media fields (look for the Info Comment on the Agent).

Source: huf/ai/model_catalogue.py; huf/ai/model_catalogue_sync.py; huf/ai/model_catalogue_retire.py; huf/patches/v1/refresh_model_catalogue.py; MODEL_REFRESH_NOTES.md

## 5. Gemini quirks

- TTS: `litellm.speech()` routes gemini through a bridge that drops `api_key` (falls back to process env). Huf therefore uses
  `litellm.completion(modalities=["audio"], audio={"voice": ..., "format": "pcm16"}, api_key=...)`; pcm16 is the only accepted format.
  Output is base64 PCM16 at 24 kHz, wrapped into WAV (`_pcm16_to_wav`) and converted to Ogg/Opus later. OpenAI-style voices (alloy) map to a valid Gemini voice.
- STT: multimodal completion with base64 audio, not a transcription endpoint. `gemini-3.5-transcribe` is not served via generateContent
  (empty transcript); use `gemini-flash-latest`.
- Retired Gemini 2.5 chat models 404; use `gemini-flash-latest`.

Source: huf/ai/handlers/media.py (_gemini_tts_completion, _pcm16_to_wav); huf/ai/audio_service.py

## 6. What works live (verified 2026-10-22, reported by the Huf team; not re-run here)

| Step | Model | Provider key |
|---|---|---|
| STT | `gemini-flash-latest` | Google |
| TTS | `gemini-3.1-flash-tts-preview` (current seed default: `gemini-3.8-flash-tts`) | Google |
| Image | `gemini-3.1-flash-image` | Google |
| Agent chat | Anthropic model | Anthropic; media steps used Google keys |

## 7. Pitfalls

- Agent has no tools attached: it says it cannot make images/voice. Attach `generate_image`, `generate_audio`, `whatsapp` (see `audio-and-media.md`).
- Stale conversation history: an old "I cannot do that" or failure is repeated. Test in a fresh conversation or clear context.
- `to` is optional on whatsapp send actions; instruct the agent not to ask for a phone number.
- Setting only the chat provider key: media with another provider's model fails until that AI Provider has its own key.
- Modality validation error on save: wrong model type in the field (see section 2).
- ffmpeg/libopus missing on the worker host: voice replies silently fall back to text; health shows `voice_reply_ffmpeg_missing`.

Source: huf/ai/whatsapp_health.py; huf/ai/tools/_registry.py; huf/ai/handlers/media.py
