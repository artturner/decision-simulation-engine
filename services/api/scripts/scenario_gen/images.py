"""Generate scene images (OpenAI gpt-image-1) and upload them to R2."""

from __future__ import annotations

import base64

from .assemble import slug_to_media_folder

IMAGE_SIZE = "1536x1024"  # 16:9-ish; supported by gpt-image-1
MEDIA_VERSION = "1"  # version folder, matching the import convention
MAX_WIDTH = 1600  # the app renders scenes at ~700 CSS px; 1600 covers retina
PALETTE_COLORS = 256


def optimize_png(png: bytes) -> bytes:
    """Shrink a scene PNG for web delivery: cap width at MAX_WIDTH and quantize
    to a dithered 256-color palette. Returns the original bytes unless the
    optimized version is at least 20% smaller."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB")
    if img.size[0] > MAX_WIDTH:
        height = round(img.size[1] * MAX_WIDTH / img.size[0])
        img = img.resize((MAX_WIDTH, height), Image.LANCZOS)
    pal = img.quantize(
        colors=PALETTE_COLORS,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    )
    buf = io.BytesIO()
    pal.save(buf, format="PNG", optimize=True)
    out = buf.getvalue()
    return out if len(out) < len(png) * 0.8 else png


def render_png(prompt: str, model: str) -> bytes:
    """Generate a single PNG from a prompt (no upload). Used by --images and by
    the redo-images preview pass."""
    from openai import OpenAI

    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set — required for --images.")
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    resp = client.images.generate(
        model=model, prompt=prompt, size=IMAGE_SIZE, n=1
    )
    b64 = resp.data[0].b64_json
    if not b64:
        raise RuntimeError("Image API returned no image data.")
    return base64.b64decode(b64)


def generate_and_upload(
    scenario_json: dict,
    slug: str,
    prompts: dict[str, dict],
    model: str,
) -> dict[str, str]:
    """Generate each scene image, upload to R2, and rewrite scene ``image`` to the
    absolute URL. Returns {scene_id: url}. Mutates ``scenario_json`` in place.
    """
    from app.services.storage import upload_media

    folder = slug_to_media_folder(slug)
    uploaded: dict[str, str] = {}
    for scene_id, spec in prompts.items():
        png = render_png(spec["prompt"], model)
        key = f"{folder}/{MEDIA_VERSION}/{spec['filename']}"
        url = upload_media(optimize_png(png), key, "image/png")
        scenario_json["scenes"][scene_id]["image"] = url
        uploaded[scene_id] = url
    return uploaded
