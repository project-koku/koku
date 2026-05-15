# Code Review Checklist

## Overview
Comprehensive checklist for conducting thorough code reviews to ensure quality, security, maintainability, and adherence to Koku project standards.

## Review Categories

### Functionality
- [ ] Code does what it's supposed to do
- [ ] Edge cases are handled appropriately
- [ ] Error handling is appropriate and follows project patterns
- [ ] No obvious bugs or logic errors
- [ ] Timezone-aware datetime objects are used correctly
- [ ] Database operations use transactions when needed
- [ ] Bulk operations are used for large datasets

### Code Quality
- [ ] Code is readable and well-structured
- [ ] Functions are small and focused (single responsibility)
- [ ] Variable names are descriptive and follow snake_case
- [ ] No code duplication
- [ ] Follows Koku project conventions (.cursorrules)
- [ ] Python 3.11+ features used appropriately
- [ ] Type hints present for function parameters and return types
- [ ] F-strings used for string formatting
- [ ] Parenthesized context managers used for multiple managers

### Import Organization
- [ ] Standard library imports first
- [ ] Third-party imports second
- [ ] Local application imports last
- [ ] Absolute imports from project root used
- [ ] Related imports grouped with blank lines

### Django Patterns
- [ ] Django ORM methods used appropriately
- [ ] select_related() and prefetch_related() used for performance
- [ ] get_or_create() pattern used when appropriate
- [ ] N+1 query problems avoided
- [ ] Database exceptions handled gracefully
- [ ] Models follow Django conventions

### Testing
- [ ] Tests placed in `test/` subdirectories alongside code
- [ ] Test files named with `test_` prefix
- [ ] Tests grouped in test classes
- [ ] Descriptive test method names
- [ ] Django TestCase used for database-related tests
- [ ] unittest.mock.patch used for mocking
- [ ] Parenthesized context managers used for multiple patches
- [ ] model_bakery (baker.make()) used for test data
- [ ] Both positive and negative cases tested
- [ ] Edge cases and error conditions tested
- [ ] Mocks verified with assert_called_once(), assert_called_with()
- [ ] Test artifacts cleaned up after tests

### Error Handling & Logging
- [ ] Custom exception classes in dedicated modules (exceptions.py)
- [ ] Specific exception types used (not generic Exception)
- [ ] Helpful error messages with context
- [ ] Structured logging with log_json() utility
- [ ] tracing_id included for request correlation
- [ ] Appropriate log levels used (DEBUG, INFO, WARNING, ERROR)
- [ ] Relevant context included in log messages

### Performance
- [ ] select_related() used for foreign key relationships
- [ ] prefetch_related() used for many-to-many relationships
- [ ] Generators used for large datasets
- [ ] Files processed in chunks (not loaded entirely into memory)
- [ ] Context managers used for resource management
- [ ] Temporary files and resources cleaned up

### Security
- [ ] No obvious security vulnerabilities
- [ ] Input validation present (Django forms/serializers)
- [ ] File paths and names sanitized
- [ ] File sizes and types checked before processing
- [ ] Sensitive data handled appropriately
- [ ] No hardcoded secrets
- [ ] Proper authentication and authorization checks
- [ ] Parameterized queries used (Django ORM handles this)

### API Design (if applicable)
- [ ] Django REST Framework serializers used
- [ ] Input data validated properly
- [ ] Nested relationships handled appropriately
- [ ] Clear error messages for validation failures
- [ ] Appropriate HTTP status codes used
- [ ] Exceptions handled gracefully
- [ ] Pagination used for large datasets
- [ ] API endpoints documented clearly

### Celery Tasks (if applicable)
- [ ] Tasks are idempotent when possible
- [ ] Task failures handled gracefully
- [ ] Appropriate retry strategies used
- [ ] Task progress and completion logged
- [ ] Appropriate queues used for task types

### File Processing (if applicable)
- [ ] Files processed in streaming mode when possible
- [ ] Temporary directories used for file operations
- [ ] File formats validated before processing
- [ ] Empty files handled gracefully
- [ ] CSV parsing errors handled gracefully
- [ ] Data integrity validated during processing

### Documentation
- [ ] Complex business logic documented
- [ ] Non-obvious code patterns explained
- [ ] Docstrings present for public functions and classes
- [ ] Google or NumPy docstring conventions followed
- [ ] Parameter types and return types included
- [ ] Architecture docs updated if needed (docs/architecture/)
- [ ] Architecture docs link to code, don't duplicate it

### Git & Version Control
- [ ] Descriptive commit messages
- [ ] Issue numbers referenced when appropriate
- [ ] Commits focused on single changes
- [ ] Conventional commit format used when possible

## Architecture Documentation Check
If significant changes were made, verify:
- [ ] Architecture docs reviewed (docs/architecture/)
- [ ] New functions/classes linked from docs if needed
- [ ] File paths/function names updated in docs if changed
- [ ] New concepts explained in docs
- [ ] Diagrams still accurate
