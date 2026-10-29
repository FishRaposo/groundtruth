"""Normalize a pinned official VerbNet checkout; never execute its Python tools.

The source commit and license must be recorded by the maintainer. This script
does not download data, select word senses or edit the runtime's expected hash.
"""

import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


def node(element):
    return {
        "tag": element.tag,
        "attributes": dict(element.attrib),
        "text": (element.text or "").strip(),
        "children": [node(child) for child in element],
    }


def derive(source, commit, license_bytes):
    classes, frames, members, index, source_hashes = {}, {}, {}, {}, {}

    def walk(element, filename, parent, inherited):
        identifier = element.attrib["ID"]
        if identifier in classes:
            raise ValueError("Duplicate lexical class identity")
        own_frames = []
        for ordinal, frame in enumerate(element.findall("./FRAMES/FRAME")):
            frame_id = f"{identifier}:frame:{ordinal}"
            frames[frame_id] = {
                "id": frame_id,
                "source_file": filename,
                "origin_class": identifier,
                "ordinal": ordinal,
                "syntax": [node(child) for child in frame.find("SYNTAX")],
                "semantics": [node(child) for child in frame.find("SEMANTICS")],
                "description": node(frame.find("DESCRIPTION")),
                "other_fields": [
                    node(child)
                    for child in frame
                    if child.tag
                    not in {"SYNTAX", "SEMANTICS", "DESCRIPTION", "EXAMPLES"}
                ],
            }
            own_frames.append(frame_id)
        applicable = [*inherited, *own_frames]
        classes[identifier] = {
            "id": identifier,
            "source_file": filename,
            "parent": parent,
            "role_declarations": [
                node(role) for role in element.findall("./THEMROLES/THEMROLE")
            ],
            "own_frames": own_frames,
            "applicable_frames": applicable,
        }
        for ordinal, member in enumerate(element.findall("./MEMBERS/MEMBER")):
            # verbnet_key is optional and not unique in the upstream data.
            identity = f"{identifier}:member:{ordinal}"
            attributes = dict(member.attrib)
            lemma = attributes["name"]
            members[identity] = {
                "id": identity,
                "class": identifier,
                "source_file": filename,
                "attributes": attributes,
            }
            index.setdefault(lemma, []).append(identity)
        for child in element.findall("./SUBCLASSES/VNSUBCLASS"):
            walk(child, filename, identifier, applicable)

    files = sorted(source.glob("*.xml"))
    if not files or len(files) > 512:
        raise ValueError("Unsupported lexical source inventory size")
    for file in files:
        if file.is_symlink() or file.resolve().parent != source.resolve():
            raise ValueError("Lexical source escaped its explicit directory")
        raw = file.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("Lexical source file exceeds build bound")
        source_hashes[file.name] = hashlib.sha256(raw).hexdigest()
        walk(ET.fromstring(raw), file.name, None, [])
    return {
        "contract": "procedure-reference-lexicon-v1",
        "source": {
            "name": "University of Colorado VerbNet 3.4",
            "url": "https://github.com/cu-clear/verbnet",
            "commit": commit,
            "files": source_hashes,
            "license_file": "VERBNET_LICENSE.txt",
            "license_sha256": hashlib.sha256(license_bytes).hexdigest(),
        },
        "meaning": (
            "lexical interpretation candidates; not actual sense, source facts "
            "or implicit-reference absence"
        ),
        "classes": classes,
        "frames": frames,
        "members": members,
        "lemma_index": dict(sorted(index.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--license-file", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(r"[0-9a-f]{40}", args.source_commit) is None:
        parser.error("Record the exact official source commit")
    license_bytes = args.license_file.read_bytes()
    data = derive(args.source_directory, args.source_commit, license_bytes)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    target = args.output_directory / "procedure_reference_lexicon_v1.json"
    raw = json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    target.write_bytes(raw)
    shutil.copyfile(args.license_file, args.output_directory / "VERBNET_LICENSE.txt")
    print(
        json.dumps(
            {
                "path": str(target),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "classes": len(data["classes"]),
                "frames": len(data["frames"]),
                "members": len(data["members"]),
                "lemmas": len(data["lemma_index"]),
            }
        )
    )


if __name__ == "__main__":
    main()
