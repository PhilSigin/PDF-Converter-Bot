# Custom PDF Converter (main_bot_v7x - actually runs on server! (13 March 2024))

# TELEGRAM BOT ADDRESS: https://t.me/Custom_PDF_bot
# Telegram API credentials (from https://my.telegram.org/)

import logging
import os
import asyncio
import time
from datetime import datetime
from configparser import ConfigParser

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, DocumentAttributeFilename, MessageMediaPhoto

# Converters
from img2pdf import convert
from PyPDF2 import PdfMerger
import extract_msg  # msg converter

# Convenience
import shlex  # for filenames with spaces

# import pprint  # for printing out lists easily

# MSG Converter! TESTED ONLY ON Intel Mac SO FAR.
import pdfkit
import re
from html_replacements import msg_replacements

# Colorful output
from colorama import init, Fore, Style

# My own aliases for styles
_Green = Fore.GREEN
_GreenEX = Fore.LIGHTGREEN_EX
_Red = Fore.RED
_RedEX = Fore.LIGHTRED_EX
_Blue = Fore.BLUE
_BlueEX = Fore.LIGHTBLUE_EX
_RS = Style.RESET_ALL
_Yell = Fore.YELLOW
_Gray = Fore.LIGHTBLACK_EX

init()

# Config file paths
CONFIG_FILE = 'config.ini'
USERS_FILE = 'users.ini'

# Load init_configuration from `init_config.ini`
init_config = ConfigParser()
init_config.read(CONFIG_FILE)

api_id = int(init_config['Telegram']['api_id'])
api_hash = init_config['Telegram']['api_hash']
bot_token = init_config['Telegram']['bot_token']

SECRET_WORD = init_config['Security']['secret_word']

DOWNLOADED_GROUPS = int(init_config['Telegram']['downloaded_groups'])
LIBREOFFICE_PATH = shlex.quote(init_config['Paths']['LIBREOFFICE_PATH'])
CURRENT_FILE_PATH_SHORT = init_config['Paths']['CURRENT_FILE_PATH_SHORT']
# CURRENT_FILE_PATH = init_config['Paths']['CURRENT_FILE_PATH']  # DEBUG: this one is never used

master_user_id = int(init_config['Telegram']['master_user_id'])

# Delete init_config to avoid confusion later in the code
del init_config

# Spam filter variables and arrays
MESSAGE_THRESHOLD = 3  # Allow 3 messages within 30 seconds
user_message_counts = {}  # counter of user messages during last 30 seconds
muted_users = {}  # Dictionary to store muted users

# I want these to go through all messages!
user_id = 0
user_name = ''
registered_moments_ago = False
is_album = False

MAX_INCOMING_FILESIZE = 20000000  # maximum file size, they say its 20 MB for Bots

""" AUTHENTICATION FUNCTIONS """


# Function to check if user is authorized
# which means he is already in users.ini
def is_authorized(local_user_id):
    config = ConfigParser()
    config.read(USERS_FILE)
    return config.has_option('Authorized users', str(local_user_id))


# Function to add UN-authorized user ID to users.ini
def add_unauthorized_user(local_userid, username):
    config = ConfigParser()
    config.read(USERS_FILE)

    # add user only if it is not there already
    if not config.has_option('Unauthorized users', str(local_userid)):
        print(f"{_Yell}--- A006 User ID: {local_userid}, {username} - ADDED to Unauthorized users" + _RS)
        config.set('Unauthorized users', str(local_userid), username)
        with open(USERS_FILE, 'w') as f:
            config.write(f)
    else:
        print(f"{_Yell}--- A005 User ID: {user_id}, {user_name} - EXISTS as Unauthorized user!" + _RS)


# ADD new authorized user (after saying right password) to users.ini
def add_authorized_user(local_user_id, username):
    config = ConfigParser()
    config.read(USERS_FILE)

    # Remove from Unauthorized users if exists
    if config.has_option('Unauthorized users', str(local_user_id)):
        config.remove_option('Unauthorized users', str(local_user_id))

    config.set('Authorized users', str(local_user_id), username)
    with open(USERS_FILE, 'w') as f:
        config.write(f)


