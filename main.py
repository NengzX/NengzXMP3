
import asyncio
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

import yt_dlp
from dotenv import load_dotenv
from telegram import Update, Chat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class YTMPConverter:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cleanup_interval = 300  # 5 minutes
        self.start_cleanup_scheduler()
    
    def start_cleanup_scheduler(self):
        """Start background thread to clean up old files"""
        def cleanup_worker():
            while True:
                self.cleanup_old_files()
                time.sleep(self.cleanup_interval)
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def cleanup_old_files(self):
        """Remove files older than 10 minutes"""
        try:
            current_time = time.time()
            for file_path in Path(self.temp_dir).glob("*"):
                if current_time - file_path.stat().st_mtime > 600:  # 10 minutes
                    file_path.unlink()
                    logger.info(f"Cleaned up old file: {file_path}")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    def download_audio(self, url):
        """Download audio from various platforms"""
        try:
            # Generate unique filename
            timestamp = str(int(time.time()))
            output_path = os.path.join(self.temp_dir, f"audio_{timestamp}")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{output_path}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'extractaudio': True,
                'audioformat': 'mp3',
                'noplaylist': True,
                'quiet': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get title
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Unknown')
                duration = info.get('duration', 0)
                
                # Check duration (limit to 30 minutes for Telegram)
                if duration and duration > 1800:  # 30 minutes
                    raise Exception("Video is too long (max 30 minutes)")
                
                # Download the audio
                ydl.download([url])
                
                # Find the downloaded file
                mp3_file = f"{output_path}.mp3"
                if os.path.exists(mp3_file):
                    return mp3_file, title
                else:
                    # Sometimes the extension might be different
                    for ext in ['mp3', 'm4a', 'webm', 'ogg']:
                        potential_file = f"{output_path}.{ext}"
                        if os.path.exists(potential_file):
                            return potential_file, title
                    
                    raise Exception("Downloaded file not found")
                    
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            raise e
    
    def cleanup_file(self, file_path, delay=30):
        """Schedule file deletion after delay"""
        def delete_file():
            time.sleep(delay)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Removed temporary file: {file_path}")
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
        
        threading.Thread(target=delete_file, daemon=True).start()

