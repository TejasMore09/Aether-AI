"""
╔══════════════════════════════════════════════════════════════════════╗
║         Aether AI — In-Memory Telemetry Vector Store                ║
║         RAG Engine for Historically-Grounded LLM Explanations       ║
╚══════════════════════════════════════════════════════════════════════╝

Architecture:
  - Indexes 4 operational data sources into a single TF-IDF matrix
  - Uses cosine similarity for sub-millisecond semantic retrieval
  - Zero external vector DB dependency (sklearn + numpy only)
  - Domain-aware relevance boosting for precision retrieval
  - Module-level singleton auto-built at FastAPI startup

Data Sources Indexed:
  1. audit_logs        — Every autonomous decision ever made (action, risk, drift, F1, loss)
  2. system_health     — Latency + drift snapshots from each evaluation cycle
  3. experiment_runs   — Model training outcomes (hyperparams, F1, dataset window)
  4. model_versions    — Version history with accuracy and deployment status
"""

import json
import os
import logging
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# ── Path resolution ────────────────────────────────────────────────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
_VERSIONS_PATH = os.path.join(_ROOT_DIR, "models", "model_versions.json")


class AetherVectorStore:
    """
    Lightweight in-memory semantic search over Aether AI's operational history.

    Design choices:
    - TF-IDF (1–2 gram) gives strong performance on the structured telemetry
      language ("domain hr_attrition action RETRAIN risk HIGH drift 47.3 percent")
    - Cosine similarity is O(n) at query time and sub-ms for ≤1000 documents
    - Domain-aware boosting (1.0 vs 0.3 multiplier) surfaces same-domain
      precedents first without fully excluding cross-domain pattern signals
    """

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),      # unigrams + bigrams capture "action retrain", "risk high"
            min_df=1,
            sublinear_tf=True,       # log(1+tf) — dampens high-frequency terms
            strip_accents="unicode",
        )
        self.documents: List[Dict[str, Any]] = []
        self._matrix = None
        self._built = False

    # ── Text serialisers ──────────────────────────────────────────────────────

    def _audit_to_text(self, log) -> str:
        """Rich text representation of an audit log record for TF-IDF."""
        details_str = ""
        try:
            d = json.loads(log.details or "{}")
            feats = d.get("drifted_features", [])
            if feats:
                details_str = "drifted features " + " ".join(feats)
        except Exception:
            pass

        return (
            f"domain {log.domain} "
            f"action {log.action} "
            f"risk level {log.risk_level} "
            f"drift percentage {log.drift_pct:.1f} percent "
            f"f1 score before {log.f1_before:.4f} "
            f"expected daily loss {log.expected_loss_usd:.0f} dollars "
            f"triggered by {log.triggered_by} "
            f"status {log.status} "
            f"{details_str}"
        ).strip()

    def _health_to_text(self, snap) -> str:
        return (
            f"domain {snap.domain} "
            f"system health latency {snap.latency_ms:.0f} milliseconds "
            f"drift percentage {snap.drift_pct:.1f} percent "
            f"autonomous action taken {snap.action}"
        )

    def _experiment_to_text(self, exp) -> str:
        try:
            metrics = json.loads(exp.metrics or "{}")
            hyperparams = json.loads(exp.hyperparams or "{}")
        except Exception:
            metrics, hyperparams = {}, {}

        f1 = metrics.get("f1_score", 0.0)
        hp_str = " ".join(f"{k} {v}" for k, v in hyperparams.items())
        return (
            f"domain {exp.domain} "
            f"model type {exp.model_type} "
            f"trained f1 score {f1:.4f} "
            f"dataset window {exp.dataset_window} "
            f"hyperparameters {hp_str} "
            f"notes {exp.notes or ''}"
        ).strip()

    def _version_to_text(self, v: dict) -> str:
        return (
            f"model version {v.get('version', 'unknown')} "
            f"accuracy {v.get('accuracy', 0):.4f} "
            f"latency {v.get('latency', 0)} milliseconds "
            f"deployment status {v.get('status', 'unknown')} "
            f"date {v.get('date', '')}"
        )

    # ── Index construction ────────────────────────────────────────────────────

    def build_index(self) -> int:
        """
        Load all operational history from the live SQLite database and the
        model versions JSON file, then fit the TF-IDF matrix.

        Returns the total number of documents indexed.
        """
        from database.db import SessionLocal
        from database.models import AuditLog, ExperimentRun, SystemHealth

        documents: List[Dict[str, Any]] = []
        db = SessionLocal()

        try:
            # ── 1. Audit Logs — highest information density ────────────────
            audit_records = (
                db.query(AuditLog)
                .order_by(AuditLog.timestamp.desc())
                .limit(200)
                .all()
            )
            for log in audit_records:
                text = self._audit_to_text(log)
                documents.append(
                    {
                        "text": text,
                        "source": "audit_log",
                        "domain": log.domain,
                        "action": log.action,
                        "risk_level": log.risk_level,
                        "drift_pct": float(log.drift_pct or 0),
                        "f1_before": float(log.f1_before or 0),
                        "expected_loss_usd": float(log.expected_loss_usd or 0),
                        "status": log.status,
                        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                        "summary": (
                            f"[{log.domain}] {log.action} | {log.risk_level} risk | "
                            f"drift={log.drift_pct:.1f}% | F1={log.f1_before:.4f} | "
                            f"loss=${log.expected_loss_usd:,.0f}/day"
                        ),
                    }
                )

            # ── 2. System Health Snapshots — operational pulse ─────────────
            health_records = (
                db.query(SystemHealth)
                .order_by(SystemHealth.timestamp.desc())
                .limit(200)
                .all()
            )
            for snap in health_records:
                text = self._health_to_text(snap)
                documents.append(
                    {
                        "text": text,
                        "source": "system_health",
                        "domain": snap.domain,
                        "action": snap.action,
                        "drift_pct": float(snap.drift_pct or 0),
                        "latency_ms": float(snap.latency_ms or 0),
                        "timestamp": snap.timestamp.isoformat() if snap.timestamp else None,
                        "summary": (
                            f"[{snap.domain}] health snapshot | "
                            f"drift={snap.drift_pct:.1f}% | "
                            f"latency={snap.latency_ms:.0f}ms | "
                            f"action={snap.action}"
                        ),
                    }
                )

            # ── 3. Experiment Runs — training outcomes ─────────────────────
            exp_records = (
                db.query(ExperimentRun)
                .order_by(ExperimentRun.timestamp.desc())
                .limit(100)
                .all()
            )
            for exp in exp_records:
                text = self._experiment_to_text(exp)
                try:
                    m = json.loads(exp.metrics or "{}")
                except Exception:
                    m = {}
                documents.append(
                    {
                        "text": text,
                        "source": "experiment_run",
                        "domain": exp.domain,
                        "model_type": exp.model_type,
                        "metrics": m,
                        "dataset_window": exp.dataset_window,
                        "timestamp": exp.timestamp.isoformat() if exp.timestamp else None,
                        "summary": (
                            f"[{exp.domain}] {exp.model_type} trained | "
                            f"F1={m.get('f1_score', 0):.4f} | "
                            f"window={exp.dataset_window}"
                        ),
                    }
                )

        finally:
            db.close()

        # ── 4. Model Versions JSON ─────────────────────────────────────────
        if os.path.exists(_VERSIONS_PATH):
            try:
                with open(_VERSIONS_PATH) as fh:
                    versions = json.load(fh)
                for v in versions:
                    text = self._version_to_text(v)
                    documents.append(
                        {
                            "text": text,
                            "source": "model_version",
                            "version": v.get("version"),
                            "accuracy": v.get("accuracy"),
                            "latency_ms": v.get("latency"),
                            "status": v.get("status"),
                            "date": v.get("date"),
                            "domain": "global",
                            "summary": (
                                f"[version] {v.get('version')} | "
                                f"accuracy={v.get('accuracy')} | "
                                f"status={v.get('status')} | "
                                f"date={v.get('date')}"
                            ),
                        }
                    )
            except Exception as exc:
                logger.warning("Could not load model_versions.json: %s", exc)

        if not documents:
            logger.warning("VectorStore: no documents found — index is empty.")
            self._built = False
            return 0

        # ── Fit TF-IDF matrix ──────────────────────────────────────────────
        self.documents = documents
        texts = [d["text"] for d in documents]
        self._matrix = self.vectorizer.fit_transform(texts)
        self._built = True

        logger.info(
            "AetherVectorStore: indexed %d documents (%s)",
            len(documents),
            str(self._count_by_source()),
        )
        return len(documents)

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        filter_domain: Optional[str] = None,
        source_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return the top-k most semantically similar historical records.

        Args:
            query_text:    Free-form description of the current system state.
            top_k:         Maximum results to return.
            filter_domain: If set, boosts same-domain records (does not exclude others).
            source_filter: If set, restricts results to one source type
                           ('audit_log' | 'system_health' | 'experiment_run' | 'model_version').
        """
        if not self._built or self._matrix is None:
            logger.warning("VectorStore queried before index was built — returning empty.")
            return []

        if not query_text.strip():
            return []

        try:
            query_vec = self.vectorizer.transform([query_text])
        except Exception as exc:
            logger.error("VectorStore: transform failed: %s", exc)
            return []

        sims: np.ndarray = cosine_similarity(query_vec, self._matrix).flatten()

        # Domain-aware boosting: same-domain documents score 3.3× higher
        if filter_domain:
            boost = np.array(
                [1.0 if d.get("domain") == filter_domain else 0.3 for d in self.documents]
            )
            sims = sims * boost

        # Source filter — hard mask
        if source_filter:
            mask = np.array(
                [1.0 if d.get("source") == source_filter else 0.0 for d in self.documents]
            )
            sims = sims * mask

        # Descending sort, take up to top_k * 3 to allow deduplication headroom
        ranked = sims.argsort()[::-1][: top_k * 3]

        results: List[Dict[str, Any]] = []
        seen: set = set()

        for idx in ranked:
            if len(results) >= top_k:
                break
            score = float(sims[idx])
            if score < 0.01:
                break  # sorted — nothing below this will be useful

            doc = dict(self.documents[idx])
            doc["similarity_score"] = round(score, 4)

            # Deduplicate by summary string
            summary = doc.get("summary", "")
            if summary not in seen:
                seen.add(summary)
                results.append(doc)

        return results

    # ── Utility ───────────────────────────────────────────────────────────────

    def rebuild(self) -> int:
        """Force a full index rebuild. Call after major DB writes."""
        self._built = False
        self._matrix = None
        self.documents = []
        return self.build_index()

    def _count_by_source(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for doc in self.documents:
            src = doc.get("source", "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts

    @property
    def is_ready(self) -> bool:
        return self._built and self._matrix is not None

    @property
    def document_count(self) -> int:
        return len(self.documents)


# ── Module-level singleton ─────────────────────────────────────────────────────
#
# A single shared instance is created when this module is first imported.
# FastAPI's startup sequence calls initialize_vector_store() which calls
# _store.build_index() once the DB tables are confirmed to exist.
#
_store = AetherVectorStore()


# ── Public API ────────────────────────────────────────────────────────────────

def initialize_vector_store() -> int:
    """
    Build the TF-IDF index from scratch.
    Must be called after `Base.metadata.create_all()` during server startup.
    Returns the number of documents indexed.
    """
    count = _store.build_index()
    return count


def semantic_lookup(
    query_text: str,
    top_k: int = 5,
    domain: Optional[str] = None,
    source_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Primary public interface for RAG retrieval.

    Automatically triggers a lazy index build if the store is not yet ready
    (handles edge-case where the endpoint is called before startup completes).
    """
    if not _store.is_ready:
        logger.info("VectorStore: lazy build triggered by semantic_lookup call.")
        _store.build_index()
    return _store.query(query_text, top_k=top_k, filter_domain=domain, source_filter=source_filter)


