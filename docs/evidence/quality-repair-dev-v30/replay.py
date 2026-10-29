"""Portable source30 DEVELOPMENT evidence replay. No inference, HTTP, SQL or installs."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.abc
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
PINNED_SOURCE = "fd0e693629aaae190d1d3759784d857a77bac0e45c4fa5b45a83d3efd1879772"
PINNED_CORPUS = "22c7cf7ccbc229d641b26ea359bdb74420c313b411505734681c843a7ba54cf4"
PINNED_REPORTS = {'margin0-reranked': ['30f9536debb5817569c4280b0a76ebbac3ce5482e0134b3413725ea9a81c3ce6', 75904814], 'margin1-reranked': ['188bc1912832ea7cbb5e3ae1a222e8fbba9a86e5acd7cce524f04f0c7556c768', 75870181], 'margin2-reranked': ['f73f00f1c43c95e726edbf029ebc48b6d5d32c317f99fa3cdb17ff770d7cbc11', 75896944], 'margin3-reranked': ['7b8a97fbd1cd2b193bd497caf60bb4da2bf276ae438392dfdb0b9664ffd3363a', 25052123], 'margin4-reranked': ['749dba9f3567541699fa0b5d9b92d0aa80c63c2fb3e0f72eadec37134ac0235e', 25749105], 'margin2-all': ['61c3d0afebde1e19ce95a21c73f50c4e8b6f75b1075050303d2888a0a2fa20ba', 325607281]}
PINNED_METADATA = {'controller.py': '8c732ab64ad7085ad3385f81e29dded23c43395b4e51b068b269f5d6a846de1f', 'current-tool-distinction.json': 'aa3d357e8445abcdce6bd30daa54ca368b37503edca6cd051c23a99b4cb52e4c', 'export-exclusions.json': '42622479eff18bf484904f13808c6dff6ca5cbd130837ab9e3b0c84531d7683d', 'frozen-candidate-corpus.zip': 'dfb95c29ec66335b1c2286977d2c55ebeb2de959a6d57607f8ade29c42b6c5ee', 'frozen-source.zip': '2e7a4cac0003727116c606f049c83ad936451c22fb64f1dfd2e5cba5023ea3e5', 'grid-declaration.zip': '6844221ed307f54f2100da1ba1f8ba6bc1b9d06aff726bcb812540fdc3769c8f', 'independent-audit-v362.zip': 'a986ed92d784688e637151be919c1da0cd83ef062935d0b7351b0094f47812ae', 'independent-audit-v373.zip': '0297b348200c275f7f093d537f7a2f353b6a60c03c411ce282fa45248d56baad', 'margin0-reranked-cleanup.json': 'c4b90f301e883bf010a8f6d6a70d5c368935a3129bf47437f238d85bf6d803ad', 'margin0-reranked-commands.json': '3c6de08feb59156256d56ccc26db9fdd7a04a480ae9b21290efc1ecfb5e1cde9', 'margin0-reranked-controller.log': 'f46bc5f308d2351086749ef6ec8f15dc97a2433bb01654cab7fb0b38c6cbf41a', 'margin0-reranked-execution-settings.json': 'b6d2c1a4aa94d43f436b96a2e0458d2b91d0bbcf82826af8707febcf07260115', 'margin0-reranked-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin0-reranked-launch.json': '4b507fcceb57e0fc041cf0ebaf82048b85dea2f9164605a1aa5af1a5daafc08b', 'margin0-reranked-preservation.json': '8108e9194088002c37230714fa673134f74073154a35b566b9f50aaf38cefbfc', 'margin0-reranked-process.json': '6929391dcdc50841212729420d430349c23005d26dd3c54dd7c433b9fc032bde', 'margin0-reranked-readiness.json': '9adbe5e2e9471be28f277fcccf4adfc6a5c6f3a3382f9de7511f473950a50092', 'margin0-reranked-result.json': 'd239aa163c7fc15eaca25522862d15d4e4afba26a335ca99cbbe2aefdb4ba127', 'margin0-reranked-SEALED.json': 'ddf0dc3f8376680e127ad949c02157d60bf72337774c89f12b138d2b9cb66454', 'margin1-reranked-cleanup.json': '2c4ae7b2410272e6b9ed1a15ba18854f17f309f14a5242d9dedda595d3ab997a', 'margin1-reranked-commands.json': '0f2c8aa43730807c55335e4903252f8696934e34ad9bde0c59ec17b4a7620def', 'margin1-reranked-controller.log': '246f74b973be374fae5e97034e65d385a7c43ffa75fa28323d8e08b132f71c49', 'margin1-reranked-execution-settings.json': '1eee3e495ad0ee78e51a3a365ba4d3591b12943ec755eb1c03b46d7541da9993', 'margin1-reranked-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin1-reranked-launch.json': '04e792394b2262c3c4b6b10fd2b6acb238a1959191c7afaac07aba1c49a17cf6', 'margin1-reranked-preservation.json': '81df1f0ed5caf6c59d6d97542a55bddf07ff36e33ba2507d47a4b430bd6d34ca', 'margin1-reranked-process.json': '2042b847086c19ee19c66c057a26ce68f297cbe305f7c91b3c6c9a1d34777eb6', 'margin1-reranked-readiness.json': '26d520364ab590cdc4280d85a05937334bd998f682da1f90acfdb305e21d12e7', 'margin1-reranked-result.json': 'd239aa163c7fc15eaca25522862d15d4e4afba26a335ca99cbbe2aefdb4ba127', 'margin1-reranked-SEALED.json': 'd4ec128cff1a61410b178ef81c865e53d513630137daf7c14e304f18e48336a9', 'margin2-all-cleanup.json': '28be523d342b42e8bbd54b53ab294504498eab256d294fd5e384acb4fb2c168a', 'margin2-all-commands.json': 'e8781fb1210cb31a63041306db35c30a2084ef4e9ec2983815b89ec0c246259a', 'margin2-all-controller.log': 'bf363f4a8773172bfae544728315001d0054bafb73023ccfc8c22b9bbb256302', 'margin2-all-execution-settings.json': '6ff5a0b4c4d207fa541471b1063c4fdf0dfe04ec7d1797941cfdbc7dbcc34a03', 'margin2-all-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin2-all-launch.json': 'ed9a55bf3d02da14299d518b4b0e751284a015425433bbdbd3064ad0d55f2542', 'margin2-all-preservation.json': '6831f313b7c5abfa86770c1b9f53c98d431b33310193b5dc64f46219d1c78082', 'margin2-all-process.json': '9224f7cf33bfefba3854b240200e249360af52d681f17dbcfbc7c351e5a78498', 'margin2-all-readiness.json': '36b1ce931c9c2ab4ff049fd4aa9dd5f4a1108630a61abb7949b0e44b982d6d39', 'margin2-all-result.json': '1ada440290883eb7ff59d7e52d563b37e25964a246182cbbb19128395199a3df', 'margin2-all-SEALED.json': 'f0782f57887a747e4f6575c2f1f424c183c738c9e2e4e6894d4cd1eab2e10523', 'margin2-reranked-cleanup.json': 'e6b91688711e1b88d05685db798c5c95c0afcc89c37ee5e0084bede75d2e5ac2', 'margin2-reranked-commands.json': '4910b6059ac6b75324ec2cbd7a31d22d9474a9d1c624fce6a4c150fe4a998151', 'margin2-reranked-controller.log': 'e8947c08e8b048edec812baf82b9a206cc532a32da8193e7e18b903fcfb3856c', 'margin2-reranked-execution-settings.json': '48adcc8f1c49949a54e68492fa7f8eb56976cd151989f433f86730eb0f6a9fbf', 'margin2-reranked-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin2-reranked-launch.json': '507b4443b5408ba1feb833ac7f81ce204e82063f7efc2df3b136f86c9d83f1a1', 'margin2-reranked-preservation.json': '7f336376bf2111a7cd8f5127ba8cd085c91b7f13fd67a5b5ad329ac166b6b5a7', 'margin2-reranked-process.json': '56b5cdaa371d49e52905aec7deb273e9012a54afc7b17daf2a70d61bee1ae66d', 'margin2-reranked-readiness.json': '36b1ce931c9c2ab4ff049fd4aa9dd5f4a1108630a61abb7949b0e44b982d6d39', 'margin2-reranked-result.json': 'd239aa163c7fc15eaca25522862d15d4e4afba26a335ca99cbbe2aefdb4ba127', 'margin2-reranked-SEALED.json': '19f49b0022d67dfbbf591afedc4a908b10608d71ecd5e64043ce3d061401ab52', 'margin3-reranked-cleanup.json': 'b309e790d7ca36185ffea1a761e36529d79ac6cb302e25ed620e20178fe26cb1', 'margin3-reranked-commands.json': '82d21097856e68670fc822d2242efbc92b42cc0aa6e6e24cf604f4fdfd0e7917', 'margin3-reranked-controller.log': 'e3e4d458b4b5960a37695caeb6577bc21388e58caa5511dce3db9253ba3fde67', 'margin3-reranked-execution-settings.json': 'cc27b0fe7bda4cd33dc86e5f60ad814158af40849d300c677c24eb5712590e5a', 'margin3-reranked-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin3-reranked-launch.json': '54dc489154758010d03caaf4de73edfc175394ac275dc35e8297573f8f39f043', 'margin3-reranked-preservation.json': '21c39a1a07fe920bc82ca8ccba6cbf5f8617eedc22f83c61acc79b51b1620435', 'margin3-reranked-process.json': 'fac8515bc26631b4eadf813ad62b01a87a1738ba9dd486f84b9beae3a8d8ecf6', 'margin3-reranked-readiness.json': '09818d3a582fe5f14e8123de09d9c3a1148f3d184cbb51887de5ee9f330887d6', 'margin3-reranked-result.json': 'da3b665c1091ad1fedc408e82b73bafbaccaf528a13a4d67ce8521964c1512c7', 'margin3-reranked-SEALED.json': '7443b2b93239b79554ed300611558ed6bae18d6add7fbade983112a97ca1fa1f', 'margin4-reranked-cleanup.json': '162a7760fe089b5ed2cf959b9a7e35572ac3c4fde1089a92149a33e75068ddac', 'margin4-reranked-commands.json': '6e3106a9d1e37842b8694f37d138b958c8f0432b16f1a368ddfa0d3a1519b837', 'margin4-reranked-controller.log': '1463049723915941473648e6f3e7dddade8ff5cb113b240d0e141b73f31ac8a4', 'margin4-reranked-execution-settings.json': 'f8bef48713d9da7e85b2c7f1ae596ae859d8a81e89db52499646cb4dce679659', 'margin4-reranked-input-checks.json': '9966130400f9b64caef36e8f466c6301810715ea354cd714814a28b9665d656f', 'margin4-reranked-launch.json': '605ed81ab1292d48103cc577089f0ebc51ffa2d15b33ecd90ea01d82d296850c', 'margin4-reranked-preservation.json': 'a1046a8decbdbb0bd6b7ca7f3e1688dcb5f92313386b18d226e3f89bfcfe434e', 'margin4-reranked-process.json': 'd16d337f13403287452a837122a149a7798eace705efde5a1515cf082807270e', 'margin4-reranked-readiness.json': '20a4809f407ca739f465799ad4cc2363b801c4b18d09036186df152a0079721f', 'margin4-reranked-result.json': 'da3b665c1091ad1fedc408e82b73bafbaccaf528a13a4d67ce8521964c1512c7', 'margin4-reranked-SEALED.json': '1888f99f4e6171cec7bff6f59abdc9d0e1ee6d321baf8d92c18b0cbce4432f3f', 'model-bindings.json': '1cc7fa908c0509f2b79ef6a37f12c0dfff18ce3dfe358774b8258e0c3b083821', 'observations.json': '8505d9028946440cb455a56b8fbcfbdc1ac75a96e5d2b7a02c8bf9fad9475d8c', 'original-launcher.py': 'cde4acb409bef2cb3cdddea1ed6bda1ee11cd08eaf5fb14c93d80ba323c61343', 'runtime-before.json': '17b24946beda5fe38ead57054328050d771a02033d4cf1e8a89bea0631dab1fc', 'source-manifest.json': 'fd0e693629aaae190d1d3759784d857a77bac0e45c4fa5b45a83d3efd1879772'}
sha = lambda data: hashlib.sha256(data).hexdigest()
read = lambda path: json.loads(path.read_text(encoding="utf-8-sig"))


def safe_name(name):
    value = PurePosixPath(name)
    if not name or value.is_absolute() or ".." in value.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe evidence path")
    return value


def report_for(run):
    raw = gzip.decompress((ROOT / run["report"]).read_bytes())
    if (sha(raw), len(raw)) != tuple(PINNED_REPORTS[run["key"]]):
        raise ValueError("Raw first report differs: " + run["key"])
    return json.loads(raw)


def integrity():
    sums = {}
    for line in (ROOT / "checksums.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        safe_name(name)
        if name in sums:
            raise ValueError("Duplicate checksum path")
        sums[name] = digest
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and p != ROOT / "checksums.sha256"}
    if actual != set(sums):
        raise ValueError("Checksum inventory is not closed")
    for name, digest in sums.items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError("Changed export: " + name)
    manifest = read(ROOT / "manifest.json")
    if set(manifest["files"]) != actual - {"manifest.json"}:
        raise ValueError("Manifest inventory differs")
    for name, record in manifest["files"].items():
        data = (ROOT / name).read_bytes()
        if record != {"sha256": sha(data), "bytes": len(data)}:
            raise ValueError("Changed inventory record: " + name)
    for name, expected in PINNED_METADATA.items():
        if sha((ROOT / name).read_bytes()) != expected:
            raise ValueError("Changed authoritative metadata: " + name)
    if sha((ROOT / "source-manifest.json").read_bytes()) != PINNED_SOURCE:
        raise ValueError("Changed frozen source authority")
    files = read(ROOT / "source-manifest.json")["files"]
    with zipfile.ZipFile(ROOT / "frozen-source.zip") as archive:
        if len(archive.namelist()) != 231 or len(set(archive.namelist())) != 231 or set(archive.namelist()) != set(files):
            raise ValueError("Frozen source inventory differs")
        for name, expected in files.items():
            safe_name(name)
            if sha(archive.read(name)) != expected:
                raise ValueError("Changed frozen source member: " + name)
    with zipfile.ZipFile(ROOT / "frozen-candidate-corpus.zip") as archive:
        if len(archive.namelist()) != 4 or set(archive.namelist()) != {"cases.json", "documents.json", "manifest.json", "profile.json"}:
            raise ValueError("Frozen corpus inventory differs")
        if sha(archive.read("manifest.json")) != PINNED_CORPUS:
            raise ValueError("Changed corpus authority")
        for name, expected in json.loads(archive.read("manifest.json"))["files"].items():
            safe_name(name)
            if sha(archive.read(name)) != expected:
                raise ValueError("Changed corpus member: " + name)
    observations = read(ROOT / "observations.json")
    if {x["key"] for x in observations["runs"]} != set(PINNED_REPORTS) or len(observations["runs"]) != 6:
        raise ValueError("Complete grid/all-method run set differs")
    methods = 0
    for run in observations["runs"]:
        report = report_for(run)
        if report["split"] != "development" or report["span_integrity_required"] is not True:
            raise ValueError("Wrong report scope")
        if set(report["results"]) != set(run["methods"]):
            raise ValueError("Method set differs")
        if run["summaries"] != {method: value["summary"] for method, value in report["results"].items()}:
            raise ValueError("Summary differs")
        settings = read(ROOT / run["settings_file"])
        if any(report["settings"][k] != v for k, v in settings["settings"].items()):
            raise ValueError("Report settings differ")
        seal = read(ROOT / run["seal_file"])
        registry = read(ROOT / run["preservation_file"])
        prefix = run["original_directory"] + "/"
        if seal["children_closed"] is not True or seal["inspection_allowed"] is not True:
            raise ValueError("Unsealed run")
        if seal["files"]["report.json"] != run["report_sha256"] or registry["files"][prefix + "report.json"] != run["report_sha256"]:
            raise ValueError("Raw report preservation binding differs")
        for suffix in ("execution-settings.json", "commands.json", "input-checks.json", "result.json", "cleanup.json", "process.json", "readiness.json"):
            digest = sha((ROOT / (run["key"] + "-" + suffix)).read_bytes())
            if seal["files"][suffix] != digest or registry["files"][prefix + suffix] != digest:
                raise ValueError("Preserved metadata differs: " + suffix)
        methods += len(run["methods"])
    return observations, {"export_files_hashed": len(sums), "source_files_hashed": 231, "corpus_files_hashed": 4, "sealed_reports": 6, "method_observations": methods, "case_rows": 80 * methods, "all_raw_first_reports_byte_exact": True}


class NoModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "transformers", "sentence_transformers"}:
            raise RuntimeError("Model imports forbidden in portable replay")


def canonical(observations, scratch):
    scratch = scratch.resolve()
    if scratch.exists() or scratch == ROOT or scratch.is_relative_to(ROOT):
        raise ValueError("Replay requires a new scratch directory outside immutable export")
    scratch.mkdir(parents=True)
    for filename, folder in (("frozen-source.zip", "source"), ("frozen-candidate-corpus.zip", "corpus")):
        base = scratch / folder
        base.mkdir()
        with zipfile.ZipFile(ROOT / filename) as archive:
            for name in archive.namelist():
                safe_name(name)
                target = (base / name).resolve()
                if not target.is_relative_to(base):
                    raise ValueError("Unsafe archive member")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(archive.read(name))
    source = scratch / "source"
    sys.meta_path.insert(0, NoModels())
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source / "apps/api"))
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    from app.portfolio import load_corpus
    from app.portfolio.evaluation import summarize

    if not Path(sys.modules["app.portfolio"].__file__).resolve().is_relative_to(source):
        raise ValueError("Wrong application authority imported")
    baseline = read(ROOT / observations["runs"][0]["settings_file"])
    corpus = load_corpus(scratch / "corpus", expected_representation_profile="connected-paragraphs-v1", expected_common_manifest_sha256=baseline["common_manifest_sha256"])
    cases = {case["id"]: case for case in corpus["cases"] if case["split"] == "development"}
    spec = importlib.util.spec_from_file_location("frozen_source30_portable_audit", source / "scripts/verify_answer_coverage_delivery.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    result = []
    for run in observations["runs"]:
        report = report_for(run)
        audited = verifier.audit_report(report, corpus)
        if not audited["verified"] or audited["case_rows"] != 80 * len(run["methods"]) or audited["runtime_verification"]["verified"]:
            raise ValueError("Frozen scorer rejected report or unexpected final runtime authority")
        documents = verifier.portable_documents(report, corpus)
        method_results = {}
        for method in run["methods"]:
            rows = report["results"][method]["cases"]
            recomputed = summarize([verifier.audit_row(row, cases[row["case_id"]], documents, True, settings=report["settings"], arm=report.get("execution_arm"), frozen_runtime=False) for row in rows])
            if recomputed != report["results"][method]["summary"]:
                raise ValueError("Recomputed summary differs: " + run["key"] + "/" + method)
            required = []
            for row in rows:
                selection = (row["observed_response"].get("provenance") or {}).get("answer_selection") or {}
                for ref in cases[row["case_id"]].get("inspection_expected_sources", []):
                    actual = report["source_document_ids"][ref["document_id"]]
                    matches = [item for item in selection["inspected_sources"] if item["document_id"] == actual and item["document_version"] == ref["version_number"] and item["content_hash"] == ref["content_hash"]]
                    required.append({"case_id": row["case_id"], "authored_id": ref["document_id"], "actual_id": actual, "version": ref["version_number"], "content_hash": ref["content_hash"], "matching_chunk_count": len(matches)})
            if len(required) != 8:
                raise ValueError("Required opposing identity count differs")
            present = sum(item["matching_chunk_count"] > 0 for item in required)
            if method == "reranked" and present != 8:
                raise ValueError("Reranked opposing identity preservation differs")
            method_results[method] = {"summary": recomputed, "required_opposing_identity_count": len(required), "opposing_identities_present": present, "required_opposing_identities": required}
        result.append({"key": run["key"], "report_sha256": run["report_sha256"], "canonical_audit": audited, "methods": method_results})
    if {"torch", "transformers", "sentence_transformers"}.intersection(sys.modules):
        raise ValueError("Model library imported")
    return {"canonical_reports": result, "frozen_scorer_verified": True, "model_libraries_imported": False, "inference_performed": False, "historical_runtime_selection_verified": False, "scratch_retained_for_inspection": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", action="store_true", help="Use frozen scorer with existing API Python dependencies; no model dependencies needed")
    parser.add_argument("--scratch-dir", type=Path, help="New directory outside immutable export")
    args = parser.parse_args()
    observations, result = integrity()
    if args.canonical:
        if args.scratch_dir is None:
            parser.error("--canonical requires --scratch-dir")
        result.update(canonical(observations, args.scratch_dir))
    result["scope"] = "Author portable DEVELOPMENT evidence replay; agent-authored synthetic labels, not independent export review, human validation, general model quality or blind/release acceptance"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
