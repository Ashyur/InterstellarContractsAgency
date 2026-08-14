import threading
import tkinter as tk
from datetime import datetime, timezone
from typing import Optional

import requests

import myNotebook as nb
from config import config

PLUGIN_NAME = "InterstellarContractsAgency"

BOUNTY_COOLDOWN_SECONDS = 300


BOUNTY_WEBHOOK_URL = "https://discord.com/api/webhooks/1534246622844682351/BRqokPHHfVfs5DRwS7k7V46rbRF1RLhAlNXVVepdWcrjy553HhnTCViE54e_6_Z5s13-"
PVP_WEBHOOK_URL = "https://discord.com/api/webhooks/1535693270863052850/lvP5He3ecXo3GXGDgIPIs0tV9n1uDRqW4R1yJIzNuSwTfsZFCZNUY6HGhy-CUKts7hTQ"
CARRIER_TRADE_WEBHOOK_URL = "https://discord.com/api/webhooks/1537005940841127950/QMywQBRqhTFoc3r3xwlJfWQczynbCpvTcqcxDfdkRZyALaX8pg8FNHtP_tnFIh7kY1t1"


TRACKED_CARRIER_NAME: Optional[str] = "BZW-T1L"

CFG_PASSKEY = "ed_bounty_pvp_passkey"

passkey_var: Optional[tk.StringVar] = None
 
current_system = "Unknown"
last_sent: dict[str, int] = {}
 
 
def get_passkey() -> str:
    return config.get_str(CFG_PASSKEY, default="")
 
 
def plugin_start3(plugin_dir: str) -> str:
    return PLUGIN_NAME
 
 
def plugin_stop() -> None:
    pass
 
 
def plugin_prefs(parent, cmdr, is_beta):
    global passkey_var
 
    passkey_var = tk.StringVar(value=get_passkey())
 
    frame = nb.Frame(parent)
    frame.columnconfigure(1, weight=1)
 
    nb.Label(frame, text="Passkey:").grid(row=0, column=0, padx=10, pady=(10, 2), sticky=tk.W)
    nb.EntryMenu(frame, textvariable=passkey_var, show="*").grid(row=0, column=1, padx=10, pady=(10, 2), sticky=tk.EW)
 
    nb.Label(
        frame,
        text=(
            "The passkey would be required to verify your kills\n"
            "or to prevent a bad actor from posting fake"
        ),
        justify=tk.LEFT,
    ).grid(row=1, column=0, columnspan=2, padx=10, pady=(6, 10), sticky=tk.W)
 
    return frame
 
 
def prefs_changed(cmdr, is_beta) -> None:
    if passkey_var is not None:
        config.set(CFG_PASSKEY, passkey_var.get().strip())
 
 
def to_unix_timestamp(iso_ts: str) -> int:
    dt = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())
 
 
def is_player_pilot(entry: dict) -> bool:
    pilot_name = entry.get("PilotName", "")
    return pilot_name.startswith("$cmdr_decorate:")
 
 
def build_bounty_embed(entry: dict, system: str) -> dict:
    pilot_name = entry.get("PilotName_Localised") or entry.get("PilotName") or "Unknown"
    ship = entry.get("Ship_Localised") or entry.get("Ship") or "Unknown"
    bounty = entry.get("Bounty", 0)
    legal_status = entry.get("LegalStatus", "Unknown")
    squadron_id = entry.get("SquadronID")
    power = entry.get("Power")
 
    allegiance_lines = []
    if squadron_id:
        allegiance_lines.append(f"_Squadron_: {squadron_id}")
    if power:
        allegiance_lines.append(f"_Power_: {power}")
    allegiance = "\n".join(allegiance_lines) if allegiance_lines else "Unknown"
 
    bounty_value = f"{bounty:,} cr" if bounty else "None (check for player bounty)"
 
    unix_ts = to_unix_timestamp(entry["timestamp"])
 
    return {
        "title": pilot_name,
        "description": f"**Sighted:** <t:{unix_ts}:R>",
        "color": 0xE74C3C if bounty else 0x95A5A6,
        "fields": [
            {"name": "Ship", "value": ship, "inline": True},
            {"name": "Allegiance", "value": allegiance, "inline": True},
            {"name": "Bounty", "value": bounty_value, "inline": True},
            {"name": "Legal Status", "value": legal_status, "inline": True},
            {"name": "Sighted (Journal)", "value": system or "Unknown", "inline": False},
            {"name": "Passkey", "value": get_passkey() or "Not set", "inline": False},
        ],
        "footer": {"text": "Info provided by local journal scan"},
        "timestamp": entry.get("timestamp"),
    }
 
 
