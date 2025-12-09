## mavlink-json

Small helper that expands MAVLink XML dialects into JSON.

### CLI
- Requires Python 3.11+
- Usage:
  - `python3 xml2json.py path/to/dialect.xml > dialect.json`

### GitHub Actions
- `.github/workflows/sync-mavlink.yml` runs every Monday (and on manual dispatch).
- It clones `mavlink/mavlink`, converts every `message_definitions/v1.0/*.xml` to JSON with `xml2json.py`, writes them to `message_definitions/v1.0/`, and auto-commits the results.
