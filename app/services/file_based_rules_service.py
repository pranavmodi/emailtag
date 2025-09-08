#!/usr/bin/env python3
"""
File-based Classification Rules Service

This service loads classification rules directly from .txt files in /app/prompts/rules/
based on rule keys, eliminating the need for database storage.

Rule Key Format: "ROOT", "ROOT_SCHEDULING", "ROOT_SCHEDULING_RX", etc.
File Path Format: /app/prompts/rules/{rule_key}.txt

Examples:
- ROOT → /app/prompts/rules/ROOT.txt
- ROOT_SCHEDULING → /app/prompts/rules/ROOT_SCHEDULING.txt  
- ROOT_SCHEDULING_RX → /app/prompts/rules/ROOT_SCHEDULING_RX.txt
"""

import os
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class FileBasedRulesService:
    """Service for loading classification rules from .txt files."""
    
    def __init__(self):
        self.rules_dir = Path(__file__).parent.parent / "prompts" / "rules"
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileBasedRulesService initialized with rules directory: {self.rules_dir}")
        
    def _get_rule_file_path(self, rule_key: str) -> Path:
        """Get the file path for a given rule key."""
        return self.rules_dir / f"{rule_key}.txt"
    
    def get_rule_content(self, rule_key: str) -> Optional[str]:
        """
        Load rule content from file based on rule key.
        
        Args:
            rule_key (str): Rule identifier like "ROOT", "ROOT_SCHEDULING_RX"
            
        Returns:
            Optional[str]: Rule content or None if file doesn't exist
        """
        file_path = self._get_rule_file_path(rule_key)
        
        try:
            if not file_path.exists():
                logger.warning(f"Rule file not found: {file_path}")
                return None
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            if not content:
                logger.warning(f"Empty rule file: {file_path}")
                return None
                
            logger.info(f"Successfully loaded rule '{rule_key}' from {file_path} ({len(content)} chars)")
            return content
            
        except Exception as e:
            logger.error(f"Error reading rule file {file_path}: {e}", exc_info=True)
            return None
    
    def save_rule_content(self, rule_key: str, content: str) -> bool:
        """
        Save rule content to file.
        
        Args:
            rule_key (str): Rule identifier
            content (str): Rule content to save
            
        Returns:
            bool: True if saved successfully
        """
        file_path = self._get_rule_file_path(rule_key)
        
        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            logger.info(f"Successfully saved rule '{rule_key}' to {file_path} ({len(content)} chars)")
            return True
            
        except Exception as e:
            logger.error(f"Error saving rule file {file_path}: {e}", exc_info=True)
            return False
    
    def list_all_rules(self) -> List[Dict[str, Any]]:
        """
        List all available rule files with metadata.
        
        Returns:
            List[Dict]: List of rule info dictionaries
        """
        rules = []
        
        if not self.rules_dir.exists():
            logger.warning(f"Rules directory does not exist: {self.rules_dir}")
            return rules
        
        for file_path in self.rules_dir.glob("*.txt"):
            try:
                rule_key = file_path.stem  # Filename without .txt extension
                stat = file_path.stat()
                
                # Get content length without loading full content
                content_length = 0
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        content_length = len(content.strip())
                except:
                    content_length = 0
                
                rules.append({
                    'rule_key': rule_key,
                    'file_path': str(file_path),
                    'file_size': stat.st_size,
                    'content_length': content_length,
                    'modified_time': datetime.fromtimestamp(stat.st_mtime),
                    'has_content': content_length > 0
                })
                
            except Exception as e:
                logger.warning(f"Error processing rule file {file_path}: {e}")
                continue
        
        # Sort by rule key
        rules.sort(key=lambda r: r['rule_key'])
        return rules
    
    def rule_exists(self, rule_key: str) -> bool:
        """Check if a rule file exists."""
        return self._get_rule_file_path(rule_key).exists()
    
    def delete_rule(self, rule_key: str) -> bool:
        """
        Delete a rule file.
        
        Args:
            rule_key (str): Rule identifier
            
        Returns:
            bool: True if deleted successfully
        """
        file_path = self._get_rule_file_path(rule_key)
        
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Successfully deleted rule '{rule_key}' from {file_path}")
                return True
            else:
                logger.warning(f"Rule file does not exist: {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting rule file {file_path}: {e}", exc_info=True)
            return False
    
    def get_rule_info(self, rule_key: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata about a specific rule.
        
        Args:
            rule_key (str): Rule identifier
            
        Returns:
            Optional[Dict]: Rule metadata or None if not found
        """
        file_path = self._get_rule_file_path(rule_key)
        
        if not file_path.exists():
            return None
            
        try:
            stat = file_path.stat()
            content = self.get_rule_content(rule_key) or ""
            
            return {
                'rule_key': rule_key,
                'file_path': str(file_path),
                'file_size': stat.st_size,
                'content_length': len(content),
                'modified_time': datetime.fromtimestamp(stat.st_mtime),
                'has_content': len(content.strip()) > 0,
                'content': content
            }
            
        except Exception as e:
            logger.error(f"Error getting rule info for {rule_key}: {e}", exc_info=True)
            return None


# Global instance
_file_based_rules_service: Optional[FileBasedRulesService] = None

def get_file_based_rules_service() -> FileBasedRulesService:
    """Get the global FileBasedRulesService instance."""
    global _file_based_rules_service
    if _file_based_rules_service is None:
        _file_based_rules_service = FileBasedRulesService()
    return _file_based_rules_service