import glob
import json
import os
import threading
import tkinter as tk
from datetime import datetime, timezone
from typing import Optional

import requests

import myNotebook as nb
from config import config


PLUGIN_NAME = "InterstellarContractsAgency"

BOUNTY_COOLDOWN_SECONDS = 300

GAME_MODE_CHECK_INTERVAL = 60_000



BOUNTY_WEBHOOK_URL = "https://discord.com/api/webhooks/1534246622844682351/BRqokPHHfVfs5DRwS7k7V46rbRF1RLhAlNXVVepdWcrjy553HhnTCViE54e_6_Z5s13-"
PVP_WEBHOOK_URL = "https://discord.com/api/webhooks/1535693270863052850/lvP5He3ecXo3GXGDgIPIs0tV9n1uDRqW4R1yJIzNuSwTfsZFCZNUY6HGhy-CUKts7hTQ"
CARRIER_TRADE_WEBHOOK_URL = "https://discord.com/api/webhooks/1537005940841127950/QMywQBRqhTFoc3r3xwlJfWQczynbCpvTcqcxDfdkRZyALaX8pg8FNHtP_tnFIh7kY1t1"


TRACKED_CARRIER_NAME: Optional[str] = "BZW-T1L"


CFG_PASSKEY = "ed_bounty_pvp_passkey"
CFG_IGNORE_WING_PLAYERS = "ed_ignore_wing_players"


STATUS_FLAG_IN_WING = 1 << 7


passkey_var: Optional[tk.StringVar] = None
ignore_wing_players_var: Optional[tk.BooleanVar] = None


current_system = "Unknown"

last_sent: dict[str, int] = {}

in_wing: bool = False

current_game_mode: str = "Unknown"


wing_value_label: Optional[tk.Label] = None
mode_value_label: Optional[tk.Label] = None
sending_value_label: Optional[tk.Label] = None


game_mode_check_started = False



def get_passkey() -> str:
    return config.get_str(
        CFG_PASSKEY,
        default=""
    )


def ignore_wing_players_enabled() -> bool:

    value = config.get_str(
        CFG_IGNORE_WING_PLAYERS,
        default="1"
    )

    return value.lower() in (
        "1",
        "true",
        "yes",
        "on"
    )



def should_suppress_sends() -> bool:

    if in_wing:
        return False

    if current_game_mode != "Open":
        return True

    return False


def display_game_mode(mode: str) -> str:

    if mode == "Group":
        return "Private Group"

    if mode == "Solo":
        return "Solo"

    if mode == "Open":
        return "Open"

    if not mode:
        return "Unknown"

    return mode


def refresh_status_labels() -> None:

    if wing_value_label is not None:

        if in_wing:
            wing_value_label["text"] = "In Wing"
        else:
            wing_value_label["text"] = "Solo"

    if mode_value_label is not None:

        mode_value_label["text"] = display_game_mode(
            current_game_mode
        )

    if sending_value_label is not None:

        if in_wing:
            sending_value_label["text"] = "Active: In Wing"

        elif current_game_mode != "Open":
            sending_value_label["text"] = (
                f"Suppressed: "
                f"{display_game_mode(current_game_mode)}"
            )

        else:
            sending_value_label["text"] = "Active"


def journal_dir() -> Optional[str]:

    configured = config.get_str(
        "journaldir",
        default=""
    )

    if configured and os.path.isdir(configured):
        return configured

    home = os.path.expanduser("~")

    candidates = [

        os.path.join(
            home,
            "Saved Games",
            "Frontier Developments",
            "Elite Dangerous",
        ),

        os.path.join(
            home,
            "Library",
            "Application Support",
            "Frontier Developments",
            "Elite Dangerous",
        ),

    ]

    for path in candidates:

        if os.path.isdir(path):
            return path

    return None


