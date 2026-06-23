"""Generate scene images (OpenAI gpt-image-1) and upload them to R2."""

from __future__ import annotations

import base64

from .assemble import slug_to_media_folder

IMAGE_SIZE = "1536x1024"  # 16:9-ish; supported by gpt-image-1
MEDIA_VERSION = "1"  # version folder, matching the import convention


def _generate_png(prompt: str, model: str) -> bytes:
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
        png = _generate_png(spec["prompt"], model)
        key = f"{folder}/{MEDIA_VERSION}/{spec['filename']}"
        url = upload_media(png, key, "image/png")
        scenario_json["scenes"][scene_id]["image"] = url
        uploaded[scene_id] = url
    return uploaded
