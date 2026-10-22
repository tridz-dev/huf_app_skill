# Audio and media (WhatsApp and web chat)

Read when the agent must understand images, PDFs or voice notes, or produce images, speech or voice notes.
All names below were confirmed in Huf `pre-develop` (`huf/ai/...`). Model choice and API keys: `models-and-keys.md`.

## 1. Inbound: what the agent receives

Gateway and web chat share `huf/ai/media_prep.py::prepare_media_for_agent`. It never raises; a failed step becomes a short labelled note.

| Kind (`classify_media`) | What the agent gets |
|---|---|
| image (`image/*`) | passed as image input (`files=[{..., is_image: 1}]`); the model must support Vision |
| document (pdf, doc(x), xls(x), ppt(x), odt, rtf, txt, md, csv, json, html, xml) | OCR/extracted text appended to the prompt as `Attached File Content (OCR Extracted)` with `--- File: <name> (hash: ...) ---` |
| audio (voice note, audio file) | transcript prepended as `[Voice note transcript (<name>)]: <text>`; the original file is kept as `is_audio: 1` |
| anything else | `[Attachment (<name>) has an unsupported type and was not read]` |

Caps: `MAX_DOC_TEXT_CHARS = 12000` per document, `MAX_TOTAL_TEXT_CHARS = 24000` across one message (then
`[Document (..) text omitted: size budget reached]`), `MAX_TRANSCRIPT_CHARS = 8000` (`[transcript truncated]`).
Failures: `[Voice note (..) could not be transcribed]`, `[Document (..) could not be read]`.

Attachment not saved (download failed): gateway adds `[Attachment unavailable: the file the user sent could not be downloaded]`
to the prompt. The agent is then the only responder (one reply only); the standalone fallback note is sent
only if the run fails or yields no reply. When saved, the prompt gets `[Attachment saved: <file_url>]`.

