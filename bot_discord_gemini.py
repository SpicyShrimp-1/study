import discord
from discord.ext import commands
from discord import app_commands
import os
import yfinance as yf
import investpy
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import google.generativeai as genai

# --- 설정 ---
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
# 중요: Replit의 Secrets에 Gemini API 키를 설정하세요.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- Gemini API 설정 ---
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-pro-latest')

# --- 봇 클라이언트 설정 ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

# --- 뉴스 피드 파싱 함수 ---
def fetch_news_from_rss(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_items = []
        for item in root.findall('.//item'):
            title = item.find('title').text
            link = item.find('link').text
            pub_date_str = item.find('pubDate').text
            try:
                pub_date = datetime.strptime(pub_date_str, '%a, %d %b %Y %H:%M:%S %Z').strftime('%Y-%m-%d %H:%M')
            except ValueError:
                pub_date = pub_date_str
            news_items.append({"title": title, "link": link, "pub_date": pub_date})
        return news_items
    except Exception as e:
        print(f"뉴스 피드 파싱 중 오류 발생: {e}")
        return None

# --- 봇 이벤트 핸들러 ---
@bot.event
async def on_ready():
    print(f'{bot.user} (으)로 로그인했습니다!')
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)}개의 슬래시 커맨드를 동기화했습니다.")
    except Exception as e:
        print(f"커맨드 동기화 중 오류 발생: {e}")
    print("--- 봇이 준비되었습니다 ---")

# --- 슬래시 커맨드 정의 ---

@bot.tree.command(name="질문", description="Gemini 모델에게 자유롭게 질문합니다.")
@app_commands.describe(질문내용="모델에게 물어볼 질문을 입력하세요.")
async def ask_gemini(interaction: discord.Interaction, 질문내용: str):
    await interaction.response.defer()
    try:
        response = await gemini_model.generate_content_async(질문내용)
        # 답변이 너무 길 경우를 대비하여 2000자 단위로 나누어 전송
        for i in range(0, len(response.text), 2000):
            await interaction.followup.send(response.text[i:i+2000])
    except Exception as e:
        await interaction.followup.send(f"질문 처리 중 오류가 발생했습니다: {e}")

@bot.tree.command(name="도움말", description="봇이 가진 모든 명령어를 보여줍니다.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="명령어 도움말",
        description="봇이 지원하는 모든 슬래시 커맨드 목록입니다.",
        color=discord.Color.light_grey()
    )
    embed.add_field(name="/질문 [질문내용]", value="Gemini 모델에게 자유롭게 질문합니다.", inline=False)
    embed.add_field(name="/가격 [종목코드]", value="해당 종목의 상세 현재가 정보를 보여줍니다.", inline=False)
    embed.add_field(name="/정보 [종목코드]", value="해당 기업의 핵심 지표를 보여줍니다.", inline=False)
    embed.add_field(name="/종목뉴스 [종목명]", value="해당 종목 관련 최신 뉴스를 검색합니다.", inline=False)
    embed.add_field(name="/경제뉴스", value="미국 경제 뉴스를 가져옵니다.", inline=False)
    embed.add_field(name="/일정 [날짜]", value="해당 날짜(YYYY-MM-DD)의 주요 경제 일정을 보여줍니다.", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="가격", description="종목의 상세한 현재가 정보를 보여줍니다.")
@app_commands.describe(종목코드="주가 조회를 원하는 종목의 코드를 입력하세요.")
async def price(interaction: discord.Interaction, 종목코드: str):
    await interaction.response.defer()
    ticker_symbol = 종목코드.upper()
    ticker = yf.Ticker(ticker_symbol)
    hist = ticker.history(period="2d")
    if len(hist) < 2:
        await interaction.followup.send(f"'{ticker_symbol}'에 대한 데이터가 충분하지 않습니다. 상장된 주식이 맞는지 확인해주세요.")
        return
    latest = hist.iloc[-1]
    previous = hist.iloc[-2]
    current_price = latest['Close']
    prev_close = previous['Close']
    change = current_price - prev_close
    change_percent = (change / prev_close) * 100
    if change >= 0:
        color = discord.Color.red()
        sign = "▲"
    else:
        color = discord.Color.blue()
        sign = "▼"
    embed = discord.Embed(
        title=f"**{ticker.info.get('longName', ticker_symbol)} ({ticker_symbol})** 가격 정보",
        color=color
    )
    embed.add_field(name="현재가", value=f"**`{current_price:,.2f}`**", inline=False)
    embed.add_field(name="전일 대비", value=f"{sign} `{change:,.2f}` (`{change_percent:.2f}%`)", inline=False)
    embed.add_field(name="금일 고가", value=f"`{latest['High']:,.2f}`", inline=True)
    embed.add_field(name="금일 저가", value=f"`{latest['Low']:,.2f}`", inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="정보", description="기업의 핵심 지표를 보여줍니다.")