# Check if unauthorized user writes too much messages
async def check_anti_spam(event):
    # True  - if user is already a Spammer
    # False - if I can continue with his messages

    if user_id in muted_users:
        return True  # User is muted, ignore message

    # Check message count and time difference
    if user_id not in user_message_counts:
        user_message_counts[user_id] = {
            'count': 0,
            'last_message_time': datetime.now()
        }

    data = user_message_counts[user_id]
    data['count'] += 1

    time_diff = datetime.now() - data['last_message_time']
    if time_diff.seconds < 30:
        if data['count'] > MESSAGE_THRESHOLD:
            # Mute user for 30 seconds with adding his name as well
            # muted_users[user_id] = datetime.now()
            muted_users[user_id] = (datetime.now(), user_name)
            print(f"{_Yell}--- W001a {user_id} Blocked for 30 seconds" + _RS)
            await event.respond("You're sending messages too quickly. Please wait 30 seconds.")
            return True  # User is now officially a spammer, ignore message
    else:
        # Reset counter and last message time
        data['count'] = 0
        data['last_message_time'] = datetime.now()

    return False  # No spam detected


# Retrieves the username that is used throughout the code
async def extract_username(event, local_user_id):
    user = await event.client.get_entity(local_user_id)
    username = user.username
    first_name = user.first_name
    last_name = user.last_name

    # I want to store username, and (both names) if available.
    username_str = str(username) if username is not None else ""
    full_name = f"{first_name} {last_name}" if first_name is not None and last_name is not None else (
            first_name or last_name or "")
    username_to_store = f"{username_str} ({full_name})" if username_str and full_name else username_str or full_name

    return username_to_store


# MAIN AUTHENTICATION FUNCTION - calls other small ones above
async def check_user_authorization(event, client):
    global user_id, user_name, is_album

    if is_album:
        message_text = event.messages[0].text
    else:
        message_text = event.message.text

    if message_text.startswith("/contact"):
        # ATTENTION DEBUG - sends me a message
        await client.forward_messages(master_user_id, event.message)
        return False


    if is_authorized(user_id):
        print(f"{_Green}--- A006 User ID: {user_id}, {user_name} - authorized, continue" + _RS)
        # await event.reply(f"{user_id}! You are authorized! Your message: {event.message.text}")
        return True  # User is authorized

    # if not authorized - let's see what user writes
    else:
        add_unauthorized_user(user_id, user_name)

        print(f"{_Yell}--- A000 User ID: {user_id}, {user_name} - not authorized, waiting for password" + _RS)


        if message_text == '/start' or message_text == '/help':
            instructions = ("**Welcome to PDF Converter bot!** \n"
                            "● To get started you have to enter **password**.\n"
                            "● After successful login you can send one or several "
                            "files and I will convert them into a single PDF file.")
            await client.send_message(user_id, instructions)

            # DEBUG: notifying administrator about a new user
            # because /start button is pressed by user during adding the bot
            await client.send_message(master_user_id,
                                      f"New user connected: {user_id}\n"
                                      f"**{user_name}**\n"
                                      f"is trying to login to PDF Converter")
            return False


        print(f"{_Gray}--- A001 Actual password: \"{SECRET_WORD}\", user sends \"{message_text}\"" + _RS)

        user_input = message_text.strip()
        if user_input == SECRET_WORD:
            # Authentication successful!
            print(f"{_GreenEX}--- A003 User ID: {user_id}, {user_name} - Password OK, user logged in!" + _RS)
            message = "🍀 Congratulations!\nYou are now logged in! "
            await client.send_message(user_id, message)

            # DEBUG: notifying administrator about a new Registered user
            await client.send_message(master_user_id,
                                      f"New user AUTHENTICATED: {user_id}\n"
                                      f"**{user_name}**")

            print(f"{_Green}--- A004 User ID: {user_id}, {user_name} - User added to config.ini" + _RS)

            add_authorized_user(user_id, user_name)

            # adding this to stop working with current message and wait for next ones
            global registered_moments_ago
            registered_moments_ago = True

            return True

        else:

            print(f"{_Yell}--- A002 User ID: {user_id}, {user_name} - wrong password!" + _RS)
            # reply message looks like this, but I would like a new message:
            # await event.reply("Wrong password!")
            await client.send_message(user_id, "✖︎ Wrong password!")

    return False  # User is not authorized


# Run this from time to time to unlock users (after they were blocked by spam-filter)
async def unblock_users(client):
    current_time = datetime.now()
    for local_user_id, (mute_time, local_user_name) in list(muted_users.items()):
        if (current_time - mute_time).seconds >= 30:
            del muted_users[local_user_id]
            await client.send_message(local_user_id, "Now you are unblocked.")
            print(f"{_Yell}--- A007 User ID: {local_user_id}, {local_user_name} has been unblocked.", _RS)


