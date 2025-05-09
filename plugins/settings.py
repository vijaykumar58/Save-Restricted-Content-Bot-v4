# Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

from telethon import events, Button
from telethon.errors import MessageNotModifiedError, RPCError
import re
import os
import asyncio
import string
import random # Used by generate_random_name if kept here
from shared_client import client as gf # Alias Telethon client as gf
from config import OWNER_ID
from utils.func import get_user_data_key, save_user_data, users_collection, remove_user_session # Import remove_user_session

# Define VIDEO_EXTENSIONS again if rename_file stays here and needs it
# Or rely on it being defined in utils.func if rename_file is moved there
VIDEO_EXTENSIONS = {
    'mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm',
    'mpeg', 'mpg', '3gp'
}
SET_PIC = 'settings.jpg' # Appears unused in the provided code snippet
MESS = 'Customize settings for your files...'

active_conversations = {} # {user_id: {'type': 'setting_type', 'message_id': int}}

# --- Helper functions for robustness ---
async def edit_message_safely(event, text: str, buttons=None):
    """Helper function to edit message and handle errors like MessageNotModifiedError"""
    try:
        # Use event.edit_message for editing the message that triggered the callback
        await event.edit_message(text, buttons=buttons)
    except MessageNotModifiedError:
        pass # Ignore if the message hasn't changed
    except RPCError as e:
        print(f"Error editing Telethon message: {e}") # Log other potential errors
    except Exception as e:
        print(f"Unexpected error editing Telethon message: {e}")

async def respond_safely(event, text: str, buttons=None):
    """Helper function to respond to an event and handle errors"""
    try:
        # Use event.respond for sending a new message in response to an event
        return await event.respond(text, buttons=buttons)
    except RPCError as e:
        print(f"Error responding to Telethon event: {e}")
        return None # Indicate failure
    except Exception as e:
        print(f"Unexpected error responding to Telethon event: {e}")
        return None


# --- Command and Callback Handlers ---
@gf.on(events.NewMessage(incoming=True, pattern='/settings'))
async def settings_command(event):
    """Handles the /settings command."""
    user_id = event.sender_id
    # Ensure the command is in a private chat if necessary, although settings are usually per-user.
    # Check if event.is_private if needed
    await send_settings_message(event, user_id) # Pass event object to use respond_safely

async def send_settings_message(event, user_id: int):
    """Sends the settings menu message."""
    buttons = [
        [
            Button.inline('📝 Set Chat ID', b'setchat'),
            Button.inline('🏷️ Set Rename Tag', b'setrename')
        ],
        [
            Button.inline('📋 Set Caption', b'setcaption'),
            Button.inline('🔄 Replace Words', b'setreplacement')
        ],
        [
            Button.inline('🗑️ Remove Words', b'delete'),
            Button.inline('🔄 Reset Settings', b'reset')
        ],
        [
            # Removed '🔑 Session Login' (addsession) for security - use /login command instead
            Button.inline('🚪 Logout Session', b'logout_session') # Renamed for clarity
        ],
        [
            Button.inline('🖼️ Set Thumbnail', b'setthumb'),
            Button.inline('❌ Remove Thumbnail', b'remthumb')
        ],
        [
            Button.url('🆘 Report Errors', 'https://t.me/team_spy_pro')
        ]
    ]
    # Use respond_safely to send the initial settings message
    await respond_safely(event, MESS, buttons=buttons)


