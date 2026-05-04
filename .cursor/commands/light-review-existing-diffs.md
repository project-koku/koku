# Light Review Existing Diffs

## Overview
Quick review of existing git diffs to identify obvious issues, style problems, and basic code quality concerns without deep analysis.

## Steps

1. **Get current diffs**
   - Review git status to see modified files
   - Check git diff for changes
   - Focus on files that are actually changed

2. **Quick style check**
   - [ ] Line length within 119 characters (Black formatting)
   - [ ] Proper indentation and spacing
   - [ ] Import organization (stdlib, third-party, local)
   - [ ] Variable naming follows snake_case
   - [ ] Constants use UPPER_CASE
   - [ ] F-strings used instead of .format() or %
   - [ ] Type hints present for new functions

3. **Basic code quality**
   - [ ] No obvious syntax errors
   - [ ] No unused imports
   - [ ] No commented-out code left behind
   - [ ] No debug print statements
   - [ ] No hardcoded values that should be constants
   - [ ] Functions are reasonably sized and focused

4. **Django-specific checks**
   - [ ] Django ORM used appropriately (not raw SQL unless necessary)
   - [ ] select_related()/prefetch_related() used if accessing related objects
   - [ ] Timezone-aware datetime objects used
   - [ ] Proper use of get_or_create() pattern if applicable

5. **Error handling**
   - [ ] Exceptions handled (not bare except clauses)
   - [ ] Appropriate exception types used
   - [ ] Error messages are helpful
   - [ ] Logging used appropriately (log_json() for structured logging)

6. **Security basics**
   - [ ] No obvious SQL injection risks (Django ORM handles this, but check raw queries)
   - [ ] Input validation present
   - [ ] No hardcoded secrets or credentials
   - [ ] File operations validate paths and sizes

7. **Test coverage**
   - [ ] New code has corresponding tests
   - [ ] Tests follow project structure (test/ subdirectories)
   - [ ] Test file named with test_ prefix

8. **Documentation**
   - [ ] Complex logic has comments
   - [ ] Public functions/classes have docstrings
   - [ ] Architecture docs updated if major changes

## Quick Fixes to Suggest
- Import organization issues
- Missing type hints
- Line length violations
- Missing error handling
- Unused imports/variables
- Style inconsistencies

## Notes
This is a light review focused on quick wins and obvious issues. For deeper analysis, use the full code review checklist.
