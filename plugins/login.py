# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import BadRequest, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, MessageNotModified, RPCError
import logging
import os
from config import API_HASH, API_ID
from shared_client import app as bot # Alias Pyrogram client as bot
# Import UB and UC from shared_client
from shared_client import UB, UC # Import caches from shared_client
from utils.func import save_user_session, get_user_data, remove_user_session, save_user_bot, remove_user_bot
from utils.encrypt import ecs, dcs
from utils.custom_filters import login_in_progress, set_user_step, get_user_step # Import custom filter and helpers

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Added basic config if not already set
logger = logging.getLogger(__name__)
model = "v3saver Team SPY"

STEP_PHONE = 1
STEP_CODE = 2
STEP_PASSWORD = 3
login_cache: Dict[int, Dict[str, Any]] = {} # Type hint for login_cache

# --- Helper function for safe message editing ---
async def edit_message_safely(message: Message, text: str, reply_markup=None):
    """Helper function to edit message and handle errors like MessageNotModified"""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except MessageNotModified:
        pass # Ignore if the message hasn't changed
    except RPCError as e:
        print(f"Error editing message: {e}") # Log other potential errors
    except Exception as e:
        print(f"Unexpected error editing message: {e}")

# Removed import from plugins.batch - UB and UC are now in shared_client

@bot.on_message(filters.command('login') & filters.private & ~login_in_progress)
async def login_command(client: Client, message: Message):
    """Handles the /login command to start the session login process."""
    user_id = message.from_user.id

    # Check if a login process is already in progress for this user
    if get_user_step(user_id):
         await message.reply_text("You are already in a login process. Use /cancel to stop it.")
         return

    set_user_step(user_id, STEP_PHONE) # Set the step to phone number input
    login_cache.pop(user_id, None) # Clear any previous login state for this user

    # Delete the user's /login command message
    try:
        await message.delete()
    except Exception:
        pass # Ignore deletion errors

    status_msg = await message.reply(
        """Please send your **phone number** with country code (e.g., `+12345678900`)
Send /cancel to stop the login process.""" # Added cancel instruction
        )
    login_cache[user_id] = {'status_msg': status_msg}


@bot.on_message(filters.command("setbot") & filters.private)
async def set_bot_token(C: Client, m: Message):
    """Handles setting the user's custom bot token."""
    user_id = m.from_user.id
    args = m.text.split(" ", 1)

    # Stop and remove existing user bot client if it exists
    if user_id in UB:
        try:
            if UB[user_id] and UB[user_id].is_connected: # Check if client exists and is connected
                await UB[user_id].stop()
                print(f"Stopped old bot for user {user_id}")
            del UB[user_id]  # Remove from dictionary
            # Consider removing the session file if it was persisted (in_memory=True reduces this need)
            # try:
            #     session_file = f"user_{user_id}.session"
            #     if os.path.exists(session_file):
            #          os.remove(session_file)
            # except Exception: pass

        except Exception as e:
            print(f"Error stopping old bot for user {user_id}: {e}")
            if user_id in UB: del UB[user_id] # Ensure removal from dictionary


    if len(args) < 2:
        await m.reply_text("⚠️ Please provide a bot token. Usage: `/setbot <token>`", quote=True)
        return

    bot_token = args[1].strip()
    try:
        await save_user_bot(user_id, bot_token)
        await m.reply_text("✅ Bot token saved successfully. It will be used for file handling.", quote=True)
        # Note: The bot client will be started on demand when needed in plugins/batch.py's get_ubot
    except Exception as e:
        print(f"Error saving bot token for user {user_id}: {e}")
        await m.reply_text(f"❌ Failed to save bot token: {e}", quote=True)


@bot.on_message(filters.command("rembot") & filters.private)
async def rem_bot_token(C: Client, m: Message):
    """Handles removing the user's custom bot token."""
    user_id = m.from_user.id

    # Stop and remove existing user bot client if it exists
    if user_id in UB:
        try:
            if UB[user_id] and UB[user_id].is_connected: # Check if client exists and is connected
                await UB[user_id].stop()
                print(f"Stopped and removed old bot for user {user_id}")
            del UB[user_id]  # Remove from dictionary
             # Consider removing the session file if it was persisted
            # try:
            #     session_file = f"user_{user_id}.session"
            #     if os.path.exists(session_file):
            #          os.remove(session_file)
            # except Exception: pass

        except Exception as e:
            print(f"Error stopping old bot for user {user_id}: {e}")
            if user_id in UB: del UB[user_id]  # Ensure removal from dictionary
             # Consider removing the session file if it was persisted
            # try:
            #     session_file = f"user_{user_id}.session"
            #     if os.path.exists(session_file):
            #          os.remove(session_file)
            # except Exception: pass

    try:
        success = await remove_user_bot(user_id)
        if success:
             await m.reply_text("✅ Bot token removed successfully.", quote=True)
        else:
             # Could indicate the token wasn't set in the first place
             await m.reply_text("ℹ️ No bot token found for your account.", quote=True)
    except Exception as e:
        print(f"Error removing bot token for user {user_id}: {e}")
        await m.reply_text(f"❌ Failed to remove bot token: {e}", quote=True)


