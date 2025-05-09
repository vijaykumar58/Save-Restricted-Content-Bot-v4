 # Copyright (c) 2025 devgagan : https://github.com/devgaganin.
# Licensed under the GNU General Public License v3.0.
# See LICENSE file in the repository root for full license text.

import os, re, time, asyncio
import json
from typing import Dict, Any, Optional
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserNotParticipant, MessageNotModified, RPCError
from config import API_ID, API_HASH, LOG_GROUP, STRING, FORCE_SUB, FREEMIUM_LIMIT, PREMIUM_LIMIT
from utils.func import get_user_data, screenshot, thumbnail, get_video_metadata
from utils.func import get_user_data_key, process_text_with_rules, is_premium_user, E, get_display_name
from shared_client import app as X # Alias Pyrogram client as X
# Y is only needed if STRING is configured, fetched dynamically or use the global
# from shared_client import userbot as Y # This might cause issues if STRING is not set

# Attempt to get userbot Y if STRING is configured, otherwise Y remains None
Y = None
if STRING:
    try:
        from shared_client import userbot as Y
    except ImportError:
        # Handle case where shared_client might not have userbot if STRING is None
        pass

# Global state dictionaries (use with caution in high concurrency, but common for bots)
Z: Dict[int, Dict[str, Any]] = {} # State for command sequence (batch/single)
P: Dict[int, int] = {} # Progress tracking for upload/download messages {message_id: progress_step}
UB: Dict[int, Client] = {} # Cache for user-specific bot clients {user_id: client_instance}
UC: Dict[int, Client] = {} # Cache for user-specific user clients {user_id: client_instance}
emp: Dict[Any, bool] = {} # Cache for empty chat status {chat_id: bool}

ACTIVE_USERS: Dict[str, Dict[str, Any]] = {} # Track active batch/single tasks {user_id: task_info}
ACTIVE_USERS_FILE = "active_users.json"

# --- Helper functions for robustness ---
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

async def delete_message_safely(message: Message):
    """Helper function to delete message and handle errors"""
    try:
        await message.delete()
    except RPCError as e:
        # Ignore errors if message is already deleted or inaccessible
        print(f"Error deleting message: {e}") # Log potential errors
    except Exception as e:
        print(f"Unexpected error deleting message: {e}")