def recover_game_mode_from_journal() -> str:

    directory = journal_dir()

    if not directory:
        return "Unknown"

    files = sorted(
        glob.glob(
            os.path.join(
                directory,
                "Journal.*.log"
            )
        ),
        key=os.path.getmtime,
        reverse=True,
    )

    if not files:
        return "Unknown"

    try:

        with open(
            files[0],
            "r",
            encoding="utf-8"
        ) as fh:

            lines = fh.readlines()

    except OSError:

        return "Unknown"

    for line in reversed(lines):

        line = line.strip()

        if not line:
            continue

        try:

            parsed = json.loads(line)

        except json.JSONDecodeError:

            continue

        if parsed.get("event") == "LoadGame":

            return parsed.get(
                "GameMode",
                "Unknown"
            )

    return "Unknown"


def update_game_mode_from_journal() -> None:


    global current_game_mode

    new_mode = recover_game_mode_from_journal()

    if (
        new_mode != "Unknown"
        and new_mode != current_game_mode
    ):

        current_game_mode = new_mode

        print(
            f"[{PLUGIN_NAME}] "
            f"GameMode changed to: "
            f"{display_game_mode(current_game_mode)}"
        )

        refresh_status_labels()

    if wing_value_label is not None:

        wing_value_label.after(
            GAME_MODE_CHECK_INTERVAL,
            update_game_mode_from_journal
        )


def plugin_start3(plugin_dir: str) -> str:

    global current_game_mode

    current_game_mode = recover_game_mode_from_journal()

    print(
        f"[{PLUGIN_NAME}] "
        f"Initial GameMode: "
        f"{display_game_mode(current_game_mode)}"
    )

    print(
        f"[{PLUGIN_NAME}] "
        f"Ignore wing players: "
        f"{ignore_wing_players_enabled()}"
    )

    return PLUGIN_NAME


def plugin_stop() -> None:
    pass



def plugin_app(parent: tk.Frame) -> tk.Frame:

    global wing_value_label
    global mode_value_label
    global sending_value_label
    global game_mode_check_started

    frame = tk.Frame(parent)

    frame.columnconfigure(
        1,
        weight=1
    )

    tk.Label(
        frame,
        text=f"{PLUGIN_NAME}:"
    ).grid(
        row=0,
        column=0,
        columnspan=2,
        sticky=tk.W
    )

    tk.Label(
        frame,
        text="Wing:"
    ).grid(
        row=1,
        column=0,
        sticky=tk.W,
        padx=(10, 4)
    )

    wing_value_label = tk.Label(
        frame,
        text="Solo"
    )

    wing_value_label.grid(
        row=1,
        column=1,
        sticky=tk.W
    )

    tk.Label(
        frame,
        text="Mode:"
    ).grid(
        row=2,
        column=0,
        sticky=tk.W,
        padx=(10, 4)
    )

    mode_value_label = tk.Label(
        frame,
        text=display_game_mode(
            current_game_mode
        )
    )

    mode_value_label.grid(
        row=2,
        column=1,
        sticky=tk.W
    )

    tk.Label(
        frame,
        text="Sending:"
    ).grid(
        row=3,
        column=0,
        sticky=tk.W,
        padx=(10, 4)
    )

    sending_value_label = tk.Label(
        frame,
        text="Suppressed"
    )

    sending_value_label.grid(
        row=3,
        column=1,
        sticky=tk.W
    )

    refresh_status_labels()

    if not game_mode_check_started:

        game_mode_check_started = True

        update_game_mode_from_journal()

    return frame


