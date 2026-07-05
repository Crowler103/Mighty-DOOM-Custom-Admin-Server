# Ingame Inbox Admin Integration

The Admin Server v17 can create and manage inbox messages for the private Mighty DOOM game server without modifying the Node.js game server code in this repository.

The local game server bridge is expected to read the SQLite tables described below and expose messages through the existing game endpoints:

```text
POST /game/inbox/get-messages
POST /game/inbox/read
POST /game/inbox/claim
POST /game/inbox/delete
```

## SQLite tables

### `admin_inbox_messages`

| Column | Meaning |
| --- | --- |
| `id` | Admin message id. |
| `user_id` | `NULL` for all users, or a concrete target user id. |
| `display_type` | Game/client display type. Defaults to `1`. |
| `title` | Message title. Required. |
| `body` | Message body text. Required. |
| `published` | Optional unix timestamp in seconds. Message should not appear before this time. |
| `expires` | Optional unix timestamp in seconds. Message should not appear after this time. |
| `resources_json` | JSON list of rewards. Empty messages use `[]`. |
| `image_id` | Optional image id passed through to the game bridge. |
| `conditions_json` | Reserved JSON object for future conditions. Defaults to `{}`. |
| `is_active` | `1` active, `0` disabled. |
| `created_at` | Unix timestamp in seconds. |
| `updated_at` | Unix timestamp in seconds. |

Global messages are stored as:

```text
admin_inbox_messages.user_id = NULL
```

User-specific messages are stored with a concrete user id:

```text
admin_inbox_messages.user_id = 7
```

### `admin_inbox_message_state`

| Column | Meaning |
| --- | --- |
| `id` | Admin state row id. |
| `message_id` | References `admin_inbox_messages.id`. |
| `user_id` | User id. |
| `state` | Inbox state value. |
| `claimed_at` | Optional unix timestamp in seconds. |
| `read_at` | Optional unix timestamp in seconds. |
| `deleted_at` | Optional unix timestamp in seconds. |
| `updated_at` | Unix timestamp in seconds. |

State values:

```text
1 = unread
2 = read
3 = claimed
4 = deleted/archived
```

## Rewards format

Rewards are stored in `admin_inbox_messages.resources_json` as a compact JSON list:

```json
[
  {"rid": 1, "amount": 1000}
]
```

If a message has no rewards, the value should be:

```json
[]
```

`rid` and `amount` must be integers. Negative values are rejected by the admin UI.

## Suggested game server behavior

For `POST /game/inbox/get-messages`, the game server can:

1. Select rows from `admin_inbox_messages` where `is_active = 1`.
2. Keep rows where `user_id IS NULL OR user_id = currentUserId`.
3. Keep rows whose `published` is `NULL` or less than/equal to the current time.
4. Keep rows whose `expires` is `NULL` or greater than the current time.
5. Join or look up `admin_inbox_message_state` by `(message_id, user_id)`.
6. Treat missing state rows as unread (`state = 1`).
7. Do not return messages where state is `4` for the current user.

For `read`, `claim` and `delete`, the game server should upsert one state row per `(message_id, user_id)` and update the matching timestamp fields.

## Admin UI behavior

The Inbox page can create, edit, activate, deactivate and delete messages. The message detail page shows user state rows and can reset state for one user or all users. Reset currently deletes the state rows so the game server can treat the message as unread again on the next request.

Before every write operation, the admin server creates a database backup and writes an audit-log entry.

## Safety notes

- This admin server only manages SQLite tables.
- It does not modify the Node.js game server.
- Do not commit real SQLite databases, backups, logs or exported private data.


## image_id compatibility

`image_id` is optional. For compatibility with older local SQLite schemas that may have created `admin_inbox_messages.image_id` as `NOT NULL`, the admin interface stores an empty string when no image is selected. The game server should treat `NULL` and an empty string as no image.
