"""Central configuration, read from environment variables (.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_fast_model: str = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    reranker_model: str = os.getenv("RERANKER_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")

    data_dir: Path = field(default_factory=lambda: ROOT / os.getenv("DATA_DIR", "data"))

    # Chunking
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))        # characters
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))

    # Retrieval
    top_k: int = int(os.getenv("TOP_K", "6"))
    candidate_k: int = int(os.getenv("CANDIDATE_K", "30"))      # before reranking

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def catalog_path(self) -> Path:
        return self.data_dir / "catalog.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "students.sqlite"


settings = Settings()
