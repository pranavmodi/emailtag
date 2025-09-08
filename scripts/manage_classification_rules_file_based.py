#!/usr/bin/env python3
"""
File-Based Classification Rules Manager CLI

This script provides a command-line interface for managing classification rules
stored as .txt files in /app/prompts/rules/ directory.

Features:
- List all rule files with numbered selection
- View rule content
- Update rule content
- Search rules
- Export/import rules
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import tempfile
import subprocess

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.file_based_rules_service import get_file_based_rules_service


class FileBasedRulesManager:
    """CLI manager for file-based classification rules."""
    
    def __init__(self):
        self.rules_service = get_file_based_rules_service()
        self.rules: List[Dict[str, Any]] = []
        
    def initialize(self):
        """Initialize the manager and load rules from files."""
        self.rules = self.rules_service.list_all_rules()
    
    def display_rules_list(self):
        """Display numbered list of all rule files."""
        if not self.rules:
            print("⚪ No rules found in /app/prompts/rules/")
            return
            
        print(f"\n📋 CLASSIFICATION RULES ({len(self.rules)} total)")
        print("="*80)
        
        for i, rule in enumerate(self.rules, 1):
            content_icon = "📝" if rule['has_content'] else "⚪"
            
            # Display rule key and basic info
            rule_key = rule['rule_key']
            content_length = rule['content_length']
            modified = rule['modified_time'].strftime('%Y-%m-%d %H:%M')
            
            print(f"{i:3d}. {content_icon} {rule_key}")
            print(f"      Content: {content_length} chars")
            print(f"      Modified: {modified}")
            
        print("="*80)
    
    def find_rule_by_number(self, num: int) -> Optional[Dict[str, Any]]:
        """Find rule by its display number."""
        if 1 <= num <= len(self.rules):
            return self.rules[num - 1]
        return None
    
    def view_rule(self, rule: Dict[str, Any]):
        """Display rule content."""
        rule_key = rule['rule_key']
        content = self.rules_service.get_rule_content(rule_key)
        
        print("\n" + "="*80)
        print(f"📝 RULE: {rule_key}")
        print("="*80)
        print(f"File: {rule['file_path']}")
        print(f"Size: {rule['file_size']} bytes")
        print(f"Content: {rule['content_length']} characters")
        print(f"Modified: {rule['modified_time']}")
        print("-"*80)
        
        if content:
            print(content)
        else:
            print("⚪ No content or file not readable.")
        
        print("="*80)
    
    def update_rule(self, rule: Dict[str, Any]):
        """Update a rule's content."""
        rule_key = rule['rule_key']
        current_content = self.rules_service.get_rule_content(rule_key) or ""
        
        print(f"\n📝 UPDATING RULE: {rule_key}")
        print(f"File: {rule['file_path']}")
        
        print(f"\nCurrent content preview:")
        preview = current_content[:200] + "..." if len(current_content) > 200 else current_content
        if preview.strip():
            print(f"  {preview}")
        else:
            print("  ⚪ No current content")
        
        print("\nChoose content update method:")
        print("1. Type content directly")
        print("2. Edit in external editor")
        print("0. Cancel")
        
        choice = input("\nEnter choice (0-2): ").strip()
        
        new_content = None
        
        if choice == "0":
            print("❌ Update cancelled.")
            return
        elif choice == "1":
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
            
        elif choice == "2":
            # Use external editor
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as f:
                f.write(current_content)
                temp_file = f.name
            
            editor = os.environ.get('EDITOR', 'nano')
            try:
                subprocess.run([editor, temp_file], check=True)
                with open(temp_file, 'r') as f:
                    new_content = f.read()
            except subprocess.CalledProcessError:
                print("❌ Editor failed. Content not updated.")
                return
            except FileNotFoundError:
                print(f"❌ Editor '{editor}' not found. Set EDITOR environment variable.")
                return
            finally:
                try:
                    os.unlink(temp_file)
                except:
                    pass
        else:
            print("❌ Invalid choice.")
            return
        
        # Save the new content
        if new_content is not None:
            if self.rules_service.save_rule_content(rule_key, new_content):
                print(f"\n✅ Rule '{rule_key}' updated successfully!")
                print(f"  New content length: {len(new_content)} characters")
                # Refresh our local cache
                self.initialize()
            else:
                print(f"❌ Failed to save rule '{rule_key}'.")
        else:
            print("⚠️  No changes made.")
    
    def search_rules(self, query: str):
        """Search rules by key or content."""
        query_lower = query.lower()
        matches = []
        
        for i, rule in enumerate(self.rules, 1):
            rule_key = rule['rule_key']
            content = self.rules_service.get_rule_content(rule_key) or ""
            
            if (query_lower in rule_key.lower() or 
                query_lower in content.lower()):
                matches.append((i, rule))
        
        if matches:
            print(f"\n🔍 Found {len(matches)} matching rules:")
            print("-" * 80)
            
            for num, rule in matches:
                content_icon = "📝" if rule['has_content'] else "⚪"
                rule_key = rule['rule_key']
                print(f"{num:3d}. {content_icon} {rule_key}")
                
                # Show content preview if query matches content
                content = self.rules_service.get_rule_content(rule_key) or ""
                if query_lower in content.lower():
                    lines = content.lower().split('\n')
                    for i, line in enumerate(lines):
                        if query_lower in line:
                            original_line = content.split('\n')[i]
                            preview = original_line[:80] + "..." if len(original_line) > 80 else original_line
                            print(f"      Preview: ...{preview}...")
                            break
                print()
        else:
            print(f"❌ No rules found matching '{query}'")
    
    def export_rules(self, output_file: str = None):
        """Export all rules to JSON file."""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"rules_export_{timestamp}.json"
        
        rules_data = {}
        for rule in self.rules:
            rule_key = rule['rule_key']
            content = self.rules_service.get_rule_content(rule_key) or ""
            rules_data[rule_key] = {
                "content": content,
                "file_path": rule['file_path'],
                "content_length": len(content),
                "modified_time": rule['modified_time'].isoformat()
            }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(rules_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Exported {len(rules_data)} rules to {output_file}")
        except Exception as e:
            print(f"❌ Export failed: {e}")
    
    def import_rules(self, input_file: str):
        """Import rules from JSON file."""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                rules_data = json.load(f)
            
            imported_count = 0
            for rule_key, rule_info in rules_data.items():
                content = rule_info.get('content', '')
                if self.rules_service.save_rule_content(rule_key, content):
                    imported_count += 1
                    print(f"✅ Imported {rule_key}")
                else:
                    print(f"❌ Failed to import {rule_key}")
            
            print(f"\n✅ Successfully imported {imported_count}/{len(rules_data)} rules")
            self.initialize()  # Refresh cache
            
        except Exception as e:
            print(f"❌ Import failed: {e}")
    
    def create_new_rule(self):
        """Create a new rule file."""
        print("\n📝 CREATE NEW RULE")
        
        rule_key = input("Enter rule key (e.g., ROOT_NEW_CATEGORY): ").strip()
        if not rule_key:
            print("❌ Rule key cannot be empty.")
            return
        
        if self.rules_service.rule_exists(rule_key):
            print(f"❌ Rule '{rule_key}' already exists.")
            return
        
        print(f"\nEnter content for rule '{rule_key}':")
        print("(Type your content, press Ctrl+D when done, or type '###END###' on a line by itself)")
        
        lines = []
        try:
            while True:
                line = input()
                if line.strip() == "###END###":
                    break
                lines.append(line)
        except EOFError:
            pass  # Ctrl+D pressed
        
        content = '\n'.join(lines)
        
        if not content.strip():
            print("❌ Content cannot be empty.")
            return
        
        if self.rules_service.save_rule_content(rule_key, content):
            print(f"✅ Created new rule '{rule_key}' with {len(content)} characters")
            self.initialize()  # Refresh cache
        else:
            print(f"❌ Failed to create rule '{rule_key}'.")
    
    def delete_rule(self, rule: Dict[str, Any]):
        """Delete a rule file."""
        rule_key = rule['rule_key']
        
        print(f"\n🗑️ DELETE RULE: {rule_key}")
        print(f"File: {rule['file_path']}")
        print(f"⚠️ This action cannot be undone!")
        
        confirm = input(f"\nAre you sure you want to delete '{rule_key}'? (yes/no): ").strip().lower()
        
        if confirm == 'yes':
            if self.rules_service.delete_rule(rule_key):
                print(f"✅ Deleted rule '{rule_key}'")
                self.initialize()  # Refresh cache
            else:
                print(f"❌ Failed to delete rule '{rule_key}'")
        else:
            print("❌ Deletion cancelled.")
    
    def print_help(self):
        """Print help information."""
        help_text = """
📋 File-Based Classification Rules Manager - Commands:

BASIC COMMANDS:
  <number>                 - Select rule by number (interactive menu)
  list                     - Show numbered list of all rules
  view <number>            - View content of rule by number
  update <number>          - Update rule by number
  search <query>           - Search rules by key or content
  
MANAGEMENT:
  create                   - Create a new rule file
  delete <number>          - Delete a rule file
  export [filename]        - Export all rules to JSON
  import <filename>        - Import rules from JSON
  reload                   - Reload rules from files
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
  create                   # Create a new rule file
  export backup.json       # Export to specific file
  
TIPS:
  • Rule files are stored in /app/prompts/rules/
  • Rule keys map to filenames (ROOT → ROOT.txt)
  • Content can be edited in external editor (set EDITOR env var)
  • Type '###END###' on its own line to finish direct content entry
"""
        print(help_text)


def main():
    """Main CLI loop."""
    print("🚀 File-Based Classification Rules Manager")
    print("=" * 60)
    
    manager = FileBasedRulesManager()
    
    try:
        print("Loading rules from files...")
        manager.initialize()
        print(f"✅ Found {len(manager.rules)} rule files")
        
        # Show initial list
        manager.display_rules_list()
        
        print(f"\n🎯 Type 'help' for commands, or start with a number to select a rule!")
        
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
                            manager.update_rule(rule)
                        else:
                            print(f"❌ Invalid rule number: {num}. Use 'list' to see available numbers.")
                    except ValueError:
                        print("❌ Invalid number. Use 'update <number>'")
                
                elif cmd == 'delete' and len(parts) > 1:
                    try:
                        num = int(parts[1])
                        rule = manager.find_rule_by_number(num)
                        if rule:
                            manager.delete_rule(rule)
                        else:
                            print(f"❌ Invalid rule number: {num}. Use 'list' to see available numbers.")
                    except ValueError:
                        print("❌ Invalid number. Use 'delete <number>'")
                
                elif cmd == 'search' and len(parts) > 1:
                    query = ' '.join(parts[1:])
                    manager.search_rules(query)
                
                elif cmd == 'create':
                    manager.create_new_rule()
                
                elif cmd == 'export':
                    filename = parts[1] if len(parts) > 1 else None
                    manager.export_rules(filename)
                
                elif cmd == 'import' and len(parts) > 1:
                    filename = parts[1]
                    manager.import_rules(filename)
                
                elif cmd == 'reload':
                    print("Reloading rules from files...")
                    manager.initialize()
                    print(f"✅ Reloaded {len(manager.rules)} rules")
                    manager.display_rules_list()
                
                elif cmd == 'stats':
                    total_rules = len(manager.rules)
                    rules_with_content = sum(1 for r in manager.rules if r['has_content'])
                    total_chars = sum(r['content_length'] for r in manager.rules)
                    
                    print(f"\n📊 Statistics:")
                    print(f"  Total rules: {total_rules}")
                    print(f"  Rules with content: {rules_with_content}")
                    print(f"  Empty rules: {total_rules - rules_with_content}")
                    print(f"  Total content: {total_chars:,} characters")
                    
                    if total_rules > 0:
                        avg_length = total_chars / total_rules
                        print(f"  Average length: {avg_length:.0f} characters")
                
                else:
                    # Check if it's just a number (direct rule selection)
                    try:
                        num = int(cmd)
                        rule = manager.find_rule_by_number(num)
                        if rule:
                            print(f"\n🎯 Selected rule #{num}: {rule['rule_key']}")
                            print("What would you like to do?")
                            print("1. View content")
                            print("2. Update rule")
                            print("3. Delete rule")
                            print("0. Back to main menu")
                            
                            action = input("Enter choice (0-3): ").strip()
                            
                            if action == "1":
                                manager.view_rule(rule)
                            elif action == "2":
                                manager.update_rule(rule)
                            elif action == "3":
                                manager.delete_rule(rule)
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
    exit_code = main()
    sys.exit(exit_code)