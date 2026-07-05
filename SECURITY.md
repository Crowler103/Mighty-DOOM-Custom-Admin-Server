# Security notes

This project is intended for a private LAN/VPN setup. Do not expose it directly
to the public internet. The admin server can edit and restore the SQLite
database, so access to it is equivalent to access to your game server data.

Recommended setup:

- bind it to a private interface or use a VPN;
- always set `ADMIN_PASSWORD`;
- keep backups outside the web root;
- do not commit `db/local.sqlite3`, backups, `.env`, or `data/game-data.json`;
- make a manual backup before testing major changes.
