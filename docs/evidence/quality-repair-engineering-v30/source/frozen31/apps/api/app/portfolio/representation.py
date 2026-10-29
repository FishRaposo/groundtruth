"""Independent, pre-prediction source representations for the common harness.

These oracles never import the application's parser, normalizer, models or results.
Embedded originals establish consistency and inversion, not source authorship.
"""

from __future__ import annotations

import copy
import hashlib
import json
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT = "comparison-representation-v1"
ORACLE = "plain-utf8-canonical-oracle-v1"
COMPILER = "common-representation-compiler-v1"
META = "comparison_representation"
PROFILES = {"legacy-flat-v1": "baseline", "connected-paragraphs-v1": "candidate"}
FILES = ("documents.json", "cases.json", "profile.json")


def _bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_bytes(value))


@dataclass(frozen=True)
class CanonicalBody:
    text: str
    raw_ranges: tuple[tuple[int, int], ...]

    def codepoint_map(self) -> list[dict[str, int]]:
        """Compress contiguous one-to-one runs; collapsed runs stay explicit."""
        result: list[dict[str, int]] = []
        for index, (start, end) in enumerate(self.raw_ranges):
            if (
                result
                and end - start == 1
                and result[-1]["raw_end"] == start
                and result[-1]["raw_end"] - result[-1]["raw_start"]
                == result[-1]["canonical_end"] - result[-1]["canonical_start"]
            ):
                result[-1]["raw_end"] = end
                result[-1]["canonical_end"] = index + 1
            else:
                result.append(
                    {
                        "raw_start": start,
                        "raw_end": end,
                        "canonical_start": index,
                        "canonical_end": index + 1,
                    }
                )
        return result


def _parser_text(raw: str) -> CanonicalBody:
    chars: list[str] = []
    ranges: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(raw):
        start = cursor
        if raw[cursor] == "\r":
            cursor += 2 if raw[cursor : cursor + 2] == "\r\n" else 1
            chars.append("\n")
        else:
            chars.append(raw[cursor])
            cursor += 1
        ranges.append((start, cursor))
    return CanonicalBody("".join(chars), tuple(ranges))


def _flat_body(parsed: CanonicalBody) -> CanonicalBody:
    output: list[str] = []
    mapped: list[tuple[int, int]] = []
    index = 0
    while index < len(parsed.text):
        if parsed.text[index].isspace():
            end = index + 1
            while end < len(parsed.text) and parsed.text[end].isspace():
                end += 1
            if output and end < len(parsed.text):
                output.append(" ")
                mapped.append(
                    (parsed.raw_ranges[index][0], parsed.raw_ranges[end - 1][1])
                )
            index = end
        else:
            output.append(parsed.text[index])
            mapped.append(parsed.raw_ranges[index])
            index += 1
    return CanonicalBody("".join(output), tuple(mapped))


def _paragraph_body(parsed: CanonicalBody) -> CanonicalBody:
    lines = parsed.text.split("\n")
    first, last = 0, len(lines)
    while first < last and not lines[first].strip():
        first += 1
    while last > first and not lines[last - 1].strip():
        last -= 1
    start = sum(len(line) + 1 for line in lines[:first])
    stop = start + len("\n".join(lines[first:last]))
    return CanonicalBody(parsed.text[start:stop], parsed.raw_ranges[start:stop])


def canonicalize(raw: str, profile: str) -> CanonicalBody:
    """Apply the pinned UTF-8 TextParser newline policy then the declared oracle."""
    if profile not in PROFILES:
        raise ValueError("Representation profile is unknown")
    raw.encode("utf-8", errors="strict")
    parsed = _parser_text(raw)
    result = (
        _flat_body(parsed) if profile == "legacy-flat-v1" else _paragraph_body(parsed)
    )
    if not result.text.strip():
        raise ValueError("Representation has an empty unusable canonical body")
    if " ".join(raw.split()) != " ".join(result.text.split()):
        raise ValueError("Representation changed substantive source characters")
    return result


