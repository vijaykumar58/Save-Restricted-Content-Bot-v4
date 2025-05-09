 # Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from shared_client import app # Using the Pyrogram client
from pyrogram import filters
from pyrogram.errors import UserNotParticipant, MessageNotModified, RPCError
from pyrogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from config import LOG_GROUP, OWNER_ID, FORCE_SUB
import base64 as spy # Keep the alias for consistency with other files
from utils.func import a1, a2, a3, a4, a5, a7, a8, a9, a10, a11 # Assuming these base64 strings are needed

# Helper function for safe message editing
async def edit_message_safely(message, text, reply_markup=None):
    """Helper function to edit message and handle errors like MessageNotModified"""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass # Ignore if the message hasn't changed
    except RPCError as e:
        print(f"Error editing message: {e}") # Log other potential errors

# Helper function for safe message deletion
async def delete_message_safely(message):
    """Helper function to delete message and handle errors"""
    try:
        await message.delete()
    except RPCError as e:
        print(f"Error deleting message: {e}") # Log potential errors

async def subscribe(app, message):
    """
    Checks if the user is subscribed to the FORCE_SUB channel.
    Returns 0 if subscribed, 1 if not or error.
    """
    if not FORCE_SUB:
        return 0 # No force subscribe channel set
        
    try:
        user = await app.get_chat_member(FORCE_SUB, message.from_user.id)
        # Check for restricted or banned status as well, not just UserNotParticipant
        if user.status in ["kicked", "banned", "restricted"]:
             await message.reply_text("You are restricted or banned from the channel. Contact -- Team SPY")
             return 1
        if user.status == "left": # UserNotParticipant might not always be raised for 'left'
            raise UserNotParticipant # Raise to trigger the except block for join message
        return 0 # User is a member and not restricted/banned

    except UserNotParticipant:
        try:
            link = await app.export_chat_invite_link(FORCE_SUB)
            caption = "Join our channel to use the bot"
            # Using a placeholder image URL. Ensure this URL is valid or replace with a local file.
            await message.reply_photo(
                photo="https://graph.org/file/d44f024a08ded19452152.jpg",
                caption=caption,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Now...", url=link)]])
            )
        except RPCError as ggn:
            # Handle errors during invite link export or sending message
            await message.reply_text(f"Something Went Wrong getting invite link. Contact admins... with following message: {ggn}")
        return 1
    except Exception as ggn:
        # Catch any other unexpected errors during the check
        await message.reply_text(f"Something Went Wrong checking subscription. Contact admins... with following message: {ggn}")
        return 1

@app.on_message(filters.command("set") & filters.private)
async def set_commands(_, message):
    """Sets the bot commands list."""
    # Check if the user is the owner
    if message.from_user.id not in OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return

    try:
        await app.set_bot_commands([
            BotCommand("start", "🚀 Start the bot"),
            BotCommand("batch", "🫠 Extract in bulk"),
            BotCommand("single", "🫠 Extract single post"), # Added from batch.py
            BotCommand("login", "🔑 Get into the bot"),
            BotCommand("setbot", "🧸 Add your bot for handling files"),
            BotCommand("logout", "🚪 Get out of the bot"),
            BotCommand("adl", "👻 Download audio from 30+ sites"),
            BotCommand("dl", "💀 Download videos from 30+ sites"),
            BotCommand("status", "⟳ Refresh Payment status"), # Renamed from /pay or /status in stats.py?
            BotCommand("transfer", "💘 Gift premium to others"),
            BotCommand("add", "➕ Add user to premium (Owner Only)"), # Added owner only note
            BotCommand("rem", "➖ Remove from premium (Owner Only)"), # Added owner only note
            BotCommand("rembot", "🤨 Remove your custom bot"),
            BotCommand("settings", "⚙️ Personalize things"),
            BotCommand("plan", "🗓️ Check our premium plans"),
            BotCommand("terms", "🥺 Terms and conditions"),
            BotCommand("help", "❓ If you're a noob, still!"),
            BotCommand("cancel", "🚫 Cancel login/batch/settings process"),
            BotCommand("stop", "🚫 Cancel batch process") # Alias for cancel
        ])
        await message.reply("✅ Commands configured successfully!")
    except Exception as e:
        await message.reply(f"❌ Failed to set commands: {e}")


