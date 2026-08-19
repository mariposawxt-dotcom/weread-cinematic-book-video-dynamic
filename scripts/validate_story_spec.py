"""Validate the text and dynamic-title contract for a WeRead video.

This helper uses only the Python standard library so it can run in a bundled
runtime without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


OLD_DEFAULTS = ("活着", "余华")
BUNDLED_SFX = (
    "assets/gear-carousel.wav",
    "assets/title-drop.wav",
)
BUNDLED_ASSETS = ("assets/default-opening.png",) + BUNDLED_SFX


def fail(message: str) -> None:
    raise ValueError(message)


def validate(spec: dict[str, Any]) -> list[str]:
    title = str(spec.get("book_title", "")).strip()
    author = str(spec.get("author", "")).strip()
    if not title:
        fail("book_title is required")
    if not author:
        fail("author is required")
    if spec.get("cover_text_embedded") is not True:
        fail("cover_text_embedded must be true; do not add cover text later")
    if spec.get("title_position_consistent") is not True:
        fail("title_position_consistent must be true across all covers")

    audio_input = spec.get("audio_input")
    if not isinstance(audio_input, dict):
        fail("audio_input must describe the single uploaded video/audio")
    if str(audio_input.get("source", "")).strip() != "user_upload":
        fail("audio_input.source must be user_upload")
    if not str(audio_input.get("filename", "")).strip():
        fail("audio_input.filename is required")
    derived = audio_input.get("derived_segments")
    if derived != ["intro", "title", "narration"]:
        fail("single upload must derive intro, title, narration segments in order")
    if audio_input.get("split_verified") is not True:
        fail("automatic audio split must be verified")
    title_segment = audio_input.get("title_segment")
    if not isinstance(title_segment, dict):
        fail("audio_input.title_segment must describe the measured title audio")
    if str(title_segment.get("expected_text", "")).strip() != title:
        fail("title_segment.expected_text must match the confirmed book title")
    if title_segment.get("trimmed_leading_silence") is not True:
        fail("title audio must trim leading silence before the spoken title")
    if title_segment.get("speech_verified") is not True:
        fail("title audio speech must be verified after trimming")
    if str(title_segment.get("duration_source", "")).strip() != "measured_after_trim":
        fail("title duration must come from the measured trimmed file")

    sync = spec.get("timing_sync")
    if not isinstance(sync, dict):
        fail("timing_sync must describe shared Remotion/HyperFrames timing")
    if sync.get("shared_manifest") is not True:
        fail("Remotion and HyperFrames must use one shared timing manifest")
    if str(sync.get("title_duration_source", "")).strip() != "max(title_audio_duration,title_drop_duration)":
        fail("title scene duration must cover the measured title and title-drop audio")
    if sync.get("legacy_fixed_title_duration_rejected") is not True:
        fail("legacy fixed title durations must be rejected")

    sfx = spec.get("sfx")
    if not isinstance(sfx, dict):
        fail("sfx must describe the approved Skill-bundled sound effects")
    if str(sfx.get("source", "")).strip() != "skill_bundle_generated":
        fail("sfx.source must be skill_bundle_generated")
    if sfx.get("assets") != list(BUNDLED_SFX):
        fail("sfx.assets must use the approved bundled sound effects")
    if not str(sfx.get("tool", "")).strip():
        fail("sfx.tool is required")
    if not str(sfx.get("license", "")).strip():
        fail("sfx.license is required")
    durations = sfx.get("durations")
    if not isinstance(durations, dict) or not 1.5 <= float(durations.get("gear", 0)) <= 3.0 or not 0.8 <= float(durations.get("title_drop", 0)) <= 2.0:
        fail("sfx durations must be measured and within the expected ranges")
    if sfx.get("speech_checked") is not True:
        fail("bundled SFX must pass speech-pollution checks")

    opening = spec.get("opening")
    if not isinstance(opening, dict):
        fail("opening must describe the per-run generated opening image")
    if str(opening.get("source", "")).strip() != "skill_bundle":
        fail("opening.source must be skill_bundle")
    if opening.get("asset") != "assets/default-opening.png":
        fail("opening.asset must use the bundled default opening image")
    if opening.get("aspect_ratio") != "9:16":
        fail("opening must be generated in 9:16")
    if opening.get("platform_ui_free") is not True:
        fail("opening must not contain platform UI")

    title_reveal = str(spec.get("title_reveal", ""))
    if title not in title_reveal or f"{author}/著" not in title_reveal:
        fail("title_reveal does not contain the confirmed title and author")

    segments = spec.get("segments")
    if not isinstance(segments, list) or len(segments) != 5:
        fail("segments must contain exactly five items")

    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            fail(f"segment {index} must be an object")
        zh = str(segment.get("zh", "")).strip()
        if zh.count("，") != 1:
            fail(f"segment {index} must contain exactly one Chinese comma")
        if any(mark in zh for mark in ("；", "、")):
            fail(f"segment {index} contains a forbidden clause/list separator")
        compact = "".join(ch for ch in zh if "\u4e00" <= ch <= "\u9fff")
        if not 12 <= len(compact) <= 24:
            fail(f"segment {index} must contain 12–24 Chinese characters")
        if "\n" in zh or "\r" in zh:
            fail(f"segment {index} must be one line")
        if not str(segment.get("en", "")).strip():
            fail(f"segment {index} is missing the English subtitle")

    prompts = spec.get("cover_prompts")
    if not isinstance(prompts, list) or len(prompts) != 12:
        fail("cover_prompts must contain twelve prompts")
    author_label = f"{author}/著"
    style_markers = ("故事感", "旧印刷", "胶片", "weathered", "cinematic typography", "integrated")
    position_markers = ("统一位置", "统一标题", "same title block", "consistent title position")
    for index, prompt in enumerate(prompts, start=1):
        prompt_text = str(prompt)
        if title not in prompt_text or author_label not in prompt_text:
            fail(f"cover prompt {index} does not use the confirmed title/author")
        if "嵌入" not in prompt_text and "printed" not in prompt_text.lower():
            fail(f"cover prompt {index} does not require text embedded in the image")
        if not any(marker in prompt_text or marker.lower() in prompt_text.lower() for marker in style_markers):
            fail(f"cover prompt {index} lacks a story-driven typography treatment")
        if not any(marker in prompt_text or marker.lower() in prompt_text.lower() for marker in position_markers):
            fail(f"cover prompt {index} does not lock the title position")

    serialized = json.dumps(spec, ensure_ascii=False)
    if title != "活着" and "活着" in serialized:
        fail("stale title 活着 remains in the generated spec")
    if author != "余华" and "余华" in serialized:
        fail("stale author 余华 remains in the generated spec")

    return [
        "PASS: five one-sentence segments",
        "PASS: each segment has exactly one comma",
        "PASS: title and author are dynamic",
        "PASS: twelve cover prompts embed title/author",
        "PASS: one upload derives intro/title/narration and uses approved bundled sound effects",
        "PASS: opening image uses the bundled default opening",
        "PASS: no stale 活着/余华 text",
    ]


def self_test() -> dict[str, Any]:
    prompt = "电影感旧胶片封面，书名《天幕红尘》，作者豆豆/著，旧印刷质感、故事感，文字直接嵌入图片并与窗面光影融合，统一标题位置"
    return {
        "book_title": "天幕红尘",
        "author": "豆豆",
        "title_reveal": "《天幕红尘》 豆豆/著",
        "cover_text_embedded": True,
        "title_position_consistent": True,
        "audio_input": {
            "source": "user_upload",
            "filename": "voice.mp4",
            "derived_segments": ["intro", "title", "narration"],
            "split_verified": True,
            "title_segment": {
                "expected_text": "天幕红尘",
                "trimmed_leading_silence": True,
                "speech_verified": True,
                "duration_source": "measured_after_trim",
            },
        },
        "timing_sync": {
            "shared_manifest": True,
            "title_duration_source": "max(title_audio_duration,title_drop_duration)",
            "legacy_fixed_title_duration_rejected": True,
        },
        "sfx": {
            "source": "skill_bundle_generated",
            "assets": list(BUNDLED_SFX),
            "tool": "FFmpeg re-synthesis from an AI-generated reference",
            "license": "user-confirmed redistribution permission",
            "durations": {"gear": 1.988, "title_drop": 1.478},
            "speech_checked": True,
        },
        "opening": {
            "source": "skill_bundle",
            "asset": "assets/default-opening.png",
            "aspect_ratio": "9:16",
            "platform_ui_free": True,
        },
        "cover_prompts": [prompt] * 12,
        "segments": [
            {"zh": "别把成功当地图，每条路都有代价。", "en": "Do not use success as a map; every road has a cost."},
            {"zh": "看清自己的位置，才能走稳自己的路。", "en": "See your place clearly, then walk your own road."},
            {"zh": "不必迎合所有人，先听见自己的声音。", "en": "You need not please everyone; hear your own voice."},
            {"zh": "真正的清醒，不是拒绝世界而是看懂世界。", "en": "Clarity is not rejecting the world, but understanding it."},
            {"zh": "愿你保持清醒，也愿你走得自由。", "en": "May you stay clear, and may you walk free."},
        ],
    }


def validate_bundled_assets() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    missing = []
    for relative_path in BUNDLED_ASSETS:
        asset_path = skill_root / relative_path
        if not asset_path.is_file() or asset_path.stat().st_size == 0:
            missing.append(relative_path)
    if missing:
        fail("missing approved bundled assets: " + ", ".join(missing))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", help="JSON manifest to validate")
    parser.add_argument("--self-test", action="store_true", help="validate a built-in 天幕红尘 example")
    args = parser.parse_args()
    if args.self_test:
        spec = self_test()
    elif args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            spec = json.load(handle)
    else:
        parser.error("use --self-test or --manifest")
        return 2
    try:
        validate_bundled_assets()
        for line in validate(spec):
            print(line)
        print("PASS: approved generated SFX assets exist")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
