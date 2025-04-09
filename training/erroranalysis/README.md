# Error Analysis Package

This package provides tools for analyzing classification errors in the email tagging system and suggesting improvements to the classification rules.

## Structure

The package is organized into the following modules:

- `__init__.py`: Package initialization
- `data_loader.py`: Functions for loading and formatting data
- `openai_analyzer.py`: OpenAI-based analysis functionality
- `analyze_errors.py`: Main script for analyzing errors

## Usage

The main script `analyze_errors.py` can be used in several ways:

### Analyze a specific conversation

```bash
python -m training.erroranalysis.analyze_errors --conversation-id <conversation_id>
```

### Count emails with "done" tag

```bash
python -m training.erroranalysis.analyze_errors --count-done-tags
```

### Analyze errors between specific categories

```bash
python -m training.erroranalysis.analyze_errors --predicted-category "Medical Records & Images" --actual-category "Accounts Receivable" --max-examples 5
```

### Analyze all errors

```bash
python -m training.erroranalysis.analyze_errors
```

## Output

The analysis results are saved to text files:

- For specific conversations: `error_analysis.txt`
- For category patterns: `error_analysis_<from_category>_to_<to_category>.txt`

Each analysis includes:
1. A detailed explanation of why the classification was incorrect
2. Updated classification rules for both categories
3. Patterns or keywords that were missed or misinterpreted

## Dependencies

- OpenAI API key (set in environment variable `OPENAI_API_KEY`)
- OpenAI model (set in environment variable `REASONING_MODEL`, defaults to 'o3-mini')
- Data directory (set in environment variable `DATA_DIR`) 