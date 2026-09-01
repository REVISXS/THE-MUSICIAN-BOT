import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
import os
import subprocess
import tempfile
import json
from datetime import datetime
import pretty_midi
import re
import time
import asyncio
import io
import urllib.request
import zipfile
import sys

# ========== TOKEN FROM ENVIRONMENT (Render / Replit / Fly.io) ==========
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
    print("Add it in Render / Replit / Fly.io Environment Variables.")
    exit(1)

# ========== WHITELIST SERVER ==========
ALLOWED_GUILD_ID = 1524909475692286086
OWNER_ID = 1071440754863525998

FREE_LIMIT = 10
PREMIUM_LIMIT = 25
UNLIMITED = 999999
USAGE_FILE = "usage.json"

ADMIN_ROLES = [
    "co founder",
    "admin",
    "staff",
    "founder",
    "owner",
    "moderator",
    "legend"
]

# ========== FFMPEG DETECTION ==========
FFMPEG_EXE = "ffmpeg.exe"

def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
        bundled_path = os.path.join(base_path, FFMPEG_EXE)
        if os.path.exists(bundled_path):
            return bundled_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(script_dir, FFMPEG_EXE)
    if os.path.exists(local_path):
        return local_path
    cwd_path = os.path.join(os.getcwd(), FFMPEG_EXE)
    if os.path.exists(cwd_path):
        return cwd_path
    try:
        result = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return "ffmpeg"
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None

def has_ffmpeg():
    return get_ffmpeg_path() is not None

def ensure_ffmpeg_sync():
    if has_ffmpeg():
        return True
    print("ffmpeg not found. Downloading...")
    try:
        zip_path = "ffmpeg.zip"
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        print(f"Downloading from: {url}")
        urllib.request.urlretrieve(url, zip_path)
        print("Download complete. Extracting...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for file in zip_ref.namelist():
                if file.endswith("ffmpeg.exe"):
                    with zip_ref.open(file) as src, open(FFMPEG_EXE, 'wb') as dst:
                        dst.write(src.read())
                    print(f"Extracted {FFMPEG_EXE}")
                    break
        os.remove(zip_path)
        print("ffmpeg is ready!")
        return True
    except Exception as e:
        print(f"Failed to download ffmpeg: {e}")
        return False

async def ensure_ffmpeg_async():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ensure_ffmpeg_sync)

# ========== MODEL — LOCKED TO SMALL ==========
TIMEOUT_SECONDS = 7200
ESTIMATE_FACTOR = 1.78

# ========== SESSION CACHE ==========
SESSION_CACHE = {}
SESSION_EXPIRY = 3600

def store_session(session_id, data):
    SESSION_CACHE[session_id] = {'data': data, 'timestamp': time.time()}
    for key in list(SESSION_CACHE.keys()):
        if time.time() - SESSION_CACHE[key]['timestamp'] > SESSION_EXPIRY:
            del SESSION_CACHE[key]

def get_session(session_id):
    if session_id in SESSION_CACHE:
        return SESSION_CACHE[session_id]['data']
    return None

def delete_session(session_id):
    if session_id in SESSION_CACHE:
        del SESSION_CACHE[session_id]
        return True
    return False

# ========== UI HELPER FUNCTIONS ==========
def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def format_duration(seconds):
    if seconds is None:
        return "Unknown"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}m {secs}s"

