"""Literature Mining Agent for searching and analyzing medical literature."""

from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from models.signal import Signal
from models.literature import LiteratureResults, Article


@dataclass
class SearchQuery:
    """Structured search query for literature databases."""
    
    drug_name: str
    adverse_event_term: str
    medra_code: Optional[str]
    query_string: str
    database: str  # pubmed, clinicaltrials, etc.


class BrowserToolError(Exception):
    """Exception raised when Browser Tool access fails."""
    pass


class LiteratureMiningAgent:
    """
    Agent responsible for searching medical literature for evidence related to detected signals.
    
    Uses Browser Tool to search PubMed, clinical trial databases, and other medical literature
    sources to contextualize detected safety signals with published evidence.
    """
    
    def __init__(self, config=None, browser=None):
        """
        Initialize Literature Mining Agent.
        
        Args:
            config: AgentCore configuration
            browser: Browser Tool instance (for testing, can be mocked)
        """
        self.config = config
        self.browser = browser
        self.agent_id = "literature_mining_agent"
    
    def search_literature(self, signal: Signal) -> LiteratureResults:
        """
        Search medical literature for evidence related to a detected signal.
        
        Args:
            signal: Detected safety signal to investigate
            
        Returns:
            LiteratureResults containing relevant articles and summary
            
        Raises:
            ValueError: If signal is invalid
        """
        if not signal:
            raise ValueError("Signal cannot be None")
        if not signal.drug_name:
            raise ValueError("Signal must have drug_name")
        if not signal.adverse_event_term:
            raise ValueError("Signal must have adverse_event_term")
        
        # Construct search queries for different databases
        queries = self._construct_search_queries(signal)
        
        # Search each database
        all_articles = []
        errors = []
        
        for query in queries:
            try:
                articles = self._search_database(query)
                all_articles.extend(articles)
            except BrowserToolError as e:
                # Gracefully handle failures - continue with other sources
                errors.append(f"Failed to search {query.database}: {str(e)}")
                continue
        
        # Extract relevant cases
        relevant_articles = self.extract_relevant_cases(all_articles, signal)
        
        # Generate summary
        summary = self._generate_summary(relevant_articles, signal)
        
        return LiteratureResults(
            query=f"{signal.drug_name} AND {signal.adverse_event_term}",
            articles=relevant_articles,
            summary=summary,
            total_results=len(relevant_articles),
            searched_at=datetime.now()
        )
    
    def _construct_search_queries(self, signal: Signal) -> List[SearchQuery]:
        """
        Construct search queries for different literature databases.
        
        Args:
            signal: Signal to search for
            
        Returns:
            List of SearchQuery objects for different databases
        """
        queries = []
        
        # PubMed query
        pubmed_query = self._build_pubmed_query(
            signal.drug_name,
            signal.adverse_event_term,
            getattr(signal, 'medra_code', None)
        )
        queries.append(SearchQuery(
            drug_name=signal.drug_name,
            adverse_event_term=signal.adverse_event_term,
            medra_code=getattr(signal, 'medra_code', None),
            query_string=pubmed_query,
            database="pubmed"
        ))
        
        # ClinicalTrials.gov query
        clinical_trials_query = self._build_clinical_trials_query(
            signal.drug_name,
            signal.adverse_event_term
        )
        queries.append(SearchQuery(
            drug_name=signal.drug_name,
            adverse_event_term=signal.adverse_event_term,
            medra_code=getattr(signal, 'medra_code', None),
            query_string=clinical_trials_query,
            database="clinicaltrials"
        ))
        
        return queries
    
    def _build_pubmed_query(
        self,
        drug_name: str,
        adverse_event_term: str,
        medra_code: Optional[str] = None
    ) -> str:
        """
        Build a PubMed search query.
        
        Args:
            drug_name: Name of the drug
            adverse_event_term: Adverse event term
            medra_code: Optional MedDRA code
            
        Returns:
            Formatted PubMed query string
        """
        # Base query with drug and event
        query_parts = [
            f'"{drug_name}"[Title/Abstract]',
            f'"{adverse_event_term}"[Title/Abstract]'
        ]
        
        # Add safety-related terms
        query_parts.append('(adverse OR safety OR toxicity OR "side effect")')
        
        # Add MedDRA code if available
        if medra_code:
            query_parts.append(f'"{medra_code}"[MeSH Terms]')
        
        return " AND ".join(query_parts)
    
    def _build_clinical_trials_query(
        self,
        drug_name: str,
        adverse_event_term: str
    ) -> str:
        """
        Build a ClinicalTrials.gov search query.
        
        Args:
            drug_name: Name of the drug
            adverse_event_term: Adverse event term
            
        Returns:
            Formatted clinical trials query string
        """
        return f"{drug_name} AND {adverse_event_term}"
    
    def _search_database(self, query: SearchQuery) -> List[Article]:
        """
        Search a specific database using the Browser Tool.
        
        Args:
            query: Search query for the database
            
        Returns:
            List of Article objects
            
        Raises:
            BrowserToolError: If browser access fails
        """
        if self.browser:
            # Use provided browser (for testing or actual Browser Tool)
            try:
                return self.browser.search(query)
            except Exception as e:
                raise BrowserToolError(f"Browser search failed: {str(e)}")
        
        # Simulate search results for now (would use actual Browser Tool in production)
        # This is a placeholder implementation
        return self._simulate_search_results(query)
    
    def _simulate_search_results(self, query: SearchQuery) -> List[Article]:
        """
        Simulate search results (placeholder for actual Browser Tool integration).
        
        Args:
            query: Search query
            
        Returns:
            List of simulated Article objects
        """
        # In production, this would be replaced with actual Browser Tool calls
        # For now, return empty list or mock data
        return []
    
    def extract_relevant_cases(
        self,
        articles: List[Article],
        signal: Signal
    ) -> List[Article]:
        """
        Extract relevant case reports, clinical trials, and meta-analyses.
        
        Args:
            articles: List of all articles found
            signal: Signal being investigated
            
        Returns:
            Filtered list of relevant articles
        """
        if not articles:
            return []
        
        relevant = []
        
        for article in articles:
            # Calculate relevance based on title and abstract content
            relevance = self._calculate_relevance(article, signal)
            
            # Update article relevance score
            article.relevance_score = relevance
            
            # Include if relevance is above threshold
            if relevance >= 0.5:  # 50% relevance threshold
                relevant.append(article)
        
        # Sort by relevance (highest first)
        relevant.sort(key=lambda a: a.relevance_score, reverse=True)
        
        # Return top 20 most relevant
        return relevant[:20]
    
    def _calculate_relevance(self, article: Article, signal: Signal) -> float:
        """
        Calculate relevance score for an article.
        
        Args:
            article: Article to score
            signal: Signal being investigated
            
        Returns:
            Relevance score between 0.0 and 1.0
        """
        score = 0.0
        text = (article.title + " " + article.abstract).lower()
        
        # Check for drug name
        if signal.drug_name.lower() in text:
            score += 0.4
        
        # Check for adverse event term
        if signal.adverse_event_term.lower() in text:
            score += 0.4
        
        # Bonus for safety-related keywords
        safety_keywords = ['adverse', 'safety', 'toxicity', 'side effect', 'risk']
        for keyword in safety_keywords:
            if keyword in text:
                score += 0.05
                break
        
        # Bonus for study type keywords
        study_keywords = ['clinical trial', 'case report', 'meta-analysis', 'cohort']
        for keyword in study_keywords:
            if keyword in text:
                score += 0.15
                break
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _generate_summary(
        self,
        articles: List[Article],
        signal: Signal
    ) -> str:
        """
        Generate a summary of literature findings.
        
        Args:
            articles: List of relevant articles
            signal: Signal being investigated
            
        Returns:
            Summary text with citations
        """
        if not articles:
            return (
                f"No published literature found for {signal.drug_name} "
                f"and {signal.adverse_event_term}. This may represent a novel signal "
                f"requiring further investigation."
            )
        
        # Count article types
        case_reports = sum(1 for a in articles if 'case report' in a.title.lower())
        clinical_trials = sum(1 for a in articles if 'trial' in a.title.lower())
        meta_analyses = sum(1 for a in articles if 'meta-analysis' in a.title.lower())
        
        summary_parts = [
            f"Literature search for {signal.drug_name} and {signal.adverse_event_term} "
            f"identified {len(articles)} relevant publications."
        ]
        
        if case_reports > 0:
            summary_parts.append(f"{case_reports} case report(s) documented similar events.")
        
        if clinical_trials > 0:
            summary_parts.append(f"{clinical_trials} clinical trial(s) reported this adverse event.")
        
        if meta_analyses > 0:
            summary_parts.append(f"{meta_analyses} meta-analysis/analyses reviewed this association.")
        
        # Add top 3 citations
        if len(articles) > 0:
            summary_parts.append("\n\nKey references:")
            for i, article in enumerate(articles[:3], 1):
                citation = f"{i}. {article.title} ({article.journal}, {article.publication_date.year})"
                if article.pmid:
                    citation += f" PMID: {article.pmid}"
                summary_parts.append(citation)
        
        return " ".join(summary_parts)



