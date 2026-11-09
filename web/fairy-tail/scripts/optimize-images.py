#!/usr/bin/env python3
"""
Fairy Tail — image & font asset pipeline.

Reads the original Lightroom JPEGs from ``web/fairy-tail/photos/`` and produces
the complete set of web renditions consumed by the site:

    web/fairy-tail/assets/photos/
        <slug>-900.jpg    long side  900 px, progressive JPEG, quality 84
        <slug>-900.webp   long side  900 px, WebP quality 80, method 6
        <slug>-1800.jpg   long side 1800 px, progressive JPEG, quality 84
        <slug>-1800.webp  long side 1800 px, WebP quality 80, method 6
        <slug>-2400.jpg   long side 2400 px, progressive JPEG, quality 84
        <slug>-2400.webp  long side 2400 px, WebP quality 80, method 6
        <slug>-3600.webp  long side 3600 px, WebP quality 80, method 6
        <slug>-full.webp  ORIGINAL pixel size (no resize), WebP q80 method 6
        lqip/<slug>.jpg   ~24 px wide, blurred, JPEG quality 45
        manifest.json     machine-readable index of every generated file

    web/fairy-tail/fonts/ six woff2 files copied verbatim from forest-gallery

Rules implemented (see task-1 and task-2 descriptions):
  * EXIF orientation is respected via ``ImageOps.exif_transpose``.
  * Originals are sRGB (verified by embedded ICC profiles), so saving plain RGB
    without an embedded profile keeps output in sRGB and strips metadata.
  * Downscale uses LANCZOS; a mild unsharp mask is applied *after* the resize
    (not on the full-size rendition, which is never resampled).
  * Aspect ratio is preserved; the long side is exactly the target size and the
    short side is rounded to the nearest pixel (never upscaled).
  * JPEG: progressive + optimize, quality 84. WebP: quality 80, method 6.
  * 2400/3600/full exist so wide, landscape and HiDPI screens do not upscale a
    1800 px rendition; 3600 and full are WebP-only (HiDPI browsers support it).
  * Originals are never modified.

The script is idempotent: an output that already exists, is non-empty and is
newer than its source is reused. A default run therefore only creates missing
or stale variants. Pass ``--force`` to regenerate everything. Pass
``--verify-only`` to re-validate existing outputs without writing.

Usage:
    python3 scripts/optimize-images.py            # generate missing/stale files
    python3 scripts/optimize-images.py --force    # regenerate all renditions
    python3 scripts/optimize-images.py --verify-only

Requires Python 3 + Pillow >= 10 (Pillow 10.2 is available in this project).
ImageMagick is not needed.
"""

from __future__ import annotations

import argparse
import filecmp
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageCms, ImageFilter, ImageOps

# --------------------------------------------------------------------------- #
# Paths (all resolved relative to this script, so it can be run from anywhere)
# --------------------------------------------------------------------------- #
SITE_DIR = Path(__file__).resolve().parents[1]        # web/fairy-tail
PHOTOS_DIR = SITE_DIR / "photos"                     # originals (read-only!)
ASSETS_DIR = SITE_DIR / "assets" / "photos"          # generated renditions
LQIP_DIR = ASSETS_DIR / "lqip"                       # generated placeholders
FONTS_DIR = SITE_DIR / "fonts"                       # font destination
FONT_SRC_DIR = SITE_DIR.parent / "forest-gallery" / "fonts"   # font source
MANIFEST_PATH = ASSETS_DIR / "manifest.json"

# --------------------------------------------------------------------------- #
# Slugs — fixed order and fixed source stems, exactly as specified by task-1.
# The source files on disk carry a "-lightroom" suffix; sources are resolved by
# stem prefix, so renaming the suffix would not break the pipeline.
# --------------------------------------------------------------------------- #
SLUG_SOURCES: list[tuple[str, str]] = [
    ("01-birch", "_7239181"),
    ("02-birch-side", "_7239182"),
    ("03-canopy", "_7239186"),
    ("04-away", "_7239188"),
    ("05-path-back", "_7239190"),
    ("06-turning", "_7239213"),
    ("07-portrait", "_7239215"),
    ("08-bending", "_7239219"),
    ("09-fern-path", "_7239224"),
    ("10-walking", "_7239225"),
    ("11-clearing", "_7239229"),
    ("12-fallen-log", "_7239243"),
    ("13-pines", "_8149506"),
    ("14-pine-path", "_8149510"),
    ("15-dream", "_8149520"),
    ("16-dream-face", "_8149522"),
    ("17-overhead", "_8149528"),
]

