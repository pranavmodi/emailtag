#!/usr/bin/env python3
"""
Hierarchical Classification Rules Management CLI

This script provides a command-line interface for navigating and managing 
hierarchical classification rules used by the email tagging system.

Features:
- Navigate hierarchy tree structure
- View rule content with syntax highlighting
- Update rule names and content
- Search rules by category or name
- Export/import rules for backup
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import uuid
import tempfile
import subprocess
from dataclasses import dataclass

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.services.hierarchical_rules_service import HierarchicalRulesService
from app.models.hierarchical_classification_rule import HierarchicalClassificationRule


@dataclass
class RuleNode:
    """Represents a rule node in the hierarchy tree."""
    category: str
    name: str
    rule_id: str
    children: List['RuleNode']
    level: int
    has_content: bool


class HierarchicalRulesManager:
    """CLI manager for hierarchical classification rules."""
    
    def __init__(self):
        self.rules_cache: List[HierarchicalClassificationRule] = []
        self.hierarchy_tree: List[RuleNode] = []
        self.current_path: List[str] = []
        
    async def initialize(self):
        """Initialize the manager and load rules from database."""
        async with AsyncSessionLocal() as db:
            service = HierarchicalRulesService(db)
            self.rules_cache = await service.get_all_hierarchical_rules(include_rule_content=True)
            self._build_hierarchy_tree()
            
    def _build_hierarchy_tree(self):
        """Build the hierarchy tree from flat rule list."""
        # Group rules by their hierarchy levels
        rules_by_category = {rule.category: rule for rule in self.rules_cache}
        
        # Build tree structure
        self.hierarchy_tree = []
        processed = set()
        
        def build_node(category: str, level: int = 0) -> Optional[RuleNode]:
            if category in processed:
                return None
                
            rule = rules_by_category.get(category)
            if not rule:
                return None
                
            processed.add(category)
            
            node = RuleNode(
                category=category,
                name=rule.name,
                rule_id=str(rule.id),
                children=[],
                level=level,
                has_content=bool(rule.rule.strip())
            )
            
            # Find children (categories that start with this category + "_")
            prefix = category + "_" if category != "ROOT" else "ROOT_"
            for child_category in rules_by_category.keys():
                if child_category != category and child_category.startswith(prefix):
                    # Make sure it's a direct child (no additional underscores)
                    remaining = child_category[len(prefix):]
                    if "_" not in remaining:
                        child_node = build_node(child_category, level + 1)
                        if child_node:
                            node.children.append(child_node)
            
            return node
        
        # Start with ROOT and build tree
        root_node = build_node("ROOT")
        if root_node:
            self.hierarchy_tree = [root_node]
            
        # Add any other top-level categories that don't start with ROOT
        for category in rules_by_category.keys():
            if not category.startswith("ROOT") and category not in processed:
                node = build_node(category)
                if node:
                    self.hierarchy_tree.append(node)
    
    def _print_tree(self, nodes: List[RuleNode], show_ids: bool = False, highlight_category: str = None):
        """Print the hierarchy tree with visual formatting."""
        for i, node in enumerate(nodes):
            is_last = i == len(nodes) - 1
            prefix = "└── " if is_last else "├── "
            
            # Add indentation for nested levels
            indent = "    " * node.level
            
            # Formatting
            name_color = "\033[92m" if highlight_category == node.category else "\033[94m"  # Green if highlighted, blue otherwise
            reset_color = "\033[0m"
            content_indicator = " 📝" if node.has_content else " ⚪"
            id_text = f" [{node.rule_id[:8]}]" if show_ids else ""
            
            print(f"{indent}{prefix}{name_color}{node.name}{reset_color}{content_indicator}{id_text}")
            print(f"{indent}    Category: {node.category}")
            
            if node.children:
                self._print_tree(node.children, show_ids, highlight_category)
    
    def _find_node_by_category(self, category: str, nodes: List[RuleNode] = None) -> Optional[RuleNode]:
        """Find a node by its category key."""
        if nodes is None:
            nodes = self.hierarchy_tree
            
        for node in nodes:
            if node.category == category:
                return node
            if node.children:
                result = self._find_node_by_category(category, node.children)
                if result:
                    return result
        return None
    
    def _find_rule_by_id(self, rule_id: str) -> Optional[HierarchicalClassificationRule]:
        """Find a rule by its ID."""
        for rule in self.rules_cache:
            if str(rule.id) == rule_id or str(rule.id).startswith(rule_id):
                return rule
        return None
    
    def _format_rule_content(self, content: str, max_width: int = 100) -> str:
        """Format rule content for display."""
        lines = content.split('\n')
        formatted_lines = []
        
        for line in lines:
            if len(line) <= max_width:
                formatted_lines.append(line)
            else:
                # Wrap long lines
                while len(line) > max_width:
                    formatted_lines.append(line[:max_width])
                    line = "  " + line[max_width:]  # Indent continuation
                if line.strip():
                    formatted_lines.append(line)
                    
        return '\n'.join(formatted_lines)
    
    async def show_tree(self, show_ids: bool = False):
        """Display the complete hierarchy tree."""
        print("\n" + "="*80)
        print("📋 HIERARCHICAL CLASSIFICATION RULES TREE")
        print("="*80)
        print("Legend: 📝 = Has content, ⚪ = No content\n")
        
        if self.hierarchy_tree:
            self._print_tree(self.hierarchy_tree, show_ids)
        else:
            print("No rules found in database.")
        print()
    
    async def navigate_to_category(self, category: str):
        """Navigate to a specific category."""
        node = self._find_node_by_category(category)
        if node:
            self.current_path = [category]
            print(f"\n📍 Navigated to: {node.name} ({category})")
            await self.show_current_context()
        else:
            print(f"❌ Category '{category}' not found.")
    
    async def show_current_context(self):
        """Show current location and available options."""
        if not self.current_path:
            await self.show_tree()
            return
            
        current_category = self.current_path[-1]
        node = self._find_node_by_category(current_category)
        
        if not node:
            print("❌ Current location invalid.")
            self.current_path = []
            return
            
        print(f"\n📍 Current Location: {node.name}")
        print(f"   Category: {current_category}")
        print(f"   Level: {node.level}")
        print(f"   Has Content: {'Yes 📝' if node.has_content else 'No ⚪'}")
        
        if node.children:
            print(f"\n🌳 Children ({len(node.children)}):")
            for child in node.children:
                content_icon = "📝" if child.has_content else "⚪"
                print(f"   • {child.name} ({child.category}) {content_icon}")
        else:
            print("\n🍃 No children (leaf node)")
    
    async def view_rule_content(self, identifier: str):
        """View the content of a rule by category or ID."""
        rule = None
        
        # Try to find by category first
        node = self._find_node_by_category(identifier)
        if node:
            rule = self._find_rule_by_id(node.rule_id)
        else:
            # Try to find by ID
            rule = self._find_rule_by_id(identifier)
        
        if not rule:
            print(f"❌ Rule not found: {identifier}")
            return
        
        print("\n" + "="*80)
        print(f"📝 RULE CONTENT: {rule.name}")
        print("="*80)
        print(f"Category: {rule.category}")
        print(f"ID: {rule.id}")
        print(f"Created: {rule.created_at}")
        print(f"Updated: {rule.updated_at}")
        print("-"*80)
        
        if rule.rule.strip():
            formatted_content = self._format_rule_content(rule.rule)
            print(formatted_content)
        else:
            print("⚪ No content defined for this rule.")
        
        print("="*80)
    
    async def update_rule(self, identifier: str, field: str = None):
        """Update a rule's name or content."""
        rule = None
        
        # Find the rule
        node = self._find_node_by_category(identifier)
        if node:
            rule = self._find_rule_by_id(node.rule_id)
        else:
            rule = self._find_rule_by_id(identifier)
        
        if not rule:
            print(f"❌ Rule not found: {identifier}")
            return
        
        print(f"\n📝 Updating Rule: {rule.name}")
        print(f"Category: {rule.category}")
        print(f"Current Name: {rule.name}")
        
        # Determine what to update
        update_name = False
        update_content = False
        
        if field == "name":
            update_name = True
        elif field == "content":
            update_content = True
        else:
            # Interactive mode - ask user
            print("\nWhat would you like to update?")
            print("1. Name")
            print("2. Content")
            print("3. Both")
            
            choice = input("Enter choice (1-3): ").strip()
            if choice == "1":
                update_name = True
            elif choice == "2":
                update_content = True
            elif choice == "3":
                update_name = True
                update_content = True
            else:
                print("❌ Invalid choice.")
                return
        
        new_name = None
        new_content = None
        
        # Get new name
        if update_name:
            new_name = input(f"Enter new name (current: {rule.name}): ").strip()
            if not new_name:
                new_name = None
                print("⚠️  Name unchanged.")
        
        # Get new content
        if update_content:
            print(f"\nCurrent content preview:")
            preview = rule.rule[:200] + "..." if len(rule.rule) > 200 else rule.rule
            print(f"  {preview}")
            
            print("\nChoose content update method:")
            print("1. Enter content directly")
            print("2. Edit in external editor")
            
            method = input("Enter choice (1-2): ").strip()
            
            if method == "1":
                print("Enter new content (press Enter twice when done):")
                lines = []
                while True:
                    line = input()
                    if line == "" and lines and lines[-1] == "":
                        lines.pop()  # Remove the last empty line
                        break
                    lines.append(line)
                new_content = '\n'.join(lines)
                
            elif method == "2":
                # Use external editor
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
                    f.write(rule.rule)
                    temp_file = f.name
                
                editor = os.environ.get('EDITOR', 'nano')
                try:
                    subprocess.run([editor, temp_file], check=True)
                    with open(temp_file, 'r') as f:
                        new_content = f.read()
                finally:
                    os.unlink(temp_file)
            else:
                print("❌ Invalid choice.")
                return
        
        # Perform the update
        if new_name or new_content:
            try:
                async with AsyncSessionLocal() as db:
                    service = HierarchicalRulesService(db)
                    updated_rule = await service.update_hierarchical_rule(
                        rule_id=rule.id,
                        name=new_name,
                        rule_content=new_content
                    )
                    
                    if updated_rule:
                        print("✅ Rule updated successfully!")
                        # Refresh cache
                        await self.initialize()
                    else:
                        print("❌ Failed to update rule.")
                        
            except Exception as e:
                print(f"❌ Error updating rule: {e}")
        else:
            print("⚠️  No changes made.")
    
    async def search_rules(self, query: str):
        """Search rules by name or category."""
        query_lower = query.lower()
        matches = []
        
        for rule in self.rules_cache:
            if (query_lower in rule.name.lower() or 
                query_lower in rule.category.lower() or
                query_lower in rule.rule.lower()):
                matches.append(rule)
        
        if matches:
            print(f"\n🔍 Found {len(matches)} matching rules:")
            print("-" * 80)
            
            for rule in matches:
                content_icon = "📝" if rule.rule.strip() else "⚪"
                print(f"{content_icon} {rule.name}")
                print(f"   Category: {rule.category}")
                print(f"   ID: {str(rule.id)[:8]}")
                
                # Show content preview if query matches content
                if query_lower in rule.rule.lower():
                    lines = rule.rule.lower().split('\n')
                    for i, line in enumerate(lines):
                        if query_lower in line:
                            original_line = rule.rule.split('\n')[i]
                            preview = original_line[:100] + "..." if len(original_line) > 100 else original_line
                            print(f"   Content preview: ...{preview}...")
                            break
                
                print()
        else:
            print(f"❌ No rules found matching '{query}'")
    
    async def export_rules(self, output_file: str = None):
        """Export all rules to JSON file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"hierarchical_rules_export_{timestamp}.json"
        
        rules_data = []
        for rule in self.rules_cache:
            rules_data.append({
                "id": str(rule.id),
                "name": rule.name,
                "category": rule.category,
                "rule": rule.rule,
                "created_at": rule.created_at.isoformat(),
                "updated_at": rule.updated_at.isoformat()
            })
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(rules_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Exported {len(rules_data)} rules to {output_file}")
    
    def print_help(self):
        """Print help information."""
        help_text = """
