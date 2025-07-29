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
class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='주식목록', aliases=['주식'])
    async def stock_list(self, ctx: commands.Context):
        """현재 주식 목록과 변동률을 임베드로 보여줍니다."""
        try:
            embed = discord.Embed(title="📈 현재 주식 목록 📈", color=discord.Color.gold())
            description = []
            for name, price in stock.stocks.items():
                _, percent_change = stock.stock_changes.get(name, (0, 0))
                symbol = "🔺" if percent_change > 0 else ("🔻" if percent_change < 0 else "➖")
                change_str = f"{symbol} {percent_change:+.2f}%"
                description.append(f"**{name}**: `${price:,.2f}` ({change_str})")
            
            embed.description = "\n".join(description) if description else "현재 주식 정보가 없습니다."
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("주식 목록을 불러오는 중 오류가 발생했습니다.")
            print(f"주식목록 오류: {e}", file=sys.stderr)

    @commands.command(name='주식구매')
    async def buy_stock(self, ctx: commands.Context, stock_name: str, amount_str: str):
        """지정한 수량만큼 주식을 구매합니다."""
        user_id = str(ctx.author.id)
        if amount_str.lower() != "all" and (not amount_str.isdigit() or int(amount_str) <= 0):
            return await ctx.send("❌ 수량은 0보다 큰 숫자 또는 'all'이어야 합니다.")
        
        amount = "all" if amount_str.lower() == "all" else int(amount_str)
        success, result = stock.buy_stock(user_id, stock_name, amount)
        
        if success:
            embed = discord.Embed(title="✅ 주식 구매 완료", color=discord.Color.green())
            embed.add_field(name="종목", value=stock_name, inline=True)
            embed.add_field(name="수량", value=f"{result['amount']}주", inline=True)
            embed.add_field(name="총 구매액", value=f"`${result['total_cost']:,.2f}`", inline=False)
            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ 구매 실패: {result}")

    @commands.command(name="주식판매")
    async def sell_stock(self, ctx: commands.Context, stock_name: str, amount_str: str):
        """보유한 주식을 판매합니다."""
        user_id = str(ctx.author.id)
        if amount_str.lower() != 'all' and (not amount_str.isdigit() or int(amount_str) <= 0):
            return await ctx.send("❌ 수량은 0보다 큰 숫자 또는 'all'이어야 합니다.")
        
        amount_to_sell = "all" if amount_str.lower() == 'all' else int(amount_str)
        success, result = stock.sell_stock(user_id, stock_name, amount_to_sell)
        if success:
            embed = discord.Embed(title="✅ 주식 판매 완료", color=discord.Color.blue())
            embed.add_field(name="종목", value=stock_name, inline=True)
            embed.add_field(name="수량", value=f"{result['amount']}주", inline=True)
            embed.add_field(name="총 판매액", value=f"`${result['total_revenue']:,.2f}`", inline=False)
            embed.add_field(name="현재 잔액", value=f"`${result['new_balance']:,.2f}`", inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ 판매 실패: {result}")

    @commands.command(name='내자산', aliases=['내주식', '나'])
    async def my_assets(self, ctx: commands.Context):
        """사용자의 현재 자산 현황을 보여줍니다."""
        result_text = stock.get_portfolio(str(ctx.author.id))
        embed = discord.Embed(title=f"💰 {ctx.author.display_name}님의 자산 현황", description=result_text, color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command(name="랭킹")
    async def ranking(self, ctx: commands.Context):
        """서버 내 주식 부자 랭킹을 보여줍니다."""
        users = stock.load_users()
        if not users:
            return await ctx.send("📊 아직 등록된 사용자가 없습니다!")

        ranking_list = sorted([(uid, stock.calculate_total_assets(uid)) for uid in users], key=lambda x: x[1], reverse=True)
        top_users = ranking_list[:10]

        embed = discord.Embed(title="🏆 주식왕 랭킹 🏆", description="*총 자산 = 현금 + 보유 주식 가치*", color=0xFFD700)
        rank_emojis = ["🥇", "🥈", "🥉"]
        text_lines = []

        for i, (user_id, total_assets) in enumerate(top_users):
            try:
                member = ctx.guild.get_member(int(user_id)) or await self.bot.fetch_user(int(user_id))
                name = member.display_name
            except (discord.NotFound, discord.HTTPException):
                name = f"알 수 없는 유저 ({str(user_id)[-4:]})"
            
            emoji = rank_emojis[i] if i < 3 else f"**{i+1}위**"
            text_lines.append(f"{emoji} {name} - `₩{total_assets:,.0f}`")
        
        embed.description = "\n".join(text_lines) or "랭킹 정보 없음"
        
        try:
            user_rank = next(i + 1 for i, (uid, _) in enumerate(ranking_list) if uid == str(ctx.author.id))
            embed.set_footer(text=f"{ctx.author.display_name}님의 현재 순위: {user_rank}위")
        except StopIteration:
            embed.set_footer(text=f"{ctx.author.display_name}님은 아직 랭킹에 없습니다.")
            
        await ctx.send(embed=embed)

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
        embed.add_field(name="💹 주식 명령어", value="`주식목록`, `주식구매`, `주식판매`, `내자산`, `랭킹`, `출석`", inline=False)
        embed.add_field(name="🎲 기타 명령어", value="`제비뽑기`, `도움말`", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name='출석')
    async def daily_claim(self, ctx: commands.Context):
        """하루에 한 번(자정 기준) 출석하여 보상을 받습니다."""
        user_id = str(ctx.author.id)
        success, result = stock.claim_daily(user_id, DAILY_REWARD)
        
        if success:
            new_balance = result['new_balance']
            await ctx.send(f"✅ {ctx.author.display_name}님, 출석 완료! **{DAILY_REWARD:,}원**이 지급되었습니다.\n현재 잔액: `${new_balance:,.2f}`")
        else:
            error_message = result['message']
            await ctx.send(f"❌ {error_message}")


# --- 메인 봇 클래스 ---
class StockBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=PREFIX, intents=intents)

    async def setup_hook(self):
        """봇이 시작될 때 필요한 확장(cogs)을 로드하고 백그라운드 작업을 시작합니다."""
        await self.add_cog(General(self))
        print("🔧 'General' Cog를 로드했습니다.")
        await self.load_extension('music')
        print("🎵 'music' Cog를 로드했습니다.")
        self.auto_update_stock.start()

    @tasks.loop(minutes=1)
    async def auto_update_stock(self):
        stock.update_stock_prices()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📈 주식 가격 자동 갱신 완료")

    @auto_update_stock.before_loop
    async def before_auto_update_stock(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 봇이 준비되었습니다: {self.user}")
        await self.change_presence(status=discord.Status.online, activity=discord.Game(f"{PREFIX}도움말 | 음악 & 주식"))

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """명령어에서 처리되지 않은 모든 오류를 처리합니다."""
        if hasattr(ctx.command, 'on_error'):
            return

        ignored = (commands.CommandNotFound, )
        if isinstance(error, ignored):
            return

        print(f"'{ctx.command.qualified_name}' 명령어에서 처리되지 않은 오류 발생: {error}", file=sys.stderr)
        traceback.print_exc()
        await ctx.send(f"⚠️ 알 수 없는 오류가 발생했습니다. 관리자에게 문의해주세요.")

# --- 봇 실행 ---
async def main():
    bot = StockBot()
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("봇을 종료합니다.")