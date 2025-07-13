import os, json, threading, requests, tkinter as tk
from tkinter import ttk
from datetime import datetime, date
import webbrowser

API_24H = "https://api.mexc.com/api/v3/ticker/24hr"
API_KLINES = "https://api.mexc.com/api/v3/klines"
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
STATE_FILE = os.path.join(DATA_DIR, 'trade_state.json')
os.makedirs(DATA_DIR, exist_ok=True)

ROCKETCHAT_SERVER = 'https://ae40-2402-800-63e6-8e0d-996-98b9-e56e-503.ngrok-free.app'
ROCKETCHAT_USER = 'caothu78'
ROCKETCHAT_PASS = 'Namhk555'
rocketchat_token = None
rocketchat_user_id = None

try:
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        trade_state = json.load(f)
except:
    trade_state = {}

def login_rocket():
    global rocketchat_token, rocketchat_user_id
    try:
        r = requests.post(f"{ROCKETCHAT_SERVER}/api/v1/login", json={
            'user': ROCKETCHAT_USER,
            'password': ROCKETCHAT_PASS
        })
        if r.ok:
            d = r.json()['data']
            rocketchat_token = d['authToken']
            rocketchat_user_id = d['userId']
    except Exception as e:
        print("Rocket.Chat login error:", e)

def create_channel_if_not_exist(channel):
    if not rocketchat_token:
        return
    try:
        headers = {
            'X-Auth-Token': rocketchat_token,
            'X-User-Id': rocketchat_user_id,
            'Content-type': 'application/json'
        }
        requests.post(f"{ROCKETCHAT_SERVER}/api/v1/channels.create", json={
            'name': channel.lower()
        }, headers=headers)
    except: pass

def send_rocket(channel, message):
    if not rocketchat_token:
        return
    try:
        create_channel_if_not_exist(channel)
        headers = {
            'X-Auth-Token': rocketchat_token,
            'X-User-Id': rocketchat_user_id,
            'Content-type': 'application/json'
        }
        requests.post(f"{ROCKETCHAT_SERVER}/api/v1/chat.postMessage", json={
            'channel': f"#{channel.lower()}",
            'text': message
        }, headers=headers)
    except Exception as e:
        print("Rocket.Chat error:", e)

def format_price(p):
    s = f"{p:.12f}".rstrip('0').rstrip('.')
    return s if s else "0"

def open_chart(event, tree):
    sel = tree.selection()
    if not sel: return
    sym = tree.item(sel[0])['values'][0].split(' ')[0]
    base = sym[:-4] if sym.endswith('USDT') else sym
    webbrowser.open(f"https://www.mexc.com/exchange/{base}_USDT?_from")

def get_klines(symbol, interval, limit):
    try:
        url = f"{API_KLINES}?symbol={symbol}&interval={interval}&limit={limit}"
        return requests.get(url, timeout=5).json()
    except:
        return []

def gain(c): return (float(c[4]) - float(c[1])) / float(c[1]) * 100
def gain_from_to(c1, c2): return (float(c2[4]) - float(c1[1])) / float(c1[1]) * 100
def kline_up(c): return float(c[4]) > float(c[1])

def is_valid_trade(symbol):
    sym = symbol.replace('_', '')
    try:
        k30 = get_klines(sym, '30m', 4)
        if len(k30) >= 3 and all(gain(c) > 5 for c in k30[:3]):
            return True
        if len(k30) >= 3 and sum(gain(c) for c in k30[:3]) >= 30:
            return True
        if len(k30) == 4 and gain_from_to(k30[0], k30[3]) >= 30:
            return True

        k15 = get_klines(sym, '15m', 4)
        if len(k15) >= 3 and sum(gain(c) for c in k15[:3]) >= 15:
            return True
        if len(k15) >= 3 and all(gain(c) > 20 for c in k15[:3]):
            return True
        if len(k15) == 4 and gain_from_to(k15[0], k15[3]) >= 30:
            return True

        k5 = get_klines(sym, '5m', 7)
        if len(k5) == 7 and all(kline_up(c) for c in k5):
            return True
        if len(k5) == 4 and gain_from_to(k5[0], k5[3]) >= 30:
            return True

        k1 = get_klines(sym, '1m', 9)
        if len(k1) >= 9 and all(kline_up(c) for c in k1):
            if gain_from_to(k1[0], k1[8]) > 20:
                return True
        if len(k1) >= 3 and all(gain(c) > 10 for c in k1[:3]):
            return True
    except: pass
    return False