📋 Hierarchical Classification Rules Manager - Commands:

NAVIGATION:
  tree [--ids]              - Show complete hierarchy tree
  nav <category>            - Navigate to specific category
  context                   - Show current location and context
  
VIEWING:
  view <category|id>        - View rule content
  search <query>            - Search rules by name/category/content
  
UPDATING:
  update <category|id>      - Update rule interactively
  update <category|id> name - Update rule name only
  update <category|id> content - Update rule content only
  
MANAGEMENT:
  export [filename]         - Export all rules to JSON
  reload                    - Reload rules from database
  stats                     - Show statistics
  
OTHER:
  help                      - Show this help
  quit, exit, q             - Exit the program

EXAMPLES:
  tree --ids                           # Show tree with rule IDs
  nav ROOT_SCHEDULING_RX              # Navigate to RX scheduling rules
  view ROOT_SCHEDULING_RX             # View RX scheduling rule content
  search "medical records"            # Search for rules containing "medical records"
  update a1b2c3d4 content            # Update content for rule with ID a1b2c3d4
  export my_rules_backup.json        # Export rules to specific file
"""
        print(help_text)


async def main():
    """Main CLI loop."""
    print("🚀 Hierarchical Classification Rules Manager")
    print("=" * 60)
    
    manager = HierarchicalRulesManager()
    
    try:
        print("Loading rules from database...")
        await manager.initialize()
        print(f"✅ Loaded {len(manager.rules_cache)} rules")
        
        # Show initial tree
        await manager.show_tree()
        
        print("\nType 'help' for available commands, 'quit' to exit.")
        
        while True:
            try:
                command = input("\n📋 rules> ").strip()
                
                if not command:
                    continue
                
                parts = command.split()
                cmd = parts[0].lower()
                
                if cmd in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                elif cmd == 'help':
                    manager.print_help()
                
                elif cmd == 'tree':
                    show_ids = '--ids' in parts
                    await manager.show_tree(show_ids)
                
                elif cmd == 'nav' and len(parts) > 1:
                    await manager.navigate_to_category(parts[1])
                
                elif cmd == 'context':
                    await manager.show_current_context()
                
                elif cmd == 'view' and len(parts) > 1:
                    await manager.view_rule_content(parts[1])
                
                elif cmd == 'search' and len(parts) > 1:
                    query = ' '.join(parts[1:])
                    await manager.search_rules(query)
                
                elif cmd == 'update' and len(parts) > 1:
                    identifier = parts[1]
                    field = parts[2] if len(parts) > 2 else None
                    await manager.update_rule(identifier, field)
                
                elif cmd == 'export':
                    filename = parts[1] if len(parts) > 1 else None
                    await manager.export_rules(filename)
                
                elif cmd == 'reload':
                    print("Reloading rules from database...")
                    await manager.initialize()
                    print(f"✅ Reloaded {len(manager.rules_cache)} rules")
                
                elif cmd == 'stats':
                    total_rules = len(manager.rules_cache)
                    rules_with_content = sum(1 for r in manager.rules_cache if r.rule.strip())
                    categories = len(set(r.category for r in manager.rules_cache))
                    
                    print(f"\n📊 Statistics:")
                    print(f"  Total rules: {total_rules}")
                    print(f"  Rules with content: {rules_with_content}")
                    print(f"  Empty rules: {total_rules - rules_with_content}")
                    print(f"  Categories: {categories}")
                
                else:
                    print("❌ Unknown command. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)