FONT_FILES = [
    "cormorant-garamond-cyrillic.woff2",
    "cormorant-garamond-italic-cyrillic.woff2",
    "cormorant-garamond-italic-latin.woff2",
    "cormorant-garamond-latin.woff2",
    "manrope-cyrillic.woff2",
    "manrope-latin.woff2",
]

# --------------------------------------------------------------------------- #
# Rendition matrix — the single source of truth for what gets generated.
# Each row is (manifest key, target long side, formats to write). ``None`` as
# the long side means "keep the original pixel size" (the full-size rendition).
# Rows are ordered smallest -> largest so manifest.json reads naturally and the
# legacy 900/1800 keys stay where they were.
# --------------------------------------------------------------------------- #
VARIANT_SPECS: list[tuple[str, int | None, tuple[str, ...]]] = [
    ("w900", 900, ("jpg", "webp")),      # legacy thumbnail-sized rendition
    ("w1800", 1800, ("jpg", "webp")),    # legacy default rendition
    ("w2400", 2400, ("jpg", "webp")),    # 1440 px-wide / landscape displays
    ("w3600", 3600, ("webp",)),          # near-original, HiDPI/retina (WebP)
    ("full", None, ("webp",)),           # original pixels, WebP, no resize
]
VARIANT_SPECS_BY_KEY = {
    key: (key, long_side, formats)
    for key, long_side, formats in VARIANT_SPECS
}
LEGACY_SIZE_KEYS = ("w900", "w1800")
NEW_SIZE_KEYS = ("w2400", "w3600", "full")

# --------------------------------------------------------------------------- #
# Encoding parameters (single source of truth for the whole pipeline).
# --------------------------------------------------------------------------- #
JPEG_QUALITY = 84
WEBP_QUALITY = 80
WEBP_METHOD = 6                   # slowest / best WebP compression
LQIP_REF_SIZE = 900               # long side the LQIP is derived from
LQIP_WIDTH = 24                   # placeholder width in px (~24 px "wide")
LQIP_QUALITY = 45
LQIP_BLUR_RADIUS = 0.6            # Gaussian blur applied to the tiny placeholder
SHARPEN = ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=3)

SRGB_DESCRIPTION = "srgb"         # case-insensitive marker of an sRGB profile


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def log(message: str) -> None:
    print(message, flush=True)


