# Documentation claim auditor

```text
text-to-speech-claim-audit
```

An offline static checker comparing documentation promises with Python AST evidence. Version 0.1.0, Python 3.9 or later, no runtime dependencies. Source files are parsed and never executed. The checker uses no network and writes no files.

Install and run:

```sh
python3 -m pip install .
text-to-speech-claim-audit /path/to/project
python3 -m text_to_speech_claim_audit /path/to/project --json
python3 -m unittest discover -s tests -v
```

The scanner reads root README.md and Markdown files beneath any docs path component. It checks paragraphs, excludes fenced blocks, and includes inline code. Matching lowercases text, expands negative contractions, replaces hyphens with spaces, and collapses whitespace. Negative templates take precedence. Exact templates use word boundaries, longest first and alphabetical ties.

A positive template without production evidence yields one HIGH finding; evidence only in tests yields MEDIUM. A negative template with production evidence yields one HIGH finding. A project without Python files can still contradict a positive promise. A negative promise alone passes. Each family produces at most one finding.

```text
Positive template example: speaks text aloud
Negative template example: does not convert text to speech
Rules: documented-tts-claim-false, documented-no-tts-claim-false
```

Evidence includes bound engine operations from supported libraries; bark generate_audio; a transformers pipeline with the appropriate literal task; and hosted audio.speech.create calls. Imports and constructions alone do not suffice. Playback, file loading, recognition, music generation, CLI subprocess invocations and string mentions are excluded. Aliases and chained constructions are resolved within a module; local definitions shadow imports. Static analysis does not prove runtime success or follow imports between files.

```text
Supported engines: pyttsx3, gTTS, edge-tts, Coqui TTS, kokoro, SAPI.
```

Symlinked files and directories are skipped. Python files in fixtures, docs and examples are excluded. Files in tests directories or named test_*.py or *_test.py count separately. Syntax-invalid files provide no evidence.

Options:

- `--json`: emit an object with status, findings, claims, production_evidence and test_evidence. Each finding contains rule, severity and message.
- `--verbose`: include evidence flags and matched families in text output.
- `--ignore PATH`: omit a relative path prefix; repeat for more paths.
- `--fail-on HIGH|MEDIUM|LOW`: failure threshold, default HIGH.
- `--version`: print 0.1.0.

Exit status is 0 below the threshold, 2 for findings at or above it, and 1 for usage or I/O errors. MEDIUM findings remain visible with the default threshold.

Related tools cover independent dimensions:

```text
voice-claim-audit: recognition, never synthesis. A tool that both transcribes
and speaks is evaluated independently for each kind of evidence.
audio-generation-claim-audit: excludes speech synthesis. Music-only AudioLDM
and MusicGen operations do not qualify here. bark generate_audio is the
deliberate exception because it generates speech from text.
microphone-claim-audit: capture, never synthesis.
speaker-claim-audit: speaker identification and diarization, never synthesis.
```

Build with `python3 -m build`. Distributed under the MIT license.
