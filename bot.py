from tickerall import Tickerall
import time

# ==========================================
# CONFIGURACIÓN DEL BOT
# ==========================================
API_KEY = "cf_api_ea89115d49cf1bd9fd6a7f7b365f9c01e9d603ab5468e79d314ac319ed8aa240"

BROKER = "mt5"
SERVER = "Headway-Demo"      
ACCOUNT = 6270468           
PASSWORD = "G@briel180611"     

SYMBOL = "XAUUSD"  
TIMEFRAME = "M5"                
LOT_SIZE = 0.01

# Configuración Chandelier Exit
ATR_PERIOD = 22
ATR_MULT = 3.0

# Configuración de salidas (en puntos del activo)
SL_POINTS = 10
TP1_POINTS = 100
TP2_POINTS = 160
TP3_POINTS = 300

# ==========================================
# VARIABLES DE ESTADO GLOBAL
# ==========================================
tp1_hit = False
tp2_hit = False
position_open = False
entry_price = None  
last_signal_price = 0 # Usaremos el precio de cierre para evitar dobles entradas

def get_pip_size(symbol_info):
    return 0.1 

def calculate_chandelier(bars):
    if len(bars) < ATR_PERIOD + 1:
        return None

    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]

    trs = []
    for i in range(1, len(bars)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        tr = max(high_low, high_close, low_close)
        trs.append(tr)

    atr = sum(trs[-ATR_PERIOD:]) / ATR_PERIOD
    highest_high = max(highs[-ATR_PERIOD:])
    lowest_low = min(lows[-ATR_PERIOD:])

    long_stop = highest_high - (atr * ATR_MULT)
    short_stop = lowest_low + (atr * ATR_MULT)

    dir_actual = 1 if closes[-1] > short_stop else (-1 if closes[-1] < long_stop else 0)
    dir_prev = 1 if closes[-2] > short_stop else (-1 if closes[-2] < long_stop else 0)

    return dir_actual, dir_prev

def open_trade(client, account_id, direction, symbol, lot, point):
    global entry_price
    bars = client.candles.get(account_id, symbol=symbol, count=1, timeframe=TIMEFRAME)
    if not bars:
        print("No se pudo obtener precio.")
        return False
    
    current_price = bars[0].close

    if direction == 1:  # LONG
        sl = current_price - (SL_POINTS * point)
        tp = current_price + (TP3_POINTS * point)
        side = "BUY"
    else:  # SHORT
        sl = current_price + (SL_POINTS * point)
        tp = current_price - (TP3_POINTS * point)
        side = "SELL"

    try:
        order = client.orders.place(
            account_id,
            type="market",
            symbol=symbol,
            side=side,
            volume=lot,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
        )
        entry_price = current_price 
        print(f"✅ Orden abierta: {side} a {current_price} | SL: {sl} | TP3: {tp}")
        return True
    except Exception as e:
        print(f"❌ Error al abrir orden: {e}")
        return False

def modify_sl(client, account_id, ticket, new_sl, tp):
    try:
        client.positions.modify(
            account_id, 
            ticket=ticket, 
            stop_loss=round(new_sl, 2), 
            take_profit=round(tp, 2)
        )
        print(f"✅ SL modificado exitosamente a {new_sl}")
    except Exception as e:
        print(f"❌ Error al modificar SL: {e}")

def main():
    global tp1_hit, tp2_hit, position_open, entry_price, last_signal_price

    client = Tickerall(api_key=API_KEY)

    try:
        session = client.sessions.start(
            broker=BROKER,
            server=SERVER,
            account=ACCOUNT,
            password=PASSWORD,
        )
        account_id = session.account_id
        print(f"✅ Conectado a Headway. Account ID: {account_id}")
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return

    point = get_pip_size(None) 
    print(f"🚀 Bot iniciado en {SYMBOL} ({TIMEFRAME})...")

    while True:
        try:
            bars = client.candles.get(account_id, symbol=SYMBOL, count=ATR_PERIOD + 10, timeframe=TIMEFRAME)
            if not bars or len(bars) < ATR_PERIOD + 1:
                time.sleep(10)
                continue

            # CORRECCIÓN: Usamos el precio de cierre de la última vela como referencia
            current_bar_close = bars[-1].close 
            
            result = calculate_chandelier(bars)
            if result is None:
                time.sleep(10)
                continue

            dir_actual, dir_prev = result
            buy_signal = (dir_actual == 1 and dir_prev == -1)
            sell_signal = (dir_actual == -1 and dir_prev == 1)

            detail = client.accounts.get(account_id)
            positions = detail.positions if detail and detail.positions else []
            bot_positions = [p for p in positions if p.symbol == SYMBOL]

            if len(bot_positions) > 0:
                pos = bot_positions[0]
                current_price = bars[-1].close
                side = pos.side  

                if entry_price is not None:
                    if side == "BUY":
                        dist = (current_price - entry_price) / point
                    else:
                        dist = (entry_price - current_price) / point

                    if dist >= TP1_POINTS and not tp1_hit:
                        modify_sl(client, account_id, pos.ticket, entry_price, pos.take_profit)
                        tp1_hit = True
                        print(f"🎯 TP1 alcanzado ({dist:.1f} pts). SL movido a Break-Even.")

                    if dist >= TP2_POINTS and not tp2_hit:
                        new_sl = entry_price + (TP1_POINTS * point) if side == "BUY" else entry_price - (TP1_POINTS * point)
                        modify_sl(client, account_id, pos.ticket, new_sl, pos.take_profit)
                        tp2_hit = True
                        print(f"🎯 TP2 alcanzado ({dist:.1f} pts). SL movido a TP1.")

            elif len(bot_positions) == 0:
                entry_price = None 
                
                # Si el precio de cierre actual es diferente al de la última señal, evaluamos operar
                if current_bar_close != last_signal_price:
                    if buy_signal:
                        if open_trade(client, account_id, 1, SYMBOL, LOT_SIZE, point):
                            position_open = True
                            tp1_hit = False
                            tp2_hit = False
                            last_signal_price = current_bar_close
                    elif sell_signal:
                        if open_trade(client, account_id, -1, SYMBOL, LOT_SIZE, point):
                            position_open = True
                            tp1_hit = False
                            tp2_hit = False
                            last_signal_price = current_bar_close

            time.sleep(15)

        except Exception as e:
            print(f"⚠️ Error en bucle: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()