def human_bytes(num: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if num < 1024 or unit == "GiB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{num} B"
        num /= 1024.0
    return f"{num:.1f} GiB"


def file_bytes(path: Path) -> int:
    return path.stat().st_size


def find_source(stem: str) -> Path:
    """Resolve the single ``stem*`` JPEG original in photos/."""
    matches = sorted(p for p in PHOTOS_DIR.glob(f"{stem}*.jpg"))
    if len(matches) != 1:
        raise SystemExit(
            f"ERROR: expected exactly one source for stem {stem!r}, "
            f"found {[p.name for p in matches]}"
        )
    return matches[0]


def source_dimensions(source: Path) -> tuple[int, int]:
    """
    Original dimensions *after* EXIF-orientation correction, read from the
    header only (no full decode). Used when renditions are reused from a
    previous run so a re-run does not have to decode 111 MB of originals.
    """
    with Image.open(source) as im:
        width, height = im.size
        orientation = im.getexif().get(0x0112)  # ExifTags.Base.Orientation
    if orientation in (5, 6, 7, 8):             # these swap width and height
        width, height = height, width
    return width, height


def convert_to_srgb(img: Image.Image) -> Image.Image:
    """
    Return an RGB image in sRGB.

    All originals already embed an sRGB profile, so the fast path simply makes
    sure the mode is RGB. If a non-sRGB ICC profile ever appears, convert
    through ImageCms instead of silently misinterpreting the colours.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    icc = img.info.get("icc_profile")
    if not icc:
        return img
    try:
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        description = ImageCms.getProfileDescription(profile).strip().lower()
    except Exception:
        return img  # unreadable profile: keep pixels, strip metadata on save
    if SRGB_DESCRIPTION in description:
        return img
    log(f"    converting ICC profile {description!r} -> sRGB")
    srgb = ImageCms.createProfile("sRGB")
    return ImageCms.profileToProfile(img, profile, srgb, outputMode="RGB")


def resize_long_side(img: Image.Image, long_side: int) -> Image.Image:
    """Resize so the *long* side is exactly ``long_side``, preserving ratio."""
    width, height = img.size
    if width >= height:                       # landscape or square
        target_w, target_h = long_side, round(height * long_side / width)
    else:                                     # portrait
        target_w, target_h = round(width * long_side / height), long_side
    # The "never upscale" guard: originals are 3648x5472, far above targets,
    # but keep it explicit so the script stays safe for smaller sources.
    if target_w > width or target_h > height:
        target_w, target_h = width, height
    return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


def save_jpeg(img: Image.Image, path: Path, quality: int, progressive: bool) -> None:
    """Save JPEG with no metadata: no icc_profile/exif arguments are passed."""
    img.save(
        path,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=progressive,
    )


def save_webp(img: Image.Image, path: Path) -> None:
    """Save lossy WebP with no metadata (none is passed to Pillow)."""
    img.save(path, format="WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)


def is_fresh(output: Path, source: Path) -> bool:
    """A rendition is reusable if it exists, is non-empty and is newer."""
    try:
        return output.is_file() and output.stat().st_size > 0 and \
            output.stat().st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def avg_color_hex(img: Image.Image) -> str:
    """Average colour as '#rrggbb', computed from a 1x1 LANCZOS resize."""
    r, g, b = img.resize((1, 1), Image.Resampling.LANCZOS).getpixel((0, 0))[:3]
    return f"#{r:02x}{g:02x}{b:02x}"


def variant_tag(long_side: int | None) -> str:
    """Filename tag for a rendition: '900'/'1800'/... or 'full'."""
    return "full" if long_side is None else str(long_side)


def variant_paths(slug: str, key: str) -> dict[str, Path]:
    """Absolute output paths ({ext: path}) for one slug/variant key."""
    _, long_side, formats = VARIANT_SPECS_BY_KEY[key]
    tag = variant_tag(long_side)
    return {ext: ASSETS_DIR / f"{slug}-{tag}.{ext}" for ext in formats}


def generate_variant(base: Image.Image, slug: str, key: str) -> tuple[int, int]:
    """
    Write one variant for ``slug`` from a decoded, oriented sRGB ``base`` image.

    The 900/1800/2400 renditions are LANCZOS-downscaled and lightly sharpened;
    ``full`` is written at the original pixel size without resampling or
    sharpening (sharpening a native-resolution image only adds artefacts).
    """
    _, long_side, _ = VARIANT_SPECS_BY_KEY[key]
    if long_side is None:
        rend = base                 # no resize, no sharpen for "full"
        owns_rend = False
    else:
        rend = resize_long_side(base, long_side).filter(SHARPEN)
        owns_rend = True
    try:
        for ext, path in variant_paths(slug, key).items():
            if ext == "jpg":
                save_jpeg(rend, path, JPEG_QUALITY, progressive=True)
            else:
                save_webp(rend, path)
        return rend.size
    finally:
        if owns_rend:
            rend.close()


# --------------------------------------------------------------------------- #
# Fonts: copy the six woff2 files verbatim (byte-identical, idempotent)
# --------------------------------------------------------------------------- #
def copy_fonts(force: bool = False) -> list[str]:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in FONT_FILES:
        src = FONT_SRC_DIR / name
        dest = FONTS_DIR / name
        if not src.is_file():
            raise SystemExit(f"ERROR: missing font source {src}")
        same = dest.is_file() and filecmp.cmp(src, dest, shallow=False)
        if force or not same:
            shutil.copy2(src, dest)
            copied.append(name)
        if file_bytes(dest) != file_bytes(src):
            raise SystemExit(f"ERROR: font copy size mismatch for {name}")
    log(f"  fonts: {len(FONT_FILES)} present, {len(copied)} copied/refreshed")
    return copied


# --------------------------------------------------------------------------- #
# Per-photo processing — one photo in memory at a time
# --------------------------------------------------------------------------- #
def process_photo(slug: str, source: Path, force: bool = False) -> dict:
    """
    Generate (or reuse) every rendition for one photo and return its manifest
    entry with real generated dimensions and byte sizes.

    Freshness is tracked per variant, so a default run only encodes the
    variants that are missing or older than the original — existing 900/1800/
    lqip files from earlier runs are left completely untouched.
    """
    paths = {
        key: variant_paths(slug, key)
        for key, _, _ in VARIANT_SPECS
    }
    lqip_path = LQIP_DIR / f"{slug}.jpg"
    stale = {
        key: force or any(not is_fresh(p, source) for p in paths[key].values())
        for key in paths
    }
    lqip_stale = force or not is_fresh(lqip_path, source)
    need_work = any(stale.values()) or lqip_stale
    generated_keys = [key for key in paths if stale[key]]
    if lqip_stale:
        generated_keys.append("lqip")

    if need_work:
        # ---- decode the original once (respecting EXIF orientation) ------- #
        with Image.open(source) as opened:
            opened.load()
            oriented = ImageOps.exif_transpose(opened)  # copy when needed
        try:
            rgb = convert_to_srgb(oriented)  # sRGB; metadata still in .info
            rgb.info = {}                    # nothing may leak into outputs
            base_w, base_h = rgb.size
            for key, _, _ in VARIANT_SPECS:
                if stale[key]:
                    generate_variant(rgb, slug, key)
            if lqip_stale:
                # LQIP: derive from the 900 px rendering, then blur the tiny copy.
                ref = resize_long_side(rgb, LQIP_REF_SIZE)
                lqip = ref.resize(
                    (LQIP_WIDTH, max(1, round(ref.height * LQIP_WIDTH / ref.width))),
                    Image.Resampling.LANCZOS,
                ).filter(ImageFilter.GaussianBlur(LQIP_BLUR_RADIUS))
                save_jpeg(lqip, lqip_path, LQIP_QUALITY, progressive=False)
                lqip.close()
                ref.close()
        finally:
            rgb.close()
            oriented.close()
    else:
        # Reuse path stays cheap: read only the source header for the original
        # dimensions (orientation-aware) instead of decoding the full JPEG.
        base_w, base_h = source_dimensions(source)

    # ---- build the manifest entry from the files that are now on disk ----- #
    # For reused outputs the dimensions are read back from the files, so the
    # manifest always reports what actually exists rather than assumptions.
    sizes_entry: dict[str, dict] = {}
    for key, long_side, formats in VARIANT_SPECS:
        dims: tuple[int, int] | None = None
        fmt: dict[str, dict] = {}
        for ext, path in paths[key].items():
            expected_format = "JPEG" if ext == "jpg" else "WEBP"
            with Image.open(path) as probe:
                if probe.format != expected_format:
                    raise SystemExit(
                        f"ERROR: wrong output format for {slug}/{key}: "
                        f"{probe.format}"
                    )
                if dims is None:
                    dims = probe.size
                elif probe.size != dims:
                    raise SystemExit(
                        f"ERROR: jpg/webp size mismatch for {slug}/{key}"
                    )
            fmt[ext] = {"file": path.name, "bytes": file_bytes(path)}
        if dims is None:  # cannot happen: every variant writes >=1 format
            raise SystemExit(f"ERROR: no rendition produced for {slug}/{key}")
        if long_side is None:
            if dims != (base_w, base_h):
                raise SystemExit(
                    f"ERROR: full rendition size {dims} != original "
                    f"{(base_w, base_h)} for {slug}"
                )
        elif max(dims) != long_side:
            raise SystemExit(
                f"ERROR: {key} long side {max(dims)} != {long_side} for {slug}"
            )
        sizes_entry[key] = {"width": dims[0], "height": dims[1], **fmt}

    with Image.open(lqip_path) as lqip_probe:
        lqip_w, lqip_h = lqip_probe.size
        if lqip_probe.format != "JPEG":
            raise SystemExit(f"ERROR: LQIP is not JPEG for {slug}")

    # avgColor from the 900 px JPEG (opened, downscaled to 1x1, closed).
    with Image.open(paths["w900"]["jpg"]) as ref:
        avg = avg_color_hex(ref)

    entry = {
        "slug": slug,
        "source": source.name,
        "width": base_w,
        "height": base_h,
        "ratio": round(base_w / base_h, 4),
        "original": {"width": base_w, "height": base_h},
        # VARIANT_SPECS is ascending, so keys read w900, w1800, w2400,
        # w3600, full — legacy fields preserved, new fields appended.
        "sizes": sizes_entry,
        "lqip": {
            "file": f"lqip/{lqip_path.name}",
            "width": lqip_w,
            "height": lqip_h,
            "bytes": file_bytes(lqip_path),
        },
        "avgColor": avg,
    }
    status = "regenerated [" + ", ".join(generated_keys) + "]" \
        if need_work else "reused"
    total = sum(
        fmt["bytes"] for size in sizes_entry.values()
        for ext, fmt in size.items() if ext in ("jpg", "webp")
    ) + entry["lqip"]["bytes"]
    dims_log = " ".join(
        f"{key}:{sizes_entry[key]['width']}x{sizes_entry[key]['height']}"
        for key, _, _ in VARIANT_SPECS
    )
    log(
        f"  {slug:14s} {base_w}x{base_h} -> {dims_log}, "
        f"lqip:{lqip_w}x{lqip_h} ({human_bytes(total)}, {status})"
    )
    return entry


# --------------------------------------------------------------------------- #
# Verification: every manifest entry is re-opened and cross-checked on disk
# --------------------------------------------------------------------------- #
def verify(manifest: list[dict]) -> None:
    log("\nVerifying generated assets ...")
    errors: list[str] = []
    counts = {"legacy": 0, "new": 0, "lqip": 0}
    for entry in manifest:
        orig_wh = (entry["width"], entry["height"])
        original = entry.get("original")
        if not isinstance(original, dict) or \
                (original.get("width"), original.get("height")) != orig_wh:
            errors.append(f"{entry['slug']}: bad or missing top-level 'original'")
        for key, long_side, formats in VARIANT_SPECS:
            meta = entry["sizes"].get(key)
            if meta is None:
                errors.append(f"{entry['slug']}: missing sizes.{key}")
                continue
            present = {ext for ext in meta if ext in ("jpg", "webp")}
            if present != set(formats):
                errors.append(
                    f"{entry['slug']}/{key}: formats {sorted(present)} "
                    f"!= expected {sorted(formats)}"
                )
            if long_side is None:
                if (meta["width"], meta["height"]) != orig_wh:
                    errors.append(
                        f"{entry['slug']}/{key}: not original size "
                        f"({meta['width']}x{meta['height']} != "
                        f"{orig_wh[0]}x{orig_wh[1]})"
                    )
            elif max(meta["width"], meta["height"]) != long_side:
                errors.append(
                    f"{entry['slug']}/{key}: long side "
                    f"{max(meta['width'], meta['height'])} != {long_side}"
                )
            bucket = "legacy" if key in LEGACY_SIZE_KEYS else "new"
            for ext in formats:
                fmt = meta.get(ext)
                if not isinstance(fmt, dict):
                    errors.append(f"{entry['slug']}/{key}: missing {ext} entry")
                    continue
                path = ASSETS_DIR / fmt["file"]
                if not path.is_file():
                    errors.append(f"missing {path}")
                    continue
                if path.stat().st_size != fmt["bytes"] or fmt["bytes"] <= 0:
                    errors.append(f"size mismatch {path}")
                with Image.open(path) as im:
                    im.verify()                 # integrity check
                with Image.open(path) as im:
                    expected = "JPEG" if ext == "jpg" else "WEBP"
                    if im.format != expected:
                        errors.append(f"format {path}: {im.format}")
                    if im.size != (meta["width"], meta["height"]):
                        errors.append(f"dimensions {path}: {im.size}")
                counts[bucket] += 1
        lqip_path = LQIP_DIR / Path(entry["lqip"]["file"]).name
        if not lqip_path.is_file():
            errors.append(f"missing {lqip_path}")
        else:
            with Image.open(lqip_path) as im:
                im.verify()
            counts["lqip"] += 1

    # Expected: 17 slugs x 2 legacy formats x 2 legacy sizes = 68 legacy,
    # 17 slugs x (2400 jpg+webp + 3600 webp + full webp) = 68 new, 17 LQIP.
    expected = {
        "legacy": len(manifest) * 2 * 2,
        "new": len(manifest) * (2 + 1 + 1),
        "lqip": len(manifest),
    }
    log(
        f"  validated {sum(counts.values())} image files = "
        f"{counts['legacy']}/{expected['legacy']} legacy (900/1800) + "
        f"{counts['new']}/{expected['new']} new (2400/3600/full) + "
        f"{counts['lqip']}/{expected['lqip']} LQIP"
    )
    for bucket, expected_count in expected.items():
        if counts[bucket] != expected_count:
            errors.append(
                f"{bucket}: expected {expected_count} files, got {counts[bucket]}"
            )
    if errors:
        for error in errors:
            log(f"  FAIL {error}")
        raise SystemExit(f"ERROR: verification failed with {len(errors)} problem(s)")
    log("  all renditions valid (format, dimensions, byte sizes)\n")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true",
                        help="regenerate all renditions even if up to date")
    parser.add_argument("--verify-only", action="store_true",
                        help="only verify existing outputs, do not generate")
    args = parser.parse_args()

    started = time.time()
    log(f"Fairy Tail asset pipeline — source: {PHOTOS_DIR}")
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LQIP_DIR.mkdir(parents=True, exist_ok=True)

    if not args.verify_only:
        copy_fonts(force=args.force)
        log(f"\nProcessing {len(SLUG_SOURCES)} photos -> {ASSETS_DIR}")

    manifest: list[dict] = []
    for slug, stem in SLUG_SOURCES:
        source = find_source(stem)
        if args.verify_only:
            # In verify-only mode the manifest is the source of truth.
            continue
        manifest.append(process_photo(slug, source, force=args.force))

    if args.verify_only:
        if not MANIFEST_PATH.is_file():
            raise SystemExit(f"ERROR: no manifest at {MANIFEST_PATH}")
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    else:
        # Atomic-ish write so a crashed run never leaves half a manifest.
        tmp = MANIFEST_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, MANIFEST_PATH)
        log(f"\nWrote {MANIFEST_PATH} ({human_bytes(file_bytes(MANIFEST_PATH))})")

    verify(manifest)

    def bytes_for(keys: tuple[str, ...]) -> int:
        return sum(
            fmt["bytes"]
            for entry in manifest
            for key in keys
            for ext, fmt in entry["sizes"][key].items()
            if ext in ("jpg", "webp")
        )

    legacy_bytes = bytes_for(LEGACY_SIZE_KEYS)
    new_bytes = bytes_for(NEW_SIZE_KEYS)
    lqip_bytes = sum(entry["lqip"]["bytes"] for entry in manifest)
    total = legacy_bytes + new_bytes + lqip_bytes
    legacy_count = len(manifest) * 2 * 2                    # 900 + 1800
    new_count = len(manifest) * (2 + 1 + 1)                 # 2400 + 3600 + full
    log(
        f"Done in {time.time() - started:.1f}s: "
        f"{legacy_count} legacy + {new_count} high-res renditions + "
        f"{len(manifest)} LQIP + manifest, {human_bytes(total)} total "
        f"(legacy {human_bytes(legacy_bytes)}, "
        f"new {human_bytes(new_bytes)}, lqip {human_bytes(lqip_bytes)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