def refresh_top():
    try:
        data = requests.get(API_24H, timeout=5).json()
    except: return
    tree_top.delete(*tree_top.get_children())
    top_list.clear()
    for it in data:
        s = it.get('symbol','')
        if not s.endswith('USDT'): continue
        last = float(it.get('lastPrice',0))
        op = float(it.get('openPrice',0))
        high = float(it.get('highPrice',0))
        low = float(it.get('lowPrice',0))
        pct24 = ((last - op) / op * 100) if op else 0
        rng = ((high - low) / low * 100) if low else 0
        if pct24 >= 20:
            tree_top.insert('', 'end', values=(s, format_price(last), f"{pct24:.2f}%", f"{rng:.2f}%", format_price(high), format_price(low)))
            top_list.append((s, last))

def refresh_trade():
    try: cap = float(capital_var.get())
    except: cap = 100.0
    for s, last in top_list:
        if s not in trade_state:
            if is_valid_trade(s):
                per = cap * 0.1
                qty = round(per / last, 6)
                trade_state[s] = {
                    'buy_price': last,
                    'buy_amount': per,
                    'quantity': qty,
                    'notified': False
                }
        if s in trade_state:
            rec = trade_state[s]
            if not rec.get('notified'):
                send_rocket(s, f"🛒 MUA {s} giá {format_price(last)} USDT – 10% vốn")
                print(f"[🔔 {s}] MUA {format_price(last)} USDT")
                rec['notified'] = True

            buy = rec['buy_price']
            qty = rec['quantity']
            pnl_pct = (last - buy) / buy * 100
            if pnl_pct <= -20:
                total = qty * last
                send_rocket(s, f"🔻 BÁN {s} toàn bộ do giảm >20%\nGiá: {format_price(last)}\nThu về: {format_price(total)}")
                log_sell(s, buy, last, qty)
                del trade_state[s]

    tree_trade.delete(*tree_trade.get_children())
    for s in trade_state:
        rec = trade_state[s]
        buy = rec['buy_price']
        qty = rec['quantity']
        last = next((l for sym, l in top_list if sym == s), buy)
        pnl_pct = (last - buy) / buy * 100
        tree_trade.insert('', 'end', values=(f"{s} ({pnl_pct:+.2f}%)", format_price(buy), format_price(last), format_price(qty * last)))

    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(trade_state, f, ensure_ascii=False, indent=2)

def log_sell(symbol, buy_price, sell_price, qty):
    with open(os.path.join(DATA_DIR, f"trade_log_{date.today()}.txt"), 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()} | SELL {symbol} | Buy: {buy_price} | Sell: {sell_price} | Qty: {qty} | PnL: {round((sell_price - buy_price) * qty, 2)}\n")

def safe_call(fn): threading.Thread(target=fn, daemon=True).start()
def refresh_top_loop(): safe_call(refresh_top); root.after(30000, refresh_top_loop)
def refresh_trade_loop(): safe_call(refresh_trade); root.after(5000, refresh_trade_loop)

root = tk.Tk()
root.title("🚀 MEXC Tool GUI")
root.geometry("1000x700")
login_rocket()

cols_top = ('Coin','Price','%24h','Range','High24h','Low24h')
tree_top = ttk.Treeview(root, columns=cols_top, show='headings', height=12)
for c in cols_top:
    tree_top.heading(c, text=c)
    tree_top.column(c, anchor='center', width=100)
tree_top.pack(fill='x', padx=10, pady=(10, 5))
tree_top.bind('<Double-1>', lambda e: open_chart(e, tree_top))

cols_trade = ('Coin', 'Buy', 'Now', 'Total')
tree_trade = ttk.Treeview(root, columns=cols_trade, show='headings', height=10)
for c in cols_trade:
    tree_trade.heading(c, text=c)
    tree_trade.column(c, anchor='center', width=120)
tree_trade.pack(fill='x', padx=10, pady=(0, 10))
tree_trade.bind('<Double-1>', lambda e: open_chart(e, tree_trade))

frm = ttk.Frame(root)
frm.pack(pady=(0, 10))
ttk.Label(frm, text='💰 Vốn (USDT):').pack(side='left')
capital_var = tk.StringVar(value='100')
ttk.Entry(frm, textvariable=capital_var, width=10).pack(side='left', padx=5)
ttk.Button(frm, text='🔄 Làm mới', command=lambda: [safe_call(refresh_top), safe_call(refresh_trade)]).pack(side='left', padx=5)

top_list = []
root.after(100, refresh_top_loop)
root.after(1000, refresh_trade_loop)
root.mainloop()