@bot.on_message(login_in_progress & filters.text & filters.private & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set', 'pay',
    'redeem', 'gencode', 'generate', 'keyinfo', 'encrypt', 'decrypt', 'keys', 'setbot', 'rembot', 'settings', 'plan', 'terms', 'help', 'status', 'transfer', 'add', 'rem', 'dl', 'adl']))
async def handle_login_steps(client: Client, message: Message):
    """Handles user input during the login process."""
    user_id = message.from_user.id
    text = message.text.strip()
    step = get_user_step(user_id)
    status_msg = login_cache.get(user_id, {}).get('status_msg') # Get the initial status message

    # Delete the user's input message
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f'Could not delete message: {e}')

    # Ensure status_msg is available, if not, something went wrong with the initial command
    if not status_msg:
         print(f"Error: Status message not found for user {user_id} in login cache.")
         set_user_step(user_id, None) # Reset state
         login_cache.pop(user_id, None)
         # Send a new message to inform the user
         await message.reply_text("❌ An error occurred with the login process. Please try again with /login.")
         return


    try:
        if step == STEP_PHONE:
            if not re.match(r'^\+\d+$', text): # Basic regex validation for phone number
                await edit_message_safely(status_msg,
                    '❌ Please provide a valid phone number starting with `+` followed by digits.')
                # Stay in this step until valid input
                return # Do not change step yet

            await edit_message_safely(status_msg,
                '🔄 Processing phone number and sending verification code...')
            # Create a temporary client for login process
            temp_client = Client(f'temp_login_{user_id}', api_id=API_ID, api_hash=API_HASH, device_model=model, in_memory=True)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(text)
                login_cache[user_id]['phone'] = text
                login_cache[user_id]['phone_code_hash'] = sent_code.phone_code_hash
                login_cache[user_id]['temp_client'] = temp_client # Store the temporary client instance
                set_user_step(user_id, STEP_CODE) # Move to the next step
                await edit_message_safely(status_msg,
                    """✅ Verification code sent to your Telegram account.

Please enter the code you received (e.g., `1 2 3 4 5` or `12345`):""" # Clarified format
                    )
            except BadRequest as e:
                 await edit_message_safely(status_msg,
                    f"""❌ Error sending code: {str(e)}
Please try again with /login.""" # Inform about specific error
                    )
                 # Clean up temporary client and state
                 try: await temp_client.disconnect() except Exception: pass
                 set_user_step(user_id, None)
                 login_cache.pop(user_id, None)
            except Exception as e:
                 # Catch any other errors during phone number processing
                 print(f"Error during phone number step for user {user_id}: {e}")
                 await edit_message_safely(status_msg,
                    f"""❌ An unexpected error occurred: {str(e)}
Please try again with /login."""
                    )
                 try: await temp_client.disconnect() except Exception: pass
                 set_user_step(user_id, None)
                 login_cache.pop(user_id, None)


        elif step == STEP_CODE:
            code = text.replace(' ', '') # Remove spaces from the code
            if not code.isdigit():
                 await edit_message_safely(status_msg, '❌ Invalid code format. Please enter the digits you received.')
                 return # Stay in this step

            phone = login_cache[user_id].get('phone')
            phone_code_hash = login_cache[user_id].get('phone_code_hash')
            temp_client = login_cache[user_id].get('temp_client')

            if not phone or not phone_code_hash or not temp_client:
                 # State inconsistency, restart the process
                 await edit_message_safely(status_msg, '❌ Login state invalid. Please try again with /login.')
                 # Clean up state
                 set_user_step(user_id, None)
                 login_cache.pop(user_id, None)
                 # Attempt to disconnect temp client if it exists in cache
                 if 'temp_client' in login_cache.get(user_id, {}):
                     try: await login_cache[user_id]['temp_client'].disconnect() except Exception: pass
                 return

            try:
                await edit_message_safely(status_msg, '🔄 Verifying code...')
                await temp_client.sign_in(phone, phone_code_hash, code)

                # If sign-in is successful, export and save the session string
                session_string = await temp_client.export_session_string()
                encrypted_session = ecs(session_string) # Encrypt the session string
                await save_user_session(user_id, encrypted_session) # Save to database

                # Disconnect and clean up the temporary client and cache
                try: await temp_client.disconnect() except Exception: pass
                login_cache.pop(user_id, None) # Remove user's state from login_cache

                await edit_message_safely(status_msg, """✅ Logged in successfully!! Your session is now active.""")
                set_user_step(user_id, None) # Reset the user's step state

            except SessionPasswordNeeded:
                # Two-step verification is required
                set_user_step(user_id, STEP_PASSWORD) # Move to password step
                await edit_message_safely(status_msg,
                    """🔒 Two-step verification is enabled.
Please enter your password:"""
                    )
            except (PhoneCodeInvalid, PhoneCodeExpired) as e:
                # Handle invalid or expired code
                await edit_message_safely(status_msg,
                    f'❌ {str(e)}. Please try again with /login.') # Inform about specific error
                # Clean up temporary client and state
                try: await temp_client.disconnect() except Exception: pass
                login_cache.pop(user_id, None)
                set_user_step(user_id, None)
            except Exception as e:
                 # Catch any other errors during code verification
                 print(f"Error during code step for user {user_id}: {e}")
                 await edit_message_safely(status_msg,
                    f"""❌ An unexpected error occurred: {str(e)}
Please try again with /login."""
                    )
                 try: await temp_client.disconnect() except Exception: pass
                 login_cache.pop(user_id, None)
                 set_user_step(user_id, None)

        elif step == STEP_PASSWORD:
            password = text # Get the password input
            temp_client = login_cache[user_id].get('temp_client')

            if not temp_client:
                 # State inconsistency, restart the process
                 await edit_message_safely(status_msg, '❌ Login state invalid. Please try again with /login.')
                 # Clean up state
                 set_user_step(user_id, None)
                 login_cache.pop(user_id, None)
                 return

            try:
                await edit_message_safely(status_msg, '🔄 Verifying password...')
                await temp_client.check_password(password)

                # If password check is successful, export and save the session string
                session_string = await temp_client.export_session_string()
                encrypted_session = ecs(session_string) # Encrypt the session string
                await save_user_session(user_id, encrypted_session) # Save to database

                # Disconnect and clean up the temporary client and cache
                try: await temp_client.disconnect() except Exception: pass
                login_cache.pop(user_id, None) # Remove user's state from login_cache

                await edit_message_safely(status_msg, """✅ Logged in successfully!! Your session is now active.""")
                set_user_step(user_id, None) # Reset the user's step state

            except BadRequest as e:
                # Handle incorrect password
                await edit_message_safely(status_msg,
                    f"""❌ Incorrect password: {str(e)}
Please try again:""")
                # Stay in password step
                # Do not change state or disconnect temp_client yet, user needs to try again
            except Exception as e:
                 # Catch any other errors during password check
                 print(f"Error during password step for user {user_id}: {e}")
                 await edit_message_safely(status_msg,
                    f"""❌ An unexpected error occurred: {str(e)}
Please try again with /login."""
                    )
                 try: await temp_client.disconnect() except Exception: pass
                 login_cache.pop(user_id, None)
                 set_user_step(user_id, None)

    except Exception as e:
        # Catch any unexpected errors during the entire handle_login_steps execution
        logger.error(f'Unexpected Error in login flow for user {user_id}: {str(e)}', exc_info=True)
        await edit_message_safely(status_msg,
            f"""❌ An unexpected error occurred during the login process: {str(e)[:50]}
Please try again with /login."""
            )
        # Attempt to disconnect temporary client if it exists in cache
        if user_id in login_cache and 'temp_client' in login_cache[user_id]:
            try:
                await login_cache[user_id]['temp_client'].disconnect()
            except Exception:
                pass
        login_cache.pop(user_id, None) # Clean up user's state
        set_user_step(user_id, None) # Reset the user's step state

