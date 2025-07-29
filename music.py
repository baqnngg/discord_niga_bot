# music.py
import asyncio
import discord
import yt_dlp
import traceback
import sys
from discord.ext import commands

# --- 옵션 설정 ---
ytdl_format_options = {
    'format': 'bestaudio/best', 'outtmpl': 'downloads/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False,
    'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0',
}
ffmpeg_options = { 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn' }
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def search(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False))
        return data.get('entries')

class GuildState:
    """서버별 음악 재생 상태를 관리하는 클래스"""
    def __init__(self, bot_loop, guild):
        self.bot_loop = bot_loop
        self.guild = guild
        self.channel = None
        self.queue = asyncio.Queue()
        self.next_song = asyncio.Event()
        self.current_song = None
        self.player_task = None
        self.loop = False
        self.loop_one = False

    def start_player_task(self, ctx):
        self.channel = ctx.channel
        if not self.player_task or self.player_task.done():
            self.player_task = self.bot_loop.create_task(self.player_loop(ctx))

    async def player_loop(self, ctx):
        """노래를 순차적으로 재생하는 메인 루프"""
        while True:
            self.next_song.clear()

            if not self.loop_one:
                try:
                    self.current_song = await asyncio.wait_for(self.queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    if self.channel:
                        await self.channel.send("⌛ 5분 동안 대기열에 다음 곡이 없어 채널을 나갑니다.")
                    cog = self.guild.bot.get_cog('Music')
                    await cog.cleanup(ctx)
                    return
            
            if self.loop and self.current_song:
                await self.queue.put(self.current_song)

            source = await YTDLSource.from_url(self.current_song['webpage_url'], loop=self.bot_loop)
            self.guild.voice_client.play(source, after=lambda e: self.bot_loop.call_soon_threadsafe(self.next_song.set))
            
            embed = discord.Embed(title="🎵 재생 시작", description=f"[{source.title}]({source.url})", color=discord.Color.green())
            embed.set_thumbnail(url=source.thumbnail)
            embed.set_footer(text=f"요청: {self.current_song.get('requester', '알 수 없음')}")
            await self.channel.send(embed=embed)
            
            await self.next_song.wait()
            if not self.loop_one:
                self.current_song = None

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states = {}

    def get_guild_state(self, ctx: commands.Context) -> GuildState:
        if ctx.guild.id not in self.guild_states:
            self.guild_states[ctx.guild.id] = GuildState(self.bot.loop, ctx.guild)
        return self.guild_states[ctx.guild.id]
        
    async def cleanup(self, ctx: commands.Context):
        state = self.get_guild_state(ctx)
        if state.player_task: state.player_task.cancel()
        if ctx.guild.voice_client: await ctx.guild.voice_client.disconnect()
        if ctx.guild.id in self.guild_states: del self.guild_states[ctx.guild.id]
    
    async def voice_channel_check(ctx: commands.Context):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("먼저 음성 채널에 참가해주세요.")
            return False
        return True

    async def is_playing_check(ctx: commands.Context):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("재생 중인 노래가 없습니다.")
            return False
        return True

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            return
        print(f"Music Cog에서 오류 발생: {error}", file=sys.stderr)
        traceback.print_exc()
        await ctx.send(f"🎵 음악 기능 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

    @commands.command(name='들어와', aliases=['join'])
    @commands.check(voice_channel_check)
    async def 들어와(self, ctx: commands.Context):
        if ctx.voice_client is None:
            await ctx.author.voice.channel.connect()
        await ctx.send(f"✅ **{ctx.voice_client.channel}** 채널에 연결했습니다.")

    @commands.command(name='나가', aliases=['leave', 'stop'])
    @commands.check(voice_channel_check)
    async def 나가(self, ctx: commands.Context):
        await self.cleanup(ctx)
        await ctx.send("🔌 음성 채널에서 나갔습니다.")

    @commands.command(name='불러봐', aliases=['p', '재생', 'play'])
    @commands.check(voice_channel_check)
    async def 불러봐(self, ctx: commands.Context, *, query: str):
        state = self.get_guild_state(ctx)
        if ctx.voice_client is None: await ctx.author.voice.channel.connect()
        async with ctx.typing():
            info = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
            if not info or not info.get('entries'): return await ctx.send("❌ 검색 결과가 없습니다.")
            song = info['entries'][0]
            song['requester'] = ctx.author.display_name
            await state.queue.put(song)
            await ctx.send(f"📌 **{song['title']}**을(를) 대기열에 추가했습니다.")
            state.start_player_task(ctx)

    @commands.command(name='검색', aliases=['search'])
    @commands.check(voice_channel_check)
    async def 검색(self, ctx: commands.Context, *, query: str):
        state = self.get_guild_state(ctx)
        if ctx.voice_client is None: await ctx.author.voice.channel.connect()
        async with ctx.typing():
            results = await YTDLSource.search(query, loop=self.bot.loop)
            if not results: return await ctx.send("❌ 검색 결과가 없습니다.")

        embed = discord.Embed(title="🔎 검색 결과", description="재생할 노래의 번호를 입력해주세요.", color=0x3498DB)
        for i, entry in enumerate(results[:5]):
            duration = f"{entry['duration'] // 60}:{entry['duration'] % 60:02d}" if entry.get('duration') else "N/A"
            embed.add_field(name=f"{i+1}. {entry['title']}", value=f"길이: {duration}", inline=False)
        
        search_msg = await ctx.send(embed=embed)
        def check(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=30.0)
            index = int(reply.content) - 1
            if not 0 <= index < len(results[:5]): return await ctx.send("잘못된 번호입니다.")
            
            song = results[index]
            song['requester'] = ctx.author.display_name
            await state.queue.put(song)
            await ctx.send(f"📌 **{song['title']}**을(를) 대기열에 추가했습니다.")
            state.start_player_task(ctx)
            await search_msg.delete()
            try: await reply.delete()
            except discord.Forbidden: pass
        except asyncio.TimeoutError:
            await search_msg.delete(); await ctx.send("시간이 초과되었습니다.")

    @commands.command(name='스킵', aliases=['skip'])
    @commands.check(voice_channel_check)
    @commands.check(is_playing_check)
    async def 스킵(self, ctx: commands.Context):
        ctx.voice_client.stop()
        await ctx.send("⏭️ 다음 곡으로 스킵합니다.")

    @commands.command(name='일시정지', aliases=['pause'])
    @commands.check(voice_channel_check)
    @commands.check(is_playing_check)
    async def 일시정지(self, ctx: commands.Context):
        ctx.voice_client.pause()
        await ctx.send("⏸️ 노래를 일시정지합니다.")

    @commands.command(name='재개', aliases=['resume'])
    @commands.check(voice_channel_check)
    async def 재개(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 노래를 다시 재생합니다.")
        else:
            await ctx.send("일시정지된 노래가 없습니다.")

    @commands.command(name='대기열', aliases=['q', 'queue'])
    @commands.check(voice_channel_check)
    async def 대기열(self, ctx: commands.Context):
        state = self.get_guild_state(ctx)
        embed = discord.Embed(title="📜 대기열", color=discord.Color.blue())
        
        if state.current_song:
            dur_sec = state.current_song.get('duration', 0)
            duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
            embed.add_field(name="🎧 현재 재생 중", value=f"[{state.current_song['title']}]({state.current_song['webpage_url']}) | `{duration}`", inline=False)
        
        if state.queue.empty():
            embed.description = "대기열이 비어있습니다."
        else:
            queue_list = []
            temp_list = list(state.queue._queue)
            for i, song in enumerate(temp_list[:10]):
                queue_list.append(f"`{i+1}.` {song['title']}")
            
            embed.add_field(name="▶️ 다음 곡들", value="\n".join(queue_list), inline=False)
            if state.queue.qsize() > 10:
                embed.set_footer(text=f"... 외 {state.queue.qsize() - 10}곡")
        await ctx.send(embed=embed)

    @commands.command(name='현재곡', aliases=['np', 'nowplaying'])
    @commands.check(voice_channel_check)
    @commands.check(is_playing_check)
    async def 현재곡(self, ctx: commands.Context):
        state = self.get_guild_state(ctx)
        song = state.current_song
        duration = f"{song['duration'] // 60}:{song['duration'] % 60:02d}" if song.get('duration') else "N/A"
        embed = discord.Embed(title=song['title'], url=song['webpage_url'], description=f"**길이:** {duration}\n**요청자:** {song.get('requester', '알 수 없음')}", color=discord.Color.purple())
        embed.set_thumbnail(url=song.get('thumbnail'))
        await ctx.send(embed=embed)
        
    @commands.command(name='반복', aliases=['loop'])
    @commands.check(voice_channel_check)
    async def 반복(self, ctx: commands.Context):
        state = self.get_guild_state(ctx)
        state.loop = not state.loop
        state.loop_one = False
        await ctx.send(f"🔁 전체 반복: **{'켜짐' if state.loop else '꺼짐'}**")

    @commands.command(name='한곡반복', aliases=['loopone'])
    @commands.check(voice_channel_check)
    async def 한곡반복(self, ctx: commands.Context):
        state = self.get_guild_state(ctx)
        state.loop_one = not state.loop_one
        state.loop = False
        await ctx.send(f"🔂 한 곡 반복: **{'켜짐' if state.loop_one else '꺼짐'}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))