@app_commands.describe(종목코드="정보를 원하는 종목의 코드를 입력하세요.")
async def info(interaction: discord.Interaction, 종목코드: str):
    await interaction.response.defer()
    ticker_symbol = 종목코드.upper()
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    if not info or info.get('longName') is None:
        await interaction.followup.send(f"'{ticker_symbol}'에 대한 정보를 찾을 수 없습니다.")
        return
    embed = discord.Embed(
        title=f"**{info.get('longName', 'N/A')} ({info.get('symbol', 'N/A')})** 핵심 지표",
        color=discord.Color.dark_gold()
    )
    def get_info(key, format_str="{}"):
        val = info.get(key)
        if val is None or val == 0:
            return "N/A"
        return format_str.format(val)
    embed.add_field(name="📊 거래량", value=get_info('volume', "{:,}"), inline=True)
    embed.add_field(name="↕️ 52주 변동폭", value=f"{get_info('fiftyTwoWeekLow', '{:,.2f}')} - {get_info('fiftyTwoWeekHigh', '{:,.2f}')}", inline=False)
    embed.add_field(name="⚖️ 주가수익비율 (P/E)", value=get_info('trailingPE', "{:.2f}"), inline=True)
    embed.add_field(name="💰 배당수익률", value=get_info('dividendYield', "{:.2%}"), inline=True)
    embed.add_field(name="📈 베타 (Beta)", value=get_info('beta', "{:.2f}"), inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="종목뉴스", description="특정 종목에 대한 최신 뉴스를 검색합니다.")
@app_commands.describe(종목명="뉴스를 검색할 종목명을 입력하세요.")
async def stock_news(interaction: discord.Interaction, 종목명: str):
    await interaction.response.defer()
    url = f"https://news.google.com/rss/search?q={종목명}&hl=ko&gl=KR&ceid=KR:ko"
    news = fetch_news_from_rss(url)
    if not news:
        await interaction.followup.send(f"'{종목명}'에 대한 뉴스를 가져오는 데 실패했습니다.")
        return
    embed = discord.Embed(title=f"'{종목명}' 관련 최신 뉴스", color=discord.Color.green())
    for item in news[:5]:
        embed.add_field(name=item['title'], value=f"[기사 링크]({item['link']}) - {item['pub_date']}", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="경제뉴스", description="주요 경제 뉴스를 가져옵니다.")
async def economic_news(interaction: discord.Interaction):
    await interaction.response.defer()
    url = "https://news.google.com/rss/search?q=economic+news&hl=en-US&gl=US&ceid=US:en"
    news = fetch_news_from_rss(url)
    if not news:
        await interaction.followup.send("주요 경제 뉴스를 가져오는 데 실패했습니다.")
        return
    embed = discord.Embed(title="주요 경제 뉴스", color=discord.Color.orange())
    for item in news[:5]:
        embed.add_field(name=item['title'], value=f"[기사 링크]({item['link']}) - {item['pub_date']}", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="일정", description="주요 경제 일정을 보여줍니다.")
@app_commands.describe(날짜="조회할 날짜(YYYY-MM-DD)를 입력하세요. (기본값: 오늘)")
async def calendar(interaction: discord.Interaction, 날짜: str = None):
    await interaction.response.defer()
    if 날짜 is None:
        날짜 = datetime.now().strftime('%Y-%m-%d')
    try:
        if '-' in 날짜:
            target_date = datetime.strptime(날짜, '%Y-%m-%d')
        else:
            target_date = datetime.strptime(날짜, '%Y%m%d')
    except ValueError:
        await interaction.followup.send("날짜 형식이 잘못되었습니다. `YYYY-MM-DD` 또는 `YYYYMMDD` 형식으로 입력해주세요.")
        return
    try:
        from_date = target_date.strftime('%d/%m/%Y')
        to_date = (target_date + timedelta(days=1)).strftime('%d/%m/%Y')
        calendar_df = investpy.economic_calendar(from_date=from_date, to_date=to_date)
        calendar_df['date'] = pd.to_datetime(calendar_df['date'], format='%d/%m/%Y')
        calendar_df = calendar_df[calendar_df['date'].dt.date == target_date.date()]
        if calendar_df.empty:
            await interaction.followup.send(f"{target_date.strftime('%Y-%m-%d')}에는 주요 경제 일정이 없습니다.")
            return
        embed = discord.Embed(title=f"{target_date.strftime('%Y-%m-%d')} 주요 경제 일정", color=discord.Color.purple())
        high_events = calendar_df[calendar_df['importance'] == 'high']
        if high_events.empty:
            embed.description = "중요도 '높음'인 이벤트가 없습니다."
        else:
            for _, event in high_events.iterrows():
                embed.add_field(
                    name=f":flag_{{event['zone'].lower()}}: {event['time']} - {event['event']}",
                    value=f"실제: {event['actual']} | 예측: {event['forecast']} | 이전: {event['previous']}",
                    inline=False
                )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"경제 일정을 가져오는 중 오류가 발생했습니다: {e}\n`investpy` 라이브러리가 현재 작동하지 않을 수 있습니다.")

from keep_alive import keep_alive

# --- 봇 실행 ---
keep_alive()
bot.run(DISCORD_TOKEN)