""" CONVERSION FUNCTIONS """


# Renames downloaded file, if it's PDF version will replace existing or converted file.
# Returns updated filename
def check_and_rename_file(path, file):

    base, ext = os.path.splitext(file)
    pdf_file = base + ".pdf"
    pdf_path = os.path.join(path, pdf_file)

    if os.path.exists(pdf_path):
        counter = 1
        while True:
            new_file = f"{base}_{counter}{ext}"
            new_path = os.path.join(path, new_file)
            if not os.path.exists(new_path):
                os.rename(os.path.join(path, file), new_path)
                file = new_file  # Update the file variable with the new file name
                break
            counter += 1

    return file


# CORE CONVERSION FUNCTION
def convert_file_to_pdf(file, extension, path):
    error = ""
    print(f"{_Gray}--- File Conversion: {extension.upper()} -- {file} -- ", end="")

    # path (local to python app) -         Conversions/Group-210
    # file -                               test.xlsx
    # extension -                          xlsx
    # input_name_with_short_path -         Conversions/Group-210/test.xlsx
    # input_name_with_short_path_escaped - 'Conversions/Group-210/test.xlsx'
    # output_pdf_name -                    test.pdf

    # PDF Conversion needs: NOTHING
    # DOC Conversion needs: PATH, input_name_with_short_path_escaped
    # IMG Conversion needs: PATH, input_name_with_short_path_escaped, output_pdf_name_with_path
    # MSG Conversion needs: PATH, input_name_with_short_path,
    #  + creates temporary: message_temp_file_with_path, escaped_filename (for TXT conversion)
    # function returns:     output_pdf_name

    input_name_with_short_path = str(os.path.join(path, file))
    input_name_with_short_path_escaped = shlex.quote(input_name_with_short_path)

    output_pdf_name = f"{os.path.splitext(file)[0]}.pdf"
    output_pdf_name_with_path = os.path.join(path, output_pdf_name)

    if extension == 'pdf':
        print(_RS, "PDF Remained untouched")

    elif extension in ['docx', 'doc', 'xlsx', 'xls']:
        command = (f"{LIBREOFFICE_PATH} --headless --convert-to pdf:writer_pdf_Export "
                   f"{input_name_with_short_path_escaped} --outdir {path}")

        # exit_code = os.system(command)
        # with TOTAL disabled output from LibreOffice:
        # exit_code = os.system(f"{command} > /dev/null 2>&1")
        # Here errors should be still seen (red ones):
        exit_code = os.system(f"{command} > /dev/null")

        if exit_code == 0:
            print(_Green+"Conversion successful", _RS)
        else:
            error = f"{file}: LibreOffice Conversion failed with exit code: " + str(exit_code)
            print(_RedEX + error, _RS)

    elif extension in ['png', 'jpg', 'jpeg', 'heic']:

        if extension == 'heic':
            # Size [decreased by 50% (-Z 0.5)] - doesn't work
            # For now let's down sample to 2500 px:
            # sips -s format pdf /Users/apple/Desktop/IMG_2868.HEIC --out /Users/apple/Desktop/IMG_2868.pdf
            command = (f"sips -Z 2500 -s format pdf {input_name_with_short_path_escaped} "
                       f"--out {output_pdf_name_with_path}")

            exit_code = os.system(f"{command} > /dev/null")

            if exit_code == 0:
                print(_Green + "Conversion successful", _RS)
            else:
                error = f"{file}: (macos) HEIC-> PDF Conversion failed with exit code: " + str(exit_code)
                print(_RedEX + error, _RS)

        else:
            # To hide PNG transparency warning in terminal/console:
            # Store the current log level (forgetting to restore it later)
            original_log_level = logging.getLogger().getEffectiveLevel()
            logging.disable(logging.ERROR)

            try:
                with open(output_pdf_name_with_path, "wb") as f:
                    f.write(convert(input_name_with_short_path))

                logging.disable(original_log_level)

                print(_Green+"Conversion successful", _RS)

            except Exception as e:
                error = f"Conversion failed:" + str(e)
                print(_RedEX, error, _RS)

    #  MESSAGE CONVERSION - my favourite

    elif extension == 'msg':

        """ Initialization """
        """ Converting msg to html (if html is not present, let's convert with simple msg converter) """

        text_content = ""

        msg_file = input_name_with_short_path
        msg_file_html = f"{os.path.splitext(input_name_with_short_path)[0]}.html"
        msg_file_pdf = output_pdf_name_with_path

        # Opening the file

        with open(msg_file, 'rb') as f:  # Open in binary mode
            file_content = f.read().decode('utf-8', errors='ignore')  # Decode

        # Manually search for html code inside <html> tags
        html_match = re.search(r'(<html.*?)(.*?)(</html>)', file_content, flags=re.DOTALL)

        if html_match:
            opening_tag = html_match.group(1)
            content = html_match.group(2)
            closing_tag = html_match.group(3)
            combined_html = opening_tag + content + closing_tag

            # I can write preliminary html to file, but instead I will go further with html stored in memory

            # I am going to have a lot of similar MSG files, that are not fitting on one A4 page, thus
            # so I want to minify content of html to remove unneeded repetitive details.
            # Those unneded details were manually saved in dictionary in an external html_replacements.py file.
            # OK, NOW! Replace keys with values to fit CUSTOM pdf to one A4 page

            for key, value in msg_replacements.items():
                combined_html = combined_html.replace(key, value)

            # At last, let's write the modified content!
            with open(msg_file_html, 'w', encoding='utf-8') as file:
                file.write(combined_html)

            """ Converter of HTML to PDF """

            # for this function to work - wkhtmltopdf should be installed.
            # https://github.com/JazzCore/python-pdfkit/wiki/Installing-wkhtmltopdf
            # from here: https://wkhtmltopdf.org/downloads.html
            # To find out path to wkhtmltopdf executable: run "which wkhtmltopdf" in terminal
            # My programme was tested only on Mac - with macOS 10.13, 10.15 on Intel Macs.

            config = pdfkit.configuration(wkhtmltopdf="/usr/local/bin/wkhtmltopdf")
            options = {'page-size': 'A4'}  # PDF size

            # Convert HTML file to PDF
            pdfkit.from_file(msg_file_html, msg_file_pdf, configuration=config, options=options)

            # By the way, I can convert a URL to PDF
            # pdfkit.from_url('https://www.google.com', 'google.pdf')

            print(_Green+"Conversion successful", _RS)

        else:
            print(_Yell, "No HTML content found in the file.", end="")

            """ WARNING: This conversion method is absolutely unreliable. While it have worked for original examples,
            the resulting data significantly differed from the HTML content, stored in the same file. I am only
            keeping this code for compatibility with other MSG files, that wont have html data inside at all. """

            try:
                message = extract_msg.Message(input_name_with_short_path)
                text_content = message.body
                print(f"{_Green}MSG > TXT", _RS, end="")
            except Exception as e:
                error = f"EXTRACT_MSG Conversion failed:" + str(e)
                print(_RedEX, error, _RS)

            # Create a temporary text file with the extracted text

            message_temp_file_with_path = f"{os.path.splitext(input_name_with_short_path)[0]}.txt"

            with open(message_temp_file_with_path, "w") as f:
                f.write(text_content)

            # Convert the temporary text file to PDF using LibreOffice as in previous sub-function
            escaped_filename = shlex.quote(message_temp_file_with_path)
            command = (f"{LIBREOFFICE_PATH} --headless --convert-to "
                       f"pdf:writer_pdf_Export {escaped_filename} --outdir {path}")

            exit_code = os.system(f"{command} > /dev/null")

            if exit_code == 0:
                print(f"{_Green}-- TXT > PDF Conversion successful", _RS)
            else:
                error = f"{file}: LibreOffice Conversion failed with exit code: " + str(exit_code)
                print(_RedEX + error, _RS)

            # Delete the temporary text file
            os.remove(message_temp_file_with_path)

    return error, output_pdf_name