def format_time_remaining(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

def create_waveform_visualization(progress, width=24):
    if progress <= 0:
        return "▬" * width
    filled = int(width * progress / 100)
    wave = ""
    for i in range(width):
        if i < filled:
            if i % 3 == 0:
                wave += "▄"
            elif i % 3 == 1:
                wave += "▀"
            else:
                wave += "█"
        else:
            wave += "░"
    return wave

def create_spectrogram(progress, width=20):
    if progress <= 0:
        return "⣿" * width
    filled = int(width * progress / 100)
    chars = ["⣀", "⣤", "⣶", "⣿"]
    result = ""
    for i in range(width):
        if i < filled:
            result += chars[i % len(chars)]
        else:
            result += "·"
    return result

def detect_platform(url):
    if not url:
        return "Web Link", "Link"
    url_lower = url.lower()
    if "tiktok" in url_lower:
        return "TikTok", "TikTok"
    elif "youtube" in url_lower or "youtu.be" in url_lower:
        return "YouTube", "YouTube"
    elif "soundcloud" in url_lower:
        return "SoundCloud", "SoundCloud"
    elif "bandcamp" in url_lower:
        return "Bandcamp", "Bandcamp"
    elif "vimeo" in url_lower:
        return "Vimeo", "Vimeo"
    else:
        return "Web Link", "Link"

# ========== UI EMBEDS ==========

def create_progress_embed(video_title, progress, time_str, stage, session_id, interaction):
    filled = int(30 * progress / 100)
    empty = 30 - filled
    bar = "█" * filled + "░" * empty

    if progress < 25:
        color = 0x0088ff
    elif progress < 50:
        color = 0x00ffaa
    elif progress < 75:
        color = 0xff8800
    else:
        color = 0x00ff66

    embed = discord.Embed(
        title="THE MUSICIAN · Studio Dashboard",
        description=f"```\n{bar} {progress}%\n```\n"
                    f"STATUS · {stage}\n"
                    f"SONG\n`{video_title[:50]}`\n"
                    f"PROGRESS `{progress}%` · ETA `{time_str}`",
        color=color
    )
    embed.set_author(
        name="Live Session · Processing",
        icon_url="https://i.imgur.com/4MQI8Wq.png"
    )
    embed.set_footer(
        text=f"Session: {session_id} • {datetime.now().strftime('%I:%M %p')}",
        icon_url=interaction.user.display_avatar.url
    )
    embed.timestamp = datetime.now()

    return embed

def create_completed_embed(video_title, duration, midi_info, qwerty_line_count, qwerty_ctrls, size_str, process_time_str, usage_text, transpose, session_id, interaction):
    description = (
        f"```diff\n+ COMPLETED  ·  {duration}\n```\n"
        f"SONG\n`{video_title[:50]}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"MIDI `{format_duration(midi_info['duration'])}` · {midi_info['note_count']:,} notes\n"
        f"QWERTY `{qwerty_line_count}` lines · `{qwerty_ctrls}` CTRLs\n"
        f"Size `{size_str}` · Model `Small` · Transpose `{transpose:+d}`\n"
        f"Time `{process_time_str}` · Usage `{usage_text}`"
    )

    embed = discord.Embed(
        title="THE MUSICIAN · Studio Dashboard",
        description=description,
        color=discord.Color.from_rgb(0, 255, 100)
    )
    embed.set_author(
        name="Completed · Ready",
        icon_url="https://i.imgur.com/4MQI8Wq.png"
    )
    embed.set_footer(
        text=f"Session: {session_id} • {datetime.now().strftime('%I:%M %p')}",
        icon_url=interaction.user.display_avatar.url
    )
    embed.timestamp = datetime.now()

    return embed

# ========== QWERTY CONVERSION ==========

def midi_to_qwerty_pianoglow(midi_note, transpose=0):
    note = midi_note + transpose
    position = note % 12
    white_keys = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p']
    black_keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']
    black_positions = {1, 3, 6, 8, 10}
    if position in black_positions:
        black_map = {1: 0, 3: 1, 6: 2, 8: 3, 10: 4}
        idx = black_map.get(position, 0)
        return black_keys[idx % len(black_keys)]
    else:
        white_positions = [0, 2, 4, 5, 7, 9, 11]
        white_map = {pos: i for i, pos in enumerate(white_positions)}
        idx = white_map.get(position, 0)
        return white_keys[idx % len(white_keys)]

def generate_qwerty_sheet_pianoglow(midi_path, transpose=0, max_notes=8000):
    try:
        midi_data = pretty_midi.PrettyMIDI(midi_path)
        all_notes = []
        for instrument in midi_data.instruments:
            for note in instrument.notes:
                all_notes.append({
                    'pitch': note.pitch,
                    'start': note.start,
                    'end': note.end,
                    'velocity': note.velocity
                })
        all_notes.sort(key=lambda x: x['start'])
        if len(all_notes) > max_notes:
            all_notes = all_notes[:max_notes]
        time_groups = {}
        for note in all_notes:
            time_key = round(note['start'], 3)
            if time_key not in time_groups:
                time_groups[time_key] = []
            time_groups[time_key].append({
                'pitch': note['pitch'],
                'duration': note['end'] - note['start'],
                'velocity': note['velocity']
            })
        lines = []
        current_line = []
        line_length = 0
        max_line_length = 80
        ctrls = 0
        total_notes = 0
        sorted_times = sorted(time_groups.keys())
        for i, time_key in enumerate(sorted_times):
            notes_at_time = time_groups[time_key]
            qwerty_notes = []
            for note in notes_at_time:
                key = midi_to_qwerty_pianoglow(note['pitch'], transpose)
                qwerty_notes.append(key)
                total_notes += 1
            qwerty_notes.sort()
            if len(qwerty_notes) > 1:
                chord_str = '[' + ''.join(qwerty_notes) + ']'
                current_line.append(chord_str)
                line_length += len(chord_str)
                ctrls += 1
            else:
                current_line.append(qwerty_notes[0])
                line_length += 1
            if i < len(sorted_times) - 1:
                gap = sorted_times[i+1] - time_key
                if gap > 0.3:
                    current_line.append('  ')
                    line_length += 2
                elif gap > 0.15:
                    current_line.append(' ')
                    line_length += 1
            if line_length >= max_line_length:
                lines.append(''.join(current_line))
                current_line = []
                line_length = 0
        if current_line:
            lines.append(''.join(current_line))
        if not lines:
            lines = ["[no notes detected]"]
        total_lines = len(lines)
        header = f"Transpose: {transpose:+d} ({total_notes} shifts, {ctrls} CTRLs)"
        sheet_text = header + "\n\n" + "\n".join(lines)
        return {
            'text': sheet_text,
            'lines': lines,
            'total_notes': total_notes,
            'lines_count': total_lines,
            'header': header,
            'ctrls': ctrls
        }
    except Exception as e:
        print(f"QWERTY generation error: {e}")
        return {
            'text': "Transpose: 0 (0 shifts, 0 CTRLs)\n\n[Error generating sheet]",
            'lines': ["[Error]"],
            'total_notes': 0,
            'lines_count': 1,
            'header': "Transpose: 0 (0 shifts, 0 CTRLs)",
            'ctrls': 0
        }

# ========== UI COMPONENTS ==========

class TransposeSelect(Select):
    def __init__(self, session_id):
        options = []
        for i in range(-12, 13):
            label = f"{i:+d}" if i != 0 else "0 (Off)"
            default = i == 0
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(i),
                    default=default
                )
            )
        super().__init__(
            placeholder="Transpose",
            options=options,
            custom_id="transpose_select"
        )
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        value = int(self.values[0])
        session = get_session(self.session_id)
        if session:
            session['transpose'] = value
            store_session(self.session_id, session)
            embed = discord.Embed(
                title="Transpose Updated",
                description=f"Transpose set to **{value:+d}** semitones",
                color=discord.Color.from_rgb(50, 220, 100)
            )
            embed.set_footer(text="THE MUSICIAN · Settings")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class ChordSelect(Select):
    def __init__(self, session_id):
        options = [
            discord.SelectOption(label="On", value="on", default=True),
            discord.SelectOption(label="Off", value="off"),
            discord.SelectOption(label="Auto", value="auto")
        ]
        super().__init__(
            placeholder="Chord Detection",
            options=options,
            custom_id="chord_select"
        )
        self.session_id = session_id

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Chord Mode Updated",
            description=f"Chord detection set to **{self.values[0].upper()}**",
            color=discord.Color.from_rgb(50, 220, 100)
        )
        embed.set_footer(text="THE MUSICIAN · Settings")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class DashboardView(View):
    def __init__(self, session_id=None, title=None):
        super().__init__(timeout=600)
        self.session_id = session_id
        self.title = title
        self.add_item(TransposeSelect(session_id))
        self.add_item(ChordSelect(session_id))

    @discord.ui.button(label="Reprocess", style=discord.ButtonStyle.primary, row=2)
    async def reprocess(self, interaction: discord.Interaction, button: Button):
        if not self.session_id:
            await interaction.response.send_message("No active session.", ephemeral=True)
            return
        session = get_session(self.session_id)
        if not session:
            await interaction.response.send_message("Session expired.", ephemeral=True)
            return
        modal = AdvancedSettingsModal(self.session_id, session)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Analyze", style=discord.ButtonStyle.secondary, row=2)
    async def analyze(self, interaction: discord.Interaction, button: Button):
        if not self.session_id:
            await interaction.response.send_message("No active session.", ephemeral=True)
            return
        session = get_session(self.session_id)
        if session:
            embed = discord.Embed(
                title="Audio Analysis",
                description=f"QWERTY\n```\n{session.get('qwerty_header', 'N/A')}\n```\n"
                            f"MIDI\n"
                            f"Notes: `{session.get('note_count', 0):,}`\n"
                            f"Duration: `{format_duration(session.get('duration', 0))}`",
                color=discord.Color.from_rgb(100, 200, 255)
            )
            embed.set_footer(text="THE MUSICIAN · Analytics")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Session expired.", ephemeral=True)

    @discord.ui.button(label="Save Preset", style=discord.ButtonStyle.secondary, row=2)
    async def save_preset(self, interaction: discord.Interaction, button: Button):
        modal = SavePresetModal(self.session_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Load Preset", style=discord.ButtonStyle.secondary, row=2)
    async def load_preset(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="Load Preset",
            description="Available presets:\n```\n1. Piano Solo\n2. Bass Boost\n3. Ambient\n4. Classical\n```",
            color=discord.Color.from_rgb(100, 200, 255)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, row=2)
    async def close(self, interaction: discord.Interaction, button: Button):
        if self.session_id:
            delete_session(self.session_id)
        await interaction.response.send_message("Session closed.", ephemeral=True)
        self.stop()

class SavePresetModal(Modal):
    def __init__(self, session_id):
        super().__init__(title="Save Preset")
        self.session_id = session_id
        self.preset_name = TextInput(label="Preset Name", placeholder="e.g., Piano Solo", required=True, max_length=50)
        self.add_item(self.preset_name)
        self.transpose_value = TextInput(label="Transpose", placeholder="-12 to +12", default="0", required=False, max_length=3)
        self.add_item(self.transpose_value)
        self.chord_mode = TextInput(label="Chord Mode", placeholder="on/off/auto", default="on", required=False, max_length=5)
        self.add_item(self.chord_mode)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Preset Saved",
            description=f"**{self.preset_name.value}**\nTranspose: `{self.transpose_value.value}`\nChord: `{self.chord_mode.value}`",
            color=discord.Color.from_rgb(50, 220, 100)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

class AdvancedSettingsModal(Modal):
    def __init__(self, session_id, session_data):
        super().__init__(title="Advanced Settings")
        self.session_id = session_id
        self.session_data = session_data
        self.transpose = TextInput(label="Transpose", placeholder="-12 to +12", default="0", required=False, max_length=5)
        self.add_item(self.transpose)
        self.offset = TextInput(label="Start Offset", placeholder="seconds", default="0", required=False, max_length=5)
        self.add_item(self.offset)
        self.duration = TextInput(label="Duration", placeholder="seconds", default="0", required=False, max_length=5)
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            transpose_val = int(self.transpose.value) if self.transpose.value.strip() else 0
            transpose_val = max(-12, min(12, transpose_val))
        except ValueError:
            transpose_val = 0
        try:
            offset_val = float(self.offset.value) if self.offset.value.strip() else 0
        except ValueError:
            offset_val = 0
        try:
            duration_val = float(self.duration.value) if self.duration.value.strip() else 0
        except ValueError:
            duration_val = 0

        if self.session_id:
            session = get_session(self.session_id)
            if session:
                session['transpose'] = transpose_val
                store_session(self.session_id, session)
                embed = discord.Embed(
                    title="Reprocess Complete",
                    description=f"**Transpose:** `{transpose_val:+d}`\n**Offset:** `{offset_val}s`\n**Duration:** `{duration_val}s`",
                    color=discord.Color.from_rgb(50, 220, 100)
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        embed = discord.Embed(title="No Session", description="Session data missing.", color=discord.Color.from_rgb(255, 180, 50))
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== CORE FUNCTIONS ==========

def load_usage():
    try:
        with open(USAGE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_usage(usage):
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage, f, indent=2)

def get_user_limit(user_id, guild):
    member = guild.get_member(user_id)
    if not member:
        return FREE_LIMIT
    for role in member.roles:
        if role.name.lower() in ADMIN_ROLES:
            return UNLIMITED
    for role in member.roles:
        if role.name.lower() == "midi":
            return PREMIUM_LIMIT
    return FREE_LIMIT

def check_rate_limit(user_id, guild):
    usage = load_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    key = str(user_id)
    if key not in usage:
        usage[key] = {"date": today, "count": 0}
    if usage[key]["date"] != today:
        usage[key] = {"date": today, "count": 0}
    limit = get_user_limit(user_id, guild)
    if limit == UNLIMITED:
        return True, limit
    if usage[key]["count"] >= limit:
        return False, limit
    usage[key]["count"] += 1
    save_usage(usage)
    return True, limit

def get_user_usage(user_id):
    usage = load_usage()
    return usage.get(str(user_id), {}).get("count", 0)

def get_audio_duration(file_path):
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_file(file_path)
        return len(audio) / 1000.0
    except:
        return None

def get_midi_info(midi_path):
    try:
        midi_data = pretty_midi.PrettyMIDI(midi_path)
        notes = []
        total_duration = midi_data.get_end_time()
        for instrument in midi_data.instruments:
            for note in instrument.notes:
                notes.append(note)
        return {"note_count": len(notes), "duration": total_duration}
    except:
        return {"note_count": 0, "duration": 0}

def get_video_title(url):
    try:
        cmd = ["yt-dlp", "--get-title", url]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        title = result.stdout.strip()
        return title
    except Exception as e:
        print(f"Failed to get video title: {e}")
        return None

def sanitize_filename(title):
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = re.sub(r'\s+', ' ', sanitized)
    return sanitized.strip()

def download_audio(url, output_dir):
    output_template = os.path.join(output_dir, "audio.%(ext)s")
    try:
        cmd = ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", output_template, url]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)
        print(f"yt-dlp output: {result.stdout}")
        for f in os.listdir(output_dir):
            if f.endswith('.mp3'):
                return os.path.join(output_dir, f)
    except subprocess.TimeoutExpired:
        print("yt-dlp timed out after 5 minutes")
        return None
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp error: {e.stderr}")
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None
    return None

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ========== DUMMY WEB SERVER FOR RENDER ==========
async def start_web_server():
    """Dummy web server to keep Render happy."""
    try:
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/', lambda req: web.Response(text="OK", status=200))
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 10000)
        await site.start()
        print("Dummy web server running on port 10000")
    except Exception as e:
        print(f"Dummy web server error: {e}")

# ========== ON READY ==========
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"\nBot is in {len(bot.guilds)} guild(s):")
    for guild in bot.guilds:
        print(f"   {guild.name} (ID: {guild.id})")

    for guild in bot.guilds:
        if guild.id != ALLOWED_GUILD_ID:
            print(f"Leaving unauthorized server: {guild.name} (ID: {guild.id})")
            print(f"   This bot is locked to server ID: {ALLOWED_GUILD_ID}")
            await guild.leave()

    if has_ffmpeg():
        print("ffmpeg found")
    else:
        print("ffmpeg not found – downloading in background...")
        asyncio.create_task(download_ffmpeg_background())

    try:
        print("\nPre-loading transkun model...")
        import transkun
        print("Transkun model pre-loaded successfully!")
    except Exception as e:
        print(f"Transkun pre-load warning: {e}")

    try:
        guild = discord.Object(id=ALLOWED_GUILD_ID)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {ALLOWED_GUILD_ID}!")
    except Exception as e:
        print(f"Sync error: {e}")

    # Start dummy web server for Render
    asyncio.create_task(start_web_server())

