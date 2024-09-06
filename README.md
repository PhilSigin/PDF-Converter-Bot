# Custom PDF Converter
#### Video demo: https://youtu.be/k1TAuKJY_6w
#### Description:
[**Custom PDF Converter**](https://t.me/Custom_PDF_bot) is a Telegram Bot, which automates
conversion of various file formats (DOCX, XLSX, JPG, PNG, MSG and HEIC) into a **single PDF document**.  Users simply interact by sending their files, and the bot replies within several
seconds with PDF attached. Key feature of this converter is ability to properly understand **Microsoft Outlook files**.

To use the bot, type "Custom PDF Converter" in the Telegram search bar and select the bot from the search results, or simply use the link https://t.me/Custom_PDF_bot. Current password is **testpass**


---




### Preface
I decided to develop a genuinely useful project that would assist my acquaintances in their workflow. Their primary system lacks the functionality to upload multiple files to the document management system, and more importantly, it cannot preview Microsoft Outlook files (.msg), which are widely used in their workflow.

### Technology Stack

I chose Python and Telegram as my primary tools. Python is a straightforward language, and deploying a Telegram bot does not require a dedicated server or public IP address, making it easy to deploy and accessible to remote users. My bot utilizes Telethon library, a framework for interacting with the Telegram API.

### Installation
The program consists of several files:
- `main_bot_v6x.py` - Main Python script
- `config.ini` - Configuration file
- `users.ini` - List of authorized users
- `html_replacements.py` - Describes how to optimize custom Outlook messages
- `README.md` - This file

During operation, the bot creates:
 - An additional folder named `Conversions` in its root path.
 - Corresponding subfolders named `Group-XX` for each conversion job. These names can be configured in `config.ini`.

### Requirements
 - **LibreOffice:** Installed on the server computer. Update the path in `config.ini` <br>(default: `/Applications/Office/LibreOffice.app/Contents/MacOS/soffice)`.
 - **wkhtmltopdf library:** Download from https://wkhtmltopdf.org/.
 - `wkhtmltopdf` library should be installed from https://wkhtmltopdf.org/downloads.html
 - Valid Telegram API credentials obtained from https://api.telegram.org/ should be placed in `users.ini` Configuration file.
```angular2html
[Telegram]
api_id = YOUR_API_ID
api_hash = YOUR_API_HASH
bot_token = YOUR_BOT_TOKEN
downloaded_groups = 1
master_user_id = YOUR_MASTER_USER_ID
```

### Deployment and Testing
Currently, Custom PDF Converter runs in PyCharm (Free Community Edition) on a local macOS machine. This setup allows convenient monitoring of the console for errors and debugging messages, facilitating code updates and immediate application restarts.

The program has been tested on macOS 10.13-10.15 and can be transferred to other Unix-based server machines (including Ubuntu) with minimal code modifications.




## How it works

### Checks users
In order for bot to processes incoming files, user needs to be authorized by logging in
with a predefined password. Once the user successfully logged in, his `user_id` is stored
on the server and that's it with user pre-checks.

> The bot is currently in testing and is not available to the public.<br>
For now, the password is just **"testpass"**.

***
### Handles Messages
- The bot waits for incoming messages
    - **Unauthorized users are prompted to enter a password,** program is waiting for **correct password** OR for `/help` or `/start` requests (in that case bot sends a brief description on how it works). Upon successful password entry, the user is added to an authorized list. In case user is sending too many messages, bot blocks user for 30 seconds (i.e. not reacting on any messages from user within that time). This was implemented as a basic password guessing protection and spam-filtering .

### Checks files
- If a user is authorized and sends one or more files, the bot verifies if the received files are of supported formats and have a size under a certain limit.
- If files are valid, the bot downloads them to a designated folder.

### Converts files
- Before the conversion of each file, the bot ensures each converted file will have a unique name to avoid overwriting existing files.
- Based on each file type, the bot uses different methods of PDF conversion.<br>
This might involve using:
  - `LibreOffice` for text documents and spreadsheets
  - `img2pdf` library for image files (JPG, PNG)
  - `sips` system command for HEIC format <br> (this would work normally only on a Mac computer,<br> have to be replaced to different command based on host OS)
  -  MSG files are handled using some more sophisticated techniques


### Combines PDFs into one file
After conversion, the bot merges all the individual PDFs into a single document
and sends it back to the user.


### Handles Errors
The program currently displays each step in the server terminal and sends information about major errors (such as incorrect file formats) directly to the user via Telegram.

> To contact me using the bot, type in a chat
> `/contact [your text]`<br>replacing `[your text]` with your specific message. Feel free to send any questions, feedback, or suggestions through this command
---


#### Interesting facts:
- As noted above, the bot was written to help my friends to cope with their in-house reporting system. Hope it will be quite useful to them, given the amount of approximately 240 sets of files to be created every day.
- Microsoft Outlook message files present a unique challenge. Accessing .msg files correctly is tricky unless you have a Windows machine with Outlook installed. Having personally explored various libraries and online converters, only one proved capable of extracting the specific information needed from the .msg files. Most others tended to focus on the "text-only part," coincidentally containing entirely different information.
- Without going into details, the project is essentially a wrapper of one line of code that converts documents: <br>`LibreOffice --convert-to pdf Report.doc`  <sub>(not an actual line :)</sub>






