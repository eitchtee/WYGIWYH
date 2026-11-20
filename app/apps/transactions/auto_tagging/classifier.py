from __future__ import annotations

import heapq
import json
import math
import re
import unicodedata
import zlib
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

MODEL_VERSION = 1

MAX_TRAINING_DOCS = 5000
TOP_K = 10
MIN_SIMILARITY = 0.35
NEAR_EXACT_SIMILARITY = 0.85
MIN_SUPPORT_NEIGHBORS = 2
CATEGORY_CONFIDENCE_THRESHOLD = 0.65
MULTI_LABEL_CONFIDENCE_THRESHOLD = 0.60

# Strip dates (2025-01-20, 20/01/2025, 20/01) and installment counters (01/12)
_DATE_OR_INSTALLMENT_RE = re.compile(
    r"\b\d{1,4}[-/.]\d{1,2}(?:[-/.]\d{1,4})?\b"
)
_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class TrainingRecord:
    description: str
    notes: str
    account_id: int
    tx_type: str
    amount: Decimal | float | int
    category_id: int | None
    tag_ids: tuple[int, ...] = ()
    entity_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class Prediction:
    category_id: int | None = None
    tag_ids: tuple[int, ...] = ()
    entity_ids: tuple[int, ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            self.category_id is None
            and not self.tag_ids
            and not self.entity_ids
        )


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(
        ch for ch in decomposed if unicodedata.category(ch) != "Mn"
    )
    lowered = stripped.lower()
    return _DATE_OR_INSTALLMENT_RE.sub(" ", lowered)


