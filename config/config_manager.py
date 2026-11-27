#!/usr/bin/env python3
"""
Configuration Manager for Reddit Scraper Toolkit
Handles configuration loading, validation, and management for different research contexts.
"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging
from dataclasses import dataclass, asdict
import os

@dataclass
class RedditConfig:
    """Reddit API configuration"""
    client_id: str
    client_secret: str
    user_agent: str

@dataclass
class SubredditConfig:
    """Subreddit-specific configuration"""
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    research_focus: Optional[str] = None

@dataclass
class PathConfig:
    """File paths configuration"""
    database: str
    checkpoint: str
    log: str
    output_dir: str

@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    user_discovery: float = 1.0
    content_extraction: float = 1.5
    comment_expansion: float = 2.0
    batch_processing: float = 2.0
    rate_limit_backoff: float = 60.0

@dataclass
class ScrapingConfig:
    """Scraping behavior configuration"""
    batch_size: int = 10
    max_users: Optional[int] = None
    max_posts_per_discovery: int = 1000
    time_filter: str = 'all'
    resume_on_interrupt: bool = True
    save_checkpoint_interval: int = 10

@dataclass
class AnalysisConfig:
    """Analysis configuration"""
    temporal_analysis: bool = True
    text_analysis: bool = True
    network_analysis: bool = True
    min_text_length: int = 10
    max_word_length: int = 20
    topic_modeling_topics: int = 10
    network_types: List[str] = None

    def __post_init__(self):
        if self.network_types is None:
            self.network_types = ['interaction', 'coparticipation']

class ConfigManager:
    """
    Central configuration management for the Reddit Scraper Toolkit.
    Supports multiple configuration formats and research contexts.
    """

    def __init__(self, config_dir: Union[str, Path] = None):
        """
        Initialize configuration manager.

        Args:
            config_dir: Directory containing configuration files
        """
        if config_dir is None:
            config_dir = Path(__file__).parent

        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)

        # Configuration templates directory
        self.templates_dir = self.config_dir / "templates"
        self.templates_dir.mkdir(exist_ok=True)

        self.logger = logging.getLogger(__name__)

    def load_config(self, config_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load configuration from file.

        Args:
            config_path: Path to configuration file (.json, .yaml, .yml)

        Returns:
            Configuration dictionary
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        file_extension = config_path.suffix.lower()

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if file_extension == '.json':
                    config = json.load(f)
                elif file_extension in ['.yaml', '.yml']:
                    config = yaml.safe_load(f)
                else:
                    raise ValueError(f"Unsupported configuration format: {file_extension}")

            # Validate and fill defaults
            config = self._validate_and_fill_defaults(config)

            self.logger.info(f"Loaded configuration from {config_path}")
            return config

        except Exception as e:
            raise ValueError(f"Error loading configuration from {config_path}: {e}")

    def create_config_from_template(self,
                                  template_name: str,
                                  subreddit_name: str,
                                  output_path: Union[str, Path] = None) -> Path:
        """
        Create a configuration file from a template.

        Args:
            template_name: Name of the template ('academic', 'commercial', 'personal', etc.)
            subreddit_name: Target subreddit name
            output_path: Output path for the configuration file

        Returns:
            Path to created configuration file
        """
        template_path = self.templates_dir / f"{template_name}.yaml"

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Load template
        with open(template_path, 'r', encoding='utf-8') as f:
            template_config = yaml.safe_load(f)

        # Customize for subreddit
        customized_config = self._customize_template(template_config, subreddit_name)

        # Determine output path
        if output_path is None:
            output_path = self.config_dir / f"{subreddit_name}_config.yaml"
        else:
            output_path = Path(output_path)

        # Save customized configuration
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(customized_config, f, default_flow_style=False, indent=2)

        self.logger.info(f"Created configuration file: {output_path}")
        return output_path

    def _customize_template(self, template_config: Dict[str, Any], subreddit_name: str) -> Dict[str, Any]:
        """Customize template configuration for specific subreddit."""
        config = template_config.copy()

        # Update subreddit info
        config['subreddit']['name'] = subreddit_name
        config['subreddit']['display_name'] = f"r/{subreddit_name}"

        # Update paths
        # One folder per community, the same layout tools/cli.py uses by default.
        base_name = subreddit_name.lower()
        archive = f"data/{base_name}_archive"
        config['paths']['database'] = f"{archive}/{base_name}.db"
        config['paths']['checkpoint'] = f"{archive}/checkpoint.pkl"
        config['paths']['log'] = f"{archive}/scrape.log"
        config['paths']['output_dir'] = f"{archive}/exports"

        return config

    def _validate_and_fill_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration and fill in defaults."""
        validated_config = config.copy()

        # Required sections
        required_sections = ['reddit', 'subreddit', 'paths']
        for section in required_sections:
            if section not in validated_config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Reddit API configuration
        reddit_config = validated_config['reddit']
        required_reddit_fields = ['client_id', 'client_secret', 'user_agent']
        for field in required_reddit_fields:
            if field not in reddit_config:
                raise ValueError(f"Missing required Reddit API field: {field}")

        # Subreddit configuration
        if 'name' not in validated_config['subreddit']:
            raise ValueError("Missing required field: subreddit.name")

        # Paths configuration
        paths_config = validated_config['paths']
        required_path_fields = ['database', 'checkpoint']
        for field in required_path_fields:
            if field not in paths_config:
                raise ValueError(f"Missing required path field: {field}")

        # Fill in defaults for optional sections
        if 'rate_limits' not in validated_config:
            validated_config['rate_limits'] = asdict(RateLimitConfig())

        if 'scraping' not in validated_config:
            validated_config['scraping'] = asdict(ScrapingConfig())

        if 'analysis' not in validated_config:
            validated_config['analysis'] = asdict(AnalysisConfig())

        # Ensure log path exists
        if 'log' not in paths_config:
            subreddit_name = validated_config['subreddit']['name']
            paths_config['log'] = f"logs/{subreddit_name}_scraper.log"

        # Ensure output directory exists
        if 'output_dir' not in paths_config:
            subreddit_name = validated_config['subreddit']['name']
            paths_config['output_dir'] = f"output/{subreddit_name}"

        return validated_config

    def get_research_context_template(self, context: str) -> Dict[str, Any]:
        """
        Get configuration template for specific research context.

        Args:
            context: Research context ('academic', 'commercial', 'personal', 'comparative')

        Returns:
            Configuration template dictionary
        """
        templates = {
            'academic': {
                'research_context': 'academic',
                'reddit': {
                    'client_id': 'YOUR_CLIENT_ID',
                    'client_secret': 'YOUR_CLIENT_SECRET',
                    'user_agent': 'Academic Research Bot v1.0 by /u/YourUsername'
                },
                'subreddit': {
                    'name': 'PLACEHOLDER',
                    'research_focus': 'Academic research on online communities'
                },
                'paths': {
                    'database': 'databases/PLACEHOLDER_data.db',
                    'checkpoint': 'checkpoints/PLACEHOLDER_checkpoint.pkl',
                    'log': 'logs/PLACEHOLDER_scraper.log',
                    'output_dir': 'output/PLACEHOLDER'
                },
                'rate_limits': asdict(RateLimitConfig(
                    user_discovery=1.5,
                    content_extraction=2.0,
                    comment_expansion=2.5,
                    batch_processing=3.0
                )),
                'scraping': asdict(ScrapingConfig(
                    batch_size=5,
                    max_users=None,
                    resume_on_interrupt=True,
                    save_checkpoint_interval=5
                )),
                'analysis': asdict(AnalysisConfig(
                    temporal_analysis=True,
                    text_analysis=True,
                    network_analysis=True,
                    topic_modeling_topics=15
                ))
            },

            'commercial': {
                'research_context': 'commercial',
                'reddit': {
                    'client_id': 'YOUR_CLIENT_ID',
                    'client_secret': 'YOUR_CLIENT_SECRET',
                    'user_agent': 'Market Research Tool v1.0'
                },
                'subreddit': {
                    'name': 'PLACEHOLDER',
                    'research_focus': 'Market research and consumer insights'
                },
                'paths': {
                    'database': 'data/PLACEHOLDER_market_data.db',
                    'checkpoint': 'checkpoints/PLACEHOLDER_checkpoint.pkl',
                    'log': 'logs/PLACEHOLDER_market_research.log',
                    'output_dir': 'output/market_research/PLACEHOLDER'
                },
                'rate_limits': asdict(RateLimitConfig(
                    user_discovery=0.8,
                    content_extraction=1.2,
                    batch_processing=1.5
                )),
                'scraping': asdict(ScrapingConfig(
                    batch_size=15,
                    max_users=5000,
                    time_filter='month'
                )),
                'analysis': asdict(AnalysisConfig(
                    temporal_analysis=True,
                    text_analysis=True,
                    network_analysis=False,
                    topic_modeling_topics=20
                ))
            },

            'personal': {
                'research_context': 'personal',
                'reddit': {
                    'client_id': 'YOUR_CLIENT_ID',
                    'client_secret': 'YOUR_CLIENT_SECRET',
                    'user_agent': 'Personal Data Collection Tool v1.0'
                },
                'subreddit': {
                    'name': 'PLACEHOLDER',
                    'research_focus': 'Personal interest and learning'
                },
                'paths': {
                    'database': 'personal_data/PLACEHOLDER.db',
                    'checkpoint': 'PLACEHOLDER_checkpoint.pkl',
                    'log': 'PLACEHOLDER.log',
                    'output_dir': 'output/PLACEHOLDER'
                },
                'rate_limits': asdict(RateLimitConfig()),
                'scraping': asdict(ScrapingConfig(
                    batch_size=8,
                    max_users=1000,
                    time_filter='week'
                )),
                'analysis': asdict(AnalysisConfig(
                    temporal_analysis=True,
                    text_analysis=True,
                    network_analysis=True,
                    topic_modeling_topics=8
                ))
            },

            'comparative': {
                'research_context': 'comparative',
                'reddit': {
                    'client_id': 'YOUR_CLIENT_ID',
                    'client_secret': 'YOUR_CLIENT_SECRET',
                    'user_agent': 'Comparative Analysis Tool v1.0'
                },
                'subreddit': {
                    'name': 'PLACEHOLDER',
                    'research_focus': 'Comparative analysis across communities'
                },
                'paths': {
                    'database': 'comparative_data/PLACEHOLDER_data.db',
                    'checkpoint': 'comparative_data/PLACEHOLDER_checkpoint.pkl',
                    'log': 'logs/comparative_PLACEHOLDER.log',
                    'output_dir': 'output/comparative/PLACEHOLDER'
                },
                'rate_limits': asdict(RateLimitConfig(
                    user_discovery=1.8,
                    content_extraction=2.2,
                    batch_processing=2.5
                )),
                'scraping': asdict(ScrapingConfig(
                    batch_size=6,
                    save_checkpoint_interval=8
                )),
                'analysis': asdict(AnalysisConfig(
                    temporal_analysis=True,
                    text_analysis=True,
                    network_analysis=True,
                    topic_modeling_topics=12,
                    network_types=['interaction', 'coparticipation']
                ))
            }
        }

        if context not in templates:
            raise ValueError(f"Unknown research context: {context}. Available: {list(templates.keys())}")

        return templates[context]

    def create_default_templates(self):
        """Create default configuration templates in the templates directory."""
        contexts = ['academic', 'commercial', 'personal', 'comparative']

        for context in contexts:
            template_path = self.templates_dir / f"{context}.yaml"

            if not template_path.exists():
                template_config = self.get_research_context_template(context)

                with open(template_path, 'w', encoding='utf-8') as f:
                    yaml.dump(template_config, f, default_flow_style=False, indent=2)

                self.logger.info(f"Created template: {template_path}")

    def validate_paths(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate and create necessary directories from configuration.

        Args:
            config: Configuration dictionary

        Returns:
            List of created directories
        """
        created_dirs = []
        paths_config = config.get('paths', {})

        # Create directories for file paths
        for path_key, path_value in paths_config.items():
            if path_key in ['database', 'checkpoint', 'log']:
                dir_path = Path(path_value).parent
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(str(dir_path))

            elif path_key == 'output_dir':
                output_path = Path(path_value)
                if not output_path.exists():
                    output_path.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(str(output_path))

        return created_dirs

    def update_config_from_env(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update configuration with environment variables.
        Useful for keeping secrets out of config files.

        Args:
            config: Configuration dictionary

        Returns:
            Updated configuration dictionary
        """
        updated_config = config.copy()

        # Reddit API credentials from environment
        env_mappings = {
            'REDDIT_CLIENT_ID': ['reddit', 'client_id'],
            'REDDIT_CLIENT_SECRET': ['reddit', 'client_secret'],
            'REDDIT_USER_AGENT': ['reddit', 'user_agent']
        }

        for env_var, config_path in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value:
                # Navigate to the nested dictionary location
                current_dict = updated_config
                for key in config_path[:-1]:
                    if key not in current_dict:
                        current_dict[key] = {}
                    current_dict = current_dict[key]

                # Set the value
                current_dict[config_path[-1]] = env_value
                self.logger.info(f"Updated {'.'.join(config_path)} from environment variable {env_var}")

        return updated_config

    def export_config_schema(self, output_path: Union[str, Path] = None) -> str:
        """
        Export JSON schema for configuration validation.

        Args:
            output_path: Output path for schema file

        Returns:
            Path to exported schema file
        """
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": "Reddit Scraper Toolkit Configuration",
            "type": "object",
            "required": ["reddit", "subreddit", "paths"],
            "properties": {
                "research_context": {
                    "type": "string",
                    "enum": ["academic", "commercial", "personal", "comparative"]
                },
                "reddit": {
                    "type": "object",
                    "required": ["client_id", "client_secret", "user_agent"],
                    "properties": {
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                        "user_agent": {"type": "string"}
                    }
                },
                "subreddit": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string"},
                        "display_name": {"type": "string"},
                        "description": {"type": "string"},
                        "research_focus": {"type": "string"}
                    }
                },
                "paths": {
                    "type": "object",
                    "required": ["database", "checkpoint"],
                    "properties": {
                        "database": {"type": "string"},
                        "checkpoint": {"type": "string"},
                        "log": {"type": "string"},
                        "output_dir": {"type": "string"}
                    }
                },
                "rate_limits": {
                    "type": "object",
                    "properties": {
                        "user_discovery": {"type": "number", "minimum": 0},
                        "content_extraction": {"type": "number", "minimum": 0},
                        "comment_expansion": {"type": "number", "minimum": 0},
                        "batch_processing": {"type": "number", "minimum": 0},
                        "rate_limit_backoff": {"type": "number", "minimum": 0}
                    }
                },
                "scraping": {
                    "type": "object",
                    "properties": {
                        "batch_size": {"type": "integer", "minimum": 1},
                        "max_users": {"type": ["integer", "null"], "minimum": 1},
                        "max_posts_per_discovery": {"type": "integer", "minimum": 1},
                        "time_filter": {
                            "type": "string",
                            "enum": ["hour", "day", "week", "month", "year", "all"]
                        },
                        "resume_on_interrupt": {"type": "boolean"},
                        "save_checkpoint_interval": {"type": "integer", "minimum": 1}
                    }
                },
                "analysis": {
                    "type": "object",
                    "properties": {
                        "temporal_analysis": {"type": "boolean"},
                        "text_analysis": {"type": "boolean"},
                        "network_analysis": {"type": "boolean"},
                        "min_text_length": {"type": "integer", "minimum": 1},
                        "max_word_length": {"type": "integer", "minimum": 1},
                        "topic_modeling_topics": {"type": "integer", "minimum": 2},
                        "network_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["interaction", "coparticipation", "mention", "similarity"]
                            }
                        }
                    }
                }
            }
        }

        if output_path is None:
            output_path = self.config_dir / "config_schema.json"
        else:
            output_path = Path(output_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2)

        self.logger.info(f"Exported configuration schema to {output_path}")
        return str(output_path)