def build_pvp_kill_embed(entry: dict, system: str, cmdr: str) -> dict:
    victim = entry.get("Victim", "Unknown")
    combat_rank = entry.get("CombatRank")
 
    unix_ts = to_unix_timestamp(entry["timestamp"])
 
    fields = [
        {"name": "Killer (CMDR)", "value": cmdr or "Unknown", "inline": True},
        {"name": "Victim", "value": victim, "inline": True},
    ]
    if combat_rank is not None:
        fields.append({"name": "Victim Combat Rank", "value": str(combat_rank), "inline": True})
    fields.append({"name": "System", "value": system or "Unknown", "inline": False})
    fields.append({"name": "Passkey", "value": get_passkey() or "Not set", "inline": False})
 
    return {
        "title": f"\U0001F480 PVP Kill: {victim}",
        "description": f"**When:** <t:{unix_ts}:R>",
        "color": 0x2ECC71,
        "fields": fields,
        "footer": {"text": "Info provided by local journal scan"},
        "timestamp": entry.get("timestamp"),
    }
 
 
def build_carrier_trade_embed(entry: dict, station_name: str, cmdr: str, event: str) -> dict:
    commodity = entry.get("Type_Localised") or entry.get("Type") or "Unknown"
    count = entry.get("Count", 0)
 
    if event == "MarketBuy":
        unit_price = entry.get("BuyPrice", 0)
        total = entry.get("TotalCost", unit_price * count)
        action = "Bought"
        color = 0xE67E22
    else:
        unit_price = entry.get("SellPrice", 0)
        total = entry.get("TotalSale", unit_price * count)
        action = "Sold"
        color = 0x3498DB
 
    unix_ts = to_unix_timestamp(entry["timestamp"])
 
    return {
        "title": f"{action} on {station_name or 'Unknown Carrier'}",
        "description": f"**When:** <t:{unix_ts}:R>",
        "color": color,
        "fields": [
            {"name": "Commander", "value": cmdr or "Unknown", "inline": True},
            {"name": "Commodity", "value": commodity, "inline": True},
            {"name": "Quantity", "value": f"{count:,}", "inline": True},
            {"name": "Unit Price", "value": f"{unit_price:,} cr", "inline": True},
            {"name": "Total", "value": f"{total:,} cr", "inline": True},
            {"name": "Carrier", "value": station_name or "Unknown", "inline": False},
            {"name": "Passkey", "value": get_passkey() or "Not set", "inline": False},
        ],
        "footer": {"text": "Info provided by local journal scan"},
        "timestamp": entry.get("timestamp"),
    }
 
 
def _post_webhook(url: str, embed: dict) -> None:
    if not url:
        print(f"[{PLUGIN_NAME}] Webhook URL not configured, skipping send.")
        return
    try:
        resp = requests.post(url, json={"embeds": [embed]}, timeout=10)
        if resp.status_code not in (200, 204):
            print(f"[{PLUGIN_NAME}] Webhook send failed ({resp.status_code}): {resp.text}")
    except requests.RequestException as exc:
        print(f"[{PLUGIN_NAME}] Webhook send error: {exc}")
 
 
def send_webhook_async(url: str, embed: dict) -> None:
    threading.Thread(target=_post_webhook, args=(url, embed), daemon=True).start()
 
 
def journal_entry(cmdr, is_beta, system, station, entry, state):
    global current_system
 
    if system:
        current_system = system
 
    event = entry.get("event")
 
    if event in ("MarketBuy", "MarketSell"):
        station_name = state.get("StationName")
        station_type = state.get("StationType")
        is_tracked_carrier = station_type == "FleetCarrier" and (
            TRACKED_CARRIER_NAME is None or station_name == TRACKED_CARRIER_NAME
        )
        if is_tracked_carrier:
            embed = build_carrier_trade_embed(entry, station_name, cmdr, event)
            send_webhook_async(CARRIER_TRADE_WEBHOOK_URL, embed)
        return
 
    if event == "PVPKill":
        embed = build_pvp_kill_embed(entry, current_system, cmdr)
        send_webhook_async(PVP_WEBHOOK_URL, embed)
        return
 
    if event != "ShipTargeted":
        return
    if not entry.get("TargetLocked"):
        return
 
    bounty = entry.get("Bounty", 0)
    player = is_player_pilot(entry)
    pilot_label = entry.get("PilotName_Localised") or entry.get("PilotName") or "Unknown"
 
    if not player:
        return
 
    pilot_key = entry.get("PilotName", pilot_label)
    entry_ts = to_unix_timestamp(entry["timestamp"])
    previous_ts = last_sent.get(pilot_key)
 
    if previous_ts is not None and (entry_ts - previous_ts) < BOUNTY_COOLDOWN_SECONDS:
        return
 
    last_sent[pilot_key] = entry_ts
 
    embed = build_bounty_embed(entry, current_system)
    send_webhook_async(BOUNTY_WEBHOOK_URL, embed)