def create_literature_mining_strands_agent(config=None):
    """
    Create a Strands Agent wrapper for Literature Mining Agent.
    
    This function creates a Strands Agent that can be used with A2AServer
    for agent-to-agent communication.
    
    Args:
        config: AgentCore configuration
        
    Returns:
        Strands Agent instance
    """
    from strands import Agent
    
    # Create the underlying agent
    agent_impl = LiteratureMiningAgent(config=config)
    
    def search_literature_tool(signal_json: str) -> str:
        """
        Tool to search medical literature for a detected signal.
        
        Args:
            signal_json: JSON string containing signal data
            
        Returns:
            JSON string with literature search results
        """
        import json
        
        try:
            # Parse signal from JSON
            signal_data = json.loads(signal_json)
            signal = Signal(**signal_data)
            
            # Search literature
            result = agent_impl.search_literature(signal)
            
            # Return as JSON
            return json.dumps({
                'query': result.query,
                'articles': [a.__dict__ for a in result.articles],
                'summary': result.summary,
                'total_results': result.total_results,
                'searched_at': result.searched_at.isoformat()
            }, default=str)
            
        except Exception as e:
            return json.dumps({
                'error': str(e),
                'error_type': type(e).__name__
            })
    
    # Create Strands Agent
    return Agent(
        name="Literature Mining Agent",
        description="""
        I am a literature mining agent specialized in searching medical literature 
        for evidence related to adverse event signals. I search PubMed, clinical trial 
        databases, and other medical sources to contextualize detected signals with 
        published evidence.
        """,
        tools=[search_literature_tool],
        instructions="""
        When you receive a signal:
        1. Construct comprehensive search queries including drug name, adverse event term, and MedDRA codes
        2. Search multiple databases (PubMed, ClinicalTrials.gov)
        3. Extract relevant case reports, clinical trials, and meta-analyses
        4. Score articles by relevance
        5. Summarize findings with citation links
        6. Handle database access failures gracefully
        """
    )
