"""
Vercel Cron Job — chamado a cada hora pelo scheduler do Vercel.
Verifica quais transfers têm slot configurado para o horário atual (BRT)
e dispara cada um com a janela de dados correta.
"""
import json, os, sys, time, requests
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")
from _helpers import get_active_transfers_for_slot, get_token, list_tables, get_bq_client, upsert_bq, update_transfer_run, add_log

# Brasil = UTC-3
BRT_OFFSET = timedelta(hours=-3)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Segurança: só aceita chamadas do Vercel Cron
        auth = self.headers.get("Authorization","")
        cron_secret = os.environ.get("CRON_SECRET","")
        if cron_secret and auth != f"Bearer {cron_secret}":
            self._j({"error":"unauthorized"}, 401); return

        now_brt = datetime.now(timezone.utc) + BRT_OFFSET
        slot_time = now_brt.strftime("%H:00")  # ex: "08:00"

        transfers = get_active_transfers_for_slot(slot_time)
        if not transfers:
            self._j({"slot":slot_time,"fired":0,"message":"Nenhum transfer neste horário"})
            return

        results = []
        for tr in transfers:
            result = fire_transfer(tr, slot_time)
            results.append(result)

        self._j({"slot":slot_time,"fired":len(results),"results":results})

    def _j(self, data, status=200):
        b = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.end_headers(); self.wfile.write(b)

app = handler

def fire_transfer(tr, slot_time):
    """Chama o endpoint de sync via HTTP interno para não bloquear o cron."""
    base_url = os.environ.get("BASE_URL","")
    try:
        resp = requests.post(f"{base_url}/api/sync",
                             json={"transfer_id":tr["id"],"slot_time":slot_time},
                             timeout=55)
        return {"transfer_id":tr["id"],"name":tr["name"],"status":"fired","response":resp.status_code}
    except Exception as e:
        return {"transfer_id":tr["id"],"name":tr["name"],"status":"error","error":str(e)}