# incoming messages check for authentication, spam etc
async def common_message_handler(client, event):
    global user_id, user_name, is_album
    user_id = 0
    user_name = ""

    if event.is_group or event.grouped_id:
        is_album = True
        user_id = event.messages[0].peer_id.user_id
    else:
        is_album = False
        user_id = event.message.peer_id.user_id

    user_name = await extract_username(event, user_id)

    if not is_album:
        print(f"\n{_Blue}--- #004a Single message from User ID: {user_id}, {user_name}" + _RS)
    else:
        print(f"\n{_BlueEX}--- #004b ALBUM from User ID: {user_id}, {user_name}" + _RS)

    # SPAM Filter, True if spam, false if not!
    if await check_anti_spam(event):
        print(f"{_Yell}--- W001b User ID: {user_id}, {user_name} - did not pass spam-check" + _RS)
        return False  # Ignore message if spam detected

    global registered_moments_ago
    registered_moments_ago = False

    # Authorization, true if user, false if not!
    if not await check_user_authorization(event, client):
        return False  # Ignore message if not authorized

    # Skips further work on message right after user was authorized with right password in this message
    if registered_moments_ago:
        return False

    return True


# Checks for file formats - BEFORE files downloads.
# Unfortunately, this code is heavily duplicated in download_each_file function.
def message_file_checks(message, warning_message):
    media = message.media
    error_text = []
    file_size = 0
    file_extension = ''
    full_filename = ''
    mime_type = ""

    # Actual file in message
    if isinstance(media, MessageMediaDocument):
        document = media.document
        attributes = document.attributes
        filename_attribute = next(
            (attr for attr in attributes if isinstance(attr, DocumentAttributeFilename)), None)

        # Extract file information directly
        file_extension = filename_attribute.file_name.split('.')[-1].lower() if filename_attribute else None
        full_filename = filename_attribute.file_name if filename_attribute else None
        mime_type = document.mime_type
        file_size = document.size

    # Image in message (sent with quick-send)
    elif isinstance(media, MessageMediaPhoto):
        photo = media.photo

        # Extract information from the PhotoSizeProgressive object
        progressive_sizes = None
        for size in reversed(photo.sizes):
            if hasattr(size, 'sizes') and isinstance(size.sizes, list):
                progressive_sizes = size.sizes
                break

        if progressive_sizes:
            # Handle photos with assumed extension and filename pattern
            # mime_type = photo.mime_type
            file_extension = 'jpg'
            full_filename = f'Photo_{message.id % 1000}.jpg'
            file_size = progressive_sizes[-1]    # Using the last size in the list
            # file_size = media.photo.sizes[-1]  # This line doesn't work

    else:
        error = "E100 CRITICAL ERROR - Unsupported media type"
        error_text.append(error)
        warning_message += f"**{error}**\n"

    # Check file size
    if file_size > MAX_INCOMING_FILESIZE:
        error = "File is too big"
        error_text.append(error)
        warning_message += f"**{error}:**\n{full_filename}\n"

    # Check MIME type and extension
    if mime_type not in (
            "image/png", "image/jpeg", "application/octet-stream",
            "application/pdf", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword", "application/x-msexcel"
    ) and file_extension not in (
            "jpg", "jpeg", "png", "heic", "msg", "pdf", "xls", "xlsx", "doc", "docx"
    ):
        error = "File is not of recognizable file format"
        error_text.append(error)
        warning_message += f"**{error}**:\n{full_filename}\n"

    temp_string_output = f"{_Gray}--- File: {file_extension.upper()}"
    if mime_type:
        temp_string_output += f" [{mime_type}] "
    temp_string_output += f"-- Filesize: {file_size} -- Filename: {full_filename} {_RS}"

    print(temp_string_output)

    for every_line in error_text:
        print(f"{_Yell}---       {every_line}{_RS}")

    return warning_message, file_extension