Needed on the agent for this to work:
- `stt_model` (or a Transcription model on the agent's provider) for voice notes.
- OCR of documents uses `ocr_document`; `enable_ocr` routes web-chat uploads through OCR. If `enable_ocr` is on,
  the agent's `model` must carry the `OCR` modality (validation in `agent.py::_validate_advanced_models`).

### WhatsApp media intake (gateway adapter)
`whatsapp_bridge.fetch_media` downloads by media id. Size limits per kind (`MEDIA_LIMITS_BY_KIND`): document 100 MB,
image 5 MB, audio 16 MB, video 16 MB, sticker 500 KB; over the limit raises `media_too_large`.
Meta sometimes labels a file `application/octet-stream` (commonly `.m4a`). Then the type is inferred from the file
extension (`_EXTENSION_MIME`: m4a mp3 ogg oga opus wav aac amr mp4 3gp pdf jpg jpeg png webp txt doc docx xls xlsx ppt pptx),
checked against the allow-list, and the payload's magic bytes must match (`_signature_matches`), else `mime_not_allowed`.
svg, html, exe, sh, js, csv are refused. A specific declared type is never overridden by the extension.

Source: huf/ai/media_prep.py; huf/ai/gateway_service.py (ATTACHMENT_UNAVAILABLE_NOTE); huf/ai/gateway_adapters/whatsapp_bridge.py; huf/ai/tests/test_gateway_media_to_agent.py, test_whatsapp_media_infer.py

## 2. Outbound: generate, then send

Tools (Agent Tool Functions seeded by `install.py`, attach them to the agent): `generate_image`, `generate_audio`,
`ocr_document`, `transcribe_audio`, and `whatsapp`.

1. `generate_image(prompt, size?, quality?, n?)` returns `images: [{url, file_id}]`. Do not paste the URL into the reply.
2. `generate_audio(input, voice?, model?, speed?, response_format?)` returns `audio: {url, file_id, ...}`.
   Leave `voice` and `model` blank: they come from `Agent.tts_voice` / `Agent.tts_model`.
3. Send with the `whatsapp` tool, using `file_url` or `file_id` of that output:
   - `{"action":"send_image","file_url":"<url from generate_image>","caption":"..."}`
   - `{"action":"send_voice_note","file_id":"<file_id from generate_audio>"}`
   - `to` is optional on every send action: omit it to reply to the person in the conversation (never ask for their number).
   - Give exactly one of `link`, `media_id`, `file_url`, `file_id`.

File ownership (`whatsapp_send_file.resolve_file`): a `file_url` must be a plain `/private/files/` or `/files/` path (no `..`, `?`, `#`).
The file must be attached to the run's conversation (as conversation, Agent Message or inbound Gateway Event media), or be an
unattached upload owned by the session user. Anything else gives `file_not_permitted`; unknown gives `file_not_found`.
Errors seen: `invalid_file_reference`, `too_large`, `unsupported_mime`, `kind_mismatch`, `invalid_kind`.

Captions: max 1024 (`MAX_CAPTION`). A longer caption is split at whitespace (`split_caption`): the first part is the caption,
the rest follows as a separate text message.

Voice notes must be Ogg/Opus. `send_voice_note` / `voice: true` converts any other audio with `to_ogg_opus` (mono, libopus, 32k)
and needs `ffmpeg` with libopus on the worker host. Without it: `ffmpeg_unavailable` ("Send an .ogg (Opus) file instead").
Check: `ffmpeg -hide_banner -encoders | rg libopus`. Only audio can be a voice note (`invalid_kind` otherwise).
Free-form sends still obey the 24h window, STOP opt-out and gateway flags (see `whatsapp-gateway.md`).

Source: huf/ai/handlers/media.py; huf/ai/whatsapp_send_file.py; huf/ai/tools/whatsapp.py; huf/ai/tools/_registry.py; huf/install.py

## 3. Automatic voice replies (Gateway.voice_reply_mode)

`Gateway.voice_reply_mode` (Select, WhatsApp only, default `Off`): `Off`, `Voice only`, `Text and voice`.
It is a Gateway field, not an Agent field; saving it on a non-WhatsApp gateway throws.

Behaviour (`whatsapp_voice_reply.py`):
- Triggers only when the inbound message is a voice note (`audio.voice == true`) and the mode is not Off.
- The reply is stripped of markdown (`plain_text`), converted with the agent's TTS model, to Ogg/Opus, then sent as a voice note.
- Replies longer than `MAX_TTS_CHARS = 1500` stay text only.
- Any failure (TTS error, ffmpeg missing, send error) is logged and falls back to the normal text reply; a reply is never lost.
- Idempotency: `Voice only` records `reply_message_id` (replay skips the send); the `Text and voice` companion note is claimed once
  per event (`huf_gw_voice_reply:<event>`, 7 days), so a replay never sends two.
- The agent also needs `tts_model` (+ `tts_voice`) and a provider key for that model.
- Saving the Gateway only warns when this host lacks ffmpeg+libopus (worker host may differ). Health reports reason
  `voice_reply_ffmpeg_missing` (warning) when mode is on and ffmpeg/libopus is missing (`ffmpeg_status()` returns `available`, `has_libopus`, `version`).

Source: huf/ai/whatsapp_voice_reply.py; huf/huf/doctype/gateway/gateway.json, gateway.py; huf/ai/whatsapp_health.py; huf/ai/tests/test_whatsapp_voice_reply.py

## 4. Recipe: voice in, voice out

Option A (no agent tools needed): set Agent `stt_model` and `tts_model` (+ `tts_voice`), set Gateway `voice_reply_mode = Voice only`
(or `Text and voice`), make sure ffmpeg with libopus exists on the worker host. The platform transcribes and answers.
Keep replies short (< 1500 chars) so they are spoken.

Option B (agent decides, e.g. images and voice on request): attach `whatsapp`, `generate_audio`, `generate_image`
(and `ocr_document`, `transcribe_audio` if the agent should call them itself) to the agent, then use instructions like:

```
When the customer sends a voice note, reply with a voice note: write a short plain-text answer (no markdown, under 1000
characters), call generate_audio with that text (leave voice and model blank), then call whatsapp with
action send_voice_note and the file_id returned by generate_audio. Do not ask for the phone number.
When asked for a picture, call generate_image, then whatsapp action send_image with the returned file_url and a short caption.
After sending, do not repeat the content as text.
```

Seed the tool attachments in `agent.json.template` via `agent_tool`; set `stt_model`, `tts_model`, `tts_voice`,
`image_generation_model` as AI Model names (see `models-and-keys.md`). Do not combine Option B voice sending with
`voice_reply_mode` on the same gateway, or the customer may get two voice notes.

Source: huf/ai/tools/_registry.py; huf/install.py; huf/ai/whatsapp_voice_reply.py
