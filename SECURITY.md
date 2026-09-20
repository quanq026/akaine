# Security and publication checklist

- Do not add real `config.py`, `.env`, keys, tokens or database files.
- Keep APKs in GitHub Releases, not Git history.
- Keep assets and bundles in external object storage.
- Run a secret scanner before every public push.
- Review third-party licenses and redistribution rights before publishing any
  game-derived code, metadata or binary.
- The bundled B30 web tool has third-party npm advisories at the time of this
  snapshot. Do not use `npm audit fix` blindly; review and update it in a
  separate pull request.
