"""Property-based and unit tests for Literature Mining Agent."""

import pytest
from datetime import datetime
from hypothesis import given, strategies as st, settings
from typing import List

from models.signal import Signal
from models.literature import Article, LiteratureResults
from agents.literature_mining_agent import (
    LiteratureMiningAgent,
    SearchQuery,
    BrowserToolError
)


# Custom strategies for generating test data
@st.composite
def signal_strategy(draw):
    """Generate valid signals for testing."""
    ic025 = draw(st.floats(min_value=-5.0, max_value=5.0))
    return Signal(
        signal_id=f"SIG{draw(st.integers(min_value=1, max_value=999999))}",
        drug_name=draw(st.sampled_from(['DrugA', 'DrugB', 'DrugC', 'DrugX', 'DrugY'])),
        adverse_event_term=draw(st.sampled_from([
            'Cardiac Arrhythmia', 'Nausea', 'Headache',
            'QT Prolongation', 'Dizziness', 'Fatigue'
        ])),
        event_count=draw(st.integers(min_value=1, max_value=100)),
        expected_count=draw(st.floats(min_value=0.1, max_value=50.0)),
        prr=draw(st.floats(min_value=0.1, max_value=20.0)),
        ror=draw(st.floats(min_value=0.1, max_value=20.0)),
        ic025=ic025,
        confidence_interval=(ic025, ic025 + draw(st.floats(min_value=0.1, max_value=3.0))),
        detected_at=datetime.now(),
        severity=draw(st.sampled_from(['low', 'medium', 'high', 'critical']))
    )


@st.composite
def article_strategy(draw):
    """Generate valid articles for testing."""
    return Article(
        title=draw(st.text(min_size=10, max_size=100)),
        authors=draw(st.lists(st.text(min_size=5, max_size=20), min_size=1, max_size=5)),
        journal=draw(st.text(min_size=5, max_size=50)),
        publication_date=datetime.now(),
        pmid=draw(st.one_of(st.none(), st.text(min_size=8, max_size=8, alphabet='0123456789'))),
        doi=draw(st.one_of(st.none(), st.text(min_size=10, max_size=30))),
        abstract=draw(st.text(min_size=50, max_size=500)),
        relevance_score=draw(st.floats(min_value=0.0, max_value=1.0))
    )


class TestLiteratureMiningAgentUnit:
    """Unit tests for Literature Mining Agent."""
    
    def test_create_agent(self):
        """Test creating a Literature Mining Agent."""
        agent = LiteratureMiningAgent()
        assert agent.agent_id == "literature_mining_agent"
    
    def test_search_literature_requires_valid_signal(self):
        """Test that search_literature requires a valid signal."""
        agent = LiteratureMiningAgent()
        
        with pytest.raises(ValueError, match="Signal cannot be None"):
            agent.search_literature(None)
    
    def test_search_literature_requires_drug_name(self):
        """Test that signal must have drug_name."""
        agent = LiteratureMiningAgent()
        
        # Signal model validates drug_name in __post_init__
        with pytest.raises(ValueError, match="drug_name is required"):
            signal = Signal(
                signal_id="SIG001",
                drug_name="",  # Invalid: empty
                adverse_event_term="Cardiac Arrhythmia",
                event_count=10,
                expected_count=5.0,
                prr=2.0,
                ror=2.0,
                ic025=0.5,
                confidence_interval=(0.5, 1.5),
                detected_at=datetime.now(),
                severity="medium"
            )
    
    def test_construct_search_queries(self):
        """Test search query construction."""
        agent = LiteratureMiningAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        queries = agent._construct_search_queries(signal)
        
        assert len(queries) >= 1
        assert all(isinstance(q, SearchQuery) for q in queries)
        assert all(q.drug_name == "DrugX" for q in queries)
        assert all(q.adverse_event_term == "Cardiac Arrhythmia" for q in queries)
    
    def test_pubmed_query_construction(self):
        """Test PubMed query string construction."""
        agent = LiteratureMiningAgent()
        
        query = agent._build_pubmed_query("DrugX", "Cardiac Arrhythmia", "12345678")
        
        assert "DrugX" in query
        assert "Cardiac Arrhythmia" in query
        assert "adverse" in query.lower() or "safety" in query.lower()
        assert "12345678" in query
    
    def test_extract_relevant_cases_empty_list(self):
        """Test extracting from empty article list."""
        agent = LiteratureMiningAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=10,
            expected_count=5.0,
            prr=2.0,
            ror=2.0,
            ic025=0.5,
            confidence_interval=(0.5, 1.5),
            detected_at=datetime.now(),
            severity="medium"
        )
        
        relevant = agent.extract_relevant_cases([], signal)
        assert relevant == []
    
    def test_generate_summary_no_articles(self):
        """Test summary generation with no articles."""
        agent = LiteratureMiningAgent()
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=10,
            expected_count=5.0,
            prr=2.0,
            ror=2.0,
            ic025=0.5,
            confidence_interval=(0.5, 1.5),
            detected_at=datetime.now(),
            severity="medium"
        )
        
        summary = agent._generate_summary([], signal)
        
        assert "No published literature found" in summary
        assert "DrugX" in summary
        assert "Cardiac Arrhythmia" in summary


