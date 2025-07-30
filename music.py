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
        self.requester = data.get('requester')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, requester=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        data['requester'] = requester
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

    @classmethod
    async def search(cls, query, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False))
        return data.get('entries')

class GuildState:
    def __init__(self, bot, guild):
        self.bot = bot
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
            self.player_task = self.bot.loop.create_task(self.player_loop(ctx))

    async def player_loop(self, ctx):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            self.next_song.clear()

            song_to_play = self.current_song if self.loop_one and self.current_song else None
            if not song_to_play:
                try:
                    song_to_play = await asyncio.wait_for(self.queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    if self.channel:
                        await self.channel.send("⌛ 5분 동안 대기열에 다음 곡이 없어 채널을 나갑니다.")
                    cog = self.bot.get_cog('음악')
                    return await cog.cleanup(self.guild)

            self.current_song = song_to_play
            if self.loop and not self.loop_one:
                await self.queue.put(self.current_song)

            source = await YTDLSource.from_url(self.current_song['webpage_url'], loop=self.bot.loop, stream=True, requester=self.current_song['requester'])
            self.guild.voice_client.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.next_song.set))
            
            embed = discord.Embed(title="🎵 재생 시작", description=f"[{source.title}]({source.url})", color=discord.Color.green())
            embed.set_thumbnail(url=source.thumbnail)
            embed.set_footer(text=f"요청: {source.requester}")
            await self.channel.send(embed=embed)
            
            await self.next_song.wait()

