"""Profile-local knowledge file indexing and BM25 retrieval."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt"}
INDEX_FILE_NAME = "index.json"
KNOWLEDGE_SETTINGS_FILE_NAME = "knowledge_settings.json"
DEFAULT_TOP_K = 6
DEFAULT_CONTEXT_CHAR_BUDGET = 6000
DEFAULT_CHUNK_SIZE = 180
DEFAULT_CHUNK_OVERLAP = 30
DEFAULT_MINIMUM_SCORE = 0.5
DEFAULT_MINIMUM_MATCHED_TERMS = 1
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "you",
}


@dataclass(frozen=True)
class KnowledgeSettings:
    top_k: int = DEFAULT_TOP_K
    context_char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
    minimum_score: float = DEFAULT_MINIMUM_SCORE
    minimum_matched_terms: int = DEFAULT_MINIMUM_MATCHED_TERMS

    @classmethod
    def from_json(cls, data: object) -> "KnowledgeSettings":
        if not isinstance(data, dict):
            return DEFAULT_KNOWLEDGE_SETTINGS

        try:
            settings = cls(
                top_k=int(data.get("top_k", DEFAULT_TOP_K)),
                context_char_budget=int(data.get("context_char_budget", DEFAULT_CONTEXT_CHAR_BUDGET)),
                chunk_size=int(data.get("chunk_size", DEFAULT_CHUNK_SIZE)),
                chunk_overlap=int(data.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)),
                minimum_score=float(data.get("minimum_score", DEFAULT_MINIMUM_SCORE)),
                minimum_matched_terms=int(data.get("minimum_matched_terms", DEFAULT_MINIMUM_MATCHED_TERMS)),
            )
        except (TypeError, ValueError):
            return DEFAULT_KNOWLEDGE_SETTINGS

        return settings if settings.is_valid() else DEFAULT_KNOWLEDGE_SETTINGS

    def is_valid(self) -> bool:
        return (
            self.top_k > 0
            and self.context_char_budget > 0
            and self.chunk_size > 0
            and 0 <= self.chunk_overlap < self.chunk_size
            and self.minimum_score >= 0
            and self.minimum_matched_terms > 0
        )

    def to_json(self) -> dict:
        return {
            "top_k": self.top_k,
            "context_char_budget": self.context_char_budget,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "minimum_score": self.minimum_score,
            "minimum_matched_terms": self.minimum_matched_terms,
        }


DEFAULT_KNOWLEDGE_SETTINGS = KnowledgeSettings()


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source: str
    text: str


@dataclass(frozen=True)
class KnowledgeResult:
    chunk: KnowledgeChunk
    score: float
    matched_terms: tuple[str, ...] = ()

    @property
    def matched_term_count(self) -> int:
        return len(self.matched_terms)


def knowledge_folder(profile_dir: Path) -> Path:
    return profile_dir / "knowledge"


def knowledge_index_folder(profile_dir: Path) -> Path:
    return profile_dir / "knowledge_index"


def _index_path(profile_dir: Path) -> Path:
    return knowledge_index_folder(profile_dir) / INDEX_FILE_NAME


def _settings_path(profile_dir: Path) -> Path:
    return profile_dir / KNOWLEDGE_SETTINGS_FILE_NAME


def ensure_knowledge_dirs(profile_dir: Path):
    knowledge_folder(profile_dir).mkdir(parents=True, exist_ok=True)
    knowledge_index_folder(profile_dir).mkdir(parents=True, exist_ok=True)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_./\\:-]+", text.lower())


def _retrieval_terms(text: str) -> list[str]:
    return [token for token in _tokenize(text) if token not in STOP_WORDS]


def _normalise_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def chunk_text(text: str, source: str, max_words: int = 180, overlap_words: int = 30) -> list[KnowledgeChunk]:
    cleaned = _normalise_text(text)
    if not cleaned:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
    chunks: list[str] = []
    current: list[str] = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            continue
        if current and len(current) + len(words) > max_words:
            chunks.append(" ".join(current).strip())
            overlap = current[-overlap_words:] if overlap_words > 0 else []
            current = list(overlap)
        if len(words) > max_words:
            start = 0
            while start < len(words):
                window = words[start : start + max_words]
                chunks.append(" ".join(window).strip())
                if start + max_words >= len(words):
                    break
                start += max(1, max_words - overlap_words)
            current = []
        else:
            current.extend(words)

    if current:
        chunks.append(" ".join(current).strip())

    return [
        KnowledgeChunk(chunk_id=f"{source}#{index:04d}", source=source, text=chunk)
        for index, chunk in enumerate(chunks, start=1)
        if chunk
    ]


def _iter_knowledge_files(profile_dir: Path) -> list[Path]:
    root = knowledge_folder(profile_dir)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_SUFFIXES
    )


def _file_snapshot(profile_dir: Path) -> dict[str, dict[str, int]]:
    root = knowledge_folder(profile_dir)
    snapshot: dict[str, dict[str, int]] = {}
    for path in _iter_knowledge_files(profile_dir):
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[path.relative_to(root).as_posix()] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
    return snapshot


class KnowledgeIndex:
    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        files: dict[str, dict[str, int]] | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunks = chunks
        self.files = files or {}
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._doc_tokens = [_tokenize(chunk.text) for chunk in chunks]
        self._doc_lengths = [len(tokens) for tokens in self._doc_tokens]
        self._avgdl = (sum(self._doc_lengths) / len(self._doc_lengths)) if self._doc_lengths else 0
        self._idf = self._build_idf()

    @classmethod
    def empty(cls) -> "KnowledgeIndex":
        return cls([])

    @classmethod
    def from_chunks(cls, chunks: list[tuple[str, str, str]]) -> "KnowledgeIndex":
        return cls([KnowledgeChunk(chunk_id=chunk_id, source=source, text=text) for chunk_id, source, text in chunks])

    def _build_idf(self) -> dict[str, float]:
        doc_count = len(self._doc_tokens)
        if doc_count == 0:
            return {}

        document_frequency: dict[str, int] = {}
        for tokens in self._doc_tokens:
            for token in set(tokens):
                document_frequency[token] = document_frequency.get(token, 0) + 1

        return {
            token: 1 + math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for token, freq in document_frequency.items()
        }

    def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        minimum_score: float = DEFAULT_MINIMUM_SCORE,
        minimum_matched_terms: int = DEFAULT_MINIMUM_MATCHED_TERMS,
    ) -> list[KnowledgeResult]:
        query_terms = _retrieval_terms(query)
        if not query_terms or not self.chunks:
            return []

        k1 = 1.5
        b = 0.75
        scores: list[KnowledgeResult] = []
        query_unique_terms = set(query_terms)
        for chunk, tokens, doc_length in zip(self.chunks, self._doc_tokens, self._doc_lengths):
            if not tokens:
                continue
            term_counts: dict[str, int] = {}
            for token in tokens:
                if token in query_unique_terms:
                    term_counts[token] = term_counts.get(token, 0) + 1
            matched_terms = tuple(sorted(term_counts))
            if len(matched_terms) < minimum_matched_terms:
                continue

            score = 0.0
            for term, frequency in term_counts.items():
                idf = self._idf.get(term, 0.0)
                denominator = frequency + k1 * (1 - b + b * (doc_length / (self._avgdl or 1)))
                score += idf * ((frequency * (k1 + 1)) / denominator)
            if score >= minimum_score:
                scores.append(KnowledgeResult(chunk=chunk, score=score, matched_terms=matched_terms))

        return sorted(scores, key=lambda item: item.score, reverse=True)[:top_k]

    def to_json(self) -> dict:
        return {
            "version": 1,
            "files": self.files,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "source": chunk.source,
                    "text": chunk.text,
                }
                for chunk in self.chunks
            ],
        }

    @classmethod
    def from_json(cls, data: dict) -> "KnowledgeIndex":
        raw_chunks = data.get("chunks", [])
        chunks: list[KnowledgeChunk] = []
        if isinstance(raw_chunks, list):
            for item in raw_chunks:
                if not isinstance(item, dict):
                    continue
                chunk_id = item.get("chunk_id")
                source = item.get("source")
                text = item.get("text")
                if isinstance(chunk_id, str) and isinstance(source, str) and isinstance(text, str) and text.strip():
                    chunks.append(KnowledgeChunk(chunk_id=chunk_id, source=source, text=text))
        files = data.get("files")
        chunk_size = data.get("chunk_size", DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP)
        try:
            chunk_size = int(chunk_size)
            chunk_overlap = int(chunk_overlap)
        except (TypeError, ValueError):
            chunk_size = DEFAULT_CHUNK_SIZE
            chunk_overlap = DEFAULT_CHUNK_OVERLAP
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            chunk_size = DEFAULT_CHUNK_SIZE
            chunk_overlap = DEFAULT_CHUNK_OVERLAP
        return cls(chunks, files if isinstance(files, dict) else {}, chunk_size, chunk_overlap)


def load_knowledge_settings(profile_dir: Path) -> KnowledgeSettings:
    path = _settings_path(profile_dir)
    if not path.exists():
        return DEFAULT_KNOWLEDGE_SETTINGS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_KNOWLEDGE_SETTINGS
    return KnowledgeSettings.from_json(data)


def save_knowledge_settings(profile_dir: Path, settings: KnowledgeSettings):
    profile_dir.mkdir(parents=True, exist_ok=True)
    _settings_path(profile_dir).write_text(
        json.dumps(settings.to_json(), indent=2),
        encoding="utf-8",
    )


def normalise_knowledge_settings(settings: KnowledgeSettings | None) -> KnowledgeSettings:
    if settings is None:
        return DEFAULT_KNOWLEDGE_SETTINGS
    return settings if settings.is_valid() else DEFAULT_KNOWLEDGE_SETTINGS


def build_knowledge_index(profile_dir: Path, settings: KnowledgeSettings | None = None) -> KnowledgeIndex:
    settings = normalise_knowledge_settings(settings)
    ensure_knowledge_dirs(profile_dir)
    root = knowledge_folder(profile_dir)
    chunks: list[KnowledgeChunk] = []
    for path in _iter_knowledge_files(profile_dir):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source = path.relative_to(root).as_posix()
        chunks.extend(
            chunk_text(
                content,
                source,
                max_words=settings.chunk_size,
                overlap_words=settings.chunk_overlap,
            )
        )

    index = KnowledgeIndex(
        chunks,
        _file_snapshot(profile_dir),
        settings.chunk_size,
        settings.chunk_overlap,
    )
    _index_path(profile_dir).write_text(
        json.dumps(index.to_json(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return index


def load_knowledge_index(profile_dir: Path) -> KnowledgeIndex:
    path = _index_path(profile_dir)
    if not path.exists():
        return KnowledgeIndex.empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return KnowledgeIndex.empty()
    if not isinstance(data, dict):
        return KnowledgeIndex.empty()
    return KnowledgeIndex.from_json(data)


def index_is_stale(
    profile_dir: Path,
    index: KnowledgeIndex,
    settings: KnowledgeSettings | None = None,
) -> bool:
    settings = normalise_knowledge_settings(settings)
    return (
        _file_snapshot(profile_dir) != index.files
        or index.chunk_size != settings.chunk_size
        or index.chunk_overlap != settings.chunk_overlap
    )


def format_retrieved_context(
    results: list[KnowledgeResult],
    max_chars: int = DEFAULT_CONTEXT_CHAR_BUDGET,
) -> str:
    if not results or max_chars <= 0:
        return ""

    header = (
        "Retrieved knowledge files:\n"
        "Use these snippets as local reference material. If they are not relevant, ignore them.\n\n"
    )
    parts = [header]
    used = len(header)
    for result in results:
        label = f"[{result.chunk.chunk_id}]"
        block = f"{label}\n{result.chunk.text.strip()}\n\n"
        remaining = max_chars - used
        if remaining <= len(label) + 8:
            break
        if len(block) > remaining:
            block = block[:remaining].rstrip() + "\n\n"
        parts.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "".join(parts).strip()


def format_source_summary(results: list[KnowledgeResult]) -> str:
    if not results:
        return "No knowledge snippets retrieved."
    labels = [result.chunk.chunk_id for result in results]
    return "Knowledge: " + ", ".join(labels)


def format_diagnostic_summary(results: list[KnowledgeResult]) -> str:
    if not results:
        return "No knowledge snippets retrieved.\n"

    parts = ["Retrieved knowledge snippets:\n"]
    for result in results:
        snippet = result.chunk.text.strip()
        matched = ", ".join(result.matched_terms) if result.matched_terms else "(none)"
        parts.append(f"[{result.chunk.chunk_id}] score={result.score:.3f} matched={matched}\n")
        if snippet:
            parts.append(f"{snippet}\n")
        parts.append("\n")
    return "".join(parts)
