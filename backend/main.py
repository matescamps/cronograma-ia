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

if not all([GCP_CREDS_JSON, GROQ_API_KEY]):
    raise ValueError(
        "ERRO CRÍTICO: Variáveis de ambiente ausentes. Defina GCP_SERVICE_ACCOUNT_JSON e GROQ_API_KEY."
    )

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


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Iniciando Focus OS API...")
    # Initialize Google Sheets
    init_gsheets_state()

    # Probe IA availability (non-fatal)
    app.state.ia_online = False
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=8)
        app.state.ia_online = resp.ok
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
