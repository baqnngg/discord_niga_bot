import asyncio
import discord
import yt_dlp
from discord.ext import commands
import random
import stock  # 주식 시스템 파일
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
client = commands.Bot(command_prefix="!", intents=intents)

DAILY_REWARD = 10000
USER_FILE = "users.json"

class StockBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(self.auto_update_stock())  # 봇 시작 시 자동으로 주식 갱신

    async def auto_update_stock(self):
        await self.wait_until_ready()  # 봇이 준비될 때까지 대기
        while not self.is_closed():
            stock.update_stock_prices()
            print("📈 주식 가격이 자동 갱신되었습니다!")
            await asyncio.sleep(60)  # 30초마다 실행

# 봇 인스턴스 생성 (StockBot 클래스 사용)
client = StockBot(command_prefix="!", intents=intents)

# YouTube 다운로드 옵션 설정
ytdl_format_options = {
    'format': 'bestaudio/best',
    'quiet': True,
    'default_search': 'ytsearch',
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

queue = []  # 음악 재생 대기열

async def connect_to_voice_channel(ctx):
    if ctx.author.voice is None:
        await ctx.send("음성 채널에 먼저 들어가 주세요.")
        return None

    channel = ctx.author.voice.channel
    vc = ctx.voice_client

    if vc is None or not vc.is_connected():
        vc = await channel.connect()
        await ctx.send(f"{ctx.author.mention} 님의 채널에 접속했습니다!")
    return vc

@client.event
async def on_ready():
    print("봇이 준비되었습니다.")
    await client.change_presence(status=discord.Status.online, activity=discord.Game("음악 재생 및 주식 거래"))

# 🎵 음악 관련 명령어 ------------------------------------------------

@client.command(name='들어와')
async def 들어와(ctx):
    await connect_to_voice_channel(ctx)

@client.command(name='나가')
async def 나가(ctx):
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.send("🔌 봇이 음성 채널에서 나갔습니다.")
    else:
        await ctx.send("❌ 봇이 현재 음성 채널에 연결되어 있지 않습니다.")

@client.command(name='불러봐', aliases=['불러', 'p'])
async def 불러봐(ctx, *, title):
    vc = await connect_to_voice_channel(ctx)
    if vc is None:
        return

    async with ctx.typing():
        try:
            info = ytdl.extract_info(f"ytsearch:{title}", download=False)
            if 'entries' not in info or len(info['entries']) == 0:
                await ctx.send("⚠️ 검색 결과를 찾을 수 없습니다.")
                return

            video = info['entries'][0]
            url2 = video['url']
            song_title = video.get('title', 'Unknown Title')

            if vc.is_playing():
                queue.append((url2, song_title))
                await ctx.send(f"📌 **{song_title}**을(를) 대기열에 추가했습니다.")
                return

            vc.play(discord.FFmpegPCMAudio(url2, **ffmpeg_options), 
                    after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop))

            await ctx.send(f'🎵 **{song_title}**을(를) 재생합니다!')
        except yt_dlp.utils.DownloadError as e:
            await ctx.send(f"⚠️ 다운로드 오류 발생: {e}")
        except Exception as e:
            await ctx.send(f"⚠️ 오류 발생: {e}")

async def play_next(ctx):
    vc = ctx.voice_client
    if vc is None or not vc.is_connected():
        return

    if len(queue) > 0:
        url2, title = queue.pop(0)

        def after_playing(error):
            if error:
                print(f"Player error: {error}")
            asyncio.run_coroutine_threadsafe(play_next(ctx), client.loop)

        vc.play(discord.FFmpegPCMAudio(url2, **ffmpeg_options), after=after_playing)
        client.loop.create_task(ctx.send(f'🎵 현재 재생하는 곡 **{title}**'))
    else:
        client.loop.create_task(ctx.send("✅ 대기열이 비어 있습니다."))

@client.command(name='대기열')
async def 대기열(ctx):
    vc = ctx.voice_client

    if vc is None or not vc.is_connected():
        await ctx.send("❌ 봇이 음성 채널에 연결되어 있지 않습니다.")
        return

    current_song = None
    if vc.is_playing() and len(queue) > 0:
        current_song = queue[0][1]

    if len(queue) == 0:
        message = "📭 대기열이 비어 있습니다."
    else:
        queue_list = "\n".join([f"{idx+1}. {title}" for idx, (_, title) in enumerate(queue)])
        message = f"📜 **대기열 목록**:\n{queue_list}"

    if current_song:
        message = f"🎵 현재 재생 중: **{current_song}**\n\n" + message

    await ctx.send(message)