# --- Active Users / Batch State Management ---
def load_active_users():
    """Loads active users data from a JSON file."""
    try:
        if os.path.exists(ACTIVE_USERS_FILE):
            with open(ACTIVE_USERS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading active users: {e}")
        return {} # Return empty dict on error

async def save_active_users_to_file():
    """Saves active users data to a JSON file."""
    try:
        # Use asyncio.to_thread for file operations to not block event loop
        await asyncio.to_thread(
            json.dump,
            ACTIVE_USERS,
            open(ACTIVE_USERS_FILE, 'w'),
            indent=4 # Pretty print for readability
        )
    except Exception as e:
        print(f"Error saving active users: {e}")

async def add_active_batch(user_id: int, batch_info: Dict[str, Any]):
    """Adds or updates an active batch task for a user."""
    ACTIVE_USERS[str(user_id)] = batch_info
    await save_active_users_to_file()

def is_user_active(user_id: int) -> bool:
    """Checks if a user has an active batch/single task."""
    return str(user_id) in ACTIVE_USERS

async def update_batch_progress(user_id: int, current: int, success: int):
    """Updates the progress of an active batch task."""
    user_str = str(user_id)
    if user_str in ACTIVE_USERS:
        ACTIVE_USERS[user_str]["current"] = current
        ACTIVE_USERS[user_str]["success"] = success
        # Only save to file periodically or on significant changes to reduce I/O
        # For simplicity here, saving on every update, but can be optimized
        await save_active_users_to_file()

async def request_batch_cancel(user_id: int):
    """Requests cancellation for an active batch task."""
    user_str = str(user_id)
    if user_str in ACTIVE_USERS:
        ACTIVE_USERS[user_str]["cancel_requested"] = True
        await save_active_users_to_file()
        return True
    return False

def should_cancel(user_id: int) -> bool:
    """Checks if cancellation has been requested for a user's task."""
    user_str = str(user_id)
    return user_str in ACTIVE_USERS and ACTIVE_USERS[user_str].get("cancel_requested", False)

async def remove_active_batch(user_id: int):
    """Removes an active batch task for a user."""
    user_str = str(user_id)
    if user_str in ACTIVE_USERS:
        del ACTIVE_USERS[user_str]
        await save_active_users_to_file()

def get_batch_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Gets information about an active batch task."""
    return ACTIVE_USERS.get(str(user_id))

# Load active users on startup
ACTIVE_USERS = load_active_users()

# --- Telegram Client and Message Fetching ---
async def upd_dlg(c: Client):
    """Updates dialogs for a Pyrogram client."""
    try:
        # Iterating through dialogs helps ensure the client has cached chat information
        async for _ in c.get_dialogs(limit=100):
            pass
        return True
    except Exception as e:
        print(f'Failed to update dialogs for client {c.me.id if c.me else "unknown"}: {e}')
        return False

async def get_msg(bot_client: Client, user_client: Optional[Client], chat_identifier: Any, message_id: int, link_type: str) -> Optional[Message]:
    """
    Fetches a message using either the bot client or a user client.
    chat_identifier can be username, chat_id, or peer.
    """
    try:
        # Prioritize user client if available and link is private or requires user context
        if user_client and link_type == 'private':
             try:
                 # Ensure user client dialogs are updated for private chats
                 await upd_dlg(user_client)
                 # Pyrogram's get_messages is robust with various chat identifiers
                 return await user_client.get_messages(chat_identifier, message_id)
             except Exception as e:
                 print(f"Attempt with user client failed for {chat_identifier}/{message_id}: {e}")
                 # Fallback or indicate failure? For private, user client is usually necessary.
                 # Let's log and return None if user client is essential for this link type.
                 # Or could try with bot client as a last resort, but it might fail for private chats.
                 # Sticking to the original logic's intent, if user_client fails for private, return None.
                 return None # User client failed for private link
        elif link_type == 'public':
            try:
                 # Use bot client for public links
                 xm = await bot_client.get_messages(chat_identifier, message_id)
                 emp[chat_identifier] = getattr(xm, "empty", False) # Cache empty status
                 if emp[chat_identifier]:
                     # If message is empty (maybe due to joining), try joining and refetching with user client if possible
                     if user_client:
                         try: await user_client.join_chat(chat_identifier) # Join with user client
                         except Exception: pass # Ignore join errors
                         # Try fetching with user client after joining
                         xm = await user_client.get_messages((await user_client.get_chat(chat_identifier)).id, message_id)
                     else:
                          # If no user client, maybe the bot client can join and fetch? (Less likely for public join needed)
                          # The original code attempts to refetch with user client implicitly if emp is True.
                          # Let's stick closer to that: if empty and user_client exists, try user_client.
                          # If still empty or no user_client, the original xm (likely None or Empty) is returned.
                          pass # No user client to attempt re-fetch after empty check
                 return xm
            except Exception as e:
                 print(f'Error fetching public message {chat_identifier}/{message_id} with bot client: {e}')
                 # If bot client fails for public, could a user client work? Possible, but less common need.
                 # Original code doesn't have a clear fallback here. Return None on error.
                 return None
        else:
            # Default case or unexpected link type, try with bot client
            try:
                return await bot_client.get_messages(chat_identifier, message_id)
            except Exception as e:
                print(f"Error fetching message {chat_identifier}/{message_id} with fallback bot client: {e}")
                return None

    except Exception as e:
        print(f'General Error in get_msg for {chat_identifier}/{message_id}: {e}')
        return None

async def get_ubot(uid: int) -> Optional[Client]:
    """Retrieves or creates a user's dedicated bot client."""
    bt = await get_user_data_key(uid, "bot_token", None)
    if not bt:
        return None
    if uid in UB and UB[uid].is_connected: # Check if cached client is connected
        return UB.get(uid)
    try:
        # Ensure unique session name for each user bot
        bot = Client(f"user_bot_{uid}", bot_token=bt, api_id=API_ID, api_hash=API_HASH, in_memory=True)
        await bot.start()
        UB[uid] = bot
        return bot
    except Exception as e:
        print(f"Error starting bot for user {uid}: {e}")
        # Clean up cache if client failed to start
        if uid in UB: del UB[uid]
        return None

async def get_uclient(uid: int) -> Optional[Client]:
    """Retrieves or creates a user's dedicated user client."""
    # Check if cached client is connected
    if uid in UC and UC[uid].is_connected:
        return UC.get(uid)

    ud = await get_user_data(uid)
    if not ud:
        # If no user data, try returning the global userbot if available and connected
        return Y if Y and Y.is_connected else None

    encss = ud.get('session_string')
    if encss:
        try:
            ss = dcs(encss) # Decrypt the session string
            # Ensure unique session name for each user client
            gg = Client(f'{uid}_user_client', api_id=API_ID, api_hash=API_HASH, device_model="v3saver", session_string=ss, in_memory=True)
            await gg.start()
            await upd_dlg(gg) # Update dialogs for the new client
            UC[uid] = gg
            return gg
        except Exception as e:
            print(f'User client error for {uid}: {e}')
            # Clean up cache if client failed to start
            if uid in UC: del UC[uid]
            # Fallback: try returning the user's bot client if available, or the global userbot
            ubot = UB.get(uid)
            if ubot and ubot.is_connected:
                return ubot
            return Y if Y and Y.is_connected else None
    else:
         # No session string, try returning the user's bot client if available, or the global userbot
        ubot = UB.get(uid)
        if ubot and ubot.is_connected:
            return ubot
        return Y if Y and Y.is_connected else None


# --- Progress Reporting ---
# The prog function is used for file upload/download progress.
# Needs to be robust against message modification errors.
async def prog(current: int, total: int, client: Client, chat_id: int, message_id: int, start_time: float):
    """Updates the progress message during file transfer."""
    global P
    p = (current / total) * 100
    # Update interval logic (original logic)
    interval = 10 if total >= 100 * 1024 * 1024 else 20 if total >= 50 * 1024 * 1024 else 30 if total >= 10 * 1024 * 1024 else 50
    step = int(p // interval) * interval

    # Only edit if a significant step is reached or at the beginning/end
    if message_id not in P or P[message_id] != step or p >= 99: # Use 99 to ensure final update
        P[message_id] = step
        c_mb = current / (1024 * 1024)
        t_mb = total / (1024 * 1024)
        bar = '🟢' * int(p / 10) + '🔴' * (10 - int(p / 10))
        # Avoid division by zero
        speed_bytes_sec = (current / (time.time() - start_time)) if (time.time() - start_time) > 0 else 0
        speed_mb_sec = speed_bytes_sec / (1024 * 1024)
        # Avoid division by zero for ETA
        eta = time.strftime('%M:%S', time.gmtime((total - current) / speed_bytes_sec)) if speed_bytes_sec > 0 else 'Calculating...'

        progress_text = (
            f"__**Pyro Handler...**__\n\n"
            f"{bar}\n\n"
            f"⚡**__Completed__**: {c_mb:.2f} MB / {t_mb:.2f} MB\n"
            f"📊 **__Done__**: {p:.2f}%\n"
            f"🚀 **__Speed__**: {speed_mb_sec:.2f} MB/s\n"
            f"⏳ **__ETA__**: {eta}\n\n"
            f"**__Powered by Team SPY__**"
        )

        # Use the safe edit function
        try:
            await client.edit_message_text(chat_id, message_id, progress_text)
        except MessageNotModified:
            pass # Ignore if text is the same
        except Exception as e:
            print(f"Error updating progress message {message_id}: {e}")

        if p >= 99: # Clean up progress tracker after completion
            P.pop(message_id, None)

# --- Message Sending ---
async def send_direct(c: Client, m: Message, target_chat_id: int, caption_text: Optional[str] = None, reply_to_message_id: Optional[int] = None) -> bool:
    """Sends a message directly using file_id if available."""
    try:
        if m.video:
            await c.send_video(target_chat_id, m.video.file_id, caption=caption_text, duration=m.video.duration, width=m.video.width, height=m.video.height, reply_to_message_id=reply_to_message_id)
        elif m.video_note:
            await c.send_video_note(target_chat_id, m.video_note.file_id, reply_to_message_id=reply_to_message_id)
        elif m.voice:
            await c.send_voice(target_chat_id, m.voice.file_id, reply_to_message_id=reply_to_message_id)
        elif m.sticker:
             # Stickers might have limitations on direct forwarding/sending by ID
             # Attempting to send by file_id might not work like other media
             # Fallback to copy or download/upload might be needed if this fails
             # For now, keeping the original logic but noting potential issue
            await c.send_sticker(target_chat_id, m.sticker.file_id, reply_to_message_id=reply_to_message_id)
        elif m.audio:
            await c.send_audio(target_chat_id, m.audio.file_id, caption=caption_text, duration=m.audio.duration, performer=m.audio.performer, title=m.audio.title, reply_to_message_id=reply_to_message_id)
        elif m.photo:
            # Photos can have multiple sizes, using the largest one
            photo_id = m.photo.file_id if hasattr(m.photo, 'file_id') else m.photo.sizes[-1].file_id if m.photo.sizes else None
            if photo_id:
                 await c.send_photo(target_chat_id, photo_id, caption=caption_text, reply_to_message_id=reply_to_message_id)
            else:
                 print(f"Could not get file_id for photo in message {m.id}")
                 return False
        elif m.document:
            await c.send_document(target_chat_id, m.document.file_id, caption=caption_text, file_name=m.document.file_name, reply_to_message_id=reply_to_message_id)
        elif m.text: # Handle text messages explicitly if needed for direct send (though process_msg handles text too)
             await c.send_message(target_chat_id, m.text.markdown, reply_to_message_id=reply_to_message_id)
        else:
            return False # No media or recognized content to send directly
        return True
    except Exception as e:
        print(f'Direct send error for message {m.id}: {e}')
        return False

# --- Message Processing (Download, Rename, Upload) ---
async def process_msg(bot_client: Client, user_client: Optional[Client], message: Message, destination_chat_id: str, link_type: str, user_id: int, source_chat_identifier: Any) -> str:
    """Processes a single message: downloads, renames, and uploads."""
    try:
        # Determine the actual target chat ID and reply message ID from user settings
        cfg_chat = await get_user_data_key(user_id, 'chat_id', None)
        target_chat_id = int(destination_chat_id) # Default to the user's chat

        reply_to_message_id = None
        if cfg_chat:
            try:
                if '/' in cfg_chat:
                    parts = cfg_chat.split('/', 1)
                    target_chat_id = int(parts[0])
                    reply_to_message_id = int(parts[1]) if len(parts) > 1 else None
                else:
                    target_chat_id = int(cfg_chat)
            except ValueError:
                # If configured chat_id is invalid, use default
                print(f"Invalid configured chat_id for user {user_id}: {cfg_chat}. Using default.")
                target_chat_id = int(destination_chat_id)
                reply_to_message_id = None # Ensure no invalid reply ID is used

        # --- Process Media Messages ---
        if message.media:
            # Get original text and apply user's text processing rules
            orig_text = message.caption.markdown if message.caption else ''
            proc_text = await process_text_with_rules(user_id, orig_text)
            user_cap = await get_user_data_key(user_id, 'caption', '')
            # Combine processed original text and user-defined caption
            final_caption = f'{proc_text}\n\n{user_cap}' if proc_text and user_cap else user_cap if user_cap else proc_text

            # Try sending directly using file_id if possible (e.g., public channels, not restricted)
            # Note: Direct send might not work for restricted content even from public channels sometimes
            if link_type == 'public' and not emp.get(source_chat_identifier, False):
                 # Check if message is restricted - direct send usually fails for restricted
                 if not getattr(message, 'web_page', None) and not message.empty and (message.text or message.caption): # Basic check for non-restricted-looking messages
                      if await send_direct(bot_client, message, target_chat_id, final_caption, reply_to_message_id):
                           return 'Sent directly.'
                 # If direct send fails or message looks restricted, proceed to download/upload

            # If direct send was not attempted or failed, proceed with download/upload
            start_time = time.time()
            # Send initial downloading message in the user's chat
            download_progress_msg = await bot_client.send_message(target_chat_id, 'Downloading...')

            # Download the media using the user client (preferred for restricted content)
            # Fallback to bot client if user client is not available or fails
            client_to_use = user_client if user_client else bot_client
            if not client_to_use:
                 await edit_message_safely(download_progress_msg, 'Error: No client available for download.')
                 return 'Failed.'

            try:
                 # Download the file
                 downloaded_file = await client_to_use.download_media(
                     message,
                     progress=prog, # Pass the progress callback
                     progress_args=(bot_client, target_chat_id, download_progress_msg.id, start_time)
                 )
            except Exception as e:
                 await edit_message_safely(download_progress_msg, f'Download failed: {str(e)[:50]}')
                 print(f"Download failed for message {message.id}: {e}")
                 return 'Failed.'


            if not downloaded_file or not os.path.exists(downloaded_file):
                await edit_message_safely(download_progress_msg, 'Download failed or file not found.')
                return 'Failed.'

            await edit_message_safely(download_progress_msg, 'Renaming...')
            # Apply renaming and text filtering rules to the filename
            # rename_file function is imported from plugins.settings
            try:
                 renamed_file = await rename_file(downloaded_file, user_id, download_progress_msg) # Pass message for potential edits in rename_file
                 if not renamed_file or not os.path.exists(renamed_file):
                      print(f"Renaming failed for {downloaded_file}")
                      renamed_file = downloaded_file # Use original if renaming fails
            except Exception as e:
                 print(f"Error during renaming {downloaded_file}: {e}")
                 renamed_file = downloaded_file # Use original if renaming fails

            file_size = os.path.getsize(renamed_file)
            file_size_gb = file_size / (1024 * 1024 * 1024)

            # --- Handle Large Files (over 2GB) ---
            # Original logic uploads large files to LOG_GROUP using the global userbot (Y), then copies to user.
            # This bypasses user-specific bot/client for large file uploads. Confirm if this is desired.
            # The global userbot (Y) might be the only client capable of uploading >2GB.
            if file_size_gb > 2 and Y and Y.is_connected:
                await edit_message_safely(download_progress_msg, 'File is larger than 2GB. Using alternative upload method...')
                # Ensure global userbot dialogs are updated
                await upd_dlg(Y)

                # Get video metadata and screenshot for the large file
                mtd = await get_video_metadata(renamed_file)
                duration, height, width = mtd.get('duration', 0), mtd.get('height', 1), mtd.get('width', 1)
                thumb_path = await screenshot(renamed_file, duration, user_id) if duration > 0 else None

                sent_message_in_log = None
                try:
                    # Upload the large file to the log group using the global userbot
                    # Use the same progress callback logic, adapting arguments
                    log_upload_start_time = time.time()
                    sent_message_in_log = await Y.send_document(
                         LOG_GROUP,
                         renamed_file,
                         thumb=thumb_path,
                         caption=final_caption,
                         # reply_to_message_id=... if needed for log group threading
                         progress=prog,
                         progress_args=(Y, LOG_GROUP, download_progress_msg.id, log_upload_start_time) # Pass log group details for progress
                    )
                    print(f"Uploaded large file to log group {LOG_GROUP}, message ID: {sent_message_in_log.id}")
                except Exception as e:
                     print(f"Error uploading large file to log group: {e}")
                     await edit_message_safely(download_progress_msg, f'Large file upload to log group failed: {str(e)[:50]}')

                # If upload to log group was successful, copy it to the user's chat
                if sent_message_in_log:
                    try:
                        await edit_message_safely(download_progress_msg, 'Copying large file...')
                        await bot_client.copy_message(
                            target_chat_id,
                            LOG_GROUP,
                            sent_message_in_log.id,
                            reply_to_message_id=reply_to_message_id
                        )
                        await delete_message_safely(download_progress_msg) # Delete the download progress message
                        print(f"Copied message {sent_message_in_log.id} from log group to {target_chat_id}")
                        return 'Done (Large file).'
                    except Exception as e:
                        print(f"Error copying large file from log group: {e}")
                        await edit_message_safely(download_progress_msg, f'Copying large file failed: {str(e)[:50]}')
                else:
                    # Upload to log group failed
                     if os.path.exists(renamed_file): os.remove(renamed_file)
                     if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                     await delete_message_safely(download_progress_msg)
                     return 'Failed (Large file upload).'


            # --- Handle Standard Files (<= 2GB) ---
            else:
                await edit_message_safely(download_progress_msg, 'Uploading...')
                upload_start_time = time.time()

                # Get video metadata and screenshot if it's a video and needed
                thumb_path = None
                if message.video:
                    mtd = await get_video_metadata(renamed_file)
                    duration, height, width = mtd.get('duration', 0), mtd.get('height', 1), mtd.get('width', 1)
                    thumb_path = await screenshot(renamed_file, duration, user_id) if duration > 0 else None
                elif message.audio:
                     # For audio, try to get thumbnail from ytdl info if available, or use a default/user-set one
                     # The ytdl.py handles audio thumbnails better. For Telegram audio, no built-in thumb usually.
                     # Could potentially use the user's set thumbnail here if no other thumb is available.
                     thumb_path = thumbnail(user_id) # Check for user-set thumbnail


                try:
                    # Upload the file using the bot client (usually sufficient for <=2GB)
                    if message.video:
                        await bot_client.send_video(
                            target_chat_id,
                            video=renamed_file,
                            caption=final_caption,
                            thumb=thumb_path,
                            width=width,
                            height=height,
                            duration=duration,
                            progress=prog,
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )
                    elif message.video_note:
                        await bot_client.send_video_note(
                            target_chat_id,
                            video_note=renamed_file,
                            progress=prog,
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )
                    elif message.voice:
                        await bot_client.send_voice(
                            target_chat_id,
                            voice=renamed_file,
                            progress=prog,
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )
                    elif message.sticker:
                         # Re-uploading stickers might not maintain sticker properties well.
                         # If send_direct failed, this might also behave unexpectedly.
                         # A simple file upload as document might be a fallback if direct send fails.
                        await bot_client.send_sticker(target_chat_id, sticker=renamed_file, reply_to_message_id=reply_to_message_id)
                    elif message.audio:
                        await bot_client.send_audio(
                            target_chat_id,
                            audio=renamed_file,
                            caption=final_caption,
                            thumb=thumb_path, # Use thumbnail if available
                            duration=message.audio.duration, # Keep original duration if available
                            performer=message.audio.performer, # Keep original metadata
                            title=message.audio.title, # Keep original metadata
                            progress=prog,
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )
                    elif message.photo:
                         # For photos, send as photo. Thumbnail logic already handled.
                        await bot_client.send_photo(
                            target_chat_id,
                            photo=renamed_file,
                            caption=final_caption,
                            progress=prog, # Progress might not show for photos depending on size
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )
                    else:
                        # Default to sending as document for other media types or if type is unknown
                        await bot_client.send_document(
                            target_chat_id,
                            document=renamed_file,
                            caption=final_caption,
                            thumb=thumb_path, # Use thumbnail if available (e.g., for video documents)
                            file_name=os.path.basename(renamed_file), # Use the potentially renamed filename
                            progress=prog,
                            progress_args=(bot_client, target_chat_id, download_progress_msg.id, upload_start_time),
                            reply_to_message_id=reply_to_message_id
                        )

                    # Clean up files after successful upload
                    if os.path.exists(renamed_file): os.remove(renamed_file)
                    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                    await delete_message_safely(download_progress_msg) # Delete the download/upload progress message

                    return 'Done.'

                except Exception as e:
                    # Error during upload
                    print(f'Upload failed for message {message.id}: {e}')
                    await edit_message_safely(download_progress_msg, f'Upload failed: {str(e)[:50]}')
                    # Clean up files even on upload failure
                    if os.path.exists(renamed_file): os.remove(renamed_file)
                    if thumb_path and os.path.exists(thumb_path): os.remove(thumb_path)
                    # Keep the error message instead of deleting download_progress_msg?
                    # await delete_message_safely(download_progress_msg)
                    return 'Failed.'

        # --- Handle Text Messages ---
        elif message.text:
            # For text messages, just send the text with processed rules if any
            processed_text = await process_text_with_rules(user_id, message.text.markdown)
            user_cap = await get_user_data_key(user_id, 'caption', '')
            final_text = f'{processed_text}\n\n{user_cap}' if processed_text and user_cap else user_cap if user_cap else processed_text

            if final_text: # Only send if there is text after processing
                 try:
                      await bot_client.send_message(target_chat_id, text=final_text, reply_to_message_id=reply_to_message_id)
                      return 'Sent.'
                 except Exception as e:
                      print(f"Error sending text message {message.id}: {e}")
                      return f'Error sending text: {str(e)[:50]}'
            else:
                 return 'Skipped (Empty text after processing).'

        else:
            # Handle unsupported message types
            print(f"Unsupported message type for message {message.id}")
            return 'Unsupported message type.'

    except Exception as e:
        # Catch any unexpected errors during the entire process_msg execution
        print(f'Unexpected Error processing message {message.id}: {e}')
        # Attempt to clean up downloaded file if it exists
        if 'renamed_file' in locals() and os.path.exists(renamed_file):
             os.remove(renamed_file)
        if 'downloaded_file' in locals() and os.path.exists(downloaded_file):
             os.remove(downloaded_file)
        if 'thumb_path' in locals() and thumb_path and os.path.exists(thumb_path):
             os.remove(thumb_path)
        # Attempt to edit/delete the progress message if it exists
        if 'download_progress_msg' in locals():
            await edit_message_safely(download_progress_msg, f'An unexpected error occurred: {str(e)[:50]}')
            # Decide whether to keep or delete the error message
            # await delete_message_safely(download_progress_msg)
        return f'Error: {str(e)[:50]}'


# --- Command Handlers ---
@X.on_message(filters.command(['batch', 'single']) & filters.private & ~login_in_progress)
async def process_cmd(c: Client, m: Message):
    """Handles /batch and /single commands."""
    user_id = m.from_user.id
    cmd = m.command[0]

    # Check force subscription first
    subscription_status = await subscribe(c, m) # Assuming subscribe is imported and works with Pyrogram client 'c'
    if subscription_status == 1:
         # Subscribe function sends a message, so just return
         return

    # Check premium limits
    is_prem = await is_premium_user(user_id)
    max_limit = PREMIUM_LIMIT if is_prem else FREEMIUM_LIMIT

    if max_limit == 0 and not is_prem:
        await m.reply_text("This bot does not provide free services. Get a subscription from the OWNER.")
        return

    pro = await m.reply_text('Doing some checks, hold on...')

    # Check if user has an active task
    if is_user_active(user_id):
        await edit_message_safely(pro, 'You have an active task. Use /stop to cancel it.')
        return

    # Check if user has set up a custom bot (required for processing)
    ubot = await get_ubot(user_id)
    # Also check if the global userbot is available as a fallback for user clients
    uc = await get_uclient(user_id) # Get user client (might return global userbot)

    if not ubot and not uc:
         # If neither a user's bot nor a user client (or global userbot) is available
         await edit_message_safely(pro, 'Please add your bot with /setbot or login with /login first.')
         return
    # At least one client (user bot or user client/global userbot) is needed to fetch messages.
    # get_msg prioritizes user_client, so having uc is more critical for private content.
    # However, even ubot can fetch some public content. The check above is a bit loose.
    # Let's refine: for processing, at least a userbot or a user client is needed.
    if not ubot and not (uc and uc.is_connected):
         await edit_message_safely(pro, 'Please add your bot with /setbot or login with /login first.')
         return

    # Start the command sequence state
    Z[user_id] = {'step': 'start' if cmd == 'batch' else 'start_single', 'progress_msg': pro}
    prompt_text = f'Send the {"start link..." if cmd == "batch" else "link you want to process"}.'
    await edit_message_safely(pro, prompt_text)


@X.on_message(filters.command(['cancel', 'stop']) & filters.private)
async def cancel_cmd(c: Client, m: Message):
    """Handles /cancel and /stop commands to cancel an active task."""
    user_id = m.from_user.id

    if is_user_active(user_id):
        batch_info = get_batch_info(user_id)
        if batch_info and not batch_info.get("cancel_requested", False):
             if await request_batch_cancel(user_id):
                  await m.reply_text('Cancellation requested. The current task will stop after the current item completes.')
             else:
                  await m.reply_text('Failed to request cancellation. Please try again.')
        else:
             await m.reply_text('No active task found or cancellation already requested.')
    else:
        # Also check if the user is in a command sequence (login or batch/single setup)
        if user_id in Z:
            del Z[user_id] # Cancel the command sequence
            await m.reply_text('Command sequence cancelled.')
        else:
            await m.reply_text('No active task or command sequence found.')


@X.on_message(filters.text & filters.private & ~login_in_progress & ~filters.command([
    'start', 'batch', 'cancel', 'login', 'logout', 'stop', 'set',
    'pay', 'redeem', 'gencode', 'single', 'generate', 'keyinfo', 'encrypt', 'decrypt',
    'keys', 'setbot', 'rembot', 'settings', 'plan', 'terms', 'help', 'status', 'transfer', 'add', 'rem', 'dl', 'adl']))
async def text_handler(c: Client, m: Message):
    """Handles text input during command sequences."""
    user_id = m.from_user.id

    if user_id not in Z:
        # If user is not in a command sequence, ignore the text message
        # Or potentially forward it to a log/support group if needed
        return

    s = Z[user_id].get('step')
    progress_msg = Z[user_id].get('progress_msg') # Get the initial progress message

    if s == 'start':
        # User is expected to send the start link for batch processing
        link = m.text
        chat_identifier, start_id, link_type = E(link) # Parse the link
        if not chat_identifier or start_id is None: # Check if parsing was successful
            await edit_message_safely(progress_msg, 'Invalid link format.')
            del Z[user_id]
            return

        Z[user_id].update({'step': 'count', 'cid': chat_identifier, 'sid': start_id, 'lt': link_type})
        await edit_message_safely(progress_msg, 'How many messages?')

    elif s == 'start_single':
        # User is expected to send the link for single message processing
        link = m.text
        chat_identifier, message_id, link_type = E(link) # Parse the link
        if not chat_identifier or message_id is None: # Check if parsing was successful
            await edit_message_safely(progress_msg, 'Invalid link format.')
            del Z[user_id]
            return

        Z[user_id].update({'step': 'process_single', 'cid': chat_identifier, 'sid': message_id, 'lt': link_type})

        # Start processing the single message immediately
        await edit_message_safely(progress_msg, 'Processing single message...')

        ubot = await get_ubot(user_id) # Get user's bot client
        uc = await get_uclient(user_id) # Get user client (might be global userbot)

        # Check if at least one client is available for fetching
        if not ubot and not (uc and uc.is_connected):
            await edit_message_safely(progress_msg, 'Cannot proceed without a bot or user client. Use /setbot or /login.')
            del Z[user_id]
            return

        # Add to active users to prevent other tasks
        await add_active_batch(user_id, {
            "total": 1, "current": 0, "success": 0, "cancel_requested": False,
            "progress_message_id": progress_msg.id # Link to the progress message
        })

        try:
            # Fetch the single message
            msg = await get_msg(ubot, uc, chat_identifier, message_id, link_type)
            if msg:
                # Process the single message
                res = await process_msg(ubot, uc, msg, str(m.chat.id), link_type, user_id, chat_identifier) # Pass user_id and source_chat_identifier
                await edit_message_safely(progress_msg, f'Single message process: {res}')
            else:
                await edit_message_safely(progress_msg, 'Message not found or inaccessible.')
        except Exception as e:
            print(f"Error during single message processing for user {user_id}: {e}")
            await edit_message_safely(progress_msg, f'Error processing message: {str(e)[:50]}')
        finally:
            # Clean up state regardless of success/failure
            await remove_active_batch(user_id)
            del Z[user_id]


    elif s == 'count':
        # User is expected to send the number of messages for batch processing
        if not m.text.isdigit():
            await edit_message_safely(progress_msg, 'Invalid input. Please enter a valid number.')
            return # Stay in this step until valid input

        count = int(m.text)
        is_prem = await is_premium_user(user_id)
        max_limit = PREMIUM_LIMIT if is_prem else FREEMIUM_LIMIT

        if count <= 0:
             await edit_message_safely(progress_msg, 'Number of messages must be positive.')
             return # Stay in this step

        if count > max_limit:
            await edit_message_safely(progress_msg, f'Maximum limit is {max_limit}. You are a {"Premium" if is_prem else "Freemium"} user.')
            return # Stay in this step

        # Valid count received, move to process step
        Z[user_id].update({'step': 'process_batch', 'did': str(m.chat.id), 'num': count}) # 'did' is destination chat id
        chat_identifier, start_id, num_messages, link_type = Z[user_id]['cid'], Z[user_id]['sid'], Z[user_id]['num'], Z[user_id]['lt']
        success_count = 0 # Initialize success counter

        await edit_message_safely(progress_msg, f'Starting batch processing for {num_messages} messages...')

        ubot = await get_ubot(user_id) # Get user's bot client
        uc = await get_uclient(user_id) # Get user client (might be global userbot)

        # Check if at least one client is available for fetching
        if not ubot and not (uc and uc.is_connected):
            await edit_message_safely(progress_msg, 'Cannot proceed without a bot or user client. Use /setbot or /login.')
            del Z[user_id]
            return

        # Add to active users to prevent other tasks
        await add_active_batch(user_id, {
            "total": num_messages, "current": 0, "success": 0, "cancel_requested": False,
            "progress_message_id": progress_msg.id # Link to the progress message
        })

        try:
            # Batch processing loop
            for j in range(num_messages):
                # Check for cancellation request before processing each message
                if should_cancel(user_id):
                    await edit_message_safely(progress_msg, f'Batch cancelled by user at message {j+1}/{num_messages}. Processed successfully: {success_count}.')
                    break # Exit the loop

                # Update batch progress state
                await update_batch_progress(user_id, j + 1, success_count)

                # Calculate the message ID to fetch in this iteration
                current_message_id = start_id + j

                try:
                    # Fetch the current message in the batch
                    msg = await get_msg(ubot, uc, chat_identifier, current_message_id, link_type)
                    if msg:
                        # Process the message (download, rename, upload)
                        res = await process_msg(ubot, uc, msg, str(m.chat.id), link_type, user_id, chat_identifier) # Pass user_id and source_chat_identifier
                        # Check the result string to determine success
                        if 'Done' in res or 'Sent' in res: # 'Copied' is for large file copy
                             success_count += 1
                        # Update the progress message with current item status (optional but helpful)
                        await edit_message_safely(progress_msg, f'Processing {j+1}/{num_messages}: {res}')
                    else:
                         # Message not found or inaccessible, update progress message
                         await edit_message_safely(progress_msg, f'Processing {j+1}/{num_messages}: Message {current_message_id} not found or inaccessible.')
                         pass # Continue to the next message even if one fails

                except Exception as e:
                    # Catch errors specific to fetching or processing a single message
                    print(f"Error processing message {current_message_id} in batch for user {user_id}: {e}")
                    await edit_message_safely(progress_msg, f'Processing {j+1}/{num_messages}: Error - {str(e)[:50]}')
                    # Decide whether to continue or break on error - continuing allows processing other messages

                # Add a small delay between processing messages to avoid hitting API limits
                await asyncio.sleep(5) # Increased delay slightly for caution


            # After the loop finishes (either completed or cancelled)
            if not should_cancel(user_id):
                 # If the loop completed without cancellation
                 await m.reply_text(f'Batch Completed ✅ Processed: {num_messages}. Successful: {success_count}/{num_messages}')
            # If cancelled, the cancellation message is already sent

        except Exception as e:
             # Catch any unexpected errors during the batch loop setup or iteration
             print(f"Unexpected error during batch processing for user {user_id}: {e}")
             await edit_message_safely(progress_msg, f'An unexpected error occurred during batch processing: {str(e)[:50]}')

        finally:
            # Clean up active batch state regardless of how the process ended
            await remove_active_batch(user_id)
            del Z[user_id] # Clean up the command sequence state
            # The progress message 'pt' is kept, potentially showing the final status or error.


    # No other steps defined for the command sequence currently

# Note: The filter `~login_in_progress` is applied to process_cmd and text_handler
# to prevent these handlers from interfering with the login flow in plugins/login.py
