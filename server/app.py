from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os,time
import yfinance as yf
import httpx
import pandas as pd

app=FastAPI(title='Nomba1BOT Signal Engine',version='0.4.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
SUPPORTED_TF=['1m','5m','15m','30m','1h','4h']
class StrategyItem(BaseModel):
 id:int
 name:str
class SignalRequest(BaseModel):
 symbol:str='EURUSD'
 strategies:list[StrategyItem]=Field(default_factory=list)
 timeframes:list[str]=Field(default_factory=lambda:SUPPORTED_TF)
class NotificationPayload(BaseModel):
 channel_preferences:list[str]=Field(default_factory=list)
 symbol:str
 signal:str
 confidence:str='0%'
 price:str='—'
 timestamp:str=''
 recipient_email:str=''
 recipient_whatsapp:str=''
FX={'EURUSD':'EURUSD=X','GBPUSD':'GBPUSD=X','USDJPY':'JPY=X','XAUUSD':'GC=F','BTCUSD':'BTC-USD','ETHUSD':'ETH-USD'}

def candles(symbol,tf):
 ticker=FX.get(symbol,symbol)
 if tf=='4h':
  df=yf.download(ticker,period='1mo',interval='1h',progress=False,auto_adjust=False)
  if df is None or df.empty:return None
  if hasattr(df.columns,'levels'):df.columns=df.columns.get_level_values(0)
  return df.dropna().resample('4h').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
 period='7d' if tf=='1m' else '5d' if tf in ('5m','15m','30m') else '1mo'
 df=yf.download(ticker,period=period,interval=tf,progress=False,auto_adjust=False)
 if df is None or df.empty:return None
 if hasattr(df.columns,'levels'):df.columns=df.columns.get_level_values(0)
 return df.dropna()

def calc(df):
 if df is None or len(df)<60:return None
 c=df['Close'].astype(float);h=df['High'].astype(float);l=df['Low'].astype(float)
 e9=c.ewm(span=9,adjust=False).mean();e21=c.ewm(span=21,adjust=False).mean();e50=c.ewm(span=50,adjust=False).mean();e200=c.ewm(span=200,adjust=False).mean()
 d=c.diff();g=d.clip(lower=0).ewm(alpha=1/14,adjust=False).mean();lo=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean();rsi=100-(100/(1+g/lo.replace(0,1e-12)))
 e12=c.ewm(span=12,adjust=False).mean();e26=c.ewm(span=26,adjust=False).mean();mac=e12-e26;ms=mac.ewm(span=9,adjust=False).mean()
 med=(h+l)/2;ao=med.rolling(5).mean()-med.rolling(34).mean();mid=c.rolling(20).mean();sd=c.rolling(20).std()
 return {'close':float(c.iloc[-1]),'ema9':float(e9.iloc[-1]),'ema21':float(e21.iloc[-1]),'ema50':float(e50.iloc[-1]),'ema200':float(e200.iloc[-1]),'rsi':float(rsi.iloc[-1]),'macd':float(mac.iloc[-1]),'macd_signal':float(ms.iloc[-1]),'ao':float(ao.iloc[-1]),'bb_hi':float((mid+2*sd).iloc[-1]),'bb_lo':float((mid-2*sd).iloc[-1])}

def strat(name,x):
 n=name.lower();s=0
 if any(k in n for k in ['moving average','ema','sma','golden cross','death cross','supertrend','trend','ichimoku','parabolic','keltner','guppy','hull']):s+=1 if x['ema50']>x['ema200'] else -1;s+=.5 if x['ema9']>x['ema21'] else -.5
 if any(k in n for k in ['rsi','stochastic','momentum','roc','macd','ppo','pvo','awesome oscillator','adx','dmi','chande','tsi']):s+=.75 if x['rsi']>50 else -.75;s+=.75 if x['macd']>x['macd_signal'] else -.75
 if any(k in n for k in ['breakout','opening range','donchian','turtle','flag','pennant','triangle','channel','darvas','range high']):s+=1 if x['close']>x['ema21'] else -1
 if any(k in n for k in ['reversion','oversold','overbought','bounce','fade','reversal']):
  s+=1 if x['rsi']<35 or x['close']<x['bb_lo'] else -1 if x['rsi']>65 or x['close']>x['bb_hi'] else .25 if x['close']<x['ema21'] else -.25
 if any(k in n for k in ['bullish','morning star','hammer','inverse head']):s+=.75
 if any(k in n for k in ['bearish','evening star','shooting star','head and shoulders']):s-=.75
 if any(k in n for k in ['liquidity','order block','fair value gap','smart money','wyckoff','supply zone','demand zone','market structure','volume profile','market profile']):s+=.75 if x['close']>x['ema50'] else -.75
 if s==0:s=.5 if x['close']>x['ema21'] else -.5
 return 'BUY' if s>=.75 else 'SELL' if s<=-.75 else 'NEUTRAL'

def evaluate(df,strategies):
 x=calc(df)
 if not x:return 'UNCERTAIN',0,{}, {'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':len(strategies)}
 v={'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0}
 for st in strategies:v[strat(st.name,x)]+=1
 sig='BUY' if v['BUY']>v['SELL'] else 'SELL' if v['SELL']>v['BUY'] else 'WAIT';conf=round(max(v['BUY'],v['SELL'])/max(1,len(strategies))*100)
 return sig,conf,x,v

@app.get('/health')
def health():return {'ok':True,'service':'Nomba1BOT','mode':'signal-only','version':'0.4.0','timeframes':SUPPORTED_TF}
@app.post('/signal')
def signal(req:SignalRequest):
 if not req.strategies:return {'symbol':req.symbol,'signal':'WAIT','confidence':0,'votes':{'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0},'data_status':'no strategies selected'}
 tfs=[x for x in req.timeframes if x in SUPPORTED_TF] or SUPPORTED_TF;tv={'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0};tf={};details={}
 for t in tfs:
  try:sig,conf,info,v= evaluate(candles(req.symbol,t),req.strategies)
  except Exception:sig,conf,info,v='UNCERTAIN',0,{}, {'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':len(req.strategies)}
  tf[t]={'signal':sig,'confidence':conf,'votes':v};details[t]=info
  for k in tv:tv[k]+=v[k]
 b=tv['BUY'];s=tv['SELL'];final='BUY' if b>s else 'SELL' if s>b else 'WAIT';dec=b+s;conf=round(max(b,s)/max(1,dec)*100) if dec else 0
 price=next((details[t].get('close') for t in tfs if details.get(t,{}).get('close') is not None),None)
 return {'symbol':req.symbol,'signal':final,'confidence':conf,'votes':tv,'timeframes':tf,'indicators':details,'price':price,'timestamp':int(time.time()),'data_status':'LIVE market data'}

async def send_whatsapp(p):
 token=os.getenv('WHATSAPP_ACCESS_TOKEN');phone=os.getenv('WHATSAPP_PHONE_NUMBER_ID');to=p.recipient_whatsapp or os.getenv('WHATSAPP_TO')
 if not all([token,phone,to]):return {'ok':False,'status':'not_configured','channel':'whatsapp'}
 url=f'https://graph.facebook.com/v23.0/{phone}/messages';text=f'Nomba1BOT educational signal\n{p.symbol}: {p.signal}\nConfidence: {p.confidence}\nPrice: {p.price}'
 async with httpx.AsyncClient(timeout=15) as c:r=await c.post(url,headers={'Authorization':f'Bearer {token}','Content-Type':'application/json'},json={'messaging_product':'whatsapp','to':to,'type':'text','text':{'body':text}})
 return {'ok':r.is_success,'status':'sent' if r.is_success else 'provider_error','channel':'whatsapp'}
async def send_email(p):
 hook=os.getenv('EMAIL_WEBHOOK_URL');to=p.recipient_email or os.getenv('EMAIL_TO')
 if not hook or not to:return {'ok':False,'status':'not_configured','channel':'email'}
 async with httpx.AsyncClient(timeout=15) as c:r=await c.post(hook,json={'to':to,'subject':f'Nomba1BOT {p.signal} • {p.symbol}','text':f'{p.symbol}: {p.signal}\nConfidence: {p.confidence}\nPrice: {p.price}','timestamp':p.timestamp})
 return {'ok':r.is_success,'status':'sent' if r.is_success else 'provider_error','channel':'email'}
@app.post('/notifications/dispatch')
async def dispatch(p:NotificationPayload):
 r=[]
 if 'whatsapp' in p.channel_preferences:r.append(await send_whatsapp(p))
 if 'email' in p.channel_preferences:r.append(await send_email(p))
 return {'ok':all(x['ok'] for x in r) if r else True,'channels':r,'site':'in_app'}
@app.post('/notifications/whatsapp')
async def whatsapp(p:NotificationPayload):return await send_whatsapp(p)
@app.get('/')
def root():return {'name':'Nomba1BOT','docs':'/docs','mode':'signal-only','notifications':['in_app','whatsapp','email'],'timeframes':SUPPORTED_TF}