def project_literal(raw: str, literal: str, body: CanonicalBody) -> dict[str, Any]:
    """Enumerate exact raw occurrences, accepting only identical nonempty images."""
    if not isinstance(literal, str) or not literal:
        raise ValueError("Representation source selector is empty")
    occurrences = []
    images = set()
    starts = [start for start, _ in body.raw_ranges]
    ends = [end for _, end in body.raw_ranges]
    offset = 0
    while (start := raw.find(literal, offset)) >= 0:
        end = start + len(literal)
        left, right = bisect_right(ends, start), bisect_left(starts, end)
        if left == right:
            raise ValueError("Representation source selector projects to empty text")
        if starts[left] < start or ends[right - 1] > end:
            raise ValueError("Representation selector cuts collapsed whitespace")
        image = body.text[left:right]
        if not image.strip():
            raise ValueError("Representation source selector has no literal content")
        images.add(image)
        occurrences.append(
            {
                "raw_range": {"start": start, "end": end},
                "canonical_range": {"start": left, "end": right},
            }
        )
        offset = start + 1
    if not occurrences or len(images) != 1:
        raise ValueError("Representation source selector is unmappable or conflicting")
    return {"original": literal, "text": images.pop(), "occurrences": occurrences}


def _contains_metadata(value: Any) -> bool:
    if isinstance(value, dict):
        return META in value or any(_contains_metadata(v) for v in value.values())
    return isinstance(value, list) and any(_contains_metadata(v) for v in value)


def _project_references(value: Any, sources, profile: str) -> Any:
    if isinstance(value, list):
        return [_project_references(v, sources, profile) for v in value]
    if not isinstance(value, dict):
        return value
    result = {key: _project_references(v, sources, profile) for key, v in value.items()}
    if "document_id" not in value or "version_number" not in value:
        return result
    fields = {"quoted_text", "acceptable_answer_spans", "content_hash"}.intersection(
        value
    )
    if not fields:
        return result
    key = (value["document_id"], value["version_number"])
    if key not in sources:
        raise ValueError("Representation reference uses an unknown source version")
    return _project_source(value, result, sources[key], profile)


def _project_source(value, result, source, profile):
    fields = {"quoted_text", "acceptable_answer_spans", "content_hash"}.intersection(
        value
    )
    raw, canonical = source

    selectors = {}
    if "quoted_text" in fields:
        selectors["quoted_text"] = project_literal(raw, value["quoted_text"], canonical)
        result["quoted_text"] = selectors["quoted_text"]["text"]
    if "acceptable_answer_spans" in fields:
        if not isinstance(value["acceptable_answer_spans"], list):
            raise ValueError(
                "Representation acceptable source selectors must be a list"
            )
        selectors["acceptable_answer_spans"] = [
            project_literal(raw, span, canonical)
            for span in value["acceptable_answer_spans"]
        ]
        result["acceptable_answer_spans"] = [
            item["text"] for item in selectors["acceptable_answer_spans"]
        ]
        if "quoted_text" in result and any(
            span not in result["quoted_text"]
            for span in result["acceptable_answer_spans"]
        ):
            raise ValueError(
                "Representation acceptable span escaped its source quotation"
            )
    if "content_hash" in fields:
        result["content_hash"] = _sha(canonical.text.encode("utf-8"))
    result[META] = {
        "contract": CONTRACT,
        "profile": profile,
        "canonical_content_hash": _sha(canonical.text.encode("utf-8")),
        "input_sha256": _sha(raw.encode("utf-8")),
        "coordinate_system": "python-unicode-codepoints",
        "original": copy.deepcopy(value),
        "selectors": selectors,
    }
    return result


def _original_payload(envelope):
    manifest_text = envelope["common_manifest_text"]
    file_texts = envelope["common_files"]
    if not isinstance(manifest_text, str) or not isinstance(file_texts, dict):
        raise ValueError("Representation originals are invalid")
    original = json.loads(manifest_text.encode("utf-8"))
    if set(original.get("files", {})) != set(FILES) or set(file_texts) != set(FILES):
        raise ValueError("Representation original file set is invalid")
    values = {}
    for name in FILES:
        text = file_texts[name]
        if (
            not isinstance(text, str)
            or _sha(text.encode("utf-8")) != original["files"][name]
        ):
            raise ValueError("Representation original checksum mismatch")
        values[name.removesuffix(".json")] = json.loads(text.encode("utf-8"))
    if _contains_metadata(original) or _contains_metadata(values):
        raise ValueError("Representation inputs must be an unprojected common corpus")
    return original, values, manifest_text, file_texts


