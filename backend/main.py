import os
import re
import json
import logging
import time
from typing import Optional, Dict, List, Any, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, datetime, timedelta
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


def _get_sheet_snapshot() -> Tuple[List[str], List[List[str]]]:
    """Return (headers, rows) from the cached worksheet. Rows exclude header row."""
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")
    worksheet = app.state.worksheet
    all_values = worksheet.get_all_values()
    if not all_values:
        return [], []
    headers = all_values[0]
    return headers, all_values[1:]


def _find_row_index_for(date_obj: date, user: str) -> Optional[int]:
    """Return 1-based sheet row index for the data row (including header offset)."""
    df = get_data_as_dataframe()
    if df.empty:
        return None
    if "Data" not in df.columns or "Aluno(a)" not in df.columns:
        return None
    mask = (df["Data"].dt.date == date_obj) & (
        df["Aluno(a)"].str.lower() == user.lower()
    )
    if not mask.any():
        return None
    # DataFrame index is zero-based for data rows (excluding header). Sheet rows add 2 (header + 1-indexing).
    idx0 = int(df[mask].index[0])
    return idx0 + 2


def _ensure_row_for(date_obj: date, user: str) -> int:
    """Ensure a row exists for (date, user). Return 1-based row index."""
    row_idx = _find_row_index_for(date_obj, user)
    if row_idx is not None:
        return row_idx

    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")

    worksheet = app.state.worksheet
    headers, rows = _get_sheet_snapshot()
    header_to_pos: Dict[str, int] = {h: i + 1 for i, h in enumerate(headers)}

    # Build a new row with defaults according to known columns
    new_row: List[str] = [""] * len(headers)
    if "Data" in header_to_pos:
        new_row[header_to_pos["Data"] - 1] = date_obj.strftime("%d/%m/%Y")
    if "Aluno(a)" in header_to_pos:
        new_row[header_to_pos["Aluno(a)"] - 1] = user
    if "Dia da Semana" in header_to_pos:
        # Use pt-BR short weekday names
        day_name = [
            "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"
        ][(date_obj.weekday()) % 7]
        new_row[header_to_pos["Dia da Semana"] - 1] = day_name

    # Append and compute the new row index (header row is 1)
    for attempt in range(3):
        try:
            worksheet.append_row(new_row, value_input_option="USER_ENTERED")
            # Row index is header (1) + number of existing data rows before append + 1
            return 1 + len(rows) + 1
        except Exception as e:
            if attempt == 2:
                logger.exception("Falha ao inserir nova linha: %s", e)
                raise HTTPException(status_code=500, detail="Falha ao inserir linha no Sheets.")
            time.sleep(0.4 * (attempt + 1))


def _safe_update_cells(row_index: int, updates: Dict[str, Any]) -> None:
    """Update multiple header-named cells in a given row with lightweight retries."""
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")
    worksheet = app.state.worksheet
    headers, _ = _get_sheet_snapshot()
    if not headers:
        raise HTTPException(status_code=500, detail="Planilha sem cabeçalho.")
    header_to_pos: Dict[str, int] = {h: i + 1 for i, h in enumerate(headers)}

    # Prepare cell updates; ignore unknown headers gracefully
    cell_updates: List[Tuple[int, int, Any]] = []
    for header, value in updates.items():
        if header in header_to_pos:
            cell_updates.append((row_index, header_to_pos[header], value))
        else:
            logger.debug("Cabeçalho não encontrado, ignorando update: %s", header)

    for (r, c, v) in cell_updates:
        for attempt in range(3):
            try:
                worksheet.update_cell(r, c, v)
                break
            except Exception as e:
                if attempt == 2:
                    logger.exception("Falha ao atualizar célula r=%s c=%s: %s", r, c, e)
                    raise HTTPException(status_code=500, detail="Falha ao atualizar a planilha.")
                time.sleep(0.4 * (attempt + 1))

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


# ---------- New Endpoints: /ask, /summary/{user}, /update_progress, /update_meta, /history/{user}

class AskRequest(BaseModel):
    topic: str
    count: Optional[int] = 3
    mode: Optional[str] = "mixed"  # mcq | truefalse | mixed