# 📈 주식 시스템 연동 ------------------------------------------------

@client.command(name='주식목록', aliases=['주식'])
async def 주식목록(ctx):
    """현재 주식 목록과 가격 확인 (정렬 수정, 소수점 2자리 유지)"""
    stocks = stock.stocks  # 현재 주식 데이터
    changes = stock.stock_changes  # 변동 내역 (가격 변동량, 변동 퍼센트 저장)

    stock_list = "📈 **현재 주식 목록** 📈\n```\n"
    stock_list += f"{'이름':<12}|{'가격':<12}|{'변동':<12}\n"
    stock_list += "-" * 42 + "\n"

    for name, price in stocks.items():
        change_amount, percent_change = changes.get(name, (0, 0))  # 변동 데이터 없으면 기본값 (0, 0)

        # 상승(🟥), 하락(🟦), 유지(➡)
        change_symbol = "🟥" if percent_change > 0 else ("🟦" if percent_change < 0 else "➡")
        change_str = f"{change_symbol} {percent_change:+.2f}%" if percent_change != 0 else " - "

        stock_list += f"{name:<12} | ${price:>11,.2f} | {change_str:>11}\n"

    stock_list += "```"
    await ctx.send(stock_list)

@client.command(name='주식구매')
async def 주식구매(ctx, 주식명: str, 수량: str):
    """주식 구매"""
    user_id = str(ctx.author.id)

    # "all" 입력 시 그대로 전달, 숫자면 정수로 변환
    if 수량.lower() != "all":
        if not 수량.isdigit():
            await ctx.send("❌ 수량은 숫자 또는 'all'이어야 합니다.")
            return
        수량 = int(수량)

    success, result = stock.buy_stock(user_id, 주식명, 수량)

    if success:
        await ctx.send(f"✅ {주식명} 주식 {수량}주를 구매했습니다. 현재 잔액: ${result:.2f}")
    else:
        await ctx.send(result)

@client.command(name="주식판매")
async def 주식판매(ctx, 주식명: str, 수량: str):
    user_id = str(ctx.author.id)
    if 수량.lower() == 'all':
        # 보유 주식 전량 가져오기
        amount = stock.get_user_stock_amount(user_id, 주식명)
        if amount == 0:
            await ctx.send("해당 주식을 보유하고 있지 않습니다.")
            return
        수량_int = amount
    else:
        try:
            수량_int = int(수량)
        except ValueError:
            await ctx.send("수량은 정수여야 합니다.")
            return

    result = stock.sell_stock(user_id, 주식명, 수량_int)
    await ctx.send(result)


@client.command(name='내자산', aliases=['내주식', '나'])
async def 내자산(ctx):
    """보유 주식 및 잔액 확인 (닉네임 사용)"""
    user_id = str(ctx.author.id)
    user_name = ctx.author.display_name
    result = stock.get_portfolio(user_id)
    await ctx.send(f"💰 **{user_name}님의 자산 현황** 💰{result}")

# @client.command(name='주식갱신')
# async def 주식갱신(ctx):
#     """관리자가 주식 가격 갱신"""
#     stock.update_stock_prices()
#     await ctx.send("📈 주식 가격이 갱신되었습니다!")

# 🎲 기타 명령어 ------------------------------------------------