async def download_ffmpeg_background():
    try:
        success = await ensure_ffmpeg_async()
        if success:
            print("ffmpeg downloaded and ready!")
        else:
            print("ffmpeg download failed. Will retry on first transcription.")
    except Exception as e:
        print(f"ffmpeg background download error: {e}")

# ========== SYNC COMMAND ==========
@bot.tree.command(name="sync", description="Force sync slash commands (Owner only)")
async def sync_commands(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        embed = discord.Embed(title="Unauthorized", description="Owner only.", color=discord.Color.from_rgb(255, 75, 75))
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        guild = discord.Object(id=ALLOWED_GUILD_ID)
        await bot.tree.sync(guild=guild)
        embed = discord.Embed(title="Synced", description="Slash commands synced.", color=discord.Color.from_rgb(50, 220, 100))
        await interaction.edit_original_response(embed=embed)
    except Exception as e:
        embed = discord.Embed(title="Sync Failed", description=f"```diff\n- {str(e)[:200]}\n```", color=discord.Color.from_rgb(255, 75, 75))
        await interaction.edit_original_response(embed=embed)

# ========== MAIN TRANSCRIPTION COMMAND ==========
@bot.tree.command(name="ttranscribe", description="Transcribe audio to MIDI + QWERTY")
@app_commands.describe(
    url="YouTube / TikTok / SoundCloud / Bandcamp / Vimeo link",
    file="Audio or video file",
    transpose="Transpose QWERTY output (-12 to +12, default: 0)"
)
async def ttranscribe(
    interaction: discord.Interaction,
    url: str = None,
    file: discord.Attachment = None,
    transpose: int = 0
):
    if not has_ffmpeg():
        await interaction.response.send_message("Downloading ffmpeg... Please wait...", ephemeral=True)
        success = await ensure_ffmpeg_async()
        if not success:
            embed = discord.Embed(title="FFmpeg Missing", description="Download failed. Please place `ffmpeg.exe` in the same folder.", color=discord.Color.from_rgb(255, 75, 75))
            await interaction.edit_original_response(content=None, embed=embed)
            return
        await interaction.edit_original_response(content="ffmpeg ready!")

    if interaction.guild.id != ALLOWED_GUILD_ID:
        embed = discord.Embed(title="Unauthorized", description=f"Your server: `{interaction.guild.id}`\nAllowed: `{ALLOWED_GUILD_ID}`", color=discord.Color.from_rgb(255, 75, 75))
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    transpose = max(-12, min(12, transpose))

    allowed, limit = check_rate_limit(interaction.user.id, interaction.guild)
    if not allowed:
        embed = discord.Embed(title="Daily Limit", description=f"You've hit **{limit}** transcriptions today.", color=discord.Color.from_rgb(255, 75, 75))
        embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not url and not file:
        embed = discord.Embed(title="Missing Input", description="Provide a **URL** or attach an **audio/video file**.", color=discord.Color.from_rgb(255, 180, 50))
        embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    start_time = time.time()
    video_title = None
    session_id = f"TM-{datetime.now().strftime('%Y%m%d')}-{str(interaction.user.id)[-4:]}"

    if url:
        source_type, platform_emoji = detect_platform(url)
    else:
        source_type, platform_emoji = "File Upload", "File"

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = None

            if file:
                ext = file.filename.split('.')[-1].lower()
                supported_formats = ['mp3', 'wav', 'flac', 'm4a', 'ogg', 'webm', 'mp4', 'mov', 'avi', 'mkv']
                if ext not in supported_formats:
                    embed = discord.Embed(title="Unsupported Format", description=f"`{ext}` not supported.", color=discord.Color.from_rgb(255, 75, 75))
                    embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                    await interaction.edit_original_response(embed=embed)
                    return

                embed = discord.Embed(title="Loading...", description=f"```\n{file.filename}\n```\nSize: `{format_bytes(file.size)}`\nSession: `{session_id}`", color=discord.Color.from_rgb(65, 150, 255))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                embed.set_footer(text=f"Session: {session_id}", icon_url=interaction.user.display_avatar.url)
                embed.timestamp = datetime.now()
                await interaction.edit_original_response(embed=embed)

                audio_path = os.path.join(tmpdir, f"audio.{ext}")
                await file.save(audio_path)
                source_type = "File Upload"
                if not video_title:
                    video_title = os.path.splitext(file.filename)[0]

            elif url:
                embed = discord.Embed(title="Connecting...", description=f"```\n{source_type}\n```\nSession: `{session_id}`", color=discord.Color.from_rgb(65, 150, 255))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                embed.set_footer(text=f"Session: {session_id}", icon_url=interaction.user.display_avatar.url)
                embed.timestamp = datetime.now()
                await interaction.edit_original_response(embed=embed)

                video_title = get_video_title(url)
                if video_title:
                    print(f"Video title: {video_title}")

                audio_path = download_audio(url, tmpdir)
                if not audio_path:
                    embed = discord.Embed(title="Failed", description="Could not extract audio. Try uploading the file directly.", color=discord.Color.from_rgb(255, 75, 75))
                    embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                    await interaction.edit_original_response(embed=embed)
                    return

            if not video_title:
                video_title = f"transcription-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            if not os.path.exists(audio_path):
                embed = discord.Embed(title="Error", description="Audio file not found.", color=discord.Color.from_rgb(255, 75, 75))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                await interaction.edit_original_response(embed=embed)
                return

            audio_duration = get_audio_duration(audio_path)
            duration_str = format_duration(audio_duration) if audio_duration else "Unknown"
            estimated_seconds = audio_duration * ESTIMATE_FACTOR if audio_duration else 300
            estimated_display = format_time_remaining(estimated_seconds)
            audio_size = os.path.getsize(audio_path)

            embed = discord.Embed(title="Transcribing...", description=f"```\n{video_title[:80]}\n```\nSource: `{source_type}`\nLength: `{duration_str}`\nTranspose: `{transpose:+d}`\nETA: `~{estimated_display}`", color=discord.Color.from_rgb(255, 200, 50))
            embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
            embed.set_footer(text=f"Session: {session_id} • {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            embed.timestamp = datetime.now()
            await interaction.edit_original_response(embed=embed)

            tmp_midi_path = os.path.join(tmpdir, "output.mid")
            cmd = ["transkun", audio_path, tmp_midi_path, "--device", "cpu"]
            print(f"Running: {' '.join(cmd)}")

            timer_stop = False

            try:
                async def timer_loop():
                    nonlocal timer_stop
                    remaining = estimated_seconds
                    start_time_timer = time.time()
                    updates = 0
                    max_updates = 600
                    if remaining < 30:
                        remaining = 60

                    while remaining > 0 and not timer_stop and updates < max_updates:
                        elapsed = time.time() - start_time_timer
                        remaining = max(0, estimated_seconds - elapsed)
                        if estimated_seconds > 0:
                            progress = min(100, int((elapsed / estimated_seconds) * 100))
                        else:
                            progress = 0
                        time_str = format_time_remaining(remaining) if remaining > 0 else "0:00"
                        if progress < 25:
                            stage = "Analyzing spectrum..."
                        elif progress < 50:
                            stage = "Detecting pitch..."
                        elif progress < 75:
                            stage = "Mapping to MIDI..."
                        else:
                            stage = "Finalizing..."

                        embed_progress = create_progress_embed(
                            video_title,
                            progress,
                            time_str,
                            stage,
                            session_id,
                            interaction
                        )
                        try:
                            await interaction.edit_original_response(embed=embed_progress)
                        except:
                            break
                        await asyncio.sleep(1)
                        updates += 1

                    if not timer_stop:
                        embed_progress = discord.Embed(
                            title="THE MUSICIAN · Studio Dashboard",
                            description="```diff\n+ COMPLETED\n```\n```\n████████████████████████████████████████ 100%\n```\n**Rendering final output...**",
                            color=discord.Color.from_rgb(0, 255, 100)
                        )
                        embed_progress.set_author(name="Completed · Finalizing", icon_url="https://i.imgur.com/4MQI8Wq.png")
                        embed_progress.set_footer(text=f"Session: {session_id} • Finalizing", icon_url=interaction.user.display_avatar.url)
                        embed_progress.timestamp = datetime.now()
                        try:
                            await interaction.edit_original_response(embed=embed_progress)
                        except:
                            pass

                timer_task = asyncio.create_task(timer_loop())

                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT_SECONDS
                )
                print(f"Transkun stdout: {result.stdout}")
                if result.stderr:
                    print(f"Transkun stderr: {result.stderr}")
                print(f"Transcription completed in {time.time() - start_time:.2f} seconds")

                timer_stop = True
                timer_task.cancel()
                try:
                    await timer_task
                except asyncio.CancelledError:
                    pass

            except subprocess.CalledProcessError as e:
                timer_stop = True
                print(f"Transkun failed: {e.stderr}")
                embed = discord.Embed(title="Failed", description=f"```diff\n- {e.stderr[:400]}\n```", color=discord.Color.from_rgb(255, 75, 75))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                await interaction.edit_original_response(embed=embed)
                return

            except subprocess.TimeoutExpired:
                timer_stop = True
                print("Transcription timed out")
                embed = discord.Embed(title="Timeout", description="Audio too long. Try a shorter file.", color=discord.Color.from_rgb(255, 150, 50))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                await interaction.edit_original_response(embed=embed)
                return

            except Exception as e:
                timer_stop = True
                print(f"Unexpected error: {e}")
                embed = discord.Embed(title="Error", description=f"```diff\n- {str(e)[:400]}\n```", color=discord.Color.from_rgb(255, 75, 75))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                await interaction.edit_original_response(embed=embed)
                return

            if not os.path.exists(tmp_midi_path):
                embed = discord.Embed(title="Error", description="No MIDI file produced.", color=discord.Color.from_rgb(255, 75, 75))
                embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
                await interaction.edit_original_response(embed=embed)
                return

            midi_info = get_midi_info(tmp_midi_path)
            midi_size = os.path.getsize(tmp_midi_path)
            size_str = format_bytes(midi_size)

            safe_title = sanitize_filename(video_title)
            if not safe_title:
                safe_title = f"transcription-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            midi_bytes = open(tmp_midi_path, 'rb').read()

            qwerty_result = generate_qwerty_sheet_pianoglow(tmp_midi_path, transpose=transpose)
            qwerty_text = qwerty_result['text']
            qwerty_line_count = qwerty_result['lines_count']
            qwerty_note_count = qwerty_result['total_notes']
            qwerty_header = qwerty_result['header']
            qwerty_ctrls = qwerty_result.get('ctrls', 0)

            end_time = time.time()
            process_time = end_time - start_time
            process_mins = int(process_time // 60)
            process_secs = int(process_time % 60)
            process_time_str = f"{process_mins}m {process_secs}s" if process_mins > 0 else f"{process_secs}s"
            remaining = limit - get_user_usage(interaction.user.id)
            usage_text = "Unlimited" if limit == UNLIMITED else f"{remaining} / {limit}"

            store_session(session_id, {
                'midi_bytes': midi_bytes,
                'qwerty_text': qwerty_text,
                'qwerty_lines': qwerty_line_count,
                'qwerty_header': qwerty_header,
                'qwerty_ctrls': qwerty_ctrls,
                'note_count': midi_info['note_count'],
                'duration': midi_info['duration'],
                'title': safe_title,
                'source': source_type,
                'transpose': transpose,
                'qwerty_notes': qwerty_note_count
            })

            print(f"Sending MIDI ({size_str}) + QWERTY ({qwerty_line_count} lines, {qwerty_ctrls} CTRLs) to Discord...")

            embed = create_completed_embed(
                safe_title,
                duration_str,
                midi_info,
                qwerty_line_count,
                qwerty_ctrls,
                size_str,
                process_time_str,
                usage_text,
                transpose,
                session_id,
                interaction
            )

            midi_file = discord.File(io.BytesIO(midi_bytes), filename=f"{safe_title}.mid")
            qwerty_file = discord.File(io.BytesIO(qwerty_text.encode('utf-8')), filename=f"{safe_title}.txt")

            view = DashboardView(session_id, safe_title)

            await interaction.edit_original_response(content=None, embed=embed, view=view)
            await interaction.followup.send(files=[midi_file, qwerty_file])

            print(f"Files sent successfully for session {session_id}")

    except Exception as e:
        print(f"Critical error: {e}")
        embed = discord.Embed(title="Critical Error", description=f"```diff\n- {str(e)[:500]}\n```", color=discord.Color.from_rgb(255, 75, 75))
        embed.set_author(name="THE MUSICIAN", icon_url="https://i.imgur.com/4MQI8Wq.png")
        await interaction.edit_original_response(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