def plugin_prefs(parent, cmdr, is_beta):

    global passkey_var
    global ignore_wing_players_var

    passkey_var = tk.StringVar(
        value=get_passkey()
    )

    ignore_wing_players_var = tk.BooleanVar(
        value=ignore_wing_players_enabled()
    )

    frame = nb.Frame(parent)

    frame.columnconfigure(
        1,
        weight=1
    )

    nb.Label(
        frame,
        text="Passkey:"
    ).grid(
        row=0,
        column=0,
        padx=10,
        pady=(10, 2),
        sticky=tk.W
    )

    nb.EntryMenu(
        frame,
        textvariable=passkey_var,
        show="*"
    ).grid(
        row=0,
        column=1,
        padx=10,
        pady=(10, 2),
        sticky=tk.EW
    )

    nb.Label(
        frame,
        text=(
            "The passkey would be required to verify your kills\n"
            "or to prevent a bad actor from posting fake"
        ),
        justify=tk.LEFT,
    ).grid(
        row=1,
        column=0,
        columnspan=2,
        padx=10,
        pady=(6, 10),
        sticky=tk.W
    )

    nb.Checkbutton(
        frame,
        text="Ignore players in my wing",
        variable=ignore_wing_players_var
    ).grid(
        row=2,
        column=0,
        columnspan=2,
        padx=10,
        pady=(4, 10),
        sticky=tk.W
    )

    nb.Label(
        frame,
        text=(
            "When enabled, players who are members of your wing "
            "will not generate bounty webhook messages."
        ),
        justify=tk.LEFT,
    ).grid(
        row=3,
        column=0,
        columnspan=2,
        padx=10,
        pady=(0, 10),
        sticky=tk.W
    )

    return frame


def prefs_changed(cmdr, is_beta) -> None:

    if passkey_var is not None:

        config.set(
            CFG_PASSKEY,
            passkey_var.get().strip()
        )

    if ignore_wing_players_var is not None:

        config.set(
            CFG_IGNORE_WING_PLAYERS,
            "1"
            if ignore_wing_players_var.get()
            else "0"
        )



def to_unix_timestamp(iso_ts: str) -> int:

    dt = datetime.strptime(
        iso_ts,
        "%Y-%m-%dT%H:%M:%SZ"
    ).replace(
        tzinfo=timezone.utc
    )

    return int(
        dt.timestamp()
    )


def is_player_pilot(entry: dict) -> bool:

    pilot_name = entry.get(
        "PilotName",
        ""
    )

    return pilot_name.startswith(
        "$cmdr_decorate:"
    )


def should_ignore_wing_player(entry: dict) -> bool:

    if not ignore_wing_players_enabled():
        return False

    if not in_wing:
        return False

    if entry.get("IsWingMember") is True:
        return True


    wing = entry.get("Wing")

    if wing:
        return True


    wing_data = entry.get("WingMember")

    if wing_data:
        return True

    for key in (
        "InWing",
        "WingMember",
        "IsInWing",
    ):

        value = entry.get(key)

        if value is True:
            return True

        if isinstance(value, str):

            if value.lower() in (
                "true",
                "yes",
                "1"
            ):
                return True

    return False

def build_bounty_embed(
    entry: dict,
    system: str
) -> dict:

    pilot_name = (
        entry.get("PilotName_Localised")
        or entry.get("PilotName")
        or "Unknown"
    )

    ship = (
        entry.get("Ship_Localised")
        or entry.get("Ship")
        or "Unknown"
    )

    bounty = entry.get(
        "Bounty",
        0
    )

    legal_status = entry.get(
        "LegalStatus",
        "Unknown"
    )

    squadron_id = entry.get(
        "SquadronID"
    )

    power = entry.get(
        "Power"
    )

    allegiance_lines = []

    if squadron_id:

        allegiance_lines.append(
            f"_Squadron_: {squadron_id}"
        )

    if power:

        allegiance_lines.append(
            f"_Power_: {power}"
        )

    allegiance = (
        "\n".join(allegiance_lines)
        if allegiance_lines
        else "Unknown"
    )

    bounty_value = (
        f"{bounty:,} cr"
        if bounty
        else "None (check for player bounty)"
    )

    unix_ts = to_unix_timestamp(
        entry["timestamp"]
    )

    return {

        "title": pilot_name,

        "description": (
            f"**Sighted:** "
            f"<t:{unix_ts}:R>"
        ),

        "color": (
            0xE74C3C
            if bounty
            else 0x95A5A6
        ),

        "fields": [

            {
                "name": "Ship",
                "value": ship,
                "inline": True
            },

            {
                "name": "Allegiance",
                "value": allegiance,
                "inline": True
            },

            {
                "name": "Bounty",
                "value": bounty_value,
                "inline": True
            },

            {
                "name": "Legal Status",
                "value": legal_status,
                "inline": True
            },

            {
                "name": "Sighted (Journal)",
                "value": system or "Unknown",
                "inline": False
            },

            {
                "name": "Passkey",
                "value": (
                    get_passkey()
                    or "Not set"
                ),
                "inline": False
            },

        ],

        "footer": {
            "text": "Info provided by local journal scan"
        },

        "timestamp": entry.get(
            "timestamp"
        ),
    }


