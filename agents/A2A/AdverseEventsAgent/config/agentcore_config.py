"""AgentCore service configuration."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CodeInterpreterConfig:
    """Configuration for AgentCore Code Interpreter service."""
    
    enabled: bool = True
    timeout_seconds: int = 300
    max_retries: int = 1
    retry_delay_seconds: int = 5
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv('CODE_INTERPRETER_ENABLED', 'true').lower() == 'true',
            timeout_seconds=int(os.getenv('CODE_INTERPRETER_TIMEOUT', '300')),
            max_retries=int(os.getenv('CODE_INTERPRETER_MAX_RETRIES', '1')),
            retry_delay_seconds=int(os.getenv('CODE_INTERPRETER_RETRY_DELAY', '5')),
        )


@dataclass
class BrowserConfig:
    """Configuration for AgentCore Browser service."""
    
    enabled: bool = True
    timeout_seconds: int = 60
    max_concurrent_requests: int = 5
    user_agent: str = "AgentCore-Browser/1.0"
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv('BROWSER_ENABLED', 'true').lower() == 'true',
            timeout_seconds=int(os.getenv('BROWSER_TIMEOUT', '60')),
            max_concurrent_requests=int(os.getenv('BROWSER_MAX_CONCURRENT', '5')),
            user_agent=os.getenv('BROWSER_USER_AGENT', 'AgentCore-Browser/1.0'),
        )


@dataclass
class GatewayConfig:
    """Configuration for AgentCore Gateway service."""
    
    enabled: bool = True
    medwatch_endpoint: Optional[str] = None
    eudravigilance_endpoint: Optional[str] = None
    timeout_seconds: int = 120
    retry_on_failure: bool = False
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv('GATEWAY_ENABLED', 'true').lower() == 'true',
            medwatch_endpoint=os.getenv('GATEWAY_MEDWATCH_ENDPOINT'),
            eudravigilance_endpoint=os.getenv('GATEWAY_EUDRAVIGILANCE_ENDPOINT'),
            timeout_seconds=int(os.getenv('GATEWAY_TIMEOUT', '120')),
            retry_on_failure=os.getenv('GATEWAY_RETRY', 'false').lower() == 'true',
        )


@dataclass
class MemoryConfig:
    """Configuration for AgentCore Semantic Memory service."""
    
    enabled: bool = True
    memory_id: Optional[str] = None
    top_k_results: int = 5
    similarity_threshold: float = 0.7
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables."""
        return cls(
            enabled=os.getenv('MEMORY_ENABLED', 'true').lower() == 'true',
            memory_id=os.getenv('MEMORY_ID'),
            top_k_results=int(os.getenv('MEMORY_TOP_K', '5')),
            similarity_threshold=float(os.getenv('MEMORY_SIMILARITY_THRESHOLD', '0.7')),
        )


@dataclass
class AgentCoreConfig:
    """Main configuration for all AgentCore services."""
    
    code_interpreter: CodeInterpreterConfig
    browser: BrowserConfig
    gateway: GatewayConfig
    memory: MemoryConfig
    
    # Runtime configuration
    region: str = "us-east-1"
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls):
        """Load all configurations from environment variables."""
        return cls(
            code_interpreter=CodeInterpreterConfig.from_env(),
            browser=BrowserConfig.from_env(),
            gateway=GatewayConfig.from_env(),
            memory=MemoryConfig.from_env(),
            region=os.getenv('AWS_REGION', 'us-east-1'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
        )
    
    @classmethod
    def default(cls):
        """Create default configuration."""
        return cls(
            code_interpreter=CodeInterpreterConfig(),
            browser=BrowserConfig(),
            gateway=GatewayConfig(),
            memory=MemoryConfig(),
        )
