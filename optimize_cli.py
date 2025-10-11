# optimize_cli.py
# Uso: roda no servidor (GitHub Actions) para executar otimização noturna automaticamente
import os, json, requests
from datetime import date
from dateutil.parser import parse as parse_date
import gspread
from google.oauth2.service_account import Credentials

# Carrega o service account JSON do env var (no GitHub Actions você deve configurar como secret)
sa_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
spreadsheet = os.environ.get("SPREADSHEET_ID_OR_URL")
tab_name = os.environ.get("SHEET_TAB_NAME", "Sheet1")

if not sa_json or not spreadsheet:
    print("Falta GCP_SERVICE_ACCOUNT_JSON ou SPREADSHEET_ID_OR_URL")
    exit(1)

sa = json.loads(sa_json)
scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa, scopes=scopes)
gc = gspread.authorize(creds)
if spreadsheet.startswith("http"):
    sh = gc.open_by_url(spreadsheet)
else:
    sh = gc.open_by_key(spreadsheet)
ws = sh.worksheet(tab_name)
data = ws.get_all_records()

# construir pendings
pendings = []
today = date.today()
for i, row in enumerate(data):
    d = row.get("Data")
    if isinstance(d, str) and d.strip() == "":
        continue
    try:
        dobj = parse_date(d, dayfirst=True).date()
    except:
        continue
    status = row.get("Status")
    if dobj < today and status not in [True, "TRUE", "True", 1, "1"]:
        pendings.append({
            "row_index": i+2,
            "date": dobj.strftime("%d/%m/%Y"),
            "aluno": row.get("Aluno(a)"),
            "exame": row.get("Exame"),
            "manhaPct": int(row.get("% Concluído (Manhã)") or 0),
            "tardePct": int(row.get("% Concluído (Tarde)") or 0),
            "noitePct": int(row.get("% Concluído (Noite)") or 0),
            "manhaTask": str(row.get("Matéria (Manhã)") or "") + " - " + str(row.get("Atividade Detalhada (Manhã)") or "")
        })

if not pendings:
    print("Nenhuma pendência antiga encontrada.")
    exit(0)

# Chamar IA para otimizar - usa GROQ ou OPENAI via env vars
groq_key = os.environ.get("GROQ_API_KEY")
groq_url = os.environ.get("GROQ_API_URL", "https://api.groq.ai/v1")
openai_key = os.environ.get("OPENAI_API_KEY")

prompt = "Sugira reagendamento JSON com moves[] para essas pendências:\n"
for p in pendings:
    prompt += f"- {p['date']}: {p['aluno']} - {p['exame']} - Manhã {p['manhaPct']}% ({p['manhaTask']})\n"
prompt = ("RETORNE SOMENTE UM JSON VÁLIDO com chave 'moves' (subject, from, to, period, reason).\n" + prompt)

def call_groq(prompt):
    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type":"application/json"}
    payload = {"prompt": prompt, "max_tokens": 800}
    resp = requests.post(groq_url, headers=headers, json=payload, timeout=30)
    return resp

def call_openai(prompt):
    import openai
    openai.api_key = openai_key
    messages = [{"role":"system","content":"Organizador de estudos."},{"role":"user","content":prompt}]
    resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, max_tokens=800, temperature=0.2)
    return resp.choices[0].message["content"]

resp_obj = None
if groq_key:
    try:
        r = call_groq(prompt)
        if r.status_code >=200 and r.status_code<300:
            try:
                resp_obj = r.json()
            except:
                import re
                m = re.search(r'\{[\s\S]*\}', r.text)
                if m:
                    resp_obj = json.loads(m.group(0))
    except Exception as e:
        print("Groq erro:", e)

if not resp_obj and openai_key:
    try:
        text = call_openai(prompt)
        import re
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            resp_obj = json.loads(m.group(0))
    except Exception as e:
        print("OpenAI erro:", e)

if not resp_obj:
    print("Nenhuma resposta válida de IA; encerrando.")
    exit(0)

moves = resp_obj.get("moves", [])
print("Moves recebidos:", moves)

# Aplicar moves (simplificado): vamos apenas anexar novas linhas com a data target e subject
for mv in moves:
    to = mv.get("to")
    subject = mv.get("subject")
    period = mv.get("period", "manha")
    row = [None] * len(ws.row_values(1))
    header = ws.row_values(1)
    hmap = {h:i for i,h in enumerate(header)}
    if "Data" in hmap:
        try:
            parsed = parse_date(to, dayfirst=True).date()
            row[hmap["Data"]] = parsed.strftime("%d/%m/%Y")
        except:
            row[hmap["Data"]] = to
    if "Atividade Detalhada (Manhã)" in hmap and period.startswith("man"):
        row[hmap["Atividade Detalhada (Manhã)"]] = subject
    elif "Atividade Detalhada (Tarde)" in hmap and period.startswith("tar"):
        row[hmap["Atividade Detalhada (Tarde)"]] = subject
    elif "Atividade Detalhada (Noite)" in hmap:
        row[hmap["Atividade Detalhada (Noite)"]] = subject
    ws.append_row(row)

print("Aplicação concluída.")
