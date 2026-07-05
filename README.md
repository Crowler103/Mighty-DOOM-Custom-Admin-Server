# Mighty DOOM Custom Admin Server

A standalone Flask-based administration interface for a Mighty DOOM private server database.

This project is designed as a companion tool for the Mighty DOOM private server project by dannyhpy:

https://gitlab.com/dannyhpy/mightydoom-gameserver

It does **not** replace or modify the original game server code. The admin server runs separately and connects directly to the SQLite database used by the private server.

> This is an unofficial community/admin tool. It is not affiliated with, endorsed by, or supported by Bethesda, id Software, Alpha Dog Games, Microsoft, or any other rights holder.

---

## What this project does

The admin server provides a web-based dashboard for managing and inspecting the local Mighty DOOM private server database.

It is intended for private/local server administration, debugging, repair work, testing and convenience tools.

Main goals:

- keep the original game server untouched
- make database content readable and manageable
- show item names, categories, descriptions and slots instead of raw IDs only
- provide safer tools for backups, restore and rollback
- make common user fixes easier from a browser
- provide API endpoints for a separate mobile admin app
- manage optional event schedules for the private game server

---

## Current features

### Dashboard web interface

- Modern dashboard-style web UI
- Sidebar navigation
- Dashboard cards and quick actions
- Mobile-friendly layout
- Two visual themes:
  - **Ops Dashboard**
  - **Hellforge Dashboard**
- Language switch:
  - English
  - German

### User administration

- View all users
- Open detailed user pages
- Edit user-related database values
- Disable or re-enable users
- Show readable inventory data
- Show equipped items with resolved names
- Show attempts with resolved item instance IDs

### Safe progress transfer

- Transfer playable progress from one user to another with a simple source → target flow
- Useful when a user profile is broken and a new user should continue at the same point
- Copies stable progress: tutorial state, chapter progress, settings, stats, talents, currencies, energy, inventory and equipped slots
- Preserves account identity fields on the target user, including UUID, e-mail, token fields and password fields
- Creates a safety backup before every transfer
- Resets volatile startup/session state on the target user: current attempt, attempts, battle pass rows, mission rows and store quota rows
- Normalizes empty `challenge_id` values to `NULL` where those columns exist
- Runs post-transfer safety checks for current attempts, orphan equipped slots and empty challenge IDs before committing the transfer


### Event admin interface

- New **Events** menu entry in the web interface
- Robust event catalog loaded from `game-data.json`
- Detects game mode, store offer and battle pass event definitions where possible
- Shows event definition id, tag, title/description keys, stage count and event type
- Create active event schedules for all users or selected user ids
- Store schedules in `admin_event_schedule` without touching the Node.js game server code
- Optional progress state table `admin_event_progress` for future game server integration
- Edit `stage_rewards` and `additional_event_modifiers` from the browser
- Set default test rewards for stages 5/10/15/20
- Import rewards from event definitions when they are present in `game-data.json`
- Activate, deactivate, assign to user, assign to all users and reset event progress
- Event schedules can be deactivated directly from the Events list
- Event detail pages include a destructive delete action that removes the schedule UUID and matching progress rows after creating a backup
- Export active schedules to `data/admin-events.json` for a future game server patch
- `scheduled_event_id` is now always generated as a valid UUID with Python `uuid.uuid4()`
- Event progress is displayed by joining `admin_event_schedule.scheduled_event_id` with `admin_event_progress.scheduled_event_id`, plus `user_id` for user-specific schedules
- Event list shows scheduled UUID, users with progress, completed users and highest reached stage
- Event detail page shows attempts, highest stage, best completion time, active run state and update timestamp per user
- Progress reset buttons restore default values instead of deleting rows: `attempts=0`, `highest_stage=0`, `best_completion_time_milliseconds=0`, `run_json=NULL`
- Migration button repairs old non-UUID event ids and migrates matching progress rows where possible

The game server integration format is documented in [`docs/EVENTS_INTEGRATION.md`](docs/EVENTS_INTEGRATION.md).


### Nachrichten / Ingame Inbox

- New **Nachrichten / Inbox** menu entry in the web interface
- Manages the existing game Inbox bridge tables without changing the Node.js game server
- Global messages are stored with `admin_inbox_messages.user_id = NULL`
- User-specific messages are stored with a concrete `admin_inbox_messages.user_id`
- Create, edit, activate/deactivate and delete messages from the browser
- Filter messages by active state, target audience, title/body text and expired/not expired state
- Edit optional rewards with simple resource/RID + amount rows
- Rewards are stored as JSON in `resources_json`, for example:

