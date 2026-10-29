"""Approved optional CPU parser assets; importing performs no I/O or downloads.

Pins are the official spaCy 3.8.18 Windows CP312 wheel and Explosion English
small model 3.8.0 verified in the isolated prototype. Outputs are proposals.
"""

from copy import deepcopy

CONTRACT = "dependency-request-capture-v1"
MAX_QUESTION_CHARS = 2048
MODEL_REVISION = "en_core_web_sm-3.8.0"
MODEL_WHEEL_URL = "https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
MODEL_WHEEL_BYTES = 12806118
MODEL_PREFIX = "en_core_web_sm/en_core_web_sm-3.8.0/"

_IDENTITY = {
    "library": "spacy",
    "library_version": "3.8.18",
    "library_wheel_sha256": (
        "8b3fe34abbd91526fc6b719672fa8c7a5e64fe54899f85aa5404a588ca3f1251"
    ),
    "library_file_manifest_sha256": (
        "330eb23bc72bf2025236c711a3cc21a7cac06db672b2d43ea2a81d9278c0818e"
    ),
    "library_file_count": 1077,
    "model": "en_core_web_sm",
    "model_version": "3.8.0",
    "model_revision": "en_core_web_sm-3.8.0",
    "model_wheel_sha256": (
        "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
    ),
    "model_config_sha256": (
        "65c545ca2da5bd4b87b22d4917318605360b37dee6ed6b18516a036f87319f79"
    ),
    "model_file_hashes": {
        "accuracy.json": (
            "e7572d7f2f3c18e9921471f9d0b3424f8cf7f1a909ae484fa10b780a13f4c676"
        ),
        "attribute_ruler/patterns": (
            "f8b97f7ebef9b8536bba5f0fc1e73af6183563e96e2325bcbb021b8c6dbc6683"
        ),
        "config.cfg": (
            "65c545ca2da5bd4b87b22d4917318605360b37dee6ed6b18516a036f87319f79"
        ),
        "lemmatizer/lookups/lookups.bin": (
            "eb64f40c0f8396d1762730c0ddf4dad2a52d138f5a389f71a1a1d088173b7737"
        ),
        "LICENSE": "3933c176979b68bc6d0bcc902c7d6c130f1d127f476f17ba5cdba8d99cfd0012",
        "LICENSES_SOURCES": (
            "20d9dfacd215112251f15341edd1a47b1f98bf393a212f10f194ffdc7ee98a90"
        ),
        "meta.json": "7456349002fa8cf31111051bd37fdbea67a1b7f7a0a60ce235466f98a6758125",
        "ner/cfg": "a7172edadafba9f472e9ac0f2660eec04b6405e471be9e20267b79c67288d22d",
        "ner/model": "cd93e9ca9126c69f1d10a1039ef67c3d9ec1223b44d079856705970f0f19ff4e",
        "ner/moves": "d82b13473ebd33e0396004dd22f00c71fe3c1251742bf1f7c4554f23fd3b0af4",
        "parser/cfg": (
            "e2a240ef01f95e58f5dd4c9d6e90d61f597b8d998966570d3009dd81e8879780"
        ),
        "parser/model": (
            "e0098910535a863d430082ece57455d5fa071cd4ca3a0054e80582076c752b1e"
        ),
        "parser/moves": (
            "ec41318c32eb7f9e4d8f050b2e8466ee67954d2d3455c1aec73abf46c82dd67f"
        ),
        "README.md": "91b0ed1742ea0803034b4d769c4536e88d9d4da7808d833f2a804b6c54aae220",
        "senter/cfg": (
            "2a4db4a729b6469da1f87d71cc7cd3ed2a73360cc85326821e850836c4671103"
        ),
        "senter/model": (
            "b69e7174a0b6307739adec3c8053ac45fdbad7171c4d3d8bfcd9713ecbc01f8c"
        ),
        "tagger/cfg": (
            "d484c3d9391f37bf9c727aa2eb4c477a24cb103020f95e52dc37842818b50118"
        ),
        "tagger/model": (
            "1ec3d93f38cebe172f2b5c89d84be72856ce42c8f1a64f1699f1d98a771f36b7"
        ),
        "tok2vec/cfg": (
            "f8a5a26e3056eb6fb06deeb3dbccfd88ae74900200c98c70b5966bbb7ec9d4de"
        ),
        "tok2vec/model": (
            "e84fc06eb319c94d28e460fc334e292120b01f18baa5dc8b50c977459820a090"
        ),
        "tokenizer": "b014e8bba4958b120af2d0c1c63eabb7c00379f2bacaf10df7c5325efd2ea467",
        "vocab/key2row": (
            "76be8b528d0075f7aae98d6fa57a6d3c83ae480a8469e668d7b0af968995ac71"
        ),
        "vocab/lookups.bin": (
            "fce9c883c56165f29573cc938c2a1c9d417ac61bd8f56b671dd5f7996de70682"
        ),
        "vocab/strings.json": (
            "b1966d1f07a05b68576df07f43f40203b4e11124ad82cc839e8312ad8d7fdae7"
        ),
        "vocab/vectors": (
            "14772b683e726436d5948ad3fff2b43d036ef2ebbe3458aafed6004e05a40706"
        ),
        "vocab/vectors.cfg": (
            "ff4359091952c8cd16f1f0482f5770fb82d1707368d5cca3c46aa501f552e3c5"
        ),
    },
    "pipeline": ["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"],
    "excluded_components": ["ner"],
    "device": "cpu",
    "license": "MIT",
    "coordinate_system": "python-unicode-codepoints",
    "tag_labels": [
        "$",
        "''",
        ",",
        "-LRB-",
        "-RRB-",
        ".",
        ":",
        "ADD",
        "AFX",
        "CC",
        "CD",
        "DT",
        "EX",
        "FW",
        "HYPH",
        "IN",
        "JJ",
        "JJR",
        "JJS",
        "LS",
        "MD",
        "NFP",
        "NN",
        "NNP",
        "NNPS",
        "NNS",
        "PDT",
        "POS",
        "PRP",
        "PRP$",
        "RB",
        "RBR",
        "RBS",
        "RP",
        "SYM",
        "TO",
        "UH",
        "VB",
        "VBD",
        "VBG",
        "VBN",
        "VBP",
        "VBZ",
        "WDT",
        "WP",
        "WP$",
        "WRB",
        "XX",
        "_SP",
        "``",
    ],
    "dependency_labels": [
        "ROOT",
        "acl",
        "acomp",
        "advcl",
        "advmod",
        "agent",
        "amod",
        "appos",
        "attr",
        "aux",
        "auxpass",
        "case",
        "cc",
        "ccomp",
        "compound",
        "conj",
        "csubj",
        "csubjpass",
        "dative",
        "dep",
        "det",
        "dobj",
        "expl",
        "intj",
        "mark",
        "meta",
        "neg",
        "nmod",
        "npadvmod",
        "nsubj",
        "nsubjpass",
        "nummod",
        "oprd",
        "parataxis",
        "pcomp",
        "pobj",
        "poss",
        "preconj",
        "predet",
        "prep",
        "prt",
        "punct",
        "quantmod",
        "relcl",
        "xcomp",
    ],
}