# DOWNLOAD ALL files - partial copy of message_file_checks function
# Saves filenames and extensions to a dictionary, updates warning message
async def download_each_file(client, message, warning_message, folder_name):

    file_info = {}
    full_filename = ''
    file_extension = ''

    media = message.media

    # Actual file in message
    if isinstance(media, MessageMediaDocument):
        document = media.document
        attributes = document.attributes
        filename_attribute = next(
            (attr for attr in attributes if isinstance(attr, DocumentAttributeFilename)), None)
        file_extension = filename_attribute.file_name.split('.')[-1].lower() if filename_attribute else None
        full_filename = filename_attribute.file_name if filename_attribute else None

    # Image in message (sent with quick-send)
    elif isinstance(media, MessageMediaPhoto):

        document = media.photo

        # Extracting information from the PhotoSizeProgressive object
        progressive_sizes = None
        for size in reversed(document.sizes):
            if hasattr(size, 'sizes') and isinstance(size.sizes, list):
                progressive_sizes = size.sizes
                break

        if progressive_sizes:
            # Handle photos with assumed extension and filename pattern
            file_extension = 'jpg'
            full_filename = f'Photo_{message.id % 1000}.jpg'

    print(f"{_Gray}--- File download:", full_filename, "- " + _RS, end="")

    try:
        await client.download_media(message, file=folder_name + '/' + full_filename)
        print("Download successful!")
    except Exception as e:
        print(f"{_Yell}Error downloading file: {e}")

    file_info[full_filename] = file_extension.lower()

    return warning_message, file_info