class Music(commands.Cog, name="음악"):
    """
    유튜브 음악 재생과 관련된 명령어 그룹입니다.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states = {}

    def get_guild_state(self, guild) -> GuildState:
        if guild.id not in self.guild_states:
            self.guild_states[guild.id] = GuildState(self.bot, guild)
        return self.guild_states[guild.id]

    async def cleanup(self, guild):
        if guild.id in self.guild_states:
            state = self.get_guild_state(guild)
            if state.player_task: state.player_task.cancel()
            del self.guild_states[guild.id]
        if guild.voice_client:
            await guild.voice_client.disconnect()
            
    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.state = self.get_guild_state(ctx.guild)
    
    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure): return
        print(f"Music Cog에서 오류 발생: {error}", file=sys.stderr)
        traceback.print_exc()
        await ctx.send(f"🎵 음악 기능 중 오류가 발생했습니다: `{error}`")

    @commands.command(name='들어와', aliases=['join'])
    async def _join(self, ctx: commands.Context):
        """봇을 현재 사용자가 있는 음성 채널로 초대합니다."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("먼저 음성 채널에 참가해주세요.")
        
        destination = ctx.author.voice.channel
        if ctx.voice_client: await ctx.voice_client.move_to(destination)
        else: await destination.connect()
        await ctx.send(f"✅ **{destination}** 채널에 연결했습니다.")

    @commands.command(name='나가', aliases=['leave', 'stop'])
    async def _leave(self, ctx: commands.Context):
        """봇을 음성 채널에서 내보내고 대기열을 초기화합니다."""
        await self.cleanup(ctx.guild)
        await ctx.send("🔌 음성 채널에서 나갔습니다.")

    @commands.command(name='불러봐', aliases=['p', '재생', 'play'])
    async def _play(self, ctx: commands.Context, *, query: str):
        """노래 제목이나 URL을 입력하여 노래를 재생하거나 대기열에 추가합니다."""
        if not ctx.voice_client: await ctx.invoke(self._join)
        async with ctx.typing():
            info = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
            if not info or not info.get('entries'): return await ctx.send("❌ 검색 결과가 없습니다.")
            song = info['entries'][0]
            song['requester'] = ctx.author.display_name
            await ctx.state.queue.put(song)
            await ctx.send(f"📌 **{song['title']}**을(를) 대기열에 추가했습니다.")
            ctx.state.start_player_task(ctx)

    @commands.command(name='검색', aliases=['search'])
    async def _search(self, ctx: commands.Context, *, query: str):
        """노래를 검색하여 목록에서 선택해 재생합니다."""
        if not ctx.voice_client: await ctx.invoke(self._join)
        async with ctx.typing():
            results = await YTDLSource.search(query, loop=self.bot.loop)
            if not results: return await ctx.send("❌ 검색 결과가 없습니다.")

        embed = discord.Embed(title="🔎 검색 결과", description="재생할 노래의 번호를 30초 안에 입력해주세요.", color=0x3498DB)
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
            await ctx.state.queue.put(song)
            await ctx.send(f"📌 **{song['title']}**을(를) 대기열에 추가했습니다.")
            ctx.state.start_player_task(ctx)
            await search_msg.delete()
            try: await reply.delete()
            except discord.Forbidden: pass
        except asyncio.TimeoutError:
            await search_msg.delete(); await ctx.send("시간이 초과되었습니다.")

    @commands.command(name='스킵', aliases=['skip'])
    async def _skip(self, ctx: commands.Context):
        """현재 재생 중인 노래를 건너뜁니다."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ 다음 곡으로 스킵합니다.")

    @commands.command(name='일시정지', aliases=['pause'])
    async def _pause(self, ctx: commands.Context):
        """노래를 일시정지합니다."""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ 노래를 일시정지합니다.")

    @commands.command(name='재개', aliases=['resume'])
    async def _resume(self, ctx: commands.Context):
        """일시정지된 노래를 다시 재생합니다."""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ 노래를 다시 재생합니다.")

    @commands.command(name='대기열', aliases=['q', 'queue'])
    async def _queue(self, ctx: commands.Context):
        """현재 대기열에 있는 노래 목록을 보여줍니다."""
        embed = discord.Embed(title="📜 대기열", color=discord.Color.blue())
        
        if ctx.state.current_song:
            dur_sec = ctx.state.current_song.get('duration', 0)
            duration = f"{dur_sec // 60}:{dur_sec % 60:02d}"
            embed.add_field(name="🎧 현재 재생 중", value=f"[{ctx.state.current_song['title']}]({ctx.state.current_song['webpage_url']}) | `{duration}`", inline=False)
        
        if ctx.state.queue.empty():
            embed.description = "대기열이 비어있습니다."
        else:
            queue_list = [f"`{i+1}.` {song['title']}" for i, song in enumerate(list(ctx.state.queue._queue)[:10])]
            embed.add_field(name="▶️ 다음 곡들", value="\n".join(queue_list), inline=False)
            if ctx.state.queue.qsize() > 10:
                embed.set_footer(text=f"... 외 {ctx.state.queue.qsize() - 10}곡")
        await ctx.send(embed=embed)

    @commands.command(name='현재곡', aliases=['np', 'nowplaying'])
    async def _nowplaying(self, ctx: commands.Context):
        """현재 재생 중인 노래의 정보를 보여줍니다."""
        if not ctx.state.current_song: return await ctx.send("재생 중인 노래가 없습니다.")
        song = ctx.state.current_song
        duration = f"{song['duration'] // 60}:{song['duration'] % 60:02d}" if song.get('duration') else "N/A"
        embed = discord.Embed(title=song['title'], url=song['webpage_url'], description=f"**길이:** {duration}\n**요청자:** {song.get('requester', '알 수 없음')}", color=discord.Color.purple())
        embed.set_thumbnail(url=song.get('thumbnail'))
        await ctx.send(embed=embed)
        
    @commands.command(name='반복', aliases=['loop'])
    async def _loop(self, ctx: commands.Context):
        """전체 대기열 반복을 켜거나 끕니다."""
        ctx.state.loop = not ctx.state.loop
        ctx.state.loop_one = False
        await ctx.send(f"🔁 전체 반복: **{'켜짐' if ctx.state.loop else '꺼짐'}**")

    @commands.command(name='한곡반복', aliases=['loopone'])
    async def _loopone(self, ctx: commands.Context):
        """현재 노래 한 곡 반복을 켜거나 끕니다."""
        ctx.state.loop_one = not ctx.state.loop_one
        ctx.state.loop = False
        await ctx.send(f"🔂 한 곡 반복: **{'켜짐' if ctx.state.loop_one else '꺼짐'}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))