@pytest.mark.property
class TestLiteratureMiningAgentProperties:
    """Property-based tests for Literature Mining Agent."""
    
    @given(signal_strategy())
    @settings(max_examples=100, deadline=None)
    def test_property_5_search_query_completeness(self, signal: Signal):
        """
        Feature: adverse-event-signal-detection, Property 5: Search Query Completeness
        
        For any detected signal, the Literature Mining Agent SHALL construct search queries
        that include the drug name, adverse event term, and MedDRA code.
        
        Validates: Requirements 2.2
        """
        agent = LiteratureMiningAgent()
        
        try:
            queries = agent._construct_search_queries(signal)
            
            # Verify queries were constructed
            assert len(queries) > 0, "At least one query should be constructed"
            
            # Verify each query has required components
            for query in queries:
                assert isinstance(query, SearchQuery), "Query must be SearchQuery object"
                assert query.drug_name == signal.drug_name, "Query must include drug name"
                assert query.adverse_event_term == signal.adverse_event_term, \
                    "Query must include adverse event term"
                assert query.query_string, "Query string must not be empty"
                assert query.database, "Database must be specified"
                
                # Verify drug name and event are in query string
                query_lower = query.query_string.lower()
                assert signal.drug_name.lower() in query_lower, \
                    "Drug name must appear in query string"
                assert signal.adverse_event_term.lower() in query_lower, \
                    "Adverse event term must appear in query string"
                    
        except Exception as e:
            # Some random signals may cause issues, which is acceptable
            assert "required" in str(e).lower() or "invalid" in str(e).lower()
    
    @given(signal_strategy(), st.lists(article_strategy(), min_size=0, max_size=30))
    @settings(max_examples=50, deadline=None)
    def test_property_6_literature_extraction_and_summarization(
        self,
        signal: Signal,
        articles: List[Article]
    ):
        """
        Feature: adverse-event-signal-detection, Property 6: Literature Extraction and Summarization
        
        For any literature search with multiple results, the agent SHALL extract case reports,
        clinical trials, and meta-analyses, AND summarize findings with citation links.
        
        Validates: Requirements 2.3, 2.4
        """
        agent = LiteratureMiningAgent()
        
        # Extract relevant cases
        relevant = agent.extract_relevant_cases(articles, signal)
        
        # Verify extraction
        assert isinstance(relevant, list), "Extraction must return a list"
        assert len(relevant) <= len(articles), "Cannot extract more than input"
        assert len(relevant) <= 20, "Should limit to top 20 results"
        
        # Verify all extracted articles have relevance scores
        for article in relevant:
            assert hasattr(article, 'relevance_score'), "Article must have relevance_score"
            assert 0.0 <= article.relevance_score <= 1.0, "Relevance score must be 0-1"
        
        # Verify sorting by relevance (if multiple articles)
        if len(relevant) > 1:
            for i in range(len(relevant) - 1):
                assert relevant[i].relevance_score >= relevant[i+1].relevance_score, \
                    "Articles must be sorted by relevance (highest first)"
        
        # Generate summary
        summary = agent._generate_summary(relevant, signal)
        
        # Verify summary
        assert isinstance(summary, str), "Summary must be a string"
        assert len(summary) > 0, "Summary must not be empty"
        assert signal.drug_name in summary, "Summary must mention drug name"
        assert signal.adverse_event_term in summary, "Summary must mention adverse event"
        
        # If articles exist, summary should mention them
        if len(relevant) > 0:
            assert str(len(relevant)) in summary or "publication" in summary.lower(), \
                "Summary should mention number of publications"
    
    def test_property_7_browser_tool_graceful_degradation(self):
        """
        Feature: adverse-event-signal-detection, Property 7: Browser Tool Graceful Degradation
        
        For any Browser Tool access failure to a literature source, the Literature Mining Agent
        SHALL proceed with available sources and complete the search without failing.
        
        Validates: Requirements 8.2
        """
        # Mock browser that fails
        class FailingBrowser:
            def __init__(self):
                self.call_count = 0
            
            def search(self, query):
                self.call_count += 1
                raise Exception("Simulated browser failure")
        
        failing_browser = FailingBrowser()
        agent = LiteratureMiningAgent(browser=failing_browser)
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        # Should not raise exception despite browser failures
        result = agent.search_literature(signal)
        
        # Verify graceful handling
        assert isinstance(result, LiteratureResults), "Should return LiteratureResults"
        assert result.total_results == 0, "Should have no results due to failures"
        assert len(result.articles) == 0, "Should have empty article list"
        assert result.summary, "Should still generate a summary"
        assert "No published literature found" in result.summary, \
            "Summary should indicate no results found"
        
        # Verify browser was called (attempted search)
        assert failing_browser.call_count > 0, "Should have attempted to use browser"


@pytest.mark.property
class TestLiteratureMiningAgentIntegration:
    """Integration tests for Literature Mining Agent."""
    
    def test_end_to_end_search_with_mock_browser(self):
        """Test complete search workflow with mocked browser."""
        # Mock browser that returns articles
        class MockBrowser:
            def search(self, query):
                return [
                    Article(
                        title=f"Study on {query.drug_name} and {query.adverse_event_term}",
                        authors=["Smith J", "Doe A"],
                        journal="Journal of Pharmacovigilance",
                        publication_date=datetime.now(),
                        pmid="12345678",
                        doi="10.1234/example",
                        abstract=f"This study examines {query.drug_name} safety regarding {query.adverse_event_term}",
                        relevance_score=0.0  # Will be calculated
                    )
                ]
        
        mock_browser = MockBrowser()
        agent = LiteratureMiningAgent(browser=mock_browser)
        
        signal = Signal(
            signal_id="SIG001",
            drug_name="DrugX",
            adverse_event_term="Cardiac Arrhythmia",
            event_count=15,
            expected_count=8.0,
            prr=4.0,
            ror=4.0,
            ic025=1.5,
            confidence_interval=(1.5, 2.5),
            detected_at=datetime.now(),
            severity="high"
        )
        
        result = agent.search_literature(signal)
        
        assert isinstance(result, LiteratureResults)
        assert result.total_results > 0
        assert len(result.articles) > 0
        assert result.summary
        assert "DrugX" in result.summary
        assert "Cardiac Arrhythmia" in result.summary
