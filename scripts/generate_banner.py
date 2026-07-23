#!/usr/bin/env python3
"""Generate the OmniChain README banner with gemini-3.1-flash-image (nano banana).

Reads the API key straight from the repo .env so the secret is never printed or
passed on the command line. Writes the PNG to imgs/omnichain_banner.png.

Usage:
    uv run --project backend python scripts/generate_banner.py
    uv run --project backend python scripts/generate_banner.py --aspect 16:9 --out imgs/foo.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from google import genai
from google.genai import types

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = "gemini-3.1-flash-image"

# The scene/subject is style-independent; the closing STYLE directive swaps the look.
BASE_PROMPT = (
    "A wide banner titled 'OMNI-CHAIN' in bold, glowing, neon text across the top. "
    "The composition is an energetic and surreal 'Chaos Jam Session' featuring four "
    "eclectic pop culture icons performing together on a stage that is a chaotic "
    "mashup of a futuristic concert setup, a digital workflow interface, and deep "
    "space elements.\n"
    "Characters (Left to Right, visibly performing):\n"
    "Dumble Dior: Dumbledore with a long grey beard and hair, wearing a custom silk "
    "wizard robe covered in Supreme logo patterns and Gucci-style interlocking 'G's, "
    "multiple chunky gold chains with magic-themed pendants, and Yeezy sneakers, "
    "holding a gold microphone with one hand and casting a minor spell with the other.\n"
    "Gucci Mane: The Atlanta rapper, wearing oversized square sunglasses, heavily iced "
    "out diamond chains (including a custom 'OMNI' pendant), a flashy designer "
    "tracksuit, and throwing a diamond hands sign while rapping into a microphone.\n"
    "Carl Sagan: Wearing a corduroy blazer over his signature turtleneck, standing "
    "behind a transparent interactive desk displaying holographic galaxy simulations, "
    "mathematical formulas, and data visualizations of a 4-stage AI prompt chaining "
    "pipeline.\n"
    "Trey Anastasio: The Phish guitarist, with his iconic red hair and beard, wearing "
    "casual stage clothes, shredding on his signature hollow-body guitar (a Languedoc).\n"
    "Action & Composition: All four characters are visibly connected in a sequential "
    "workflow by pulsing, glowing digital chains made of light and code symbols, which "
    "visually represent the data flowing from one stage to the next. The stage itself "
    "is made of floating, illuminated platforms. The background is a chaotic, saturated "
    "cosmic nebula mixed with swirling galaxies that look like disco balls, geometric "
    "vector data stream patterns, and dynamic concert stage lighting in deep purples, "
    "blues, magentas, and electric greens.\n"
)

# Named style directives appended to BASE_PROMPT. Pick with --style.
STYLES = {
    "popart": (
        "The overall style is a high-quality, saturated pop art digital illustration "
        "with photorealistic details on the characters."
    ),
    "cinematic": (
        "The overall style is a photorealistic cinematic movie poster: dramatic "
        "volumetric stage lighting, shallow depth of field, film-grain, ray-traced "
        "reflections, and lifelike skin, fabric, and hair textures. The four "
        "performers look like real photographed people captured mid-performance, "
        "richly detailed and grounded, while the cosmic background stays vivid but "
        "slightly out of focus behind them. Shot on a full-frame cinema camera, 35mm, "
        "high dynamic range."
    ),
    "photoreal": (
        "The overall style is an ultra-realistic concert photograph: natural, "
        "physically accurate lighting from real stage rigs and spotlights, true-to-life "
        "human skin pores, fabric weave, and metal glint on the jewelry, authentic "
        "motion blur on hands and instruments, and realistic haze/atmosphere. It should "
        "look like a real press photo of four performers on stage, not an illustration. "
        "The futuristic UI and cosmic elements read as real projected holograms and LED "
        "stage screens behind them. Photojournalistic, 50mm lens, crisp focus on faces."
    ),
    "neon-noir": (
        "The overall style is a moody, photorealistic neon-noir look: cinematic teal "
        "and magenta rim lighting, deep shadows, wet reflective stage floor, volumetric "
        "haze, and lifelike textures on the characters. Realistic humans, dramatic "
        "contrast, premium editorial photography feel."
    ),
}


def _load_api_key(env_file: Path) -> str:
    """Pull GEMINI_API_KEY / GOOGLE_API_KEY from .env without exporting it globally."""
    if not env_file.is_file():
        sys.exit(f"error: {env_file} not found")
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            value = value.strip().strip('"').strip("'")
            if value and value != "your-api-key":
                return value
    sys.exit("error: no GEMINI_API_KEY/GOOGLE_API_KEY set in .env")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the OmniChain README banner.")
    parser.add_argument("--out", type=Path, default=None, help="output PNG path")
    parser.add_argument(
        "--style",
        default="popart",
        choices=sorted(STYLES),
        help="visual style directive (default: popart)",
    )
    parser.add_argument("--aspect", default="21:9", help="aspect ratio (e.g. 21:9, 16:9)")
    parser.add_argument("--size", default="2K", help="image size: 512, 1K, 2K, 4K")
    parser.add_argument(
        "--edit",
        type=Path,
        default=None,
        help="edit an existing banner instead of generating from scratch",
    )
    parser.add_argument(
        "--instruction",
        default=None,
        help="edit instruction (required with --edit)",
    )
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    args = parser.parse_args()

    # Force Developer-API (key) auth: image gen isn't served from Vertex 'global'.
    client = genai.Client(api_key=_load_api_key(args.env_file))
    image_config = types.ImageConfig(aspect_ratio=args.aspect, image_size=args.size)

    if args.edit is not None:
        if not args.instruction:
            sys.exit("error: --instruction is required with --edit")
        src = args.edit if args.edit.is_absolute() else (Path.cwd() / args.edit).resolve()
        if not src.is_file():
            sys.exit(f"error: --edit image not found: {src}")
        out = args.out or src.with_name(f"{src.stem}_edited{src.suffix}")
        out = out if out.is_absolute() else (Path.cwd() / out).resolve()
        print(f"Editing {src.name} ({args.aspect}, {args.size}) with {MODEL}...")
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                args.instruction,
                types.Part.from_bytes(data=src.read_bytes(), mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=image_config,
            ),
        )
    else:
        out = args.out or (REPO_ROOT / "imgs" / f"omnichain_banner_{args.style}.png")
        out = out if out.is_absolute() else (Path.cwd() / out).resolve()
        prompt = f"{BASE_PROMPT}{STYLES[args.style]}"
        print(f"Generating banner [{args.style}] ({args.aspect}, {args.size}) with {MODEL}...")
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=image_config,
            ),
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    saved = False
    for part in response.parts:
        if part.text:
            print(f"[model] {part.text}")
        elif part.inline_data is not None:
            out.write_bytes(part.inline_data.data)
            saved = True

    if not saved:
        sys.exit("error: model returned no image (see any text above)")
    kb = out.stat().st_size / 1024
    print(f"Saved {out.relative_to(REPO_ROOT)} ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
