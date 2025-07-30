# bot.py
import asyncio
import discord
from discord.ext import commands, tasks
import random
import stock
from datetime import datetime
import os
import traceback
import sys
from dotenv import load_dotenv

# --- 초기 설정 ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("오류: .env 파일에 DISCORD_TOKEN이 설정되지 않았습니다.", file=sys.stderr)
    exit()

# 상수 정의
PREFIX = "!"
DAILY_REWARD = 10000

# 봇 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# --- 주식 및 기타 기능 Cog ---
class General(commands.Cog, name="주식"):
    """
    주식 거래, 자산 관리, 도박 등 경제 및 기타 활동 명령어입니다.
    """
    def __init__(self, bot):
        self.bot = bot

    # ⭐ [수정] 가독성과 정보량을 개선한 새로운 주식목록 명령어
    @commands.command(name='주식목록', aliases=['주식'])
    async def stock_list(self, ctx: commands.Context):
        """현재 주식 목록과 변동률을 멋진 임베드로 보여줍니다."""
        try:
            # [설명] stock.stocks 데이터가 없을 경우를 대비한 방어 코드
            if not stock.stocks:
                await ctx.send("표시할 주식 정보가 없습니다.")
                return

            # [설명] 임베드 기본 틀 생성. 제목, 설명, 색상, 타임스탬프를 설정하여 더 많은 정보 제공
            embed = discord.Embed(
                title="📈 실시간 주식 시세 표 📈",
                description="현재 상장된 주식 목록과 변동률입니다.",
                color=discord.Color.blue(),
                timestamp=datetime.now() # [설명] 정보 업데이트 시점을 알려주는 타임스탬프 추가
            )

            # [설명] 각 정보를 리스트로 만들어 컬럼(열)처럼 보이게 구성
            stock_names = []
            stock_prices = []
            stock_changes_str = []
            
            # [설명] stock.stocks가 {'이름': {'price': 가격, ...}} 형태일 것을 가정하고 수정
            for name, data in stock.stocks.items():
                price = data.get('price', 0) # [설명] data 딕셔너리에서 'price' 키로 가격을 가져옵니다.
                _, percent_change = stock.stock_changes.get(name, (0, 0))
                
                symbol = "🔺" if percent_change > 0 else ("🔻" if percent_change < 0 else "➖")
                
                stock_names.append(f"**{name}**")
                stock_prices.append(f"`${price:,.2f}`") # [설명] 가격을 코드 블록(`)으로 감싸 가독성 향상
                stock_changes_str.append(f"`{symbol} {percent_change:+.2f}%`") # [설명] 변동률도 코드 블록으로 감싸 정렬 효과

            # [설명] 준비된 리스트들을 'inline=True' 필드로 추가하여 표 형태로 만듭니다.
            embed.add_field(name="종목명", value="\n".join(stock_names), inline=True)
            embed.add_field(name="현재가", value="\n".join(stock_prices), inline=True)
            embed.add_field(name="변동률", value="\n".join(stock_changes_str), inline=True)

            # [설명] 추가적인 명령어 안내를 footer에 추가하여 사용자 편의성 증진
            embed.set_footer(text="자세한 정보는 !주식정보 <종목명> 을 입력하세요.")

            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("주식 목록을 불러오는 중 오류가 발생했습니다.")
            traceback.print_exc() # [설명] 디버깅을 위해 전체 오류 로그를 출력
            print(f"주식목록 오류: {e}", file=sys.stderr)


    @commands.command(name='주식정보')
    async def stock_info(self, ctx: commands.Context, stock_name: str):
        """특정 주식의 상세 정보를 보여줍니다."""
        if stock_name not in stock.stocks:
            return await ctx.send("❌ 존재하지 않는 종목입니다.")
        
        data = stock.stocks[stock_name]
        embed = discord.Embed(title=f"📊 {stock_name} 상세 정보", color=discord.Color.blue())
        embed.add_field(name="현재가", value=f"`${data['price']:,.2f}`", inline=True)
        embed.add_field(name="분야", value=data['sector'], inline=True)
        embed.add_field(name="안정성 지수", value=data['volatility'], inline=True)
        embed.add_field(name="총 발행량", value=f"{data['total_shares']:,}주", inline=True)
        embed.add_field(name="현재 유통량", value=f"{data['available_shares']:,}주", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name='주식구매')
    async def buy_stock(self, ctx: commands.Context, stock_name: str, amount_str: str):
        user_id = str(ctx.author.id)
        if amount_str.lower() != "all" and (not amount_str.isdigit() or int(amount_str) <= 0):
            return await ctx.send("❌ 수량은 0보다 큰 숫자 또는 'all'이어야 합니다.")
        
        try: amount = "all" if amount_str.lower() == "all" else int(amount_str)
        except ValueError: return await ctx.send("❌ 유효한 수량을 입력해주세요.")

        success, result = stock.buy_stock(user_id, stock_name, amount)
        
        if success:
            embed = discord.Embed(title="✅ 주식 구매 완료", color=discord.Color.green())
            embed.add_field(name="종목", value=stock_name, inline=True)
            embed.add_field(name="수량", value=f"{result['amount']}주", inline=True)
            embed.add_field(name="주당 가격", value=f"`${result['total_cost']/result['amount']:,.2f}`", inline=True)
            embed.add_field(name="총 구매액", value=f"`${result['total_cost']:,.2f}`", inline=False)
            embed.add_field(name="수수료 (0.2%)", value=f"`${result['fee']:,.2f}`", inline=False)
            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)
        else: await ctx.send(f"❌ 구매 실패: {result}")

    @commands.command(name="주식판매")
    async def sell_stock(self, ctx: commands.Context, stock_name: str, amount_str: str):
        user_id = str(ctx.author.id)
        if amount_str.lower() != 'all' and (not amount_str.isdigit() or int(amount_str) <= 0):
            return await ctx.send("❌ 수량은 0보다 큰 숫자 또는 'all'이어야 합니다.")

        try: amount_to_sell = "all" if amount_str.lower() == 'all' else int(amount_str)
        except ValueError: return await ctx.send("❌ 유효한 수량을 입력해주세요.")

        success, result = stock.sell_stock(user_id, stock_name, amount_to_sell)
        if success:
            embed = discord.Embed(title="✅ 주식 판매 완료", color=discord.Color.blue())
            embed.add_field(name="종목", value=stock_name, inline=True)
            embed.add_field(name="수량", value=f"{result['amount']}주", inline=True)
            embed.add_field(name="주당 가격", value=f"`${result['total_revenue']/result['amount']:,.2f}`", inline=True)
            embed.add_field(name="총 판매액", value=f"`${result['total_revenue']:,.2f}`", inline=False)
            embed.add_field(name="수수료 (0.2%)", value=f"`-${result['fee']:,.2f}`", inline=False)
            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)
        else: await ctx.send(f"❌ 판매 실패: {result}")

    @commands.command(name='내자산', aliases=['내주식', '나', '포트폴리오'])
    async def my_assets(self, ctx: commands.Context):
        result_text = stock.get_portfolio(str(ctx.author.id))
        embed = discord.Embed(title=f"💰 {ctx.author.display_name}님의 자산 현황", description=result_text, color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command(name="랭킹")
    async def ranking(self, ctx: commands.Context):
        users = stock.load_users()
        if not users: return await ctx.send("📊 아직 등록된 사용자가 없습니다!")
        ranking_list = sorted([(uid, stock.calculate_total_assets(uid)) for uid in users], key=lambda x: x[1], reverse=True)
        top_users = ranking_list[:10]
        embed = discord.Embed(title="🏆 주식왕 랭킹 🏆", description="*총 자산 = 현금 + 보유 주식 가치*", color=0xFFD700)
        rank_emojis = ["🥇", "🥈", "🥉"]
        text_lines = []
        for i, (uid, assets) in enumerate(top_users):
            try:
                member = ctx.guild.get_member(int(uid)) or await self.bot.fetch_user(int(uid))
                name, emoji = member.display_name, rank_emojis[i] if i < 3 else f'**{i+1}위**'
                text_lines.append(f"{emoji} {name} - `₩{assets:,.0f}`")
            except (discord.NotFound, discord.HTTPException): continue
        embed.description = "\n".join(text_lines) or "랭킹 정보 없음"
        try:
            user_rank = next(i + 1 for i, (uid, _) in enumerate(ranking_list) if uid == str(ctx.author.id))
            embed.set_footer(text=f"{ctx.author.display_name}님의 현재 순위: {user_rank}위")
        except StopIteration:
            embed.set_footer(text=f"{ctx.author.display_name}님은 아직 랭킹에 없습니다.")
        await ctx.send(embed=embed)

    @commands.command(name='출석')
    async def daily_claim(self, ctx: commands.Context):
        user_id = str(ctx.author.id)
        success, result = stock.claim_daily(user_id, DAILY_REWARD)
        if success:
            await ctx.send(f"✅ {ctx.author.display_name}님, 출석 완료! **{DAILY_REWARD:,}원**이 지급되었습니다.\n현재 잔액: `${result['new_balance']:,.2f}`")
        else:
            await ctx.send(f"❌ {result['message']}")
            
    # --- [수정] 새로운 도박 명령어 (도움말 기능 강화) ---
    @commands.command(name='도박', aliases=['겜블'])
    async def gamble(self, ctx: commands.Context, game_type: str = None, *, args: str = None):
        """
        다양한 도박 게임을 즐깁니다.
        !도박 을 입력하여 자세한 도움말을 확인하세요.
        """
        user_id = str(ctx.author.id)
        
        # ⭐ 게임 종류를 입력하지 않았을 경우, 상세 도움말 표시
        if not game_type:
            embed = discord.Embed(
                title="🎲 도박 게임 도움말 🎲",
                description=f"원하는 게임을 선택하여 `{PREFIX}도박 <게임이름> <베팅금액>` 형식으로 즐겨보세요!",
                color=discord.Color.gold()
            )
            embed.set_footer(text="<금액> 대신 'all'을 입력하여 전재산을 베팅할 수 있습니다.")

            # 슬롯머신 설명
            embed.add_field(
                name="🎰 슬롯머신",
                value=(
                    f"`{PREFIX}도박 슬롯 <금액>`\n"
                    "세 개의 릴을 돌려 같은 그림이 나오면 승리!\n\n"
                    "**[배당률]**\n"
                    "💎💎💎 : **20배**\n"
                    "💰💰💰 : **10배**\n"
                    "7️⃣7️⃣7️⃣ : **5배**\n"
                    "🍒🍒🍒 : **2배**\n"
                    "🍒 두 개 포함 시 : **본전**"
                ),
                inline=False
            )

            # 주사위 설명
            embed.add_field(
                name="\n🎲 주사위",
                value=(
                    f"`{PREFIX}도박 주사위 <금액>`\n"
                    "두 개의 주사위를 굴려 특정 조건에 맞으면 승리!\n\n"
                    "**[승리 조건]**\n"
                    "💠 더블 (같은 숫자 2개) : **4배**\n"
                    "7️⃣ 두 주사위 합이 7 : **2배**"
                ),
                inline=False
            )
            
            # 동전던지기 설명
            embed.add_field(
                name="\n🪙 동전던지기",
                value=(
                    f"`{PREFIX}도박 동전 <앞/뒤> <금액>`\n"
                    "간단하게 동전의 앞/뒤를 맞추는 50:50 게임!\n\n"
                    "**[승리 조건]**\n"
                    "✅ 예측 성공 시 : **2배**"
                ),
                inline=False
            )
            
            return await ctx.send(embed=embed)

        # 인자(args) 파싱
        bet_amount_str = None
        choice = None
        if args:
            parts = args.split()
            if game_type == "동전":
                if len(parts) == 2:
                    choice, bet_amount_str = parts[0], parts[1]
                else:
                    return await ctx.send("❌ 사용법: `!도박 동전 <앞/뒤> <금액>`")
            else:
                bet_amount_str = parts[0]
        
        if not bet_amount_str:
            return await ctx.send("❌ 베팅할 금액을 입력해주세요.")

        # --- 슬롯 머신 ---
        if game_type == "슬롯":
            success, result = stock.process_slot_machine(user_id, bet_amount_str)
            if not success:
                return await ctx.send(f"❌ 슬롯머신 실패: {result['message']}")
            
            voice_client = None
            if ctx.author.voice and ctx.author.voice.channel:
                if ctx.voice_client: voice_client = await ctx.voice_client.move_to(ctx.author.voice.channel)
                else: voice_client = await ctx.author.voice.channel.connect()

            try:
                emojis = ['💎', '💰', '7️⃣', '🍒', '💔']
                embed = discord.Embed(title="🎰 슬롯머신 🎰", description="릴이 돌아갑니다...", color=discord.Color.light_grey())
                embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                embed.add_field(name="결과", value="[ ❓ | ❓ | ❓ ]", inline=False)
                message = await ctx.send(embed=embed)
                if voice_client: voice_client.play(discord.FFmpegPCMAudio(os.path.join('sounds', 'spin.mp3')))
                
                await asyncio.sleep(1)
                for _ in range(2):
                    spinning_reels = [random.choice(emojis) for _ in range(3)]
                    embed.set_field_at(0, name="결과", value=f"[ {spinning_reels[0]} | {spinning_reels[1]} | {spinning_reels[2]} ]", inline=False)
                    await message.edit(embed=embed)
                    await asyncio.sleep(0.7)

                final_reels = result['reels']
                revealed_reels = ["❓", "❓", "❓"]
                for i in range(3):
                    revealed_reels[i] = final_reels[i]
                    embed.set_field_at(0, name="결과", value=f"[ {revealed_reels[0]} | {revealed_reels[1]} | {revealed_reels[2]} ]", inline=False)
                    await message.edit(embed=embed)
                    await asyncio.sleep(1)
                
                while voice_client and voice_client.is_playing(): await asyncio.sleep(0.1)
                
                if result['winnings'] > result['bet_amount']:
                    embed.description = f"🎉 **축하합니다! `{result['winnings'] - result['bet_amount']:,.0f}원` 획득!** 🎉"
                    embed.color = discord.Color.green()
                    if voice_client: voice_client.play(discord.FFmpegPCMAudio(os.path.join('sounds', 'win.mp3')))
                elif result['winnings'] > 0:
                    embed.description = f"🎉 **본전입니다! `{result['bet_amount']:,.0f}원`을 돌려받았습니다!** 🎉"
                    embed.color = discord.Color.blue()
                else:
                    embed.description = f"💸 **아쉽네요... `{result['bet_amount']:,.0f}원`을 잃었습니다.** 💸"
                    embed.color = discord.Color.red()
                    if voice_client: voice_client.play(discord.FFmpegPCMAudio(os.path.join('sounds', 'lose.mp3')))

                embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
                await message.edit(embed=embed)
                
            finally:
                if voice_client:
                    while voice_client.is_playing(): await asyncio.sleep(0.1)
                    await asyncio.sleep(1)
                    await voice_client.disconnect()
        
        # --- 주사위 게임 ---
        elif game_type == "주사위":
            success, result = stock.process_dice_roll(user_id, bet_amount_str)
            if not success:
                return await ctx.send(f"❌ 주사위 게임 실패: {result['message']}")

            embed = discord.Embed(title="🎲 주사위 게임 🎲", color=discord.Color.dark_orange())
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            dices = result['dices']
            dice_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣']
            embed.add_field(name="결과", value=f"{dice_emojis[dices[0]-1]} + {dice_emojis[dices[1]-1]} = **{sum(dices)}**")

            if result['winnings'] > 0:
                embed.description = f"🎉 **축하합니다! `{result['winnings'] - result['bet_amount']:,.0f}원` 획득!** 🎉"
                embed.color = discord.Color.green()
            else:
                embed.description = f"💸 **아쉽네요... `{result['bet_amount']:,.0f}원`을 잃었습니다.** 💸"
                embed.color = discord.Color.red()
            
            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)

        # --- 동전던지기 게임 ---
        elif game_type == "동전":
            if not choice: return await ctx.send("❌ 사용법: `!도박 동전 <앞/뒤> <금액>`")
            success, result = stock.process_coin_flip(user_id, bet_amount_str, choice)
            if not success:
                return await ctx.send(f"❌ 동전던지기 실패: {result['message']}")

            embed = discord.Embed(title="🪙 동전 던지기 🪙", color=discord.Color.light_grey())
            embed.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            embed.add_field(name="나의 선택", value=f"**{result['choice']}**", inline=True)
            embed.add_field(name="결과", value=f"**{result['result']}**", inline=True)

            if result['winnings'] > 0:
                embed.description = f"🎉 **축하합니다! `{result['winnings'] - result['bet_amount']:,.0f}원` 획득!** 🎉"
                embed.color = discord.Color.green()
            else:
                embed.description = f"💸 **아쉽네요... `{result['bet_amount']:,.0f}원`을 잃었습니다.** 💸"
                embed.color = discord.Color.red()

            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)
        
        else:
            await ctx.send(f"❌ 알 수 없는 게임 종류입니다: `{game_type}`\n(선택 가능: 슬롯, 주사위, 동전)")


    @commands.command(name='제비뽑기', aliases=['재비', '뽑기'])
    async def draw(self, ctx: commands.Context, *names: str):
        """입력된 이름들 중에서 한 명을 랜덤으로 뽑습니다."""
        if len(names) < 2:
            return await ctx.send("2명 이상 입력해주세요! 예시: `!제비뽑기 철수 영희 민수`")
        await ctx.send(f"🎉 당첨자는 **{random.choice(names)}** 입니다! 🎉")


    @commands.command(name='도움말', aliases=['도움'])
    async def help_command(self, ctx: commands.Context):
        embed = discord.Embed(title="📜 봇 도움말", description=f"명령어 접두사는 `{PREFIX}` 입니다.", color=0x5865F2)
        embed.add_field(name="🎵 음악 명령어", value="`들어와`, `나가`, `불러봐`, `검색`, `대기열`, `스킵`, `일시정지`, `재개`, `현재곡`, `반복`, `한곡반복`", inline=False)
        embed.add_field(name="💹 주식 명령어", value="`주식목록`, `주식정보`, `주식구매`, `주식판매`, `내자산`, `랭킹`, `출석`", inline=False)
        embed.add_field(name="🎲 도박 및 기타", value="`도박`, `도움말`, `제비뽑기`\n(`!도박`을 입력하여 게임 종류를 확인하세요!)", inline=False)
        await ctx.send(embed=embed)