# Note: The /cancel command handler is already present in plugins/start.py and plugins/batch.py.
# A dedicated /cancel for the login process might be beneficial here to specifically clean up login state.
# Let's add a /cancel handler specifically for the login process state.

@bot.on_message(filters.command('cancel') & filters.private & login_in_progress)
async def cancel_login_command(client: Client, message: Message):
    """Handles /cancel command specifically during the login process."""
    user_id = message.from_user.id
    # Check if the user is in the login process
    if get_user_step(user_id):
        status_msg = login_cache.get(user_id, {}).get('status_msg') # Get the initial status message

        # Attempt to disconnect the temporary client if it exists in cache
        if user_id in login_cache and 'temp_client' in login_cache[user_id]:
            try:
                await login_cache[user_id]['temp_client'].disconnect()
            except Exception:
                pass

        # Clean up login state
        login_cache.pop(user_id, None)
        set_user_step(user_id, None)

        # Inform the user about cancellation
        if status_msg:
            await edit_message_safely(status_msg, '✅ Login process cancelled.')
        else:
            # If status message was not found (shouldn't happen if get_user_step is true, but for safety)
            temp_msg = await message.reply('✅ Login process cancelled.')
            try: await temp_msg.delete(5) except Exception: pass # Delete temp message after 5 seconds

    # Delete the user's /cancel command message
    try:
        await message.delete()
    except Exception:
        pass # Ignore deletion errors