def parser_identity() -> dict:
    """Return a detached provenance identity, never a semantic attestation."""
    return deepcopy(_IDENTITY)


APPROVED_ENTRY_POINTS = (
    ("en_core_web_sm", "spacy_models", "en_core_web_sm", "en_core_web_sm"),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.CharacterEmbed.v1",
        "spacy_legacy.architectures.tok2vec:CharacterEmbed_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.EntityLinker.v1",
        "spacy_legacy.architectures.entity_linker:EntityLinker_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.HashEmbedCNN.v1",
        "spacy_legacy.architectures.tok2vec:HashEmbedCNN_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.MaxoutWindowEncoder.v1",
        "spacy_legacy.architectures.tok2vec:MaxoutWindowEncoder_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.MishWindowEncoder.v1",
        "spacy_legacy.architectures.tok2vec:MishWindowEncoder_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.MultiHashEmbed.v1",
        "spacy_legacy.architectures.tok2vec:MultiHashEmbed_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.Tagger.v1",
        "spacy_legacy.architectures.tagger:Tagger_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.TextCatBOW.v1",
        "spacy_legacy.architectures.textcat:TextCatBOW_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.TextCatCNN.v1",
        "spacy_legacy.architectures.textcat:TextCatCNN_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.TextCatEnsemble.v1",
        "spacy_legacy.architectures.textcat:TextCatEnsemble_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.Tok2Vec.v1",
        "spacy_legacy.architectures.tok2vec:Tok2Vec_v1",
    ),
    (
        "spacy-legacy",
        "spacy_architectures",
        "spacy-legacy.TransitionBasedParser.v1",
        "spacy_legacy.architectures.parser:TransitionBasedParser_v1",
    ),
    (
        "spacy-legacy",
        "spacy_loggers",
        "spacy-legacy.ConsoleLogger.v1",
        "spacy_legacy.loggers:console_logger_v1",
    ),
    (
        "spacy-legacy",
        "spacy_loggers",
        "spacy-legacy.ConsoleLogger.v2",
        "spacy_legacy.loggers:console_logger_v2",
    ),
    (
        "spacy-legacy",
        "spacy_loggers",
        "spacy-legacy.WandbLogger.v1",
        "spacy_legacy.loggers:wandb_logger_v1",
    ),
    (
        "spacy-legacy",
        "spacy_scorers",
        "spacy-legacy.textcat_multilabel_scorer.v1",
        "spacy_legacy.scorers:make_textcat_multilabel_scorer_v1",
    ),
    (
        "spacy-legacy",
        "spacy_scorers",
        "spacy-legacy.textcat_scorer.v1",
        "spacy_legacy.scorers:make_textcat_scorer_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.ChainLogger.v1",
        "spacy_loggers.chain:chain_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.ClearMLLogger.v1",
        "spacy_loggers.clearml:clearml_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.ClearMLLogger.v2",
        "spacy_loggers.clearml:clearml_logger_v2",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.CupyLogger.v1",
        "spacy_loggers.cupy:cupy_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.LookupLogger.v1",
        "spacy_loggers.lookup:lookup_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.MLflowLogger.v1",
        "spacy_loggers.mlflow:mlflow_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.MLflowLogger.v2",
        "spacy_loggers.mlflow:mlflow_logger_v2",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.PyTorchLogger.v1",
        "spacy_loggers.pytorch:pytorch_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.WandbLogger.v1",
        "spacy_loggers.wandb:wandb_logger_v1",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.WandbLogger.v2",
        "spacy_loggers.wandb:wandb_logger_v2",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.WandbLogger.v3",
        "spacy_loggers.wandb:wandb_logger_v3",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.WandbLogger.v4",
        "spacy_loggers.wandb:wandb_logger_v4",
    ),
    (
        "spacy-loggers",
        "spacy_loggers",
        "spacy.WandbLogger.v5",
        "spacy_loggers.wandb:wandb_logger_v5",
    ),
    ("srsly", "spacy_readers", "srsly.read_json.v1", "srsly:read_json"),
    ("srsly", "spacy_readers", "srsly.read_jsonl.v1", "srsly:read_jsonl"),
    ("srsly", "spacy_readers", "srsly.read_msgpack.v1", "srsly:read_msgpack"),
    ("srsly", "spacy_readers", "srsly.read_yaml.v1", "srsly:read_yaml"),
)
