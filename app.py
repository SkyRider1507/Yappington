import disnake
from disnake.ext import commands, tasks
from gtts import gTTS
import asyncio
import tempfile
import os
import json
from collections import defaultdict
import re

intents = disnake.Intents.all()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.change_presence(activity=disnake.Activity(type=disnake.ActivityType.listening, name="People Yapping!"))
    print(f'Logged in as {bot.user}!')
    print("Bot Online!")

class TTSManager:
    def __init__(self):
        self.voice_clients = {}
        self.custom_nicknames = {}
        self.shortcuts = self.load_shortcuts()
        self.last_speaker = defaultdict(str)
        self.message_queue = defaultdict(list)
        self.current_audio_file = {}
        # Start the auto-disconnect check
        self.check_voice_channels.start()

    @tasks.loop(seconds=30)  # Check every 30 seconds
    async def check_voice_channels(self):
        for guild_id, voice_client in list(self.voice_clients.items()):
            if voice_client.is_connected():
                # Get the number of non-bot members in the channel
                channel_members = [member for member in voice_client.channel.members 
                                 if not member.bot]
                
                # If no non-bot members are present, disconnect
                if not channel_members:
                    await voice_client.disconnect()
                    del self.voice_clients[guild_id]
                    print(f"Auto-disconnected from guild {guild_id} due to inactivity")

    @check_voice_channels.before_loop
    async def before_check_voice_channels(self):
        # Wait until the bot is ready before starting the task
        await bot.wait_until_ready()

    def __del__(self):
        # Ensure the task is cancelled when the manager is destroyed
        try:
            self.check_voice_channels.cancel()
        except:
            pass

    def load_shortcuts(self):
        try:
            with open('shortcuts.json', 'r') as f:
                data = json.load(f)
                # Convert all keys to strings to ensure server IDs are stored as strings
                return {str(guild_id): shortcuts for guild_id, shortcuts in data.items()}
        except FileNotFoundError:
            # Create the file with an empty structure if it doesn't exist
            empty_data = {}
            with open('shortcuts.json', 'w') as f:
                json.dump(empty_data, f, indent=4)
            return defaultdict(dict)

    def save_shortcuts(self):
        # Ensure all server IDs are stored as strings
        data_to_save = {str(guild_id): shortcuts for guild_id, shortcuts in self.shortcuts.items()}
        with open('shortcuts.json', 'w') as f:
            json.dump(data_to_save, f, indent=4)

    def get_server_shortcuts(self, guild_id):
        """Get shortcuts for a specific server"""
        return self.shortcuts.get(str(guild_id), {})

    def add_server_shortcut(self, guild_id, shortcut, full_text):
        """Add a shortcut for a specific server"""
        guild_id = str(guild_id)  # Ensure guild_id is a string
        if guild_id not in self.shortcuts:
            self.shortcuts[guild_id] = {}
        self.shortcuts[guild_id][shortcut.lower()] = full_text
        self.save_shortcuts()

    def remove_server_shortcut(self, guild_id, shortcut):
        """Remove a shortcut from a specific server"""
        guild_id = str(guild_id)  # Ensure guild_id is a string
        if guild_id in self.shortcuts and shortcut.lower() in self.shortcuts[guild_id]:
            del self.shortcuts[guild_id][shortcut.lower()]
            self.save_shortcuts()
            return True
        return False

    def process_message(self, message, content):
        # URL pattern matching
        url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        
        # Check for different types of content
        if message.attachments:
            if any(att.content_type and 'image' in att.content_type for att in message.attachments):
                return f"{message.author.display_name} sent an image"
            elif any(att.content_type and 'gif' in att.content_type for att in message.attachments):
                return f"{message.author.display_name} sent a gif"
            return f"{message.author.display_name} sent an attachment"
            
        # Replace URLs with appropriate text
        if url_pattern.search(content):
            if 'gif' in content.lower():
                return f"{message.author.display_name} sent a gif"
            elif any(ext in content.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return f"{message.author.display_name} sent an image"
            return f"{message.author.display_name} sent a link"

        # Process shortcuts (server-specific)
        guild_id = str(message.guild.id)
        words = content.split()
        for i, word in enumerate(words):
            if guild_id in self.shortcuts and word.lower() in self.shortcuts[guild_id]:
                words[i] = self.shortcuts[guild_id][word.lower()]

        # Process mentions
        for mention in message.mentions:
            mention_str = f'<@{mention.id}>'
            for i, word in enumerate(words):
                if mention_str in word:
                    words[i] = word.replace(mention_str, mention.name)

        for channel in message.channel_mentions:
            channel_str = f'<#{channel.id}>'
            for i, word in enumerate(words):
                if channel_str in word:
                    words[i] = word.replace(channel_str, f"channel {channel.name}")

        processed_content = ' '.join(words)

        channel_id = str(message.channel.id)
        current_speaker = str(message.author.id)

        if self.last_speaker[channel_id] != current_speaker:
            speaker_name = self.custom_nicknames.get(current_speaker, message.author.display_name)
            self.last_speaker[channel_id] = current_speaker
            return f"{speaker_name} says: {processed_content}"
        return processed_content

    def create_tts_audio(self, text, lang='en'):
        tts = gTTS(text=text, lang=lang)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            tts.save(fp.name)
            return fp.name

    async def play_audio(self, guild_id, audio_file):
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                self.message_queue[guild_id].append(audio_file)
                return
            await self.play_next(guild_id, audio_file)

    async def play_next(self, guild_id, audio_file):
        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            audio_source = disnake.FFmpegPCMAudio(audio_file)
            self.current_audio_file[guild_id] = audio_file

            def after_playing(error):
                if guild_id in self.current_audio_file:
                    try:
                        os.remove(self.current_audio_file[guild_id])
                        del self.current_audio_file[guild_id]
                    except:
                        pass
                asyncio.run_coroutine_threadsafe(self.check_queue(guild_id), bot.loop)

            voice_client.play(audio_source, after=after_playing)

    async def stop_and_clear(self, guild_id):
        had_messages = False

        if guild_id in self.voice_clients:
            voice_client = self.voice_clients[guild_id]
            if voice_client.is_playing():
                voice_client.stop()

        if guild_id in self.current_audio_file:
            try:
                os.remove(self.current_audio_file[guild_id])
                del self.current_audio_file[guild_id]
                had_messages = True
            except:
                pass

        if guild_id in self.message_queue:
            for audio_file in self.message_queue[guild_id]:
                try:
                    os.remove(audio_file)
                    had_messages = True
                except:
                    pass
            self.message_queue[guild_id].clear()

        return had_messages

    async def check_queue(self, guild_id):
        if self.message_queue[guild_id]:
            next_audio = self.message_queue[guild_id].pop(0)
            await self.play_next(guild_id, next_audio)

def create_embed(title, description, color=disnake.Color.blue()):
    embed = disnake.Embed(title=title, description=description, color=color)
    embed.set_thumbnail(url="https://zip.skyrider15.com/u/E1cap2.png")
    embed.set_footer(text="SkyRider Development | Thanks for using Yappington!", icon_url="https://zip.skyrider15.com/u/E1cap2.png")
    return embed

tts_manager = TTSManager()

@bot.event
async def on_voice_state_update(member, before, after):
    # Skip if the member is a bot
    if member.bot:
        return

    # Check if the member left a voice channel
    if before.channel and not after.channel:
        guild_id = before.channel.guild.id
        if guild_id in tts_manager.voice_clients:
            voice_client = tts_manager.voice_clients[guild_id]
            if voice_client.channel == before.channel:
                # Check if there are any non-bot members left in the channel
                remaining_members = [m for m in before.channel.members if not m.bot]
                if not remaining_members:
                    await voice_client.disconnect()
                    del tts_manager.voice_clients[guild_id]
                    print(f"Disconnected from {before.channel.name} as no users remain")

@bot.slash_command(description="Joins the user's current voice channel")
async def join(inter: disnake.ApplicationCommandInteraction):
    if inter.author.voice:
        channel = inter.author.voice.channel
        if inter.guild.id in tts_manager.voice_clients:
            await tts_manager.voice_clients[inter.guild.id].move_to(channel)
        else:
            tts_manager.voice_clients[inter.guild.id] = await channel.connect()

        embed = create_embed("Yappington Connected Successfully!", f"Connected to {channel.name}", disnake.Color.orange())
        await inter.response.send_message(embed=embed)
    else:
        embed = create_embed("Error", "You need to be in a voice channel first!", disnake.Color.red())
        await inter.response.send_message(embed=embed)

@bot.slash_command(description="Leaves the current voice channel")
async def leave_tts(inter: disnake.ApplicationCommandInteraction):
    if inter.guild.id in tts_manager.voice_clients:
        await tts_manager.voice_clients[inter.guild.id].disconnect()
        del tts_manager.voice_clients[inter.guild.id]
        embed = create_embed("Yappington Disconnected!", "Successfully Disconnected from voice channel")
        await inter.response.send_message(embed=embed)
    else:
        embed = create_embed("Error", "I'm not in a voice channel!", disnake.Color.red())
        await inter.response.send_message(embed=embed)

@bot.slash_command(description="Adds a new shortcut for text-to-speech")
async def add_shortcut(inter: disnake.ApplicationCommandInteraction, shortcut: str, full_text: str):
    tts_manager.add_server_shortcut(inter.guild.id, shortcut, full_text)
    embed = create_embed("Shortcut Added", f"Added shortcut for this server: {shortcut} = {full_text}")
    await inter.response.send_message(embed=embed)

@bot.slash_command(description="Removes an existing shortcut")
async def remove_shortcut(inter: disnake.ApplicationCommandInteraction, shortcut: str):
    if tts_manager.remove_server_shortcut(inter.guild.id, shortcut):
        embed = create_embed("Shortcut Removed", f"Removed shortcut: {shortcut}")
    else:
        embed = create_embed("Error", "Shortcut not found for this server.", disnake.Color.red())
    await inter.response.send_message(embed=embed)

@bot.slash_command(description="Lists all shortcuts for this server")
async def list_shortcuts(inter: disnake.ApplicationCommandInteraction):
    shortcuts = tts_manager.get_server_shortcuts(inter.guild.id)
    if shortcuts:
        shortcuts_list = "\n".join([f"{k} = {v}" for k, v in shortcuts.items()])
        embed = create_embed("Server Shortcuts", f"Current shortcuts for this server:\n{shortcuts_list}")
    else:
        embed = create_embed("No Shortcuts", "No shortcuts are set for this server.")
    await inter.response.send_message(embed=embed)

@bot.slash_command(description="Clears the text-to-speech message queue")
async def clear_queue(inter: disnake.ApplicationCommandInteraction):
    had_messages = await tts_manager.stop_and_clear(inter.guild.id)

    if had_messages:
        embed = create_embed("Queue Cleared", "Stopped current playback and cleared all pending messages", disnake.Color.green())
    else:
        embed = create_embed("Queue Empty", "No messages were in the queue", disnake.Color.orange())

    await inter.response.send_message(embed=embed)

@bot.slash_command(description="Sets a custom nickname for text-to-speech")
async def nickname(inter: disnake.ApplicationCommandInteraction, nickname: str):
    tts_manager.custom_nicknames[str(inter.author.id)] = nickname
    embed = create_embed("Nickname Set", f"Your Yappington nickname has been set to: {nickname}")
    await inter.response.send_message(embed=embed)

@bot.slash_command(description="Resets your nickname to the default display name")
async def reset_nickname(inter: disnake.ApplicationCommandInteraction):
    if str(inter.author.id) in tts_manager.custom_nicknames:
        del tts_manager.custom_nicknames[str(inter.author.id)]
        embed = create_embed("Nickname Reset", "Your Yappington nickname has been reset to your display name")
    else:
        embed = create_embed("No Nickname", "You don't have a custom nickname set")
    await inter.response.send_message(embed=embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.guild and message.guild.id in tts_manager.voice_clients:
        voice_client = tts_manager.voice_clients[message.guild.id]
        if message.channel == voice_client.channel:
            processed_message = tts_manager.process_message(message, message.content)
            audio_file = tts_manager.create_tts_audio(processed_message)
            await tts_manager.play_audio(message.guild.id, audio_file)

    await bot.process_commands(message)
    
bot.run('YOUR_TOKEN_HERE')