# Note: The /cancel command in plugins/batch.py and plugins/start.py should handle
# cancellation when not in the login_in_progress state.

@bot.on_message(filters.command('logout') & filters.private)
async def logout_command(client: Client, message: Message):
    """Handles the /logout command to terminate Telegram session and remove from DB."""
    user_id = message.from_user.id

    # Delete the user's /logout command message
    try:
        await message.delete()
    except Exception:
        pass # Ignore deletion errors

    status_msg = await message.reply('🔄 Processing logout request...')

    try:
        session_data = await get_user_data(user_id)

        if not session_data or 'session_string' not in session_data:
            await edit_message_safely(status_msg, '❌ No active session found for your account.')
            # Also remove bot token if it exists, as logout might imply wanting a clean slate
            # await remove_user_bot(user_id) # Optional: uncomment to remove bot token on logout
            return

        encss = session_data['session_string']
        try:
            session_string = dcs(encss) # Decrypt the session string
        except Exception as e:
             print(f"Error decrypting session string for user {user_id} during logout: {e}")
             await edit_message_safely(status_msg, '❌ Failed to decrypt session string. Cannot terminate Telegram session.')
             # Still attempt to remove from DB
             await remove_user_session(user_id)
             await edit_message_safely(status_msg, '❌ Failed to decrypt session string. Removed from database.')
             return


        # Create a temporary client using the session string to log out
        temp_client = Client(f'temp_logout_{user_id}', api_id=API_ID, api_hash=API_HASH, session_string=session_string, in_memory=True) # Use in_memory=True
        try:
            await temp_client.connect()
            await edit_message_safely(status_msg, '🔄 Terminating Telegram session...')
            await temp_client.log_out() # Terminate the Telegram session itself
            print(f"Telegram session terminated for user {user_id}")

            await edit_message_safely(status_msg, '✅ Telegram session terminated. Removing data from database...')

        except Exception as e:
            # Error during Telegram session termination
            logger.error(f'Error terminating Telegram session for user {user_id}: {str(e)}', exc_info=True)
            await edit_message_safely(status_msg,
                f"""⚠️ Error terminating Telegram session: {str(e)[:50]}
Still removing data from database..."""
                )
        finally:
            # Ensure the temporary client is disconnected
            try: await temp_client.disconnect() except Exception: pass

        # Remove the session string and bot token from the database
        await remove_user_session(user_id) # Remove session string
        await remove_user_bot(user_id) # Also remove bot token on logout for a clean slate

        # Remove the user's client from the cache if it exists
        if user_id in UC:
             try:
                 if UC[user_id] and UC[user_id].is_connected: await UC[user_id].stop()
             except Exception: pass
             del UC[user_id]
        # Remove user's bot from the cache if it exists
        if user_id in UB:
             try:
                 if UB[user_id] and UB[user_id].is_connected: await UB[user_id].stop()
             except Exception: pass
             del UB[user_id]


        # Attempt to remove any local session files (though in_memory=True reduces this need)
        try:
            user_session_file = f"{user_id}_user_client.session"
            if os.path.exists(user_session_file):
                 os.remove(user_session_file)
        except Exception: pass
        try:
            temp_logout_session_file = f"temp_logout_{user_id}.session"
            if os.path.exists(temp_logout_session_file):
                 os.remove(temp_logout_session_file)
        except Exception: pass


        await edit_message_safely(status_msg, '✅ Logged out successfully!! All associated data removed.')

    except Exception as e:
        # Catch any unexpected errors during the entire logout process
        logger.error(f'Unexpected Error in logout command for user {user_id}: {str(e)}', exc_info=True)
        try:
            # Attempt to remove data from DB and cache as a fallback
            await remove_user_session(user_id)
            await remove_user_bot(user_id)
            if user_id in UC: del UC[user_id]
            if user_id in UB: del UB[user_id]
        except Exception: pass # Ignore errors during fallback cleanup

        await edit_message_safely(status_msg,
            f'❌ An unexpected error occurred during logout: {str(e)[:50]}')
