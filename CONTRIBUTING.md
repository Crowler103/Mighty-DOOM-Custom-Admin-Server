# Contributing

Keep code and comments in English. User-facing labels should go through the
existing translation helpers so German and English stay consistent.

Before opening a pull request, run:

```bash
python -m compileall app.py src
```

If you add a database write operation, make sure it:

1. creates a backup when appropriate,
2. writes an audit-log entry,
3. validates IDs and JSON fields before committing.
