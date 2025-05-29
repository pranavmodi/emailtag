#!/usr/bin/env python3
import asyncio
import sys
import os
from dotenv import load_dotenv
import asyncpg
from typing import List, Dict, Any

# Load environment variables
load_dotenv()

async def examine_classification_rules():
    """Connect to the database and examine classification_rule table contents."""
    
    # Get database connection parameters from .env
    db_user = os.getenv('POSTGRES_USER')
    db_password = os.getenv('POSTGRES_PASSWORD') 
    db_host = os.getenv('POSTGRES_SERVER')
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB')
    
    print("="*80)
    print("DATABASE CONNECTION INFO")
    print("="*80)
    print(f"Host: {db_host}")
    print(f"Port: {db_port}")
    print(f"Database: {db_name}")
    print(f"User: {db_user}")
    print(f"Password: {'*' * len(db_password) if db_password else 'None'}")
    
    # Build connection string
    connection_string = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    try:
        print(f"\n🔌 Connecting to database...")
        conn = await asyncpg.connect(connection_string)
        print("✅ Connected successfully!")
        
        # First, let's see what tables exist
        print(f"\n" + "="*80)
        print("ALL TABLES IN DATABASE")
        print("="*80)
        
        tables_query = """
        SELECT table_name, table_type
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """
        
        table_rows = await conn.fetch(tables_query)
        if table_rows:
            print(f"{'Table Name':<30} {'Type':<15}")
            print("-" * 50)
            for row in table_rows:
                print(f"{row['table_name']:<30} {row['table_type']:<15}")
        else:
            print("❌ No tables found in public schema")
            
        # Look for classification-related tables
        classification_tables = [row['table_name'] for row in table_rows if 'classification' in row['table_name'].lower()]
        rule_tables = [row['table_name'] for row in table_rows if 'rule' in row['table_name'].lower()]
        
        print(f"\n🔍 Classification-related tables: {classification_tables}")
        print(f"🔍 Rule-related tables: {rule_tables}")
        
        # Try to find the correct table name
        possible_table_names = ['classification_rule', 'classification_rules', 'classificationrule', 'classificationrules']
        actual_table_name = None
        
        for table_name in possible_table_names:
            if table_name in [row['table_name'] for row in table_rows]:
                actual_table_name = table_name
                print(f"✅ Found classification table: '{actual_table_name}'")
                break
        
        if not actual_table_name:
            # Try the first classification or rule table we found
            if classification_tables:
                actual_table_name = classification_tables[0]
                print(f"🔄 Using first classification table found: '{actual_table_name}'")
            elif rule_tables:
                actual_table_name = rule_tables[0]
                print(f"🔄 Using first rule table found: '{actual_table_name}'")
            else:
                print("❌ No classification or rule tables found!")
                return
        
        # Get table schema first
        print(f"\n" + "="*80)
        print(f"TABLE SCHEMA FOR '{actual_table_name.upper()}'")
        print("="*80)
        
        schema_query = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns 
        WHERE table_name = $1
        ORDER BY ordinal_position;
        """
        
        schema_rows = await conn.fetch(schema_query, actual_table_name)
        if schema_rows:
            print(f"{'Column':<20} {'Type':<15} {'Nullable':<10} {'Default':<20}")
            print("-" * 70)
            for row in schema_rows:
                print(f"{row['column_name']:<20} {row['data_type']:<15} {row['is_nullable']:<10} {str(row['column_default']):<20}")
        else:
            print(f"❌ Table '{actual_table_name}' not found or no columns returned")
            return
            
        # Get all distinct categories
        print(f"\n" + "="*80)
        print("ALL DISTINCT CATEGORIES (ACTIVE AND INACTIVE)")
        print("="*80)
        
        categories_query = f"""
        SELECT category, COUNT(*) as rule_count, 
               COUNT(CASE WHEN is_active = true THEN 1 END) as active_count,
               COUNT(CASE WHEN is_active = false THEN 1 END) as inactive_count
        FROM {actual_table_name} 
        GROUP BY category 
        ORDER BY category;
        """
        
        category_rows = await conn.fetch(categories_query)
        if category_rows:
            print(f"{'Category':<40} {'Total':<8} {'Active':<8} {'Inactive':<8}")
            print("-" * 70)
            for row in category_rows:
                print(f"{row['category']:<40} {row['rule_count']:<8} {row['active_count']:<8} {row['inactive_count']:<8}")
        else:
            print("❌ No categories found")
            
        # Get detailed info for each active category
        print(f"\n" + "="*80)
        print("DETAILED ACTIVE RULES BY CATEGORY")
        print("="*80)
        
        detailed_query = f"""
        SELECT category, name, 
               LENGTH(content) as content_length,
               LEFT(content, 200) as content_preview,
               created_at, updated_at, version
        FROM {actual_table_name} 
        WHERE is_active = true
        ORDER BY category, created_at;
        """
        
        detailed_rows = await conn.fetch(detailed_query)
        if detailed_rows:
            current_category = None
            for row in detailed_rows:
                if row['category'] != current_category:
                    current_category = row['category']
                    print(f"\n📁 CATEGORY: '{current_category}'")
                    print("-" * 60)
                
                print(f"  📄 Rule: {row['name']}")
                print(f"     Length: {row['content_length']} chars")
                print(f"     Created: {row['created_at']}")
                print(f"     Version: {row['version']}")
                print(f"     Preview: {row['content_preview'].replace(chr(10), ' ').replace(chr(13), ' ')}...")
                print()
        else:
            print("❌ No active rules found")
            
        # Look for potential intermediate-level rule patterns
        print(f"\n" + "="*80)
        print("SEARCHING FOR INTERMEDIATE-LEVEL RULE PATTERNS")
        print("="*80)
        
        patterns_to_check = [
            '%_Main%',
            '%_Level1%', 
            '%_Level%',
            '%Main%',
            '%Level%',
            'Accounts%Receivable%',
            'Scheduling%',
            'Medical%Records%'
        ]
        
        for pattern in patterns_to_check:
            pattern_query = f"""
            SELECT category, name, is_active
            FROM {actual_table_name} 
            WHERE category ILIKE $1
            ORDER BY category, name;
            """
            
            pattern_rows = await conn.fetch(pattern_query, pattern)
            if pattern_rows:
                print(f"\n🔍 Pattern '{pattern}' matches:")
                for row in pattern_rows:
                    status = "✅ ACTIVE" if row['is_active'] else "❌ INACTIVE"
                    print(f"   {status} Category: '{row['category']}' | Rule: '{row['name']}'")
            else:
                print(f"❌ No matches for pattern '{pattern}'")
                
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        print(f"Connection string (masked): postgresql://{db_user}:***@{db_host}:{db_port}/{db_name}")
        
    finally:
        if 'conn' in locals():
            await conn.close()
            print(f"\n🔌 Database connection closed.")

if __name__ == "__main__":
    print("CLASSIFICATION RULES DATABASE EXAMINER")
    print("="*80)
    asyncio.run(examine_classification_rules())
    print("\n" + "="*80)
    print("EXAMINATION COMPLETE")
    print("="*80) 