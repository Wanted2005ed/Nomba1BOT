from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os, time
import yfinance as yf

app=FastAPI(title='Nomba1BOT Signal Engine',version='0.1.0')
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
    if df is None or df.empty: return None
    if hasattr(df.columns,'levels'):
        df.columns=df.columns.get_level_values(0)
    return df.dropna()

def basic_signal(df):
    if df is None or len(df)<30:return 'UNCERTAIN',0
    close=df['Close']
    fast=close.ewm(span=9,adjust=False).mean().iloc[-1]
    slow=close.ewm(span=21,adjust=False).mean().iloc[-1]
    spread=abs(fast-slow)/max(abs(float(close.iloc[-1])),1e-9)
    if spread<0.00015:return 'NEUTRAL',50
    return ('BUY' if fast>slow else 'SELL'),min(95,55+int(spread*100000))

@app.get('/health')
def health():return {'ok':True,'service':'Nomba1BOT','mode':'signal-only'}

@app.post('/signal')
def signal(req:SignalRequest):
    if not req.strategies: return {'symbol':req.symbol,'signal':'WAIT','confidence':0,'votes':{'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0},'data_status':'no strategies selected'}
    votes={'BUY':0,'SELL':0,'NEUTRAL':0,'UNCERTAIN':0}; tf={}
    for interval in req.timeframes:
        try:sig,conf=basic_signal(candles(req.symbol,interval))
        except Exception:sig,conf='UNCERTAIN',0
        tf[interval]={'signal':sig,'confidence':conf}
        votes[sig]+=len(req.strategies)
    buy=votes['BUY'];sell=votes['SELL'];total=sum(votes.values()) or 1
    final='BUY' if buy>sell and buy>=total*.5 else 'SELL' if sell>buy and sell>=total*.5 else 'WAIT'
    confidence=round(max(buy,sell)/total*100) if final!='WAIT' else round(abs(buy-sell)/total*100)
    return {'symbol':req.symbol,'signal':final,'confidence':confidence,'votes':votes,'timeframes':tf,'timestamp':int(time.time()),'data_status':'market-data'}

@app.post('/notifications/whatsapp')
def whatsapp(payload:dict):
    # Provider credentials stay server-side. Wire this endpoint to the chosen WhatsApp API.
    if not os.getenv('WHATSAPP_ACCESS_TOKEN'):
        return {'ok':False,'status':'not_configured','message':'WhatsApp provider credentials are not configured.'}
    return {'ok':True,'status':'adapter_ready'}

@app.get('/')
def root():return {'name':'Nomba1BOT','docs':'/docs','mode':'signal-only'}