```json
[{"rid": 1, "amount": 1000}]
```

- Empty rewards are stored as `[]`
- Message user state is stored in `admin_inbox_message_state`
- State values used by the game server bridge:
  - `1` = unread
  - `2` = read
  - `3` = claimed
  - `4` = deleted/archived
- Detail pages show per-user state with `read_at`, `claimed_at`, `deleted_at` and `updated_at`
- User state can be reset for one user or all users of a message
- Deleting a message creates a backup first and removes the message plus all related state rows
- Every write operation creates an audit-log entry

SQLite tables used by the Inbox system:

```text
admin_inbox_messages
admin_inbox_message_state
```

The Node.js game server is expected to keep using these endpoints on its side:

```text
POST /game/inbox/get-messages
POST /game/inbox/read
POST /game/inbox/claim
POST /game/inbox/delete
```

### Resource catalog

The admin server can load `game-data.json` and use it as a readable catalog.

This allows the interface to show:

- Resource ID / RID
- internal tag
- readable display name where available
- category
- item type
- slot information
- item description where available
- weapon, gear, launcher, ultimate and slayer metadata
- cosmetic references
- currency names
- talent/stat information where available

Important database mapping rules used by the interface:

- `items.id` is the concrete item instance ID.
- `items.rid` is the resource/item ID from game data.
- `inventory_slots.item_id` points to `items.id`.
- `attempts.weapon_ids` and `attempts.gear_ids` contain item instance IDs as JSON.
- `challenge_id` must be `NULL`, not an empty string.

### Inventory and item tools

- Add items with readable RID dropdowns
- Select item tiers using dropdowns
- Select cosmetics using dropdowns
- Equip items into valid slots
- Prevent obviously wrong slot assignments
- Show slot compatibility based on game data

### Energy Auto-Fill

- Per-user Energy Auto-Fill configuration
- Keep a user's energy value at a defined target value
- Default target can be used for RID `28` / Energy
- Configurable interval, for example every 120 seconds
- Manual “set now” action
- Runs while the admin server is active

### Backups and restore

- Create local database backups
- List existing backups
- Download backups from the web interface
- Restore backups from the web interface
- Restore backups through the mobile API
- Automatically create a safety backup before restore operations

### Audit logging

The admin server can install SQLite audit triggers into the database.

These triggers can log database changes even when they are made by the original game server, not by the admin interface.

Tracked tables include:

- `users`
- `items`
- `inventory_slots`
- `attempts`
- `currencies`
- `energies`
- `talents`
- `user_stats`
- `chapter_progress`
- `battle_passes`
- `missions`
- `tutorial_sequences`
- `store_quotas`
- `user_settings`

Logged changes include old and new row data where possible.

### Audit rollback

Each logged database change can be rolled back directly from the web interface.

Supported rollback actions:

- `db-insert` → delete the inserted row again
- `db-update` → restore the previous values
- `db-delete` → insert the deleted row again

Before each rollback, the admin server creates a safety backup.

Already rolled-back audit entries are marked so the same change cannot accidentally be rolled back twice.

### Mobile API support

The server includes API endpoints used by the separate Android admin app.

The Android app is **not** part of this server-only repository.

The mobile API can expose server options such as:

- user list
- user details
- energy values
- currencies
- backups
- backup restore
- audit entries
- audit rollback
- catalog search
- tables in read-only form

---

## Files that are intentionally not included

For safety and legal/privacy reasons, the public repository should **not** include:

```text
db/local.sqlite3
data/game-data.json
backups/
*.db
*.sqlite
*.sqlite3
.env
APK files
Android build folders
private server data
real user data
```

Use the included example files as placeholders only.

For your local installation, you must provide your own local files:

```text
db/local.sqlite3
data/game-data.json
```

---

## Requirements

- Windows or Linux server/PC
- Python 3.10 or newer recommended
- A working Mighty DOOM private server database
- Local access to the SQLite database file
- `game-data.json` for readable item/resource names

---

## Quick start on Windows

The easiest way to start the admin server on Windows is the included batch file:

```powershell
.\start_admin_all_interfaces.bat
```

Before starting, make sure these local files exist:

```text
db\local.sqlite3
data\game-data.json
```

You can open `start_admin_all_interfaces.bat` in a text editor and adjust:

- database path
- game-data path
- host
- port
- admin username
- admin password

