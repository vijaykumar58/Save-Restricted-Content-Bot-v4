# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from telethon import TelegramClient
from telethon.errors import FloodWaitError as TelethonFloodWaitError # Rename to avoid conflict
from config import API_ID, API_HASH, BOT_TOKEN, STRING
from pyrogram import Client
from pyrogram.errors import FloodWait as PyrogramFloodWait # Specific Pyrogram FloodWait
import sys
import asyncio # Import asyncio for sleep
from typing import Dict, Any # Import for type hinting
import time # Import time for logging wait duration

# Initialize clients (these are the primary clients used by the bot)
client = TelegramClient("telethonbot", API_ID, API_HASH) # Telethon client
app = Client("pyrogrambot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN) # Pyrogram client

# Initialize global userbot (optional, based on STRING)
userbot = None
if STRING:
    try:
        userbot = Client("4gbbot", api_id=API_ID, api_hash=API_HASH, session_string=STRING)
    except Exception as e:
        print(f"Warning: Failed to initialize global userbot with provided STRING: {e}", file=sys.stderr)
        print("The bot will start without the global userbot.", file=sys.stderr)
        userbot = None # Ensure userbot is None if initialization fails

# Dictionaries to cache user-specific clients (moved from plugins/batch.py)
UB: Dict[int, Client] = {} # Cache for user-specific bot clients {user_id: client_instance}
UC: Dict[int, Client] = {} # Cache for user-specific user clients {user_id: client_instance}


async def start_client():
    """Starts the Telethon and Pyrogram clients with FloodWait retry logic."""
    print("Starting clients ...")

    clients_to_start = []
    if not client.is_connected():
        clients_to_start.append(('Telethon client', client, TelethonFloodWaitError))
    if app and not app.is_connected:
         clients_to_start.append(('Pyrogram client', app, PyrogramFloodWait))
    if userbot and not userbot.is_connected:
         clients_to_start.append(('Global Userbot', userbot, PyrogramFloodWait)) # Assuming userbot uses Pyrogram

    # Retry logic for starting each client
    for client_name, client_instance, flood_wait_error_type in clients_to_start:
        retries = 0
        max_retries = 5 # Limit the number of retries
        while retries < max_retries:
            try:
                print(f"Attempting to start {client_name} (Attempt {retries + 1}/{max_retries})...")
                if client_name == 'Telethon client':
                    await client_instance.start(bot_token=BOT_TOKEN) # Telethon start needs bot_token if bot
                else:
                    await client_instance.start() # Pyrogram start
                print(f"{client_name} started...")
                break # Exit the retry loop if successful
            except flood_wait_error_type as e:
                wait_time = getattr(e, 'seconds', getattr(e, 'value', 60)) # Get wait time (Telethon vs Pyrogram)
                print(f"FloodWait for {client_name}: Need to wait {wait_time} seconds. Retrying in {min(wait_time + 5, 600)} seconds...", file=sys.stderr) # Add a small buffer, cap wait
                await asyncio.sleep(min(wait_time + 5, 600)) # Wait and cap the wait time
                retries += 1
            except Exception as e:
                print(f"Error starting {client_name}: {e}", file=sys.stderr)
                # Decide if other errors should trigger retry or stop
                # For now, let's not retry on non-FloodWait errors during startup
                break # Exit the retry loop on other errors

        if retries == max_retries:
             print(f"Failed to start {client_name} after {max_retries} attempts due to FloodWait or other error.", file=sys.stderr)
             # Depending on criticality, you might want to sys.exit(1) here
             # if client_name in ['Telethon client', 'Pyrogram client']: sys.exit(1)


    # Clients are started (or failed to start after retries).
    # They will now listen for updates if successful.


# Note: Individual user clients (UC) and user bots (UB) are started on demand
# in plugin code (like plugins/login.py or plugins/batch.py) and cached in UB/UC.
