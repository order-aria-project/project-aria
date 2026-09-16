from __future__ import annotations

import ctypes
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ROOT = PROJECT_ROOT / ".parakeet_tdt_v3_venv"
SITE = VENV_ROOT / "Lib" / "site-packages"

# Keep all CUDA runtime lookup inside the isolated ASR environment.
_DLL_DIRS = [
    SITE / "nvidia" / "cublas" / "bin",
    SITE / "nvidia" / "cuda_nvrtc" / "bin",
    SITE / "nvidia" / "cuda_runtime" / "bin",
    SITE / "nvidia" / "cudnn" / "bin",
]

_handles = []
for directory in _DLL_DIRS:
    if directory.exists():
        os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
        try:
            _handles.append(os.add_dll_directory(str(directory)))
        except Exception:
            pass

os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import soundfile as sf
import torch
from transformers import AutoModelForTDT, AutoProcessor

MODEL_ID = "nvidia/parakeet-tdt-0.6b-v3"


def load_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device == "cuda" else torch.float32

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    model = AutoModelForTDT.from_pretrained(
        MODEL_ID,
        dtype=dtype,
        device_map=device,
    )
    model.eval()
    return processor, model, device, dtype


def transcribe(processor, model, device, dtype, wav_path: str) -> str:
    audio, sample_rate = sf.read(str(wav_path))
    if getattr(audio, "ndim", 1) > 1:
        audio = audio[:, 0]

    inputs = processor(
        audio=audio,
        sampling_rate=sample_rate,
        return_tensors="pt",
    )
    inputs = {
        key: (value.to(device) if hasattr(value, "to") else value)
        for key, value in inputs.items()
    }

    if device == "cuda" and "input_features" in inputs:
        inputs["input_features"] = inputs["input_features"].to(dtype)

    started = time.perf_counter()

    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            return_dict_in_generate=True,
            max_new_tokens=256,
        )

    decoded = processor.batch_decode(
        generated.sequences,
        skip_special_tokens=True,
    )
    text = decoded[0].strip() if decoded else ""

    elapsed = time.perf_counter() - started
    return text, elapsed


def main() -> None:
    processor, model, device, dtype = load_model()
    print("READY", flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            text, elapsed = transcribe(
                processor,
                model,
                device,
                dtype,
                request["wav_path"],
            )

            print(
                json.dumps(
                    {
                        "ok": True,
                        "text": text,
                        "elapsed": elapsed,
                        "device": device,
                    }
                ),
                flush=True,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": str(exc),
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
