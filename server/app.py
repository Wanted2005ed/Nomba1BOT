from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os, time
import yfinance as yf

app=FastAPI(title='Nomba1BOT Signal Engine',version='0.2.0')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])

class SignalRequest(BaseModel):
    symbol:str='EURUSD'
    strategies:list[int]=Field(default_factory=list)
    timeframes:list[str]=['5m','15m','30m']

FX={'EURUSD':'EURUSD=X','GBPUSD':'GBPUSD=X','USDJPY':'JPY=X','XAUUSD':'GC=F','BTCUSD':'BTC-USD','ETHUSD':'ETH-USD'}

def candles(symbol, interval):
    ticker=FX.get(symbol,symbol)
    period='5d' if interval in ('5m','15m') else '1mo'
    df=yf.download(ticker,period=period,interval=interval,progress=False,auto_adjust=False)
    if df is None or df.empty:return None
    if hasattr(df.columns,'levels'):df.columns=df.columns.get_level_values(0)
    return df.dropna()

def core_signal(df):
    if df is None or len(df)<60:return 'UNCERTAIN',0,{}
    close=df['Close'].astype(float); high=df['High'].astype(float); low=df['Low'].astype(float)
    ema50=close.ewm(span=50,adjust=False).mean(); ema200=close.ewm(span=200,adjust=False).mean()
    delta=close.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False).mean(); loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean()
    rsi=100-(100/(1+(gain/loss.replace(0,1e-12))))
    ema12=close.ewm(span=12,adjust=False).mean(); ema26=close.ewm(span=26,adjust=False).mean(); macd=ema12-ema26; macd_signal=macd.ewm(span=9,adjust=False).mean()
    median=(high+low)/2; ao=median.rolling(5).mean()-median.rolling(34).mean()
    values=[ema50.iloc[-1]>ema200.iloc[-1],rsi.iloc[-1]>50,macd.iloc[-1]>macd_signal.iloc[-1],ao.iloc[-1]>0]
    score=sum(1 if x else -1 for x in values)
    if score>=2:sig='BUY'
    elif score<=-2:sig='SELL'
    else:sig='NEUTRAL'
    confidence=round(50+abs(score)*12.5)
    details={'ema50':round(float(ema50.iloc[-1]),6),'ema200':round(float(ema200.iloc[-1]),6),'rsi':round(float(rsi.iloc[-1]),2),'macd':round(float(macd.iloc[-1]),6),'macd_signal':round(float(macd_signal.iloc[-1]),6),'ao':round(float(ao.iloc[-1]),6),'price':round(float(close.iloc[-1]),6)}
    return sig,min(100,confidence),details

@app.get('/health')
def health():return {'ok':True,'service':'Nomba1BOT','mode':'signal-only','version':'0.2.0'}

@app.post('/signal')
def signal(req:SignalRequest):
    if not req.strategies:return {'symbol':req.symbol,'signal':'WAIT','confidence':0,'votes':{'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0},'data_status':'no strategies selected'}
    votes={'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0};tf={};details={}
    for interval in req.timeframes:
        try:sig,conf,info=core_signal(candles(req.symbol,interval))
        except Exception:sig,conf,info='UNCERTAIN',0,{}
        tf[interval]={'signal':sig,'confidence':conf};details[interval]=info;votes[sig]+=len(req.strategies)
    buy=votes['BUY'];sell=votes['SELL'];total=sum(votes.values()) or 1
    final='BUY' if buy>sell and buy>=total*.5 else 'SELL' if sell>buy and sell>=total*.5 else 'WAIT'
    confidence=round(max(buy,sell)/total*100) if final!='WAIT' else round(abs(buy-sell)/total*100)
    price=next((details[x].get('price') for x in req.timeframes if details.get(x,{}).get('price') is not None),None)
    return {'symbol':req.symbol,'signal':final,'confidence':confidence,'votes':votes,'timeframes':tf,'indicators':details,'price':price,'timestamp':int(time.time()),'data_status':'market-data'}

@app.post('/notifications/whatsapp')
def whatsapp(payload:dict):
    if not os.getenv('WHATSAPP_ACCESS_TOKEN'):return {'ok':False,'status':'not_configured','message':'WhatsApp provider credentials are not configured.'}
    return {'ok':True,'status':'adapter_ready'}

@app.get('/')
def root():return {'name':'Nomba1BOT','docs':'/docs','mode':'signal-only'}