@gf.on(events.CallbackQuery)
async def callback_query_handler(event):
    """Handles callback queries from inline buttons."""
    user_id = event.sender_id
    data = event.data

    callback_actions = {
        b'setchat': {
            'type': 'setchat',
            'prompt': """Send me the ID of that chat (with -100 prefix):

👉 **Note:** if you are using custom bot then your bot should be admin that chat if not then this bot should be admin.
👉 If you want to upload in topic group and in specific topic then pass chat id as **-100CHANNELID/TOPIC_ID** for example: **-1004783898/12**"""
        },
        b'setrename': {
            'type': 'setrename',
            'prompt': 'Send me the rename tag:'
        },
        b'setcaption': {
            'type': 'setcaption',
            'prompt': 'Send me the caption:'
        },
        b'setreplacement': {
            'type': 'setreplacement',
            'prompt': "Send me the replacement words in the format: 'WORD(s)' 'REPLACEWORD'"
        },
        # Removed b'addsession'
        b'delete': {
            'type': 'deleteword',
            'prompt': 'Send words separated by space to delete them from caption/filename...'
        },
        b'setthumb': {
            'type': 'setthumb',
            'prompt': 'Please send the photo you want to set as the thumbnail.'
        }
    }

    if data in callback_actions:
        action = callback_actions[data]
        # Dismiss the loading indicator on the button
        await event.answer("Enter the required information.")
        await start_conversation(event, user_id, action['type'], action['prompt'])

    elif data == b'logout_session': # Updated callback data
        await event.answer("Logging out session...") # Dismiss loading indicator
        # Use the remove_user_session function from utils.func
        success = await remove_user_session(user_id)
        if success:
            await edit_message_safely(event, '✅ Logged out and deleted session successfully. Use /login for full Telegram session termination.')
            # Note: Full Telegram session termination is handled by the /logout command in plugins/login.py
            # This callback just removes the session string from the DB.
        else:
            await edit_message_safely(event, '❌ Failed to remove session.')

    elif data == b'reset':
        await event.answer("Resetting settings...") # Dismiss loading indicator
        try:
            # Unset all relevant fields in the user's database entry
            result = await users_collection.update_one(
                {'user_id': user_id},
                {'$unset': {
                    'delete_words': '',
                    'replacement_words': '',
                    'rename_tag': '',
                    'caption': '',
                    'chat_id': '',
                    # Do NOT unset session_string here, handle separately via logout
                    # 'session_string': ''
                }}
            )

            # Remove the user's thumbnail file
            thumbnail_path = f'{user_id}.jpg'
            if os.path.exists(thumbnail_path):
                try:
                    os.remove(thumbnail_path)
                except Exception as e:
                    print(f"Error removing thumbnail file during reset for user {user_id}: {e}")


            if result.modified_count > 0 or os.path.exists(thumbnail_path): # Check if db was modified or thumbnail existed
                 await edit_message_safely(event, '✅ All settings reset successfully. Use /logout for full session termination.')
            else:
                 await edit_message_safely(event, 'ℹ️ No settings found to reset.')

        except Exception as e:
            print(f"Error resetting settings for user {user_id}: {e}")
            await edit_message_safely(event, f'❌ Error resetting settings: {e}')

    elif data == b'remthumb':
        await event.answer("Removing thumbnail...") # Dismiss loading indicator
        thumbnail_path = f'{user_id}.jpg'
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
                await edit_message_safely(event, '✅ Thumbnail removed successfully!')
            except Exception as e:
                print(f"Error removing thumbnail file for user {user_id}: {e}")
                await edit_message_safely(event, f'❌ Error removing thumbnail: {e}')
        else:
            await edit_message_safely(event, 'ℹ️ No thumbnail found to remove.')


async def start_conversation(event, user_id: int, conv_type: str, prompt_message: str):
    """Starts a conversation sequence for a setting."""
    # If user has an active conversation, inform them and cancel the old one (implicitly by overwriting)
    if user_id in active_conversations:
         await respond_safely(event, 'Previous settings operation cancelled. Starting new one.') # Use respond_safely
         # Optional: could explicitly remove from active_conversations here before adding new one

    # Send the prompt message to the user
    msg = await respond_safely(event, f'{prompt_message}\n\n(Send /cancel to cancel this operation)') # Use respond_safely
    if msg: # Ensure message was sent successfully
        active_conversations[user_id] = {'type': conv_type, 'message_id': msg.id}
    else:
        print(f"Failed to start conversation for user {user_id}, type {conv_type}")


@gf.on(events.NewMessage(pattern='/cancel'))
async def cancel_conversation(event):
    """Handles the /cancel command to cancel a settings conversation."""
    user_id = event.sender_id
    if user_id in active_conversations:
        del active_conversations[user_id]
        await respond_safely(event, '✅ Settings operation cancelled.') # Use respond_safely
    else:
        # If no active conversation, maybe check for batch/login cancellation?
        # This handler specifically cancels settings conversations.
        # The batch/login plugins have their own /cancel handlers.
        await respond_safely(event, 'ℹ️ No active settings operation to cancel.') # Use respond_safely


@gf.on(events.NewMessage(incoming=True))
async def handle_conversation_input(event):
    """Handles user text/media input during active settings conversations."""
    user_id = event.sender_id

    # Ignore if no active conversation or if the message is a command
    if user_id not in active_conversations or event.message.text and event.message.text.startswith('/'):
        return

    conv_type = active_conversations[user_id]['type']

    # Define handlers for different conversation types
    handlers = {
        'setchat': handle_setchat,
        'setrename': handle_setrename,
        'setcaption': handle_setcaption,
        'setreplacement': handle_setreplacement,
        # Removed 'addsession' handler
        'deleteword': handle_deleteword,
        'setthumb': handle_setthumb # setthumb needs to handle media
    }

    # If there's a handler for the current conversation type
    if conv_type in handlers:
        try:
            # Call the appropriate handler function
            await handlers[conv_type](event, user_id)
        except Exception as e:
            print(f"Error handling settings input for user {user_id}, type {conv_type}: {e}")
            await respond_safely(event, f"❌ An error occurred while processing your input: {e}") # Inform user about the error

    # Remove the user from active conversations after handling input
    # This assumes a single message is expected for each setting.
    # If a setting requires multiple inputs, the handler needs to manage the state within active_conversations itself.
    # Based on current handlers, a single input message seems expected.
    if user_id in active_conversations:
        del active_conversations[user_id]