# --- 메인 봇 클래스 ---
class StockBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        await self.add_cog(General(self))
        print("🔧 'General' Cog를 로드했습니다.")
        try:
            await self.load_extension('music')
            print("🎵 'music' Cog를 로드했습니다.")
        except commands.ExtensionNotFound:
            print("⚠️ 'music.py' 파일을 찾을 수 없습니다.")
        except Exception as e:
            print(f"music Cog 로드 중 오류 발생: {e}", file=sys.stderr)
            traceback.print_exc()
        self.auto_update_stock.start()

    @tasks.loop(minutes=1)
    async def auto_update_stock(self):
        stock.update_stock_prices()

    @auto_update_stock.before_loop
    async def before_auto_update_stock(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 봇이 준비되었습니다: {self.user}")
        await self.change_presence(status=discord.Status.online, activity=discord.Game(f"{PREFIX}도움말"))

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if hasattr(ctx.command, 'on_error'): return
        if isinstance(error, commands.CommandNotFound): return
        
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"❌ 명령어 사용법이 잘못되었습니다. `!도움말`을 확인해주세요.\n> 오류: `{error}`")

        print(f"'{ctx.command.qualified_name}' 명령어에서 처리되지 않은 오류 발생: {error}", file=sys.stderr)
        traceback.print_exc()
        await ctx.send(f"⚠️ 알 수 없는 오류가 발생했습니다. 명령어와 형식을 다시 확인해주세요.")

# --- 봇 실행 ---
async def main():
    bot = StockBot()
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n봇을 종료합니다.")