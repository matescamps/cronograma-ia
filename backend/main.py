import os
import re
import json
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date
import requests
from dotenv import load_dotenv

# Load environment variables (from .env when present)
load_dotenv()

# Configure structured logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger("focus_os")

# Non-negotiable defaults (act as safe fallbacks if envs are absent)
DEFAULT_SPREADSHEET_ID = "1AdMTt9YmJ2QM-We_9NxsEIvW1lJeocLAWBsNbOiDTLE"
DEFAULT_SHEET_NAME = "Cronograma e Utilizadores"

# Read environment variables (support both ID or full URL)
GCP_CREDS_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
SPREADSHEET_IDENTIFIER = (
    os.getenv("SPREADSHEET_ID_OR_URL")
    or os.getenv("SPREADSHEET_ID")
    or DEFAULT_SPREADSHEET_ID
)
SHEET_NAME = os.getenv("SHEET_TAB_NAME") or DEFAULT_SHEET_NAME
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

app = FastAPI(title="Focus OS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _redact(text: Optional[str]) -> str:
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def extract_spreadsheet_key(identifier: str) -> str:
    """Return the spreadsheet key whether an ID or full URL was provided."""
    if not identifier:
        return ""
    if identifier.startswith("http"):
        # Try to capture the segment between '/d/' and the next '/'
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", identifier)
        if match:
            return match.group(1)
        # If no match, return as-is; gspread can open_by_url
        return identifier
    return identifier


def init_gsheets_state() -> None:
    """Initialize Google Sheets connection and cache worksheet in app state, with detailed logging."""
    app.state.worksheet = None
    app.state.gs_last_error = None
    try:
        if not GCP_CREDS_JSON:
            logger.warning("Variável GCP_SERVICE_ACCOUNT_JSON ausente; pulando conexão ao Google Sheets.")
            return
        logger.info("Inicializando autenticação com Google usando service account (email mascarado).")
        creds_dict = json.loads(GCP_CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        identifier = SPREADSHEET_IDENTIFIER
        key_or_url = extract_spreadsheet_key(identifier)
        logger.info(
            "Conectando ao Spreadsheet: identificador=%s (sheet='%s')",
            _redact(key_or_url),
            SHEET_NAME,
        )

        if key_or_url.startswith("http"):
            spreadsheet = client.open_by_url(key_or_url)
        else:
            spreadsheet = client.open_by_key(key_or_url)

        logger.info("Spreadsheet aberto com sucesso. Enumerando abas disponíveis...")
        available_titles = [ws.title for ws in spreadsheet.worksheets()]
        logger.info("Abas encontradas: %s", ", ".join(available_titles))

        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except WorksheetNotFound:
            logger.error(
                "Aba '%s' não encontrada. Verifique o nome exato. Abas disponíveis: %s",
                SHEET_NAME,
                ", ".join(available_titles),
            )
            raise

        app.state.worksheet = worksheet
        logger.info("Conexão com a aba '%s' estabelecida.", worksheet.title)
    except Exception as e:
        app.state.gs_last_error = str(e)
        app.state.worksheet = None
        logger.exception("Falha ao conectar ao Google Sheets: %s", e)


def get_data_as_dataframe() -> pd.DataFrame:
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(
            status_code=503,
            detail="Serviço indisponível: conexão com a planilha falhou. Consulte /status para detalhes.",
        )

    worksheet = app.state.worksheet
    logger.info("Solicitando dados da planilha '%s' via get_all_values()...", worksheet.title)
    all_values = worksheet.get_all_values()
    logger.info("Linhas retornadas (incl. cabeçalho): %d", len(all_values))
    if not all_values:
        return pd.DataFrame()

    headers = all_values[0]
    df = pd.DataFrame(all_values[1:], columns=headers)
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    else:
        logger.warning("Coluna 'Data' não encontrada na planilha. Datas serão ignoradas.")
    return df


def _safe_number(value) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        value_str = str(value).replace('%', '').strip()
        if value_str == '':
            return 0.0
        return float(value_str)
    except Exception:
        return 0.0


@app.get("/summary/{user}")
def get_summary(user: str) -> dict:
    """Resumo agregado do dia para o usuário: progresso por período e métricas gerais."""
    df = get_data_as_dataframe()
    if df.empty:
        return {"user": user, "date": str(date.today()), "periods": [], "overall": {"percent": 0, "planned": 0, "done": 0}}

    today = date.today()
    df_today = df[df['Data'].dt.date == today]
    df_user = df_today[(df_today['Aluno(a)'].str.lower() == user.lower()) | (df_today['Aluno(a)'].str.lower() == 'ambos')]
    if df_user.empty:
        return {"user": user, "date": str(today), "periods": [], "overall": {"percent": 0, "planned": 0, "done": 0}}

    # Escolhe a primeira linha relevante (simplificação)
    row = df_user.iloc[0]
    periods = []
    totals_planned = 0
    totals_done = 0
    percents = []
    for period in ['Manhã', 'Tarde', 'Noite']:
        subject = str(row.get(f"Matéria ({period})", '')).strip()
        activity = str(row.get(f"Atividade Detalhada ({period})", '')).strip()
        planned = _safe_number(row.get(f"Questões Planejadas ({period})", 0))
        done = _safe_number(row.get(f"Questões Feitas ({period})", 0))
        percent = _safe_number(row.get(f"% Concluído ({period})", 0))
        if not percent and planned > 0:
            percent = min(100.0, round((done / planned) * 100.0))
        if subject or activity or planned or done or percent:
            periods.append({
                "period": period,
                "subject": subject,
                "activity": activity,
                "planned": planned,
                "done": done,
                "percent": percent,
            })
            if planned or done:
                totals_planned += planned
                totals_done += done
            if percent:
                percents.append(percent)

    overall_percent = round(sum(percents) / len(percents)) if percents else (round((totals_done / totals_planned) * 100) if totals_planned else 0)

    summary = {
        "user": user,
        "date": str(today),
        "periods": periods,
        "overall": {
            "percent": overall_percent,
            "planned": totals_planned,
            "done": totals_done,
        },
        "meta": {
            "difficulty": _safe_number(row.get('Dificuldade (1-5)', 0)),
            "priority": str(row.get('Prioridade', '')).strip(),
            "status": str(row.get('Situação', '')).strip(),
            "alert": str(row.get('Alerta/Comentário', '')).strip(),
            "phase": str(row.get('Fase do Plano', '')).strip(),
            "weekday": str(row.get('Dia da Semana', '')).strip(),
            "exam": str(row.get('Exame', '')).strip(),
        }
    }

    return summary

@app.get("/")
def read_root():
    return {"status": "Focus OS API online. Ready for duty."}

@app.get("/tasks/{user}")
def get_today_tasks(user: str):
    try:
        df = get_data_as_dataframe()
        if df.empty: return []
        
        today = date.today()
        df_today = df[df['Data'].dt.date == today]
        df_user_today = df_today[
            (df_today['Aluno(a)'].str.lower() == user.lower()) | 
            (df_today['Aluno(a)'].str.lower() == 'ambos')
        ].fillna('').to_dict('records')
        
        return df_user_today
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CoachRequest(BaseModel):
    subject: str
    activity: str

@app.post("/coach", response_model=dict)
def get_coach_advice(request: CoachRequest):
    prompt = f'Você é o "System Coach" do Focus OS. Sua missão é gerar um plano tático e 2 flashcards. Responda EXCLUSIVAMENTE em JSON com chaves "summary" e "flashcards" (lista de objetos com "q" e "a"). MISSÃO: Matéria: {request.subject}, Atividade: {request.activity}'
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return json.loads(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        logger.error("Falha na chamada à IA Groq: %s", e)
        return {"summary": f"// TRANSMISSÃO INTERROMPIDA // Plano de contingência para {request.subject}: Focar nos fundamentos. Revisar por 20min, praticar por 30min.", "flashcards": [{"q": "Principal objetivo?", "a": "Entender o conceito central."}, {"q": "O que evitar?", "a": "Distrações."}]}


class AskRequest(BaseModel):
    message: str
    user: str | None = None
    context: dict | None = None


@app.post("/ask", response_model=dict)
def ask_ai(req: AskRequest):
    """Endpoint de chat livre com a IA (resposta em texto)."""
    base_system = (
        "Você é o assistente 'System Coach' do Focus OS. Responda de forma clara,"
        " objetiva e motivadora. Se relevante, sugira 2-3 passos práticos."
    )
    try:
        if not GROQ_API_KEY:
            return {"answer": "IA offline no momento. Tente novamente mais tarde."}
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        messages = [
            {"role": "system", "content": base_system},
            {"role": "user", "content": req.message},
        ]
        payload = {
            "model": "gemma2-9b-it",
            "messages": messages,
            "temperature": 0.6,
        }
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return {"answer": content}
    except Exception as e:
        logger.error("Falha em /ask: %s", e)
        return {"answer": "Desculpe, houve um erro ao processar sua pergunta. Tente novamente."}


# ------------------ Progress & History (writes to Google Sheets) ------------------
class UpdateProgressRequest(BaseModel):
    user: str
    period: str  # 'Manhã' | 'Tarde' | 'Noite'
    planned: int | None = None
    done: int | None = None
    theory_done: bool | None = None
    percent: float | None = None
    status: str | None = None


class UpdateMetaRequest(BaseModel):
    user: str
    difficulty: float | None = None  # Dificuldade (1-5)
    priority: str | None = None
    situation: str | None = None  # Situação
    alert: str | None = None  # Alerta/Comentário
    phase: str | None = None  # Fase do Plano


def _weekday_pt_br(d: date) -> str:
    mapping = {
        0: "Segunda",
        1: "Terça",
        2: "Quarta",
        3: "Quinta",
        4: "Sexta",
        5: "Sábado",
        6: "Domingo",
    }
    return mapping[d.weekday()]


def _ensure_worksheet_ready():
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Planilha indisponível.")
    return app.state.worksheet


def _headers_map(ws) -> dict:
    headers = ws.row_values(1)
    return {h: idx + 1 for idx, h in enumerate(headers)}


def _find_row_for_today(ws, user: str) -> int | None:
    all_values = ws.get_all_values()
    if not all_values:
        return None
    headers = all_values[0]
    try:
        col_data = headers.index("Data")
        col_user = headers.index("Aluno(a)")
    except ValueError:
        return None
    today_str = date.today().strftime("%d/%m/%Y")
    for i in range(1, len(all_values)):
        row = all_values[i]
        data_val = row[col_data] if col_data < len(row) else ""
        user_val = row[col_user].lower() if col_user < len(row) and row[col_user] else ""
        if data_val == today_str and user_val == user.lower():
            return i + 1  # 1-based index (including header)
    return None


def _create_today_row(ws, user: str) -> int:
    headers = ws.row_values(1)
    size = len(headers)
    row = [""] * size
    header_to_index = {h: i for i, h in enumerate(headers)}
    if "Data" in header_to_index:
        row[header_to_index["Data"]] = date.today().strftime("%d/%m/%Y")
    if "Aluno(a)" in header_to_index:
        row[header_to_index["Aluno(a)"]] = user
    if "Dia da Semana" in header_to_index:
        row[header_to_index["Dia da Semana"]] = _weekday_pt_br(date.today())
    ws.append_row(row, value_input_option="USER_ENTERED")
    return ws.row_count


@app.post("/update_progress")
def update_progress(req: UpdateProgressRequest) -> dict:
    ws = _ensure_worksheet_ready()
    period = req.period
    if period not in ("Manhã", "Tarde", "Noite"):
        raise HTTPException(status_code=400, detail="Período inválido.")

    row_idx = _find_row_for_today(ws, req.user)
    if row_idx is None:
        logger.info("Linha do dia não encontrada para %s. Criando...", req.user)
        row_idx = _create_today_row(ws, req.user)

    headers = _headers_map(ws)
    updates: list[tuple[int, int, str]] = []

    def maybe_update(header_name: str, value) -> None:
        if value is None:
            return
        col = headers.get(header_name)
        if not col:
            return
        updates.append((row_idx, col, value))

    # Derivar percent se não enviado e se possível
    percent = req.percent
    if percent is None and req.planned and req.planned > 0 and req.done is not None:
        percent = min(100, round((req.done / req.planned) * 100))

    maybe_update(f"Questões Planejadas ({period})", req.planned)
    maybe_update(f"Questões Feitas ({period})", req.done)
    maybe_update(f"% Concluído ({period})", percent)
    if req.theory_done is not None:
        maybe_update(f"Teoria Feita ({period})", "Sim" if req.theory_done else "Não")
    maybe_update("Status", req.status)

    # Execute updates
    for r, c, v in updates:
        ws.update_cell(r, c, v)

    return {"ok": True, "row": row_idx, "updated": len(updates)}


@app.post("/update_meta")
def update_meta(req: UpdateMetaRequest) -> dict:
    ws = _ensure_worksheet_ready()
    row_idx = _find_row_for_today(ws, req.user)
    if row_idx is None:
        row_idx = _create_today_row(ws, req.user)
    headers = _headers_map(ws)
    updates: list[tuple[int, int, str]] = []

    def maybe_update(header_name: str, value) -> None:
        if value is None:
            return
        col = headers.get(header_name)
        if not col:
            return
        updates.append((row_idx, col, value))

    maybe_update("Dificuldade (1-5)", req.difficulty)
    maybe_update("Prioridade", req.priority)
    maybe_update("Situação", req.situation)
    maybe_update("Alerta/Comentário", req.alert)
    maybe_update("Fase do Plano", req.phase)

    for r, c, v in updates:
        ws.update_cell(r, c, v)

    return {"ok": True, "row": row_idx, "updated": len(updates)}


@app.get("/history/{user}")
def history(user: str, days: int = 14) -> dict:
    df = get_data_as_dataframe()
    if df.empty:
        return {"user": user, "items": []}
    df_user = df[(df['Aluno(a)'].str.lower() == user.lower()) | (df['Aluno(a)'].str.lower() == 'ambos')]
    df_user = df_user.sort_values(by='Data', ascending=False)
    items = []
    count = 0
    for _, row in df_user.iterrows():
        if pd.isna(row.get('Data')):
            continue
        d = row['Data'].date()
        # Percentual médio dos períodos
        pcts = []
        for period in ['Manhã', 'Tarde', 'Noite']:
            pct = _safe_number(row.get(f"% Concluído ({period})", 0))
            if pct:
                pcts.append(pct)
        overall = round(sum(pcts)/len(pcts)) if pcts else 0
        items.append({
            "date": d.isoformat(),
            "weekday": _weekday_pt_br(d),
            "overall": overall,
            "difficulty": _safe_number(row.get('Dificuldade (1-5)', 0)),
            "status": str(row.get('Situação', '')).strip(),
        })
        count += 1
        if count >= days:
            break
    return {"user": user, "items": items}


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Iniciando Focus OS API...")
    # Initialize Google Sheets
    init_gsheets_state()

    # Probe IA availability (non-fatal)
    app.state.ia_online = False
    try:
        if GROQ_API_KEY:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=8)
            app.state.ia_online = resp.ok
        else:
            app.state.ia_online = False
            logger.warning("GROQ_API_KEY ausente; IA marcada como offline.")
        logger.info("IA Groq online: %s", app.state.ia_online)
    except Exception as e:
        logger.warning("Não foi possível verificar IA Groq: %s", e)


@app.get("/status")
def status() -> dict:
    sheet_ok = hasattr(app.state, "worksheet") and app.state.worksheet is not None
    last_error = getattr(app.state, "gs_last_error", None)
    worksheet_title = app.state.worksheet.title if sheet_ok else None
    return {
        "sheet": {
            "online": sheet_ok,
            "worksheet": worksheet_title,
            "identifier": _redact(extract_spreadsheet_key(SPREADSHEET_IDENTIFIER)),
            "last_error": last_error,
        },
        "ia": {
            "online": bool(getattr(app.state, "ia_online", False)),
            "model": "gemma2-9b-it",
        },
    }