# Gathers all PDFs into one
def combine_pdfs(files, short_path):
    print(f"{_Green}--- Files combine started.", _RS, end="")

    # Create a PdfMerger object
    merger = PdfMerger()

    # Add each PDF file in the list to the merger
    for file in files:
        file_with_path = os.path.join(short_path, file)
        try:
            with open(file_with_path, 'rb') as pdf_file:
                merger.append(pdf_file)
        except IOError as e:
            raise OSError(f"Error opening PDF file: {e}")

    # Create the output file
    output_path = os.path.join(short_path, f"Package #{str(DOWNLOADED_GROUPS)}.pdf")
    try:
        with open(output_path, 'wb') as output_file:
            merger.write(output_file)
            print(f"{_GreenEX}PDF ready:", output_path, _RS)
            return output_path
    except IOError as e:
        raise OSError(f"Error writing output file: {e}")


# MAIN FUNCTION that calls for files check, downloads, conversion
async def files_conversion(client, event):
    warning_message = ""
    file_count = 0
    error = ""
    all_files_download_and_conversion_start_time = time.time()

    """ MESSAGE FILE CHECKS AND ERROR PRINTOUTS """

    if is_album:
        for message in event.messages:
            warning_message, file_extension = message_file_checks(message, warning_message)
            file_count += 1

    else:
        warning_message, file_extension = message_file_checks(event.message, warning_message)
        file_count += 1

        if file_count == 1 and file_extension == "pdf":
            # File is already a PDF, nothing to do
            error = "The file supplied is already a PDF, no need for conversion!"
            print(f"{_Green}---       {error}{_RS}")
            await client.send_message(user_id, error)
            return error

    if warning_message:
        print(f"{_Red}--- Finished with this message due to: \n", warning_message, _RS)
        await client.send_message(user_id, warning_message)
        return warning_message

    """ DOWNLOAD ALL FILES """

    # Querying and updating total number of groups at the moment
    # to be sure that I am downloading files to a NEW folder

    global DOWNLOADED_GROUPS
    groups_re_config = ConfigParser(comment_prefixes='#', allow_no_value=True)
    groups_re_config.read(CONFIG_FILE)

    DOWNLOADED_GROUPS = int(groups_re_config['Telegram']['downloaded_groups'])
    DOWNLOADED_GROUPS += 1

    groups_re_config.set('Telegram', 'downloaded_groups', str(DOWNLOADED_GROUPS))
    with open(CONFIG_FILE, 'w') as f:
        groups_re_config.write(f)

    del groups_re_config

    current_file_paths = CURRENT_FILE_PATH_SHORT + str(DOWNLOADED_GROUPS)

    print(f"{_Blue}--- D152 New current folder: {_BlueEX} {current_file_paths}" + _RS)

    warning_message = ""
    file_count_downloaded = 0
    file_info_downloaded = {}

    if is_album:
        for message in event.messages:
            warning_message, file_info = await download_each_file(client, message, warning_message, current_file_paths)
            file_info_downloaded.update(file_info)
            file_count_downloaded += 1
    else:
        warning_message, file_info = await download_each_file(client, event.message, warning_message,
                                                              current_file_paths)
        file_count_downloaded += 1
        file_info_downloaded.update(file_info)

    # printing out list of files and their extensions (debug)
    # pprint.pprint(file_info_downloaded)

    if warning_message:
        print(f"{_Red}--- Finished downloading files from this message due to: \n", warning_message, _RS)
        await client.send_message(user_id, warning_message)
        return warning_message

    files_converted = []

    print(f"{_Blue}--- File Conversion started" + _RS)

    # Sort list of files based on extension priority (MSG first!!)
    file_info_downloaded = dict(sorted(file_info_downloaded.items(), key=lambda item: ("msg" != item[1], item[0])))

    """ CONVERT FILE ONE BY ONE """

    for file, ext in file_info_downloaded.items():
        error_new, file = convert_file_to_pdf(file, ext, current_file_paths)
        files_converted.append(file)
        if error_new:
            if error:
                error += "\n"
            error += error_new

    if error:
        await client.send_message(user_id, error)
        await client.send_message(master_user_id, error)
        return

    print(f"{_BlueEX}--- Conversion Finished,", len(files_converted), "file(s) ready." + _RS)

    """ SEND SINGLE PDF OR CONVERT MULTIPLE FILES TO PDF AND SEND """

    if len(files_converted) == 1:
        file_save_path = f"{CURRENT_FILE_PATH_SHORT}{DOWNLOADED_GROUPS}"
        file_path = os.path.join(f"{file_save_path}", files_converted[0])
    elif len(files_converted) > 1:
        file_path = combine_pdfs(files_converted, current_file_paths)
    else:
        print(f"{_Red}Error! Zero files converted", _RS)
        return

    await client.send_file(user_id, file_path)

    print(f"{_Green}--- Successfully sent file {_GreenEX}{file_path}{_Green} "
          f"to user {_GreenEX}{user_id} - {user_name}" + _RS)

    all_files_download_and_conversion_end_time = time.time()
    execution_time = all_files_download_and_conversion_end_time - all_files_download_and_conversion_start_time
    print(f"{_Blue}--- Conversion time: {execution_time:.2f} sec.", _RS)