# --- Specific Setting Handlers ---
async def handle_setchat(event, user_id: int):
    """Handles setting the target chat ID."""
    chat_id_input = event.text.strip()
    # Basic validation for chat_id format
    if not re.match(r'^-?\d+$|^-100\d+/\d+$', chat_id_input):
         await respond_safely(event, "❌ Invalid chat ID format. Please provide a numeric ID (e.g., -100123456789) or -100CHANNELID/TOPIC_ID.")
         # Keep the conversation active? Or cancel? Let's cancel for simplicity like other handlers seem to imply.
         # active_conversations.pop(user_id, None) # Already handled by handle_conversation_input
         return

    try:
        await save_user_data(user_id, 'chat_id', chat_id_input)
        await respond_safely(event, f'✅ Chat ID set successfully to `{chat_id_input}`!')
    except Exception as e:
        print(f"Error saving chat ID for user {user_id}: {e}")
        await respond_safely(event, f'❌ Error setting chat ID: {e}')

async def handle_setrename(event, user_id: int):
    """Handles setting the rename tag."""
    rename_tag = event.text.strip()
    try:
        await save_user_data(user_id, 'rename_tag', rename_tag)
        await respond_safely(event, f'✅ Rename tag set to: `{rename_tag}`')
    except Exception as e:
        print(f"Error saving rename tag for user {user_id}: {e}")
        await respond_safely(event, f'❌ Error setting rename tag: {e}')

async def handle_setcaption(event, user_id: int):
    """Handles setting the custom caption."""
    caption = event.text # Get the raw text of the message
    try:
        await save_user_data(user_id, 'caption', caption)
        await respond_safely(event, f'✅ Caption set successfully!')
    except Exception as e:
        print(f"Error saving caption for user {user_id}: {e}")
        await respond_safely(event, f'❌ Error setting caption: {e}')

async def handle_setreplacement(event, user_id: int):
    """Handles setting word replacement rules."""
    match = re.match(r"'(.*?)'\s+'(.*?)'", event.text.strip()) # Use non-greedy match and strip
    if not match:
        await respond_safely(event, "❌ Invalid format. Usage: 'WORD(s)' 'REPLACEWORD'")
        # active_conversations.pop(user_id, None) # Already handled
        return

    word, replace_word = match.groups()
    # Ensure words and replacements are not empty after stripping
    if not word:
        await respond_safely(event, "❌ Word to replace cannot be empty.")
        return
    # replace_word can be empty to effectively delete the word

    try:
        # Check if the word to replace is in the delete list
        delete_words = await get_user_data_key(user_id, 'delete_words', [])
        if word in delete_words:
             await respond_safely(event, f"❌ The word '{word}' is currently in your delete list. Remove it from the delete list first if you want to use replacement.")
             return

        replacements = await get_user_data_key(user_id, 'replacement_words', {})
        replacements[word] = replace_word
        await save_user_data(user_id, 'replacement_words', replacements)
        await respond_safely(event, f"✅ Replacement saved: '{word}' will be replaced with '{replace_word}'")

    except Exception as e:
        print(f"Error saving replacement words for user {user_id}: {e}")
        await respond_safely(event, f'❌ Error saving replacement: {e}')

# Removed async def handle_addsession(event, user_id):

async def handle_deleteword(event, user_id: int):
    """Handles adding words to the delete list."""
    words_to_delete = event.message.text.split()
    if not words_to_delete:
         await respond_safely(event, "❌ Please provide words to delete.")
         return

    try:
        delete_words = await get_user_data_key(user_id, 'delete_words', [])
        # Add new words and ensure uniqueness
        delete_words = list(set(delete_words + words_to_delete))
        await save_user_data(user_id, 'delete_words', delete_words)
        await respond_safely(event, f"✅ Words added to delete list: {', '.join(words_to_delete)}")

    except Exception as e:
        print(f"Error saving delete words for user {user_id}: {e}")
        await respond_safely(event, f'❌ Error saving words to delete list: {e}')