def _compile_payload(original, values, manifest_text, file_texts, profile):
    from app.portfolio import version_upload_bytes

    if profile not in PROFILES:
        raise ValueError("Representation profile is unknown")
    projected = copy.deepcopy(values)
    sources = {}
    for document in projected["documents"]:
        for version in document["versions"]:
            raw_bytes = version_upload_bytes(version)
            raw = raw_bytes.decode("utf-8", errors="strict")
            canonical = canonicalize(raw, profile)
            sources[(document["id"], version["version_number"])] = (raw, canonical)
            version.update(
                input_content=raw,
                input_sha256=_sha(raw_bytes),
                content=canonical.text,
                content_hash=_sha(canonical.text.encode("utf-8")),
            )
            version[META] = {
                "contract": CONTRACT,
                "profile": profile,
                "coordinate_system": "python-unicode-codepoints",
                "codepoint_map": canonical.codepoint_map(),
            }
    projected["cases"] = _project_references(projected["cases"], sources, profile)
    manifest = copy.deepcopy(original)
    browser = manifest.get("browser")
    if browser and "expected_quote" in browser:
        document = next(
            d for d in projected["documents"] if d["id"] == browser["document_id"]
        )
        raw, canonical = sources[
            (document["id"], document["versions"][-1]["version_number"])
        ]
        browser["expected_quote"] = project_literal(
            raw, browser["expected_quote"], canonical
        )["text"]
    payloads = {name: _bytes(projected[name.removesuffix(".json")]) for name in FILES}
    manifest["files"] = {name: _sha(body) for name, body in payloads.items()}
    envelope = {
        "contract": CONTRACT,
        "profile": profile,
        "execution_arm": PROFILES[profile],
        "oracle_contract": ORACLE,
        "compiler_contract": COMPILER,
        "compiler_sha256": _sha(Path(__file__).read_bytes()),
        "origin_common_manifest_sha256": _sha(manifest_text.encode("utf-8")),
        "common_source_contract_sha256": _digest(values["documents"]),
        "common_case_contract_sha256": _digest(values["cases"]),
        "common_contract_sha256": _digest({"manifest": original, **values}),
        "common_manifest_text": manifest_text,
        "common_files": file_texts,
    }
    manifest[META] = envelope
    envelope["projection_sha256"] = _digest(
        {
            "manifest": manifest,
            "files": {n: b.decode("utf-8") for n, b in payloads.items()},
        }
    )
    return manifest, projected, payloads


def validate_representation(
    manifest,
    values,
    expected_profile: str | None = None,
    expected_common_manifest_sha256: str | None = None,
) -> None:
    """Recompile every declared output from embedded frozen originals; fail closed."""
    envelope = manifest.get(META)
    if META not in manifest:
        if (
            expected_profile is not None
            or expected_common_manifest_sha256 is not None
            or _contains_metadata(values)
        ):
            raise ValueError("Representation envelope is missing")
        return
    try:
        if not isinstance(envelope, dict) or envelope.get("contract") != CONTRACT:
            raise ValueError("Representation contract is unknown")
        profile = envelope.get("profile")
        if profile not in PROFILES or (
            expected_profile is not None and profile != expected_profile
        ):
            raise ValueError(
                "Representation profile/arm differs from the requested profile"
            )
        if (
            expected_common_manifest_sha256 is not None
            and envelope.get("origin_common_manifest_sha256")
            != expected_common_manifest_sha256
        ):
            raise ValueError(
                "Representation common manifest differs from the frozen input"
            )
        original, common, manifest_text, file_texts = _original_payload(envelope)
        expected, projected, _ = _compile_payload(
            original, common, manifest_text, file_texts, profile
        )
        if manifest != expected or values != projected:
            raise ValueError(
                "Representation differs from the pinned oracle or common contract"
            )
    except (
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Representation metadata or originals are invalid") from exc


def compile_corpus(source: Path, target: Path, profile: str) -> dict[str, Any]:
    """Compile to a new sibling/independent directory; never modify common input."""
    from app.portfolio import load_corpus

    source, target = source.resolve(strict=True), target.resolve()
    if target.exists() or target == source or target.is_relative_to(source):
        raise ValueError("Representation target must be new and outside its input")
    common = load_corpus(source)
    if META in common["manifest"]:
        raise ValueError(
            "Representation compiler requires an unprojected common corpus"
        )
    envelope = {
        "common_manifest_text": (source / "manifest.json").read_bytes().decode("utf-8"),
        "common_files": {
            name: (source / name).read_bytes().decode("utf-8") for name in FILES
        },
    }
    original, values, manifest_text, file_texts = _original_payload(envelope)
    manifest, _, payloads = _compile_payload(
        original, values, manifest_text, file_texts, profile
    )
    target.mkdir()
    for name, body in payloads.items():
        (target / name).write_bytes(body)
    (target / "manifest.json").write_bytes(_bytes(manifest))
    return load_corpus(target, expected_representation_profile=profile)