@app.post("/ask", response_model=dict)
def ask_quiz(req: AskRequest):
    count = min(max(req.count or 3, 3), 5)
    mode = req.mode if req.mode in {"mcq", "truefalse", "mixed"} else "mixed"
    system_prompt = (
        "Gere perguntas curtas para revisão médica. Responda EM JSON. Estrutura: "
        "{\"questions\":[{\"type\":\"mcq|truefalse\",\"question\":\"...\",\"options\":[\"A\",\"B\",...],\"answer\":\"A|true|false\",\"explanation\":\"...\"}]}"
    )
    user_prompt = (
        f"Tópico: {req.topic}. Quantidade: {count}. Modo: {mode}. "
        "Se 'mcq', inclua 4 opções. Priorize alta qualidade e clareza."
    )
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "gemma2-9b-it",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])  # type: ignore[index]
    except Exception as e:
        logger.warning("Falha no /ask (fallback): %s", e)
        # Fallback simples
        sample = {
            "questions": [
                {
                    "type": "truefalse",
                    "question": "A hemoglobina transporta oxigênio no sangue.",
                    "answer": "true",
                    "explanation": "A hemoglobina dos eritrócitos se liga ao O2 nos pulmões.",
                },
                {
                    "type": "mcq",
                    "question": "Qual válvula separa átrio esquerdo do ventrículo esquerdo?",
                    "options": ["Pulmonar", "Aórtica", "Mitral", "Tricúspide"],
                    "answer": "Mitral",
                    "explanation": "A válvula mitral (bicúspide) fica entre átrio e ventrículo esquerdos.",
                },
                {
                    "type": "mcq",
                    "question": "Principal local de absorção de nutrientes?",
                    "options": ["Estômago", "Duodeno/Jejuno", "Íleo terminal", "Cólon"],
                    "answer": "Duodeno/Jejuno",
                    "explanation": "A maior parte da absorção ocorre no intestino delgado proximal.",
                },
            ][:count]
        }
        return sample


@app.get("/summary/{user}")
def get_summary(user: str) -> dict:
    try:
        df = get_data_as_dataframe()
        if df.empty:
            return {"insights": "Sem dados para hoje.", "stats": {}}

        today = date.today()
        # Filter
        df_user = df[(df.get("Aluno(a)", "").str.lower() == user.lower()) | (df.get("Aluno(a)", "").str.lower() == "ambos")]
        df_recent = df_user.copy()
        if "Data" in df_recent.columns:
            df_recent = df_recent.sort_values("Data", ascending=False)

        # Today stats
        df_today = df_recent[df_recent["Data"].dt.date == today] if "Data" in df_recent.columns else pd.DataFrame()
        pct = None
        diff = None
        status = None
        alert = None
        if not df_today.empty:
            # Try to parse % Concluído (may contain % sign)
            if "% Concluído" in df_today.columns:
                val = str(df_today.iloc[0]["% Concluído"]).strip().replace("%", "")
                pct = int(float(val)) if val.replace(".", "", 1).isdigit() else None
            if "Dificuldade (1-5)" in df_today.columns:
                try:
                    diff = int(float(str(df_today.iloc[0]["Dificuldade (1-5)"])) )
                except Exception:
                    diff = None
            if "Status" in df_today.columns:
                status = str(df_today.iloc[0]["Status"]).strip()
            if "Alerta/Comentário" in df_today.columns:
                alert = str(df_today.iloc[0]["Alerta/Comentário"]).strip()

        insights = []
        if pct is not None:
            insights.append(f"Progresso de hoje: {pct}%")
        if diff is not None:
            insights.append(f"Dificuldade percebida: {diff}/5")
        if status:
            insights.append(f"Status: {status}")
        if alert:
            insights.append(f"Alerta: {alert}")
        if not insights:
            insights.append("Mantenha o foco nas prioridades de hoje.")

        return {
            "insights": " • ".join(insights),
            "stats": {
                "today_percent": pct,
                "today_difficulty": diff,
                "today_status": status,
                "today_alert": alert,
            },
        }
    except Exception as e:
        logger.exception("Erro em /summary: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao gerar resumo.")


class UpdateProgressRequest(BaseModel):
    user: str
    date_str: Optional[str] = None  # dd/mm/yyyy
    questoes_planejadas: Optional[int] = None
    questoes_feitas: Optional[int] = None
    teoria_feita: Optional[bool] = None
    percentual_concluido: Optional[int] = None
    status: Optional[str] = None


