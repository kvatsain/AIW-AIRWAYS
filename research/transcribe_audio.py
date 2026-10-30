"""Local-only transcription of the supplied challenge recording."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tmp" / "audio-packages"))
os.environ["HF_HOME"] = str(ROOT / "tmp" / "huggingface")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
from faster_whisper import WhisperModel
import av

# PyAV 19 removed metadata_errors; faster-whisper 1.2.1 still passes it.
av_open = av.open
def compatible_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return av_open(*args, **kwargs)
av.open = compatible_av_open

source = ROOT / "references" / "Problem2.m4a"
model_name = sys.argv[1] if len(sys.argv) > 1 else "base"
model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=4,
                     download_root=str(ROOT / "tmp" / "whisper-models"))
segments, info = model.transcribe(str(source), beam_size=5, vad_filter=True,
                                  condition_on_previous_text=False)
output = ROOT / "research" / "Problem2_transcript.txt"
items = []
with output.open("w", encoding="utf-8") as handle:
    handle.write(f"Local automatic transcription; model: faster-whisper {model_name}, CPU int8.\n")
    handle.write(f"Source: {source.name}\nDetected language: {info.language}; probability: {info.language_probability:.3f}\n")
    handle.write("Transcription may contain recognition errors; verify important details against the recording.\n\n")
    handle.flush()
    print(f"Language={info.language}, duration={info.duration:.1f}s", flush=True)
    for segment in segments:
        item = {"start": segment.start, "end": segment.end, "text": segment.text.strip(),
                "avg_logprob": segment.avg_logprob}
        items.append(item)
        line = f"[{segment.start:07.2f}–{segment.end:07.2f}] {segment.text.strip()}"
        handle.write(line + "\n")
        handle.flush()
        print(line, flush=True)
(ROOT / "research" / "Problem2_transcript.json").write_text(
    json.dumps({"source": source.name, "model": model_name, "language": info.language,
                "language_probability": info.language_probability, "duration_seconds": info.duration,
                "segments": items}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Saved {output}", flush=True)