# Initialize converter
converter = YTMPConverter()

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Set up command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def is_admin_or_owner(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check if user is admin or owner in group/channel"""
        chat = update.effective_chat
        user = update.effective_user
        
        # If it's a private chat, always allow
        if chat.type == Chat.PRIVATE:
            return True
        
        try:
            # Get user's status in the chat
            member = await context.bot.get_chat_member(chat.id, user.id)
            
            # Check if user is admin or owner
            if member.status in ['administrator', 'creator']:
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_type = update.effective_chat.type
        
        if chat_type == Chat.PRIVATE:
            welcome_message = """
🎵 **Professional YT-MP3 Converter Bot**

Welcome! Send me a video URL from YouTube, Vimeo, SoundCloud, or 1000+ other sites, and I'll convert it to MP3 for you!

**Features:**
✅ High-quality MP3 conversion (192 kbps)
✅ Supports 1000+ video platforms
✅ Works in groups and channels (admin only)
✅ Fast and reliable processing
✅ Automatic file cleanup
✅ Free to use

**How to use:**
• **Private chat**: Just send me any video URL
• **Groups/Channels**: Only admins can use the bot

Type /help for more information.
            """
        else:
            welcome_message = """
🎵 **YT-MP3 Converter Bot for Groups/Channels**

Hello! I can convert video URLs to MP3 files.

**Important:** Only group/channel admins can use this bot.

Send any video URL and I'll convert it to MP3!
            """
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        chat_type = update.effective_chat.type
        
        help_message = """
🔧 **How to use this bot:**

1. Find a video on YouTube, Vimeo, SoundCloud, etc.
2. Copy the video URL
3. Send the URL to this bot
4. Wait for the MP3 file (usually 30-60 seconds)
5. Download and enjoy!

**Supported platforms:**
• YouTube • Vimeo • SoundCloud • TikTok
• Instagram • Facebook • And 1000+ more sites!

**Limitations:**
• Maximum video length: 30 minutes
• Files are automatically deleted after sending
"""

        if chat_type != Chat.PRIVATE:
            help_message += "\n**Group/Channel Usage:**\n• Only admins and owners can use this bot\n• Perfect for music sharing in communities"
        
        help_message += """
**Commands:**
/start - Start the bot
/help - Show this help message

For support or issues, contact the bot administrator.
        """
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all text messages"""
        # Check if message contains a URL
        text = update.message.text.strip()
        
        # Basic URL validation
        if not (text.startswith('http://') or text.startswith('https://')):
            return  # Ignore non-URL messages
        
        # Check admin permissions for groups/channels
        if update.effective_chat.type != Chat.PRIVATE:
            is_admin = await self.is_admin_or_owner(update, context)
            if not is_admin:
                await update.message.reply_text(
                    "❌ Only group/channel admins can use this bot.",
                    reply_to_message_id=update.message.message_id
                )
                return
        
        await self.handle_url(update, context, text)
    
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
        """Handle URL processing"""
        user_id = update.effective_user.id
        chat_type = update.effective_chat.type
        
        # Send processing message
        processing_msg = await update.message.reply_text(
            "🔄 Processing your request...\nThis may take a few moments.",
            reply_to_message_id=update.message.message_id if chat_type != Chat.PRIVATE else None
        )
        
        try:
            # Download and convert audio
            file_path, title = converter.download_audio(url)
            
            # Check file size (Telegram limit is 50MB)
            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await processing_msg.edit_text(
                    "❌ File is too large for Telegram (max 50MB). Please try a shorter video."
                )
                converter.cleanup_file(file_path, delay=5)
                return
            
            # Update status
            await processing_msg.edit_text("📤 Uploading MP3 file...")
            
            # Prepare caption based on chat type
            if chat_type == Chat.PRIVATE:
                caption = f"🎵 **{title}**\n\nConverted by YT-MP3 Bot"
            else:
                admin_name = update.effective_user.first_name
                caption = f"🎵 **{title}**\n\nRequested by: {admin_name}\nConverted by YT-MP3 Bot"
            
            # Send the audio file
            with open(file_path, 'rb') as audio_file:
                await update.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer="YT-MP3 Converter",
                    caption=caption,
                    parse_mode='Markdown',
                    reply_to_message_id=update.message.message_id if chat_type != Chat.PRIVATE else None
                )
            
            # Delete processing message
            await processing_msg.delete()
            
            # For groups/channels, delete the original URL message for cleanliness
            if chat_type != Chat.PRIVATE:
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id
                    )
                except Exception as e:
                    logger.warning(f"Could not delete original message: {e}")
            
            # Schedule file cleanup
            converter.cleanup_file(file_path, delay=60)
            
            logger.info(f"Successfully converted and sent: {title} to user {user_id} in {chat_type}")
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Conversion error for user {user_id}: {error_message}")
            
            # Handle specific errors
            if "Video is too long" in error_message:
                await processing_msg.edit_text(
                    "❌ Video is too long (maximum 30 minutes allowed)"
                )
            elif "not available" in error_message.lower():
                await processing_msg.edit_text(
                    "❌ Video not available or private. Please check the URL."
                )
            elif "unsupported" in error_message.lower():
                await processing_msg.edit_text(
                    "❌ Unsupported platform or URL format."
                )
            else:
                await processing_msg.edit_text(
                    f"❌ Error processing your request: {error_message}\n\n"
                    "Please try again or contact support if the issue persists."
                )
    
    async def run(self):
        """Start the bot"""
        logger.info("Starting Telegram bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep the bot running
        while True:
            await asyncio.sleep(1)

async def main():
    """Main function to run the bot"""
    # Get bot token from environment variable
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token or bot_token == 'your_bot_token_here':
        logger.error("TELEGRAM_BOT_TOKEN not set or using default value!")
        logger.info("Please update your .env file with your actual bot token")
        logger.info("1. Go to @BotFather on Telegram")
        logger.info("2. Create a new bot with /newbot")
        logger.info("3. Copy the token and replace 'your_bot_token_here' in .env file")
        return
    
    # Create and run bot
    bot = TelegramBot(bot_token)
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
