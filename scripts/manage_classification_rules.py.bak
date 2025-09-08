#!/usr/bin/env python3
"""
Simple Classification Rules Manager CLI

This script provides a straightforward interface for viewing and managing 
hierarchical classification rules used by the email tagging system.

Features:
- List all rules with numbered selection
- View rule content
- Update rule names and content
- Search rules
- Export/import rules
"""

import os
import sys
import asyncio
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import tempfile
import subprocess

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.services.hierarchical_rules_service import HierarchicalRulesService
from app.models.hierarchical_classification_rule import HierarchicalClassificationRule


class SimpleRulesManager:
    """Simple CLI manager for hierarchical classification rules."""
    
    def __init__(self):
        self.rules: List[HierarchicalClassificationRule] = []
        
    async def initialize(self):
        """Initialize the manager and load rules from database."""
        async with AsyncSessionLocal() as db:
            service = HierarchicalRulesService(db)
            self.rules = await service.get_all_hierarchical_rules(include_rule_content=True)
            # Sort rules by category for consistent ordering
            self.rules.sort(key=lambda r: r.category)
    
    def display_rules_list(self):
        """Display numbered list of all rules."""
        if not self.rules:
            print("⚪ No rules found in database.")
            return
            
        print(f"\n📋 CLASSIFICATION RULES ({len(self.rules)} total)")
        print("="*80)
        
        for i, rule in enumerate(self.rules, 1):
            content_icon = "📝" if rule.rule.strip() else "⚪"
            
            # Truncate long names for better display
            name_display = rule.name[:50] + "..." if len(rule.name) > 50 else rule.name
            category_display = rule.category[:30] + "..." if len(rule.category) > 30 else rule.category
            
            print(f"{i:3d}. {content_icon} {name_display}")
            print(f"      Category: {category_display}")
            print(f"      Updated: {rule.updated_at.strftime('%Y-%m-%d %H:%M')}")
            
        print("="*80)
    
    def find_rule_by_number(self, num: int) -> Optional[HierarchicalClassificationRule]:
        """Find rule by its display number."""
        if 1 <= num <= len(self.rules):
            return self.rules[num - 1]
        return None
    
    def find_rule_by_id(self, rule_id: str) -> Optional[HierarchicalClassificationRule]:
        """Find a rule by its ID (supports partial matches)."""
        for rule in self.rules:
            if str(rule.id) == rule_id or str(rule.id).startswith(rule_id):
                return rule
        return None
    
    def format_rule_content(self, content: str, max_width: int = 100) -> str:
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
    
    def view_rule(self, rule: HierarchicalClassificationRule):
        """Display rule content."""
        print("\n" + "="*80)
        print(f"📝 RULE: {rule.name}")
        print("="*80)
        print(f"Category: {rule.category}")
        print(f"ID: {rule.id}")
        print(f"Created: {rule.created_at}")
        print(f"Updated: {rule.updated_at}")
        print("-"*80)
        
        if rule.rule.strip():
            formatted_content = self.format_rule_content(rule.rule)
            print(formatted_content)
        else:
            print("⚪ No content defined for this rule.")
        
        print("="*80)
    
    async def update_rule(self, rule: HierarchicalClassificationRule):
        """Update a rule's name or content."""
        print(f"\n📝 UPDATING RULE: {rule.name}")
        print(f"Category: {rule.category}")
        
        print("\nWhat would you like to update?")
        print("1. Name only")
        print("2. Content only") 
        print("3. Both name and content")
        print("0. Cancel")
        
        choice = input("\nEnter choice (0-3): ").strip()
        
        new_name = None
        new_content = None
        
        if choice == "0":
            print("❌ Update cancelled.")
            return
        
        # Update name
        if choice in ["1", "3"]:
            print(f"\nCurrent name: {rule.name}")
            new_name = input("Enter new name (or press Enter to keep current): ").strip()
            if not new_name:
                new_name = None
                print("⚠️  Name unchanged.")
        
        # Update content  
        if choice in ["2", "3"]:
            print(f"\nCurrent content preview:")
            preview = rule.rule[:200] + "..." if len(rule.rule) > 200 else rule.rule
            if preview.strip():
                print(f"  {preview}")
            else:
                print("  ⚪ No current content")
            
            print("\nChoose content update method:")
            print("1. Type content directly")
            print("2. Edit in external editor")
            print("0. Skip content update")
            
            content_choice = input("Enter choice (0-2): ").strip()
            
            if content_choice == "1":
                print("\nEnter new content (press Ctrl+D when done, or type '###END###' on a line by itself):")
                lines = []
                try:
                    while True:
                        line = input()
                        if line.strip() == "###END###":
                            break
                        lines.append(line)
                except EOFError:
                    pass  # Ctrl+D pressed
                new_content = '\n'.join(lines)
                
            elif content_choice == "2":
                # Use external editor
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
                    f.write(rule.rule)
                    temp_file = f.name
                
                editor = os.environ.get('EDITOR', 'nano')
                try:
                    subprocess.run([editor, temp_file], check=True)
                    with open(temp_file, 'r') as f:
                        new_content = f.read()
                except subprocess.CalledProcessError:
                    print("❌ Editor failed. Content not updated.")
                except FileNotFoundError:
                    print(f"❌ Editor '{editor}' not found. Set EDITOR environment variable.")
                finally:
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            elif content_choice == "0":
                print("⚠️  Content update skipped.")
        
        # Perform the update if we have changes
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
                        print("\n✅ Rule updated successfully!")
                        
                        # Show what changed
                        changes = []
                        if new_name:
                            changes.append(f"Name: '{rule.name}' → '{new_name}'")
                        if new_content is not None:
                            content_preview = new_content[:50] + "..." if len(new_content) > 50 else new_content
                            changes.append(f"Content updated ({len(new_content)} characters)")
                        
                        print("Changes made:")
                        for change in changes:
                            print(f"  • {change}")
                        
                        # Refresh our local copy
                        await self.initialize()
                    else:
                        print("❌ Failed to update rule.")
                        
            except Exception as e:
                print(f"❌ Error updating rule: {e}")
        else:
            print("⚠️  No changes made.")
    
    def search_rules(self, query: str):
        """Search rules by name, category, or content."""
        query_lower = query.lower()
        matches = []
        
        for i, rule in enumerate(self.rules, 1):
            if (query_lower in rule.name.lower() or 
                query_lower in rule.category.lower() or
                query_lower in rule.rule.lower()):
                matches.append((i, rule))
        
        if matches:
            print(f"\n🔍 Found {len(matches)} matching rules:")
            print("-" * 80)
            
            for num, rule in matches:
                content_icon = "📝" if rule.rule.strip() else "⚪"
                print(f"{num:3d}. {content_icon} {rule.name}")
                print(f"      Category: {rule.category}")
                
                # Show content preview if query matches content
                if query_lower in rule.rule.lower():
                    lines = rule.rule.lower().split('\n')
                    for i, line in enumerate(lines):
                        if query_lower in line:
                            original_line = rule.rule.split('\n')[i]
                            preview = original_line[:80] + "..." if len(original_line) > 80 else original_line
                            print(f"      Preview: ...{preview}...")
                            break
                print()
        else:
            print(f"❌ No rules found matching '{query}'")
    
    async def export_rules(self, output_file: str = None):
        """Export all rules to JSON file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"rules_export_{timestamp}.json"
        
        rules_data = []
        for rule in self.rules:
            rules_data.append({
                "id": str(rule.id),
                "name": rule.name,
                "category": rule.category,
                "rule": rule.rule,
                "created_at": rule.created_at.isoformat(),
                "updated_at": rule.updated_at.isoformat()
            })
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Exported {len(rules_data)} rules to {output_file}")
        except Exception as e:
            print(f"❌ Export failed: {e}")
    
    def print_help(self):
        """Print help information."""
        help_text = """