def build_pvp_kill_embed(
    entry: dict,
    system: str,
    cmdr: str
) -> dict:

    victim = entry.get(
        "Victim",
        "Unknown"
    )

    combat_rank = entry.get(
        "CombatRank"
    )

    unix_ts = to_unix_timestamp(
        entry["timestamp"]
    )

    fields = [

        {
            "name": "Killer (CMDR)",
            "value": cmdr or "Unknown",
            "inline": True
        },

        {
            "name": "Victim",
            "value": victim,
            "inline": True
        },

    ]

    if combat_rank is not None:

        fields.append(
            {
                "name": "Victim Combat Rank",
                "value": str(combat_rank),
                "inline": True
            }
        )

    fields.append(
        {
            "name": "System",
            "value": system or "Unknown",
            "inline": False
        }
    )

    fields.append(
        {
            "name": "Passkey",
            "value": (
                get_passkey()
                or "Not set"
            ),
            "inline": False
        }
    )

    return {

        "title": (
            f"\U0001F480 PVP Kill: "
            f"{victim}"
        ),

        "description": (
            f"**When:** "
            f"<t:{unix_ts}:R>"
        ),

        "color": 0x2ECC71,

        "fields": fields,

        "footer": {
            "text": "Info provided by local journal scan"
        },

        "timestamp": entry.get(
            "timestamp"
        ),
    }


def build_carrier_trade_embed(
    entry: dict,
    station_name: str,
    cmdr: str,
    event: str
) -> dict:

    commodity = (
        entry.get("Type_Localised")
        or entry.get("Type")
        or "Unknown"
    )

    count = entry.get(
        "Count",
        0
    )

    if event == "MarketBuy":

        unit_price = entry.get(
            "BuyPrice",
            0
        )

        total = entry.get(
            "TotalCost",
            unit_price * count
        )

        action = "Bought"

        color = 0xE67E22

    else:

        unit_price = entry.get(
            "SellPrice",
            0
        )

        total = entry.get(
            "TotalSale",
            unit_price * count
        )

        action = "Sold"

        color = 0x3498DB

    unix_ts = to_unix_timestamp(
        entry["timestamp"]
    )

    return {

        "title": (
            f"{action} on "
            f"{station_name or 'Unknown Carrier'}"
        ),

        "description": (
            f"**When:** "
            f"<t:{unix_ts}:R>"
        ),

        "color": color,

        "fields": [

            {
                "name": "Commander",
                "value": cmdr or "Unknown",
                "inline": True
            },

            {
                "name": "Commodity",
                "value": commodity,
                "inline": True
            },

            {
                "name": "Quantity",
                "value": f"{count:,}",
                "inline": True
            },

            {
                "name": "Unit Price",
                "value": f"{unit_price:,} cr",
                "inline": True
            },

            {
                "name": "Total",
                "value": f"{total:,} cr",
                "inline": True
            },

            {
                "name": "Carrier",
                "value": station_name or "Unknown",
                "inline": False
            },

            {
                "name": "Passkey",
                "value": (
                    get_passkey()
                    or "Not set"
                ),
                "inline": False
            },

        ],

        "footer": {
            "text": "Info provided by local journal scan"
        },

        "timestamp": entry.get(
            "timestamp"
        ),
    }



