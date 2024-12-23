Yappington is hosted on a Pterodactyl Panel. If you just want the bot without hosting it yourself, You may add it using this link: 
https://discord.com/oauth2/authorize?client_id=1316764467836747816

If you would like to host Yappington yourself, 
Download the `app.py` file or clone it from this repository.
Upload the file to your hosting provider.
Ensure the dependencies are installed.
Go to https://discord.dev and create a bot.
Give the bot the permissions you wish to give, it will need all Voice Chat permissions for the TTS Functions to work.
Insert your bot token into the `main.py` file.
Invite the Bot to your server.

Start the bot on your hosting provider, Once it has finished starting it should print:
"Logged in as BOT_USERNAME!"
"Bot Online!"

Go to any VC in your server and do `/join`, if you dont see your bot's slash commands reload your Discord by pressing `CTRL R` in most cases.

After the bot has joined your VC, type out a message and it should play it back to you!

Mission complete! Enjoy!

# Dependencies required for Yappington
- Disnake
- PyNaCl 
- gtts
- pyttsx3
- ffmpeg-python 
- asyncio