📋 Simple Classification Rules Manager - Commands:

BASIC COMMANDS:
  <number>                 - Select rule by number (interactive menu)
  list                     - Show numbered list of all rules
  view <number>            - View content of rule by number
  update <number>          - Update rule by number
  search <query>           - Search rules by name/category/content
  
MANAGEMENT:
  export [filename]        - Export all rules to JSON
  reload                   - Reload rules from database
  stats                    - Show statistics
  
OTHER:
  help                     - Show this help
  quit, exit, q            - Exit the program

EXAMPLES:
  1                        # Select rule #1 (shows interactive menu)
  list                     # Show all rules with numbers
  view 5                   # View content of rule #5 directly
  update 5                 # Update rule #5 directly
  search "scheduling"      # Find rules containing "scheduling"
  export backup.json       # Export to specific file
  
TIPS:
  • Use 'list' first to see all rules with their numbers
  • Rule numbers correspond to the list order
  • Content can be edited in external editor (set EDITOR env var)
  • Type '###END###' on its own line to finish direct content entry
"""
        print(help_text)


async def main():
    """Main CLI loop."""
    print("🚀 Simple Classification Rules Manager")
    print("=" * 60)
    
    manager = SimpleRulesManager()
    
    try:
        print("Loading rules from database...")
        await manager.initialize()
        print(f"✅ Loaded {len(manager.rules)} rules")
        
        # Show initial list
        manager.display_rules_list()
        
        print(f"\n🎯 Type 'help' for commands, or start with 'view <number>' to view a rule!")
        
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
                
                elif cmd == 'list':
                    manager.display_rules_list()
                
                elif cmd == 'view' and len(parts) > 1:
                    try:
                        num = int(parts[1])
                        rule = manager.find_rule_by_number(num)
                        if rule:
                            manager.view_rule(rule)
                        else:
                            print(f"❌ Invalid rule number: {num}. Use 'list' to see available numbers.")
                    except ValueError:
                        print("❌ Invalid number. Use 'view <number>'")
                
                elif cmd == 'update' and len(parts) > 1:
                    try:
                        num = int(parts[1])
                        rule = manager.find_rule_by_number(num)
                        if rule:
                            await manager.update_rule(rule)
                        else:
                            print(f"❌ Invalid rule number: {num}. Use 'list' to see available numbers.")
                    except ValueError:
                        print("❌ Invalid number. Use 'update <number>'")
                
                elif cmd == 'search' and len(parts) > 1:
                    query = ' '.join(parts[1:])
                    manager.search_rules(query)
                
                elif cmd == 'export':
                    filename = parts[1] if len(parts) > 1 else None
                    await manager.export_rules(filename)
                
                elif cmd == 'reload':
                    print("Reloading rules from database...")
                    await manager.initialize()
                    print(f"✅ Reloaded {len(manager.rules)} rules")
                    manager.display_rules_list()
                
                elif cmd == 'stats':
                    total_rules = len(manager.rules)
                    rules_with_content = sum(1 for r in manager.rules if r.rule.strip())
                    categories = len(set(r.category for r in manager.rules))
                    
                    print(f"\n📊 Statistics:")
                    print(f"  Total rules: {total_rules}")
                    print(f"  Rules with content: {rules_with_content}")
                    print(f"  Empty rules: {total_rules - rules_with_content}")
                    print(f"  Unique categories: {categories}")
                    
                    if total_rules > 0:
                        avg_content_length = sum(len(r.rule) for r in manager.rules) / total_rules
                        print(f"  Average content length: {avg_content_length:.0f} characters")
                
                else:
                    # Check if it's just a number (direct rule selection)
                    try:
                        num = int(cmd)
                        rule = manager.find_rule_by_number(num)
                        if rule:
                            print(f"\n🎯 Selected rule #{num}: {rule.name}")
                            print("What would you like to do?")
                            print("1. View content")
                            print("2. Update rule")
                            print("0. Back to main menu")
                            
                            action = input("Enter choice (0-2): ").strip()
                            
                            if action == "1":
                                manager.view_rule(rule)
                            elif action == "2":
                                await manager.update_rule(rule)
                            elif action == "0":
                                print("↩️  Back to main menu.")
                            else:
                                print("❌ Invalid choice.")
                        else:
                            print(f"❌ Invalid rule number: {num}. Use 'list' to see available numbers.")
                    except ValueError:
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