@app.post("/update_progress")
def update_progress(body: UpdateProgressRequest) -> dict:
    try:
        if not body.user:
            raise HTTPException(status_code=400, detail="Parâmetro 'user' é obrigatório.")
        target_date = (
            datetime.strptime(body.date_str, "%d/%m/%Y").date() if body.date_str else date.today()
        )
        row_idx = _ensure_row_for(target_date, body.user)

        updates: Dict[str, Any] = {}
        # Map into sheet columns when present
        if body.questoes_planejadas is not None:
            updates["Questões Planejadas"] = body.questoes_planejadas
        if body.questoes_feitas is not None:
            updates["Questões Feitas"] = body.questoes_feitas
        # Support combined column if present
        if body.questoes_planejadas is not None or body.questoes_feitas is not None:
            headers, _ = _get_sheet_snapshot()
            if "Questões Planejadas/Feitas" in headers:
                qp = body.questoes_planejadas if body.questoes_planejadas is not None else ""
                qf = body.questoes_feitas if body.questoes_feitas is not None else ""
                updates["Questões Planejadas/Feitas"] = f"{qp}/{qf}"

        if body.teoria_feita is not None:
            updates["Teoria Feita"] = "Sim" if body.teoria_feita else "Não"
        if body.percentual_concluido is not None:
            val = max(0, min(100, int(body.percentual_concluido)))
            updates["% Concluído"] = f"{val}%"
        if body.status is not None:
            updates["Status"] = body.status

        if not updates:
            raise HTTPException(status_code=400, detail="Nenhum campo de progresso para atualizar.")

        _safe_update_cells(row_idx, updates)
        return {"ok": True, "row": row_idx}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro em /update_progress: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao atualizar progresso.")


class UpdateMetaRequest(BaseModel):
    user: str
    date_str: Optional[str] = None
    dificuldade: Optional[int] = None  # 1-5
    prioridade: Optional[str] = None
    situacao: Optional[str] = None
    alerta: Optional[str] = None
    fase_plano: Optional[str] = None


@app.post("/update_meta")
def update_meta(body: UpdateMetaRequest) -> dict:
    try:
        if not body.user:
            raise HTTPException(status_code=400, detail="Parâmetro 'user' é obrigatório.")
        target_date = (
            datetime.strptime(body.date_str, "%d/%m/%Y").date() if body.date_str else date.today()
        )
        row_idx = _ensure_row_for(target_date, body.user)

        updates: Dict[str, Any] = {}
        if body.dificuldade is not None:
            value = max(1, min(5, int(body.dificuldade)))
            updates["Dificuldade (1-5)"] = value
        if body.prioridade is not None:
            updates["Prioridade"] = body.prioridade
        if body.situacao is not None:
            # Some sheets may use 'Situação' with cedilla
            updates["Situação"] = body.situacao
            updates["Situacao"] = body.situacao  # fallback header variant
        if body.alerta is not None:
            updates["Alerta/Comentário"] = body.alerta
        if body.fase_plano is not None:
            updates["Fase do Plano"] = body.fase_plano

        if not updates:
            raise HTTPException(status_code=400, detail="Nenhum campo de meta para atualizar.")

        _safe_update_cells(row_idx, updates)
        return {"ok": True, "row": row_idx}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro em /update_meta: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao atualizar metas.")


@app.get("/history/{user}")
def history(user: str) -> dict:
    try:
        df = get_data_as_dataframe()
        if df.empty:
            return {"history": []}
        # Filter by user or 'Ambos'
        mask_user = (df.get("Aluno(a)", "").str.lower() == user.lower()) | (df.get("Aluno(a)", "").str.lower() == "ambos")
        df_user = df[mask_user].copy()
        if "Data" not in df_user.columns:
            return {"history": []}
        # Keep last 14 days including today
        start_date = date.today() - timedelta(days=13)
        df_user = df_user[(df_user["Data"].dt.date >= start_date) & (df_user["Data"].dt.date <= date.today())]
        # Build records
        records: List[Dict[str, Any]] = []
        for _, row in df_user.sort_values("Data").iterrows():
            pct_val = None
            if "% Concluído" in df_user.columns:
                raw = str(row.get("% Concluído", "")).strip().replace("%", "")
                try:
                    pct_val = int(float(raw))
                except Exception:
                    pct_val = None
            diff_val = None
            if "Dificuldade (1-5)" in df_user.columns:
                try:
                    diff_val = int(float(str(row.get("Dificuldade (1-5)", ""))))
                except Exception:
                    diff_val = None
            records.append({
                "date": row["Data"].strftime("%d/%m"),
                "percent": pct_val,
                "difficulty": diff_val,
            })
        return {"history": records}
    except Exception as e:
        logger.exception("Erro em /history: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao obter histórico.")
