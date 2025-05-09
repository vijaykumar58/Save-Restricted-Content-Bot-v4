# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from telethon import TelegramClient
from config import API_ID, API_HASH, BOT_TOKEN, STRING
from pyrogram import Client
import sys
from typing import Dict, Any # Import for type hinting

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
    """Starts the Telethon and Pyrogram clients."""
    print("Starting clients ...")
    # Start the main Telethon client
    if not client.is_connected():
        try:
            await client.start(bot_token=BOT_TOKEN)
            print("SpyLib (Telethon client) started...")
        except Exception as e:
            print(f"Error starting Telethon client: {e}", file=sys.stderr)
            # Depending on criticality, you might want to sys.exit(1) here

    # Start the global userbot if configured and initialized
    if userbot and not userbot.is_connected:
        try:
            await userbot.start()
            print("Global Userbot started...")
        except Exception as e:
            print(f"Hey honey!! check your premium string session, it may be invalid or expire: {e}", file=sys.stderr)
            # The original code sys.exit(1) here, deciding whether to be strict or allow bot without userbot
            # sys.exit(1) # Uncomment to exit if global userbot fails

    # Start the main Pyrogram client (aliased as 'app')
    if not app.is_connected:
        try:
            await app.start()
            print("Pyro App Started...")
        except Exception as e:
            print(f"Error starting Pyrogram client: {e}", file=sys.stderr)
            # Depending on criticality, you might want to sys.exit(1) here
            # sys.exit(1) # Uncomment to exit if Pyrogram client fails

    # Clients are started. They will now listen for updates.
    # No need to return them, they are accessible globally via the module.
    # return client, app, userbot # Returning is optional if they are used globally

# Note: Individual user clients (UC) and user bots (UB) are started on demand
# in plugin code (like plugins/login.py or plugins/batch.py) and cached in UB/UC.