def _tokenize_text(text: str) -> list[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []
    return [
        tok
        for tok in _WORD_RE.findall(normalized)
        if len(tok) >= 2 and not tok.isdigit()
    ]


def _add_text_features(
    features: dict[str, float],
    tokens: list[str],
    *,
    unigram_weight: float,
    bigram_weight: float,
    char_ngram_weight: float,
) -> None:
    for tok in tokens:
        features[tok] = features.get(tok, 0.0) + unigram_weight
        if char_ngram_weight > 0.0 and len(tok) >= 6 and tok.isalpha():
            for i in range(len(tok) - 3):
                ngram = f"c:{tok[i : i + 4]}"
                features[ngram] = features.get(ngram, 0.0) + char_ngram_weight

    for i in range(len(tokens) - 1):
        bigram = f"b:{tokens[i]}_{tokens[i + 1]}"
        features[bigram] = features.get(bigram, 0.0) + bigram_weight


def _amount_bucket(amount: Decimal | float | int | None) -> int:
    if amount is None:
        return 0
    val = abs(float(amount))
    if val < 1.0:
        return 0
    return int(math.floor(math.log10(val))) + 1


def _extract_feature_parts(
    description: str,
    notes: str,
    account_id: int,
    tx_type: str,
    amount: Decimal | float | int | None,
) -> tuple[dict[str, float], set[str], bool]:
    """Extract combined features plus the set of tokens from description.

    Returns ``(features, desc_feature_keys, has_description)``.
    """
    desc_tokens = _tokenize_text(description)
    notes_tokens = _tokenize_text(notes)
    if not desc_tokens and not notes_tokens:
        return {}, set(), False

    desc_features: dict[str, float] = {}
    if desc_tokens:
        _add_text_features(
            desc_features,
            desc_tokens,
            unigram_weight=2.0,
            bigram_weight=1.5,
            char_ngram_weight=0.6,
        )

    features = dict(desc_features)
    if notes_tokens:
        _add_text_features(
            features,
            notes_tokens,
            unigram_weight=1.0,
            bigram_weight=0.75,
            char_ngram_weight=0.0,
        )

    features[f"__type_{tx_type}"] = 0.5
    features[f"__acct_{account_id}"] = 0.6
    features[f"__amt_{_amount_bucket(amount)}"] = 0.4
    return features, set(desc_features.keys()), bool(desc_tokens)


def extract_features(
    description: str,
    notes: str,
    account_id: int,
    tx_type: str,
    amount: Decimal | float | int | None,
) -> dict[str, float]:
    """Extract weighted text + structured features for a transaction.

    Returns an empty dict when neither description nor notes yields any
    meaningful text tokens, preventing blind matches on account/type alone.
    """
    features, _, _ = _extract_feature_parts(
        description=description,
        notes=notes,
        account_id=account_id,
        tx_type=tx_type,
        amount=amount,
    )
    return features


@dataclass
class TransactionAutoTagger:
    """Zero-dependency TF-IDF + Cosine Similarity k-NN classifier."""

    idf: dict[str, float] = field(default_factory=dict)
    # Flat posting lists: [doc_idx_0, weight_0, doc_idx_1, weight_1, ...]
    inverted_index: dict[str, list[float | int]] = field(default_factory=dict)
    doc_categories: list[int | None] = field(default_factory=list)
    doc_tags: list[list[int]] = field(default_factory=list)
    doc_entities: list[list[int]] = field(default_factory=list)
    doc_counts: list[int] = field(default_factory=list)
    total_records: int = 0
    version: int = MODEL_VERSION

    @property
    def num_docs(self) -> int:
        return self.total_records or len(self.doc_categories)

    @classmethod
    def fit(cls, records: list[TrainingRecord]) -> TransactionAutoTagger:
        # Collapse identical (features, labels) into weighted prototypes
        prototypes: dict[tuple, int] = {}
        doc_features: list[dict[str, float]] = []
        doc_categories: list[int | None] = []
        doc_tags: list[list[int]] = []
        doc_entities: list[list[int]] = []
        doc_counts: list[int] = []
        df: dict[str, int] = defaultdict(int)
        total_records = 0

        for rec in records[:MAX_TRAINING_DOCS]:
            feats = extract_features(
                description=rec.description,
                notes=rec.notes,
                account_id=rec.account_id,
                tx_type=rec.tx_type,
                amount=rec.amount,
            )
            if not feats:
                continue
            total_records += 1
            for tok in feats:
                df[tok] += 1

            sorted_tags = tuple(sorted(rec.tag_ids))
            sorted_entities = tuple(sorted(rec.entity_ids))
            sig = (
                tuple(sorted(feats.items())),
                rec.category_id,
                sorted_tags,
                sorted_entities,
            )
            existing_idx = prototypes.get(sig)
            if existing_idx is not None:
                doc_counts[existing_idx] += 1
            else:
                prototypes[sig] = len(doc_features)
                doc_features.append(feats)
                doc_categories.append(rec.category_id)
                doc_tags.append(list(sorted_tags))
                doc_entities.append(list(sorted_entities))
                doc_counts.append(1)

        if total_records == 0:
            return cls()

        idf = {
            tok: round(math.log((1.0 + total_records) / (1.0 + count)) + 1.0, 4)
            for tok, count in df.items()
        }

        inverted_index: dict[str, list[float | int]] = defaultdict(list)
        for doc_idx, feats in enumerate(doc_features):
            weights = {
                tok: (1.0 + math.log(tf)) * idf[tok]
                for tok, tf in feats.items()
            }
            norm = math.sqrt(sum(w * w for w in weights.values()))
            if norm <= 0.0:
                continue
            for tok, w in weights.items():
                postings = inverted_index[tok]
                postings.append(doc_idx)
                postings.append(round(w / norm, 4))

        return cls(
            idf=idf,
            inverted_index=dict(inverted_index),
            doc_categories=doc_categories,
            doc_tags=doc_tags,
            doc_entities=doc_entities,
            doc_counts=doc_counts,
            total_records=total_records,
            version=MODEL_VERSION,
        )

    def to_bytes(self) -> bytes:
        payload = {
            "v": self.version,
            "n": self.total_records,
            "idf": self.idf,
            "idx": self.inverted_index,
            "cat": self.doc_categories,
            "tag": self.doc_tags,
            "ent": self.doc_entities,
            "cnt": self.doc_counts,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return zlib.compress(raw, level=6)

    @classmethod
    def from_bytes(cls, blob: bytes | memoryview) -> TransactionAutoTagger | None:
        if not blob:
            return None
        try:
            payload = json.loads(zlib.decompress(bytes(blob)).decode("utf-8"))
        except (zlib.error, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if payload.get("v") != MODEL_VERSION or "cnt" not in payload:
            return None
        return cls(
            idf=payload["idf"],
            inverted_index=payload["idx"],
            doc_categories=payload["cat"],
            doc_tags=payload["tag"],
            doc_entities=payload["ent"],
            doc_counts=payload["cnt"],
            total_records=payload.get("n", len(payload["cat"])),
            version=payload["v"],
        )

    def predict(
        self,
        *,
        description: str,
        notes: str,
        account_id: int,
        tx_type: str,
        amount: Decimal | float | int | None,
        allowed_category_ids: set[int] | None = None,
        allowed_tag_ids: set[int] | None = None,
        allowed_entity_ids: set[int] | None = None,
    ) -> Prediction:
        if self.num_docs == 0:
            return Prediction()

        feats, desc_feature_keys, has_description = _extract_feature_parts(
            description=description,
            notes=notes,
            account_id=account_id,
            tx_type=tx_type,
            amount=amount,
        )
        if not feats:
            return Prediction()

        query_weights: dict[str, float] = {}
        matched_text_tokens = 0
        unknown_idf = math.log(1.0 + self.num_docs) + 1.0
        norm_sq = 0.0

        for tok, tf in feats.items():
            tok_idf = self.idf.get(tok)
            if tok_idf is not None:
                w = (1.0 + math.log(tf)) * tok_idf
                query_weights[tok] = w
                norm_sq += w * w
                if not tok.startswith("__"):
                    matched_text_tokens += 1
            elif not tok.startswith("__"):
                # Penalize unknown description tokens so unrelated descriptions
                # abstain, but don't let unique notes (e.g. itemized details)
                # discard a matching description.
                if not has_description or tok in desc_feature_keys:
                    w = (1.0 + math.log(tf)) * unknown_idf
                    norm_sq += w * w

        if matched_text_tokens == 0 or norm_sq <= 0.0:
            return Prediction()

        norm = math.sqrt(norm_sq)

        scores: dict[int, float] = defaultdict(float)
        for tok, w in query_weights.items():
            q_w = w / norm
            postings = self.inverted_index.get(tok)
            if postings:
                for i in range(0, len(postings), 2):
                    scores[postings[i]] += q_w * postings[i + 1]

        candidates = [
            (sim, doc_idx)
            for doc_idx, sim in scores.items()
            if sim >= MIN_SIMILARITY
        ]
        if not candidates:
            return Prediction()

        top_neighbors = heapq.nlargest(TOP_K, candidates, key=lambda x: x[0])
        total_support = sum(self.doc_counts[doc_idx] for _, doc_idx in top_neighbors)
        if total_support < MIN_SUPPORT_NEIGHBORS:
            if top_neighbors[0][0] < NEAR_EXACT_SIMILARITY:
                return Prediction()

        total_weight = 0.0
        cat_weights: dict[int, float] = defaultdict(float)
        cat_present_weight = 0.0
        tag_weights: dict[int, float] = defaultdict(float)
        entity_weights: dict[int, float] = defaultdict(float)

        for sim, doc_idx in top_neighbors:
            count = self.doc_counts[doc_idx]
            w = (sim * sim) * (1.0 + math.log(count))
            total_weight += w

            cat_id = self.doc_categories[doc_idx]
            if cat_id is not None:
                cat_present_weight += w
                cat_weights[cat_id] += w

            for tid in self.doc_tags[doc_idx]:
                tag_weights[tid] += w

            for eid in self.doc_entities[doc_idx]:
                entity_weights[eid] += w

        predicted_category: int | None = None
        if cat_weights and (cat_present_weight / total_weight) >= 0.5:
            best_cat, best_w = max(cat_weights.items(), key=lambda item: item[1])
            if (best_w / cat_present_weight) >= CATEGORY_CONFIDENCE_THRESHOLD:
                if allowed_category_ids is None or best_cat in allowed_category_ids:
                    predicted_category = best_cat

        predicted_tags = tuple(
            sorted(
                tid
                for tid, w in tag_weights.items()
                if (w / total_weight) >= MULTI_LABEL_CONFIDENCE_THRESHOLD
                and (allowed_tag_ids is None or tid in allowed_tag_ids)
            )
        )

        predicted_entities = tuple(
            sorted(
                eid
                for eid, w in entity_weights.items()
                if (w / total_weight) >= MULTI_LABEL_CONFIDENCE_THRESHOLD
                and (allowed_entity_ids is None or eid in allowed_entity_ids)
            )
        )

        return Prediction(
            category_id=predicted_category,
            tag_ids=predicted_tags,
            entity_ids=predicted_entities,
        )