# Help text divided into pages
help_pages = [
    (
        "📝 **Bot Commands Overview (1/2)**:\n\n"
        "1. **/start**\n"
        "> 🚀 Start the bot\n\n"
        "2. **/help**\n"
        "> ❓ Get help about commands\n\n"
        "3. **/terms**\n"
        "> 🥺 Read the terms and conditions\n\n"
        "4. **/plan**\n"
        "> 🗓️ Check premium plans\n\n"
        "5. **/status**\n"
        "> ⟳ Check your login and premium status\n\n"
        "6. **/login**\n"
        "> 🔑 Log into the bot for private channel access\n\n"
        "7. **/logout**\n"
        "> 🚪 Log out from the bot\n\n"
        "8. **/setbot**\n"
        "> 🧸 Add your bot token for file handling\n\n"
        "9. **/rembot**\n"
        "> 🤨 Remove your custom bot token\n"
    ),
    (
        "📝 **Bot Commands Overview (2/2)**:\n\n"
        "10. **/batch**\n"
        "> 🫠 Start a bulk extraction process (After login)\n\n"
        "11. **/single**\n"
        "> 🫠 Extract a single post (After login)\n\n"
        "12. **/cancel** or **/stop**\n"
        "> 🚫 Cancel ongoing login, batch, or settings process\n\n"
        "13. **/settings**\n"
        "> ⚙️ Personalize things like target chat, rename tag, caption, text filters, thumbnail, etc.\n\n"
        "14. **/transfer userID**\n"
        "> 💘 Transfer your premium to another user (Premium only)\n\n"
        "15. **/add userID duration_value duration_unit**\n"
        "> ➕ Add user to premium (Owner only - Use in private chat)\n\n"
        "16. **/rem userID**\n"
        "> ➖ Remove user from premium (Owner only - Use in private chat)\n\n"
        "17. **/dl link**\n"
        "> 💀 Download videos from supported sites (e.g., YouTube, Instagram)\n\n"
        "18. **/adl link**\n"
        "> 👻 Download audio from supported sites\n\n"
        # Commands not found in provided files but mentioned in help: /get, /lock, /stats, /speedtest, /myplan, /session, /pay, /redeem, /gencode, /generate, /keyinfo, /encrypt, /decrypt, /keys
        # Added ones found in other files: /single, /setbot, /rembot, /status, /transfer, /add, /rem, /settings, /dl, /adl
        "Note: Some commands mentioned in the old help might not be available or have changed in this version. Check /set for available commands."
        "\n\n**__Powered by Team SPY__**"
    )
]


async def send_or_edit_help_page(client, message, page_number):
    """Sends or edits the help message with pagination."""
    if page_number < 0 or page_number >= len(help_pages):
        # Should not happen with proper button logic, but as a safeguard
        await edit_message_safely(message, "Invalid help page.")
        return

    # Create navigation buttons
    buttons = []
    if page_number > 0:
        buttons.append(InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page_number}"))
    if page_number < len(help_pages) - 1:
        buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page_number}"))

    keyboard = InlineKeyboardMarkup([buttons])

    # Attempt to delete the user's command message if it's not the initial reply
    if message.id != message.top_message.id: # Check if it's a reply to bot's message or initial command
         await delete_message_safely(message)


    # Send the help message with the current page content and navigation buttons
    # If the message was edited (from a callback query), edit it. Otherwise, send a new one.
    if hasattr(message, 'edit_text'): # Check if it's a Message object from callback
         await edit_message_safely(message, help_pages[page_number], reply_markup=keyboard)
    else: # It's an initial command message
         await message.reply_text(help_pages[page_number], reply_markup=keyboard)