async def main():

    # Testing if LibreOffice is present at the Server
    if os.access(LIBREOFFICE_PATH.strip("'"), os.X_OK):
        print(f"{_Green}--- #000 LibreOffice found at", LIBREOFFICE_PATH, _RS)
    else:
        print(f"{_RedEX}--- #000 LibreOffice not found at", LIBREOFFICE_PATH, _RS)
        return

    async with (TelegramClient('bot', api_id, api_hash) as client):
        await client.start(bot_token=bot_token)

        print(f"{_Green}--- #001 Telegram Client Started" + _RS)
        print(f"{_Green}--- #002 Current password from config.ini:", SECRET_WORD + _RS)

        """ START OF MAIN PROGRAM - rewritten to work with Bot, not User Chat as before """

        # Event handler for incoming Groups of messages
        @client.on(events.Album)
        async def handle_album(event):
            print("\nNEW ALBUM)")

            """ START - Preliminary checks for authorization etc """

            handler_answer = await common_message_handler(client, event)

            # Ignore everything further if receive FALSE (not authorized, wrong password etc.)
            if not handler_answer:
                print(f"{_Red}--- Finished with this message! {_RedEX}Not authorized!", _RS)
                return

            """ END of Checks """

            await files_conversion(client, event)
            return

        #
        # Event handler for incoming Single Messages
        @client.on(events.NewMessage())
        async def handle_message(event):

            # If it's a group of messages, handle it only with @client.on(events.Album)
            if event.is_group or event.grouped_id:
                return

            print("\nNEW MESSAGE")

            """ START - Preliminary checks for authorization etc """

            handler_answer = await common_message_handler(client, event)

            # Ignore everything further if receive FALSE (not authorized, wrong password etc.)
            if not handler_answer:
                print(f"{_Red}--- Finished with this message! {_RedEX}Not authorized!", _RS)
                return

            """ END of Checks """

            # Single message can be received without any files.
            # Let's filter them out:
            if not event.media:
                print(
                    f"{_Yell}--- C001 User ID: {user_id}, {user_name} - {Style.BRIGHT}Message without files:" + _RS)
                print(
                    f"{_Gray}--- C001 User ID: {user_id}, {user_name} - {_Yell}{event.message.text}" + _RS)
                message = ("Send me one or more files in a single message, and I will convert them to a single PDF. "
                           "File formats accepted: \n**Word/Excel/PDF/JPEG/PNG/MSG**")
                await client.send_message(user_id, message)
                print(f"{_Yell}--- Finished with this message - no files to convert", _RS)

                return

            await files_conversion(client, event)
            return

        # Periodically check for muted users and send unblock messages

        print(f"{_Green}--- #003 Groups of files received before: {DOWNLOADED_GROUPS}" + _RS)
        while True:
            await unblock_users(client)
            await asyncio.sleep(10)  # Adjust the sleep time as needed

        # DEBUG! This place looks unreachable!
        # await client.start()
        # await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
