# Event Admin and Game Server Integration

The Admin Server v16 can create and manage custom event schedules without changing the Node.js Mighty DOOM game server code.

The admin interface stores event schedules in its own SQLite tables and can export the active schedule to `data/admin-events.json`. The game server can read either the SQLite tables directly or this JSON export.

## Critical ID rule

`admin_event_schedule.scheduled_event_id` is the authoritative event instance id. It must be a valid UUID and it must be used as the game client's `ScheduledEvent.id`.

The progress table must use the exact same value:

```text
admin_event_schedule.scheduled_event_id = admin_event_progress.scheduled_event_id
```

The admin UI never joins progress by the internal `admin_event_schedule.id`. For user-specific schedules it also filters by `user_id`.

Older rows created by pre-v15 builds may contain legacy ids such as `admin-1-8-...` or numeric ids. Use the Events page button **Event-UUIDs/Progress reparieren** to migrate schedule rows to UUIDs and move matching progress rows where possible.

## SQLite tables

### `admin_event_schedule`

| Column | Meaning |
| --- | --- |
| `id` | Admin-internal row id. Do not send this to the game client as the event id. |
| `scheduled_event_id` | Stable UUID used as `ScheduledEvent.id` and progress key. |
| `event_definition_id` | Game event definition id from `game-data.json` |
| `event_type` | `1` GameMode, `2` StoreOffer, `3` BattlePass |
| `tag` | Internal event tag |
| `title` | Human-readable title shown in the admin UI |
| `user_id` | `NULL` for all users, or a concrete target user id |
| `start_time` | UTC ISO timestamp |
| `end_time` | UTC ISO timestamp |
| `availability` | Availability value for the game client |
| `min_api_version` | Optional minimum API version |
| `max_api_version` | Optional maximum API version |
| `stop_time` | Optional UTC ISO stop timestamp |
| `args_json` | Plain JSON object edited in the admin UI |
| `is_active` | `1` active, `0` inactive |
| `created_at` | UTC ISO timestamp |
| `updated_at` | UTC ISO timestamp |

### `admin_event_progress`

| Column | Meaning |
| --- | --- |
| `id` | Admin-internal row id |
| `scheduled_event_id` | UUID from `admin_event_schedule.scheduled_event_id` |
| `user_id` | User id |
| `attempts` | Number of attempts used. Default: `0` |
| `highest_stage` | Highest completed/reached stage. Default: `0` |
| `best_completion_time_milliseconds` | Best completion time. Default: `0` |
| `run_json` | Optional JSON snapshot of the active event run. Default: `NULL` |
| `updated_at` | UTC ISO timestamp |

## JSON export

The export button writes active admin events to:

```text
data/admin-events.json
```

The exported schema is:

```json
{
  "schema": "mightydoom-admin-events/v1",
  "generated_at": "2026-07-05T12:00:00+00:00",
  "source": "Mighty DOOM Admin",
  "scheduled_events": [
    {
      "admin_schedule_id": 1,
      "id": "6cfaf124-9313-4089-b415-00763e7f2c85",
      "scheduled_event_id": "6cfaf124-9313-4089-b415-00763e7f2c85",
      "event_definition_id": 54,
      "event_type": 1,
      "tag": "game_mode_event_zombie_horde",
      "title": "Game Mode Event Zombie Horde",
      "user_id": null,
      "start_time": 1780000000,
      "end_time": 1780604800,
      "availability": 1,
      "min_api_version": null,
      "max_api_version": null,
      "stop_time": null,
      "args": "base64-json",
      "args_json": {
        "additional_event_modifiers": [10, 26],
        "stage_rewards": [
          {"stage": 5, "resources": [{"rid": 1, "amount": 2500}], "loot_rolls": []}
        ]
      }
    }
  ],
  "progress": []
}
```

For the game client, `args` should be used as `ScheduledEvent.args`. It is a Base64 encoded compact JSON representation of `args_json`.

## Suggested game server behavior

For `POST /game/events/get-schedule`, the game server can:

1. Load active rows from `admin_event_schedule` or `data/admin-events.json`.
2. Keep rows where `is_active = 1`.
3. Keep rows where `user_id IS NULL OR user_id = currentUserId`.
4. Keep rows whose `start_time`/`end_time` include the current time.
5. Return objects matching the known `ScheduledEvent` shape. Use `scheduled_event_id` as the returned `id`.

For playable game mode events, `event_type` must be `1`.

For `POST /game/events/get-progress`, read `admin_event_progress` by both `scheduled_event_id` and `user_id`. If no row exists, return an empty/default `GameModeEventState`:

```json
{
  "attempts": 0,
  "scheduled_event_id": "6cfaf124-9313-4089-b415-00763e7f2c85",
  "run": null,
  "highest_stage": 0,
  "best_completion_time_milliseconds": 0
}
```

When the game server stores completion progress, keep the same UUID:

```text
scheduled_event_id = "6cfaf124-9313-4089-b415-00763e7f2c85"
user_id = 11
attempts = 1
run_json = NULL
highest_stage = 20
best_completion_time_milliseconds = 126340
```

## Admin UI behavior

The Events list shows the UUID, number of users with progress, completed users and maximum reached stage. The event detail page shows per-user progress with attempts, highest stage, best completion time, active run state and `updated_at`.

The Events list also exposes quick activate/deactivate actions. The event detail page has a destructive delete action for old or test events. It creates a backup first, then removes every `admin_event_schedule` row with the same `scheduled_event_id` and all matching `admin_event_progress` rows.

Progress reset buttons set defaults instead of deleting progress rows:

- `attempts = 0`
- `highest_stage = 0`
- `best_completion_time_milliseconds = 0`
- `run_json = NULL`

## Notes

- This admin server does not modify the Node.js game server.
- Event completion behavior still belongs in the game server event endpoints.
- The admin UI intentionally prepares `stage_rewards` and `additional_event_modifiers`, but the exact end-screen behavior should be fixed in the game server implementation.
- Before every event schedule change, the admin server creates a database backup and writes an audit log entry.