@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    """Handles the /help command."""
    # Check force subscription before showing help
    subscription_status = await subscribe(client, message)
    if subscription_status == 1:
        return # Stop if not subscribed

    # Delete the user's /help command message
    # Handled within send_or_edit_help_page for consistency

    await send_or_edit_help_page(client, message, 0) # Send the first page


@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def on_help_navigation(client, callback_query):
    """Handles pagination button presses for the help message."""
    await callback_query.answer() # Dismiss the loading indicator

    action, current_page_str = callback_query.data.split("_")[1], callback_query.data.split("_")[2]
    current_page_number = int(current_page_str)

    if action == "prev":
        next_page_number = current_page_number - 1
    elif action == "next":
        next_page_number = current_page_number + 1
    else:
        return # Should not happen with the regex filter

    # Use callback_query.message to edit the existing message
    await send_or_edit_help_page(client, callback_query.message, next_page_number)

@app.on_message(filters.command("terms") & filters.private)
async def terms_command(client, message):
    """Handles the /terms command."""
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command. All decisions regarding authorization are made at our discretion and mood.\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/kingofpatal")],
        ]
    )
    await message.reply_text(terms_text, reply_markup=buttons)


@app.on_message(filters.command("plan") & filters.private)
async def plan_command(client, message):
    """Handles the /plan command."""
    plan_text = (
        "> 💰 **Premium Price**:\n\n Starting from $2 or 200 INR accepted via **__Amazon Gift Card__** (terms and conditions apply).\n"
        "📥 **Download Limit**: Users can download up to 100,000 files in a single batch command.\n"
        "🛑 **Batch**: You will get two modes /bulk and /batch.\n" # Note: Code only showed /batch and /single
        "   - Users are advised to wait for the process to automatically cancel before proceeding with any downloads or uploads.\n\n"
        "📜 **Terms and Conditions**: For further details and complete terms and conditions, please send /terms.\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/kingofpatal")],
        ]
    )
    await message.reply_text(plan_text, reply_markup=buttons)


@app.on_callback_query(filters.regex("see_plan"))
async def see_plan_callback(client, callback_query):
    """Handles the 'See Plans' inline button."""
    await callback_query.answer() # Dismiss the loading indicator
    plan_text = (
        "> 💰**Premium Price**\n\n Starting from $2 or 200 INR accepted via **__Amazon Gift Card__** (terms and conditions apply).\n"
        "📥 **Download Limit**: Users can download up to 100,000 files in a single batch command.\n"
        "🛑 **Batch**: You will get two modes /bulk and /batch.\n" # Note: Code only showed /batch and /single
        "   - Users are advised to wait for the process to automatically cancel before proceeding with any downloads or uploads.\n\n"
        "📜 **Terms and Conditions**: For further details and complete terms and conditions, please send /terms or click See Terms👇\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/kingofpatal")],
        ]
    )
    await edit_message_safely(callback_query.message, plan_text, reply_markup=buttons)


@app.on_callback_query(filters.regex("see_terms"))
async def see_terms_callback(client, callback_query):
    """Handles the 'See Terms' inline button."""
    await callback_query.answer() # Dismiss the loading indicator
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command. All decisions regarding authorization are made at our discretion and mood.\n"
    )

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/kingofpatal")],
        ]
    )
    await edit_message_safely(callback_query.message, terms_text, reply_markup=buttons)

# Note: The /start handler seems to be in plugins/premium.py based on the base64 decoding.
# Ensure only one handler for /start is active to avoid conflicts.
# If you intend this file to handle /start, you would add:
# @app.on_message(filters.command("start") & filters.private)
# async def start_handler(client, message):
#    # ... your start logic here, potentially calling subscribe ...
#    pass # Replace pass with actual logic