@client.command(name="랭킹")
async def 랭킹(ctx):
    """개선된 랭킹 시스템 - 더 예쁘고 상세한 정보 제공"""
    users = stock.load_users()
    ranking_list = []

    for user_id, user_data in users.items():
        balance = user_data.get("balance", 0)
        total_stock_value = 0

        stocks_owned = user_data.get("stocks", {})
        for stock_name, qty in stocks_owned.items():
            if isinstance(qty, list):
                qty = int(qty[0])
            price = stock.stocks.get(stock_name, 0)
            if isinstance(price, list):
                price = float(price[0])
            total_stock_value += price * qty

        total_assets = balance + total_stock_value
        ranking_list.append((user_id, total_assets, balance, total_stock_value))

    # 자산 기준으로 정렬
    ranking_list.sort(key=lambda x: x[1], reverse=True)

    if not ranking_list:
        await ctx.send("📊 아직 등록된 사용자가 없습니다!")
        return

    # 상위 10명만 표시
    top_users = ranking_list[:10]
    
    # 임베드 메시지로 더 예쁘게 만들기
    embed = discord.Embed(
        title="🏆 주식왕 랭킹 🏆",
        description="*총 자산 = 현금 + 보유 주식 가치*",
        color=0xFFD700  # 금색
    )
    
    # 순위별 이모지와 색상
    rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    ranking_text = ""
    
    for i, (user_id, total_assets, balance, stock_value) in enumerate(top_users):

        member = ctx.guild.get_member(int(user_id))
        if member is None:
            try:
                member = await ctx.guild.fetch_member(int(user_id))
            except Exception:
                member = None

        if member:
            name = member.display_name
        else:
            try:
                user = await bot.fetch_user(int(user_id))
                name = user.name
            except Exception:
                # fallback
                user_stocks = users.get(user_id, {}).get("stocks", {})
                if user_stocks:
                    max_stock = max(user_stocks.items(), key=lambda x: int(x[1][0]))
                    stock_name = max_stock[0]
                    short_id = str(user_id)[-4:]
                    name = f"{stock_name} 투자자#{short_id}"
                else:
                    short_id = str(user_id)[-4:]
                    name = f"💼 외부 투자자#{short_id}"


        
        # 순위 이모지
        rank_emoji = rank_emojis[i] if i < len(rank_emojis) else f"{i+1}위"
        
        # 자산 비율 계산
        cash_ratio = (balance / total_assets * 100) if total_assets > 0 else 0
        stock_ratio = (stock_value / total_assets * 100) if total_assets > 0 else 0
        
        # 프로그레스 바 만들기 (간단한 버전)
        progress_bar = "▰" * min(10, int(total_assets / max(ranking_list[0][1], 1) * 10))
        progress_bar += "▱" * (10 - len(progress_bar))
        
        ranking_text += f"{rank_emoji} **{name}**\n"
        ranking_text += f"💰 총 자산: `₩{total_assets:,.0f}`\n"
        ranking_text += f"💵 현금: `₩{balance:,.0f}` ({cash_ratio:.1f}%)\n"
        ranking_text += f"📈 주식: `₩{stock_value:,.0f}` ({stock_ratio:.1f}%)\n"
        ranking_text += f"📊 {progress_bar}\n\n"
    
    embed.add_field(
        name="📋 순위표",
        value=ranking_text,
        inline=False
    )
    
    # 통계 정보 추가
    total_users = len(ranking_list)
    avg_assets = sum([assets for _, assets, _, _ in ranking_list]) / total_users if total_users > 0 else 0
    
    embed.add_field(
        name="📈 전체 통계",
        value=f"👥 총 참여자: {total_users}명\n📊 평균 자산: ₩{avg_assets:,.0f}",
        inline=True
    )
    
    # 현재 사용자 순위 찾기
    user_rank = None
    for i, (user_id, _, _, _) in enumerate(ranking_list):
        if user_id == str(ctx.author.id):
            user_rank = i + 1
            break
    
    if user_rank:
        embed.add_field(
            name="🎯 내 순위",
            value=f"{ctx.author.display_name}님은 **{user_rank}위**입니다!",
            inline=True
        )
    
    # 푸터 추가
    embed.set_footer(text=f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    await ctx.send(embed=embed)

# 추가: 개인 상세 정보 명령어
@client.command(name="내순위")
async def 내순위(ctx):
    """내 개인 순위와 상세 정보 확인"""
    user_id = str(ctx.author.id)
    users = stock.load_users()
    
    if user_id not in users:
        await ctx.send("❌ 아직 주식 시스템을 이용한 기록이 없습니다. `!출석`으로 시작해보세요!")
        return
    
    # 전체 랭킹 계산
    ranking_list = []
    for uid, user_data in users.items():
        balance = user_data.get("balance", 0)
        total_stock_value = 0
        
        stocks_owned = user_data.get("stocks", {})
        for stock_name, qty in stocks_owned.items():
            if isinstance(qty, list):
                qty = int(qty[0])
            price = stock.stocks.get(stock_name, 0)
            if isinstance(price, list):
                price = float(price[0])
            total_stock_value += price * qty
        
        total_assets = balance + total_stock_value
        ranking_list.append((uid, total_assets, balance, total_stock_value))
    
    ranking_list.sort(key=lambda x: x[1], reverse=True)
    
    # 내 순위 찾기
    my_rank = None
    my_data = None
    for i, (uid, assets, balance, stock_value) in enumerate(ranking_list):
        if uid == user_id:
            my_rank = i + 1
            my_data = (assets, balance, stock_value)
            break
    
    if my_rank is None:
        await ctx.send("❌ 순위 정보를 찾을 수 없습니다.")
        return
    
    total_assets, balance, stock_value = my_data
    
    # 임베드 생성
    embed = discord.Embed(
        title=f"📊 {ctx.author.display_name}님의 상세 정보",
        color=0x00FF00 if my_rank <= 3 else (0xFFFF00 if my_rank <= 10 else 0xFF0000)
    )
    
    # 순위에 따른 이모지
    if my_rank == 1:
        rank_emoji = "🥇"
    elif my_rank == 2:
        rank_emoji = "🥈"
    elif my_rank == 3:
        rank_emoji = "🥉"
    else:
        rank_emoji = "🏅"
    
    embed.add_field(
        name=f"{rank_emoji} 현재 순위",
        value=f"**{my_rank}위** / {len(ranking_list)}명",
        inline=True
    )
    
    embed.add_field(
        name="💰 총 자산",
        value=f"₩{total_assets:,.0f}",
        inline=True
    )
    
    embed.add_field(
        name="📈 자산 구성",
        value=f"💵 현금: ₩{balance:,.0f}\n📊 주식: ₩{stock_value:,.0f}",
        inline=True
    )
    
    # 상위권과의 차이
    if my_rank > 1:
        gap_to_top = ranking_list[0][1] - total_assets
        gap_to_prev = ranking_list[my_rank-2][1] - total_assets
        embed.add_field(
            name="🎯 격차 분석",
            value=f"1위와 차이: ₩{gap_to_top:,.0f}\n{my_rank-1}위와 차이: ₩{gap_to_prev:,.0f}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@client.command(name='재비뽑기', aliases=['재비', '뽑기'])
async def 재비뽑기(ctx, *이름들):
    if len(이름들) < 2:
        await ctx.send("2명 이상 입력해주세요! 예시: `!재비뽑기 철수 영희 민수`")
        return

    당첨자 = random.choice(이름들)
    await ctx.send(f"🎉 당첨자는 **{당첨자}** 입니다! 🎉")

@client.command(name='도움말')
async def 도움말(ctx):
    """사용 가능한 명령어 목록을 출력"""
    help_text = """
    **🎵 음악 명령어**
    `!들어와` - 봇을 음성 채널로 초대
    `!나가` - 봇을 음성 채널에서 내보냄
    `!불러봐 [노래 제목]` - 유튜브에서 노래를 검색하고 재생
    `!대기열` - 현재 대기열 확인

    **💹 주식 명령어**
    `!주식목록` - 현재 등록된 주식 목록을 확인
    `!주식구매 [주식명] [수량]` - 주식을 구매
    `!주식판매 [주식명] [수량]` - 보유한 주식을 판매
    `!주식정보 [주식명]` - 특정 주식의 현재 가격과 정보 조회
    `!내주식` - 사용자가 보유한 주식 목록 확인
    `!주식변동` - 랜덤으로 주가 변동 (관리자 전용)

    **🎲 기타 명령어**
    `!재비뽑기 이름1 이름2 ...` - 랜덤으로 한 명을 뽑음
    `!도움말` - 이 도움말을 표시
    `!랭킹` - 랭킹을 표시
    `!내순위` - 내순위 표시

    🔹 사용 예시:
    `!불러봐 밤양갱` → "밤양갱" 노래 재생
    `!재비뽑기 철수 영희 민수` → 랜덤으로 한 명 선정
    `!주식구매 삼성전자 10` → 삼성전자 주식 10주 구매
    """

    await ctx.send(help_text)

@client.command(name='출석')
async def 출석(ctx):
    user_id = str(ctx.author.id)
    user = stock.get_user(user_id)

    now = datetime.utcnow().timestamp()  # 현재 UTC 시간 (초 단위)
    last_claim = user.get("last_claim", 0)  # 기본값 0

    # 1. last_claim이 문자열이면 변환 시도
    if isinstance(last_claim, str):
        try:
            last_claim = float(last_claim)  # 정수형 변환 시도
        except ValueError:
            try:
                # 날짜 형식인 경우 datetime으로 변환 후 timestamp로 변환
                last_claim = datetime.strptime(last_claim, "%Y-%m-%d").timestamp()
            except ValueError:
                last_claim = 0  # 변환 실패 시 기본값 0으로 설정

    # 2. 출석 체크
    if now - last_claim < 86400:  # 24시간 제한
        await ctx.send(f"❌ {ctx.author.display_name}님은 이미 오늘 출석하셨습니다!")
        return

    # 3. 보상 지급 및 잔액 소수점 2자리 유지
    user["balance"] = round(user["balance"] + DAILY_REWARD, 2)
    user["last_claim"] = now  # timestamp 형식으로 저장

    stock.save_data(USER_FILE, stock.users)

    await ctx.send(f"✅ {ctx.author.display_name}님, 출석 완료! {DAILY_REWARD}원이 지급되었습니다. 현재 잔액: ${user['balance']:.2f}")

client.run(os.getenv("DISCORD_TOKEN"))