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
gc = gspread_authorize(creds) # Renomeado para evitar conflito com gspread
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
    d = row.get(COL_DATA)
    if isinstance(d, str) and d.strip() == "":
        continue
    try:
        dobj = parse_date(d, dayfirst=True).date()
    except:
        continue
    status = row.get(COL_STATUS)
    if dobj < today and status not in COMPLETED_STATUSES:
        pendings.append({
            "row_index": i+2,
            "date": dobj.strftime("%d/%m/%Y"),
            "aluno": row.get(COL_ALUNO),
            "exame": row.get(COL_EXAME),
            "manhaPct": int(row.get(COL_MANHA_PCT) or 0),
            "tardePct": int(row.get(COL_TARDE_PCT) or 0),
            "noitePct": int(row.get(COL_NOITE_PCT) or 0),
            "manhaTask": f"{row.get(COL_MANHA_MATERIA) or ''} - {row.get(COL_MANHA_ATIVIDADE) or ''}"
        })

if not pendings:
    print("Nenhuma pendência antiga encontrada.")
    exit(0)

# Chamar IA para otimizar - usa GROQ ou OPENAI via env vars
groq_key = os.environ.get("GROQ_API_KEY")
groq_url = os.environ.get("GROQ_API_URL", "https://api.groq.ai/v1")
openai_key = os.environ.get("OPENAI_API_KEY")

pending_lines = "\n".join([
    f"- {p['date']}: {p['aluno']} - {p['exame']} - Manhã {p['manhaPct']}% ({p['manhaTask']})" for p in pendings
])
prompt = f"RETORNE SOMENTE UM JSON VÁLIDO com chave 'moves' (subject, from, to, period, reason).\nSugira reagendamento JSON com moves[] para essas pendências:\n{pending_lines}"

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

def get_ai_suggestion(prompt):
    """Tenta obter a sugestão da IA, primeiro com Groq, depois com OpenAI como fallback."""
    def parse_response(text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group(0))
        return None

    if groq_key:
        try:
            print("Tentando chamada com Groq...")
            r = call_groq(prompt)
            r.raise_for_status() # Lança exceção para status de erro (4xx ou 5xx)
            return parse_response(r.text)
        except Exception as e:
            print(f"Erro na chamada com Groq: {e}")

    if openai_key:
        try:
            print("Tentando chamada com OpenAI...")
            text = call_openai(prompt)
            return parse_response(text)
        except Exception as e:
            print(f"Erro na chamada com OpenAI: {e}")
    return None

resp_obj = get_ai_suggestion(prompt)
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
    if COL_DATA in hmap:
        try:
            parsed = parse_date(to, dayfirst=True).date()
            row[hmap[COL_DATA]] = parsed.strftime("%d/%m/%Y")
        except:
            row[hmap[COL_DATA]] = to
    if COL_MANHA_ATIVIDADE in hmap and period.startswith("man"):
        row[hmap[COL_MANHA_ATIVIDADE]] = subject
    elif COL_TARDE_ATIVIDADE in hmap and period.startswith("tar"):
        row[hmap[COL_TARDE_ATIVIDADE]] = subject
    elif COL_NOITE_ATIVIDADE in hmap: # Fallback para noite
        row[hmap[COL_NOITE_ATIVIDADE]] = subject
    ws.append_row(row)

print("Aplicação concluída.")
