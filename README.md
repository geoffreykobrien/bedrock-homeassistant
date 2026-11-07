# Crafty Controller for Home Assistant

Monitor and control Minecraft servers (Bedrock **and** Java) managed by [Crafty Controller 4](https://craftycontrol.com) from Home Assistant.

Why this exists: Bedrock Dedicated Server 1.26.60+ switched to the NetherNet transport and no longer answers the classic RakNet status ping, so Home Assistant's built-in Minecraft Server integration (and Crafty's own status display) show it as offline. This integration never pings the game. It talks to Crafty's API and reads join/leave lines from the server log, so it keeps working regardless of protocol.

## Features

- **UI setup**: enter your Crafty URL and API token, and every server is discovered automatically. Servers you create later show up on their own.
- **Reconfigure** the URL, token or SSL setting at any time. If the token stops working, Home Assistant prompts you for a new one (**reauth**).
- **Options**: polling interval, player-tracking source, and which servers to include.
- **One device per server**, with these entities:
  - Running, Crashed and Updating binary sensors
  - Players online, with each player's name and how long they've been on as attributes, plus Version, Started, CPU, Memory and World size sensors
  - Server power switch (on starts the server, off stops it gracefully)
  - Start, Stop, Restart and Backup buttons, plus Force kill and Update server software, which are disabled by default
  - **Player activity** event entity (`joined` / `left`) for automations
- **Crafty host device** with Host CPU and Host memory sensors
- **Events** on the bus: `crafty_controller_player_joined` / `crafty_controller_player_left`
- **Service** `crafty_controller.send_command`: send any console command, such as `say Dinner in 10!` or `gamemode creative @a`
- **Dashboard card** (`custom:crafty-server-card`), registered automatically with a visual editor, so there's no resource to add by hand
- **Diagnostics** download, with the token and paths redacted

## Install

### HACS (recommended)
1. In HACS, open ⋮ → **Custom repositories**, add `https://github.com/geoffreykobrien/bedrock-homeassistant`, and choose category **Integration**.
2. Install **Crafty Controller**, then restart Home Assistant.

### Manual
Copy `custom_components/crafty_controller` into your `config/custom_components/` folder and restart.

## Setup

1. Create a Crafty API token. See [Creating the Crafty API token](#creating-the-crafty-api-token) below.
2. In Home Assistant, go to **Settings → Devices & services → Add integration → Crafty Controller**.
3. Enter the Crafty URL (for example `https://192.168.1.50:8443`) and the token. Leave **Verify SSL** off if Crafty uses its default self-signed certificate.

## Creating the Crafty API token

A Crafty API key belongs to a Crafty user. It can never do more than that user can, and it only sees servers that user has access to. You have two options:

- **Option A (quick):** a Full Access key on your own superuser account.
- **Option B (recommended):** a dedicated `homeassistant` user that only has the permissions this integration needs.

### What each permission is used for

| Integration feature | Crafty permission on the key |
|---|---|
| Discover servers; Running, Crashed, CPU, Memory, World size, Version, Started | The server must be in the user's role (no specific checkbox) |
| Players online, who's online, join/leave events (log tracking, needed for Bedrock) | **Logs** |
| Start, Stop, Restart and Force kill buttons; server switch | **Commands** |
| Backup button | **Backup** |
| `crafty_controller.send_command` service | **Terminal** |
| Update server software button | **Config** |
| Host CPU and Host memory sensors | **Full Access** only. They stay unavailable otherwise, which is harmless |

A read-only dashboard only needs **Logs**. Leave out Commands, Backup, Terminal and Config if you don't want Home Assistant to be able to control the servers. The matching buttons will just return an error.

> If a server shows as unavailable, or players never appear, the Home Assistant log will say which permission is missing. Some Crafty versions have been reported to require Full Access even for the stats endpoint. If a narrow key can't read stats, use Option A.

### Option A: Full Access key on your account

1. In Crafty, open **Panel Config → Users** and click **Edit** on your user.
2. Open the **API Keys** tab.
3. Enter a name (for example `homeassistant`), tick **Full Access**, and click **Create**.
4. In the key list, click **Get A Token** next to the new key and copy the long string it shows.

This token can do anything your account can, so treat it like a password. To revoke it, delete the key from the same tab.

### Option B: dedicated user with only the needed permissions

1. **Create a role.** Go to **Panel Config → Roles → Add role** and name it `Home Assistant`. Add every server Home Assistant should see, and for each one tick the permissions from the table above (for example **Logs**, **Commands**, **Backup** and **Terminal**). Save.
2. **Create a user.** Go to **Panel Config → Users → Add user** and name it `homeassistant`. Give it any strong password (it's never used to log in), assign the **Home Assistant** role, leave **Superuser** off, and save.
3. **Create the key.** Edit the `homeassistant` user and open the **API Keys** tab. Enter a name, tick the same permissions you gave the role, and click **Create**.
4. Click **Get A Token** and copy the string.

New servers you create later won't appear in Home Assistant until you add them to the role.

### Changing the token later

Go to **Settings → Devices & services → Crafty Controller → ⋮ → Reconfigure** and paste the new token. If Crafty starts rejecting the token, Home Assistant will show a **Re-authenticate** prompt.

## Dashboard card

Add a card, search for **Crafty Minecraft Server**, and pick the server. Or use YAML:

```yaml
type: custom:crafty-server-card
device_id: <your server's device id>
title: Liam's Server     # optional
show_players: true
show_stats: true
show_controls: true      # Stop and Restart ask for a second tap to confirm
```

## Player tracking

| Option | How it works | Best for |
|---|---|---|
| **Automatic** (default) | Log for Bedrock servers or any server whose ping fails, Crafty's ping data otherwise | Mixed setups |
| Crafty's ping data | Uses `online`/`players` from Crafty's stats | Java servers |
| Server log | Replays `Player connected/disconnected` (Bedrock) and `joined/left the game` (Java) since the last server start | Bedrock 1.26.60+ |

## Automation examples

Notify when someone joins:

```yaml
triggers:
  - trigger: event
    event_type: crafty_controller_player_joined
actions:
  - action: notify.mobile_app_phone
    data:
      message: "{{ trigger.event.data.player }} joined {{ trigger.event.data.server_name }}"
```

Warn players and stop the server on school nights:

```yaml
triggers:
  - trigger: time
    at: "20:50:00"
conditions:
  - condition: time
    weekday: [sun, mon, tue, wed, thu]
actions:
  - action: crafty_controller.send_command
    data:
      device_id: <server device id>
      command: say Server shuts down in 10 minutes!
  - delay: "00:10:00"
  - action: switch.turn_off
    target:
      entity_id: switch.bedrock_creative_server
```

## Notes

- The `Started` timestamp and Bedrock join times are read in Home Assistant's time zone. Run Crafty in the same zone, or they'll be offset.
- Crafty's host metrics come from its `/metrics/host` endpoint. If your token can't read it, the host sensors just stay unavailable.
- Tested against the Crafty 4 API v2 spec. Please open an issue with a diagnostics download if something looks off.

## Development

```bash
pip install -r requirements_test.txt
pytest
```
