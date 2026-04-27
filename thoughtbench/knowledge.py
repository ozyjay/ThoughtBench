"""Profile-local knowledge file indexing and BM25 retrieval."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt"}
INDEX_FILE_NAME = "index.json"
DEFAULT_TOP_K = 6
DEFAULT_CONTEXT_CHAR_BUDGET = 6000


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    source: str
    text: str


@dataclass(frozen=True)
class KnowledgeResult:
    chunk: KnowledgeChunk
    score: float


def knowledge_folder(profile_dir: Path) -> Path:
    return profile_dir / "knowledge"


def knowledge_index_folder(profile_dir: Path) -> Path:
    return profile_dir / "knowledge_index"


def _index_path(profile_dir: Path) -> Path:
    return knowledge_index_folder(profile_dir) / INDEX_FILE_NAME


def ensure_knowledge_dirs(profile_dir: Path):
    knowledge_folder(profile_dir).mkdir(parents=True, exist_ok=True)
    knowledge_index_folder(profile_dir).mkdir(parents=True, exist_ok=True)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_./\\:-]+", text.lower())


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
    def __init__(self, chunks: list[KnowledgeChunk], files: dict[str, dict[str, int]] | None = None):
        self.chunks = chunks
        self.files = files or {}
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
            token: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
            for token, freq in document_frequency.items()
        }

    def retrieve(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[KnowledgeResult]:
        query_terms = _tokenize(query)
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
            if not term_counts:
                continue

            score = 0.0
            for term, frequency in term_counts.items():
                idf = self._idf.get(term, 0.0)
                denominator = frequency + k1 * (1 - b + b * (doc_length / (self._avgdl or 1)))
                score += idf * ((frequency * (k1 + 1)) / denominator)
            if score > 0:
                scores.append(KnowledgeResult(chunk=chunk, score=score))

        return sorted(scores, key=lambda item: item.score, reverse=True)[:top_k]

    def to_json(self) -> dict:
        return {
            "version": 1,
            "files": self.files,
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
        return cls(chunks, files if isinstance(files, dict) else {})


def build_knowledge_index(profile_dir: Path) -> KnowledgeIndex:
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
        chunks.extend(chunk_text(content, source))

    index = KnowledgeIndex(chunks, _file_snapshot(profile_dir))
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


def index_is_stale(profile_dir: Path, index: KnowledgeIndex) -> bool:
    return _file_snapshot(profile_dir) != index.files


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