def _post_webhook(
    url: str,
    embed: dict
) -> None:

    if not url:

        print(
            f"[{PLUGIN_NAME}] "
            "Webhook URL not configured, "
            "skipping send."
        )

        return

    try:

        resp = requests.post(
            url,
            json={
                "embeds": [embed]
            },
            timeout=10
        )

        if resp.status_code not in (
            200,
            204
        ):

            print(
                f"[{PLUGIN_NAME}] "
                f"Webhook send failed "
                f"({resp.status_code}): "
                f"{resp.text}"
            )

    except requests.RequestException as exc:

        print(
            f"[{PLUGIN_NAME}] "
            f"Webhook send error: {exc}"
        )


def send_webhook_async(
    url: str,
    embed: dict
) -> None:

    threading.Thread(
        target=_post_webhook,
        args=(url, embed),
        daemon=True
    ).start()



def dashboard_entry(
    cmdr,
    is_beta,
    entry: dict
) -> None:

    global in_wing

    flags = entry.get(
        "Flags",
        0
    )

    in_wing = bool(
        flags & STATUS_FLAG_IN_WING
    )

    refresh_status_labels()


def journal_entry(
    cmdr,
    is_beta,
    system,
    station,
    entry,
    state
):

    global current_system
    global current_game_mode

    if system:
        current_system = system

    event = entry.get(
        "event"
    )


    if event == "LoadGame":

        current_game_mode = entry.get(
            "GameMode",
            "Unknown"
        )

        print(
            f"[{PLUGIN_NAME}] "
            f"GameMode: "
            f"{display_game_mode(current_game_mode)}"
        )

        refresh_status_labels()

        return


    if event in (
        "MarketBuy",
        "MarketSell"
    ):

        if should_suppress_sends():
            return

        station_name = state.get(
            "StationName"
        )

        station_type = state.get(
            "StationType"
        )

        is_tracked_carrier = (
            station_type == "FleetCarrier"
            and (
                TRACKED_CARRIER_NAME is None
                or station_name == TRACKED_CARRIER_NAME
            )
        )

        if is_tracked_carrier:

            embed = build_carrier_trade_embed(
                entry,
                station_name,
                cmdr,
                event
            )

            send_webhook_async(
                CARRIER_TRADE_WEBHOOK_URL,
                embed
            )

        return


    if event == "PVPKill":

        if should_suppress_sends():
            return

        embed = build_pvp_kill_embed(
            entry,
            current_system,
            cmdr
        )

        send_webhook_async(
            PVP_WEBHOOK_URL,
            embed
        )

        return


    if event != "ShipTargeted":
        return

    if not entry.get(
        "TargetLocked"
    ):
        return

    if should_suppress_sends():
        return

    bounty = entry.get(
        "Bounty",
        0
    )

    player = is_player_pilot(
        entry
    )

    pilot_label = (
        entry.get("PilotName_Localised")
        or entry.get("PilotName")
        or "Unknown"
    )


    if not player:
        return


    if should_ignore_wing_player(entry):

        print(
            f"[{PLUGIN_NAME}] "
            f"Ignoring wing member: "
            f"{pilot_label}"
        )

        return

    pilot_key = entry.get(
        "PilotName",
        pilot_label
    )

    entry_ts = to_unix_timestamp(
        entry["timestamp"]
    )

    previous_ts = last_sent.get(
        pilot_key
    )

    if (
        previous_ts is not None
        and (
            entry_ts - previous_ts
        ) < BOUNTY_COOLDOWN_SECONDS
    ):

        return

    last_sent[pilot_key] = entry_ts


    embed = build_bounty_embed(
        entry,
        current_system
    )

    send_webhook_async(
        BOUNTY_WEBHOOK_URL,
        embed
    )