def rebuild_index() -> int:
    """Force a full index rebuild — useful after simulating drift or bulk retraining."""
    return _store.rebuild()


def get_index_stats() -> Dict[str, Any]:
    """Return metadata about the current state of the in-memory index."""
    return {
        "is_ready": _store.is_ready,
        "document_count": _store.document_count,
        "document_sources": _store._count_by_source(),
        "vectorizer_vocabulary_size": (
            len(_store.vectorizer.vocabulary_) if _store.is_ready else 0
        ),
    }


def format_context_block(results: List[Dict[str, Any]], max_items: int = 5) -> str:
    """
    Format retrieved documents into a human-readable context block
    suitable for injection into an LLM system prompt.
    """
    if not results:
        return "No relevant historical precedents found in operational memory."

    lines = ["SYSTEM OPERATIONAL MEMORY (retrieved from live telemetry database):"]
    lines.append("\u2501" * 60)

    for i, doc in enumerate(results[:max_items], 1):
        source_label = doc.get("source", "unknown").replace("_", " ").title()
        domain       = doc.get("domain", "unknown")
        summary      = doc.get("summary", "No summary available")
        score        = doc.get("similarity_score", 0.0)
        timestamp    = doc.get("timestamp", "")

        lines.append(f"[{i}] [{domain} | {source_label}]  (relevance: {score:.3f})")
        lines.append(f"    {summary}")

        # Source-specific detail rows
        if doc.get("source") == "audit_log":
            lines.append(
                f"    Risk: {doc.get('risk_level','?')} | "
                f"Drift: {doc.get('drift_pct', 0):.1f}% | "
                f"F1 before action: {doc.get('f1_before', 0):.4f} | "
                f"Daily loss: ${doc.get('expected_loss_usd', 0):,.0f}"
            )
        elif doc.get("source") == "experiment_run":
            m = doc.get("metrics", {})
            lines.append(
                f"    Post-training F1: {m.get('f1_score', 0):.4f} | "
                f"Model: {doc.get('model_type','?')} | "
                f"Window: {doc.get('dataset_window','?')}"
            )
        elif doc.get("source") == "system_health":
            lines.append(
                f"    Latency: {doc.get('latency_ms', 0):.0f}ms | "
                f"Drift: {doc.get('drift_pct', 0):.1f}%"
            )

        if timestamp:
            lines.append(f"    Recorded: {timestamp[:19].replace('T', ' ')} UTC")
        lines.append("")

    lines.append("\u2501" * 60)
    return "\n".join(lines)
