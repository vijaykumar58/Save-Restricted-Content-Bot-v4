# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import asyncio
from shared_client import start_client
import importlib
import os
import sys

# Explicitly import custom_filters module early to ensure filters are defined
import utils.custom_filters

async def load_and_run_plugins():
    """
    Starts the Telegram clients and dynamically loads and initializes plugins
    from the 'plugins' directory.
    """
    # Start the clients first
    await start_client()

    plugin_dir = "plugins"
    # List all python files in the plugins directory, excluding __init__.py
    plugins = [f[:-3] for f in os.listdir(plugin_dir) if f.endswith(".py") and f != "__init__.py"]

    print(f"Found plugins: {plugins}") # Optional: log found plugins

    for plugin in plugins:
        try:
            # Import the plugin module
            module = importlib.import_module(f"plugins.{plugin}")
            print(f"Successfully imported plugin: {plugin}") # Optional: log successful import

            # The original code looked for a run_<plugin>_plugin function,
            # but your plugins define handlers directly using decorators.
            # Importing the module is enough to register the handlers with Pyrogram/Telethon clients.
            # If plugins had specific initialization logic beyond handler registration,
            # you would call it here if it existed (e.g., if hasattr(module, 'initialize'): await module.initialize()).
            # Based on the provided code, simple import is sufficient to register handlers.

        except Exception as e:
            # Log errors during plugin import
            print(f"Error importing or initializing plugin {plugin}: {e}", file=sys.stderr)
            # Depending on severity, you might want to exit or continue
            # sys.exit(1) # Uncomment if a failed plugin import should stop the bot

    # The clients are running and handlers are registered.
    # The bot will now listen for incoming updates.


async def main():
    """Main function to load plugins and keep the bot running."""
    await load_and_run_plugins()
    print("Bot is running. Press Ctrl+C to stop.")
    # Keep the main loop running to allow the clients to process updates
    # The Pyrogram/Telethon clients have their own internal loops listening for updates.
    # This sleep loop prevents the main asyncio event loop from closing.
    while True:
        await asyncio.sleep(3600) # Sleep for a long time, bot is event-driven

if __name__ == "__main__":
    print("Starting clients ...")
    try:
        # Use asyncio.run() which is standard in Python 3.7+
        # It handles creating, running, and closing the event loop.
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        # Clean shutdown for clients might be needed here depending on their design
        # (e.g., await client.disconnect(), await app.stop(), await userbot.stop())
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)