async def handle_setthumb(event, user_id: int):
    """Handles setting the custom thumbnail."""
    if event.photo:
        try:
            # Download the photo
            temp_path = await event.download_media()
            thumb_path = f'{user_id}.jpg'

            # Remove old thumbnail if it exists
            if os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception as e:
                    print(f"Error removing old thumbnail {thumb_path}: {e}")
                    # Continue saving the new one even if old one fails to remove

            # Rename the downloaded photo to the standard thumbnail filename
            os.rename(temp_path, thumb_path)
            await respond_safely(event, '✅ Thumbnail saved successfully!')

        except Exception as e:
            print(f"Error setting thumbnail for user {user_id}: {e}")
            await respond_safely(event, f'❌ Error saving thumbnail: {e}')
            # Clean up the downloaded temp file if renaming failed
            if 'temp_path' in locals() and os.path.exists(temp_path):
                 try:
                      os.remove(temp_path)
                 except Exception:
                      pass # Ignore errors during temp file cleanup
    else:
        await respond_safely(event, '❌ Please send a photo to set as the thumbnail. Operation cancelled.')
        # active_conversations.pop(user_id, None) # Already handled


# --- File Renaming Utility (Kept here as it's imported by batch.py from settings.py) ---
# CONSIDER MOVING THIS TO utils/func.py for better code organization
def generate_random_name(length=7):
    """Generates a random string for use in filenames."""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


async def rename_file(file: str, sender: int, edit_message_event=None):
    """
    Applies user's renaming rules to a downloaded file.
    Assumes file is the path to the downloaded file.
    edit_message_event is an optional Telethon event/message to edit for progress/status.
    """
    try:
        delete_words = await get_user_data_key(sender, 'delete_words', [])
        custom_rename_tag = await get_user_data_key(sender, 'rename_tag', '')
        replacements = await get_user_data_key(sender, 'replacement_words', {})

        original_filename = os.path.basename(file)
        name_without_ext, file_extension = os.path.splitext(original_filename)

        # Remove leading/trailing whitespace after splitext
        name_without_ext = name_without_ext.strip()
        file_extension = file_extension.lstrip('.').lower() # Remove dot and lowercase extension

        # Apply word deletions
        processed_name = name_without_ext
        for word in delete_words:
            processed_name = processed_name.replace(word, '') # Simple string replacement

        # Apply word replacements
        for word, replace_word in replacements.items():
            processed_name = processed_name.replace(word, replace_word) # Simple string replacement

        # Add custom rename tag if it exists
        if custom_rename_tag:
             # Add space before tag if the processed name is not empty
             if processed_name:
                 processed_name = f"{processed_name} {custom_rename_tag}"
             else:
                 processed_name = custom_rename_tag

        # Sanitize the resulting filename to remove invalid characters
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', processed_name)
        # Ensure filename is not empty after sanitization and processing
        if not sanitized_name:
            sanitized_name = generate_random_name() # Generate a random name if processing results in empty string

        # Ensure extension is present, default to mp4 if unknown or problematic (original logic)
        # A more robust approach would be to preserve the original extension unless explicitly changing type.
        final_extension = file_extension if file_extension in VIDEO_EXTENSIONS else 'mp4' if file_extension else 'mp4' # Simplified logic
        # Or maybe better: use the original extension if available, otherwise default?
        # final_extension = file_extension if file_extension else 'bin' # More general fallback

        new_file_name = f'{sanitized_name}.{final_extension}'
        new_file_path = os.path.join(os.path.dirname(file), new_file_name)

        # Avoid overwriting if file with new name already exists (unlikely but safe)
        count = 1
        base_new_name, base_new_ext = os.path.splitext(new_file_path)
        while os.path.exists(new_file_path):
             new_file_path = f"{base_new_name}_{count}{base_new_ext}"
             count += 1


        os.rename(file, new_file_path)
        print(f"Renamed '{original_filename}' to '{os.path.basename(new_file_path)}'")

        # Optional: Edit the progress message to show the new filename
        # This requires passing the event/message object from the calling function (e.g., batch.py)
        # The original function signature takes `edit`, assuming it's a message object.
        # Let's assume edit_message_event is a message object we can edit.
        # This might require changes in how rename_file is called in batch.py
        # For now, just print the rename status.

        return new_file_path # Return the new file path

    except Exception as e:
        print(f"Rename error for file '{file}': {e}")
        # If renaming fails, return the original file path so processing can continue
        return file


# Note: The /start handler from plugins.premium.py seems to handle the base64 decoding for welcome message parts.
# This file focuses specifically on the /settings command and its related interactions.