The BAT file is only a convenience wrapper. It starts the Flask admin server and passes the required command-line options automatically.

After starting, open the admin interface in your browser:

```text
http://SERVER-IP:8090
```

On the same machine, this usually also works:

```text
http://127.0.0.1:8090
```

---

## Manual start on Windows

Install dependencies first:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Then start the server with one command:

```powershell
py -3 app.py --db "db\local.sqlite3" --game-data "data\game-data.json" --host 0.0.0.0 --port 8090 --user admin --password "change-this-password"
```

### What this command does

`py -3 app.py` starts the admin server with Python 3.

`--db "db\local.sqlite3"` tells the admin server where the Mighty DOOM SQLite database is located.

`--game-data "data\game-data.json"` tells the admin server where the game data catalog is located. This file is used to display readable item names, categories, slots and descriptions.

`--host 0.0.0.0` makes the admin interface reachable from other devices in your local network, for example from a phone or tablet.

`--port 8090` starts the web interface on port 8090.

`--user admin` sets the login username for the admin interface.

`--password "change-this-password"` sets the login password. Change this before using the server on your network.

---

## Manual start on Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py --db "db/local.sqlite3" --game-data "data/game-data.json" --host 0.0.0.0 --port 8090 --user admin --password "change-this-password"
```

---

## Recommended local folder setup

Example layout for a private/local setup:

```text
mightydoom-admin-server/
├─ app.py
├─ requirements.txt
├─ start_admin_all_interfaces.bat
├─ db/
│  └─ local.sqlite3
├─ data/
│  └─ game-data.json
└─ backups/
```

The admin server reads and writes the SQLite database directly. Keep regular backups.

---

## Security notes

This tool is meant for private/local administration.

Do **not** expose it directly to the public internet.

Recommended precautions:

- Use a strong admin password.
- Keep it inside your local network or VPN.
- Make backups before testing risky changes.
- Progress transfer can overwrite target user progress; verify source and target IDs carefully.
- Do not commit real databases or backup files to GitHub.
- Do not commit real `.env` files.
- Do not publish private user data.
- Do not run the admin interface on an untrusted network.

---

## Database safety

The admin server contains tools that directly modify the SQLite database.

That is useful, but it also means wrong changes can break user progress or game state.

Safety features include:

- manual database backups
- automatic backups before restore operations
- automatic backups before rollback operations
- audit logging for selected tables
- rollback buttons for logged database changes

Even with these protections, you should still keep external backups of `local.sqlite3`.

---

## Audit trigger setup

The DB audit feature is optional.

When enabled, the admin server installs SQLite triggers into the database. These triggers write changes to admin audit tables.

This makes it possible to see and roll back changes that were made by the game server itself.

Only changes that happen **after** the audit triggers are installed can be logged.

---

## Language support

The web interface currently supports:

- English
- German

Translations are handled inside the server UI layer. The selected language can be changed from the dashboard.

---

## Themes

The dashboard currently includes two visual themes:

- **Ops Dashboard**: dark blue/purple/cyan admin dashboard style
- **Hellforge Dashboard**: darker red/orange DOOM-inspired dashboard style

The selected theme can be changed from the dashboard.

---

## Development notes

The project is intentionally kept as a server-only repository.

The Android admin app was built separately and is not included here.

When contributing or modifying the server:

- keep comments and docstrings in English
- avoid committing generated files
- avoid committing local database files
- keep UI text available in both English and German
- keep the original private server code untouched
- prefer safe database operations with backups

---

## Troubleshooting

### The web interface cannot find the database

Check the `--db` path or the path inside `start_admin_all_interfaces.bat`.

The database file must exist before the admin server starts.

### Item names are missing

Check the `--game-data` path or the path inside `start_admin_all_interfaces.bat`.

Without `game-data.json`, the admin server can still show raw IDs, but readable names and slot metadata may be missing.

### The server is not reachable from another device

Use:

```text
--host 0.0.0.0
```

Also check your firewall and make sure the port is allowed.

### Backup restore is not visible or does not work

Make sure you are running the current server version and that the backup folder exists.

### Audit rollback is not available

Install or update the DB audit triggers from the DB-Audit page first.

Only changes logged after trigger installation can be rolled back.

---

## License

See `LICENSE`.

---

## Credits

This admin server is built as a companion tool for the Mighty DOOM private server project by dannyhpy:

https://gitlab.com/dannyhpy/mightydoom-gameserver

Thanks to the community members working on preservation, private server experiments and local tooling.
