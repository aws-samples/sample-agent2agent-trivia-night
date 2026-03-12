"""Literature data models."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class Article:
    """Represents a literature article."""
    
    title: str
    authors: List[str]
    journal: str
    publication_date: datetime
    pmid: Optional[str]
    doi: Optional[str]
    abstract: str
    relevance_score: float
    
    def __post_init__(self):
        """Validate article data."""
        if not self.title:
            raise ValueError("title is required")
        if not self.authors:
            raise ValueError("authors list cannot be empty")
        if not self.journal:
            raise ValueError("journal is required")
        if not self.abstract:
            raise ValueError("abstract is required")
        if not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError("relevance_score must be between 0.0 and 1.0")


@dataclass
class LiteratureResults:
    """Represents results from a literature search."""
    
    query: str
    articles: List[Article]
    summary: str
    total_results: int
    searched_at: datetime
    
    def __post_init__(self):
        """Validate literature results data."""
        if not self.query:
            raise ValueError("query is required")
        if self.total_results < 0:
            raise ValueError("total_results must be non-negative")
        if self.total_results > 0 and not self.articles:
            raise ValueError("articles list cannot be empty when total_results > 0")
