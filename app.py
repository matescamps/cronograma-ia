# app.py - Cronograma Interativo com IA (Streamlit)
# - Lê/Escreve Google Sheets usando service account
# - Integra com Groq (ou OpenAI fallback)
# - Briefing diário, otimização (JSON moves), aplicar moves, salvar edições
# - UI com data editor e botões

import streamlit as st
import pandas as pd
import json, requests, time
from datetime import datetime, date
from dateutil.parser import parse as parse_date
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Cronograma Medicina — Assistente IA", layout="wide")

# ---------- CONFIG ----------
# Nome da aba dentro da planilha (ex: "Sheet1" ou "Cronograma")
SHEET_TAB_NAME = st.secrets.get("SHEET_TAB_NAME", "Sheet1")

# Colunas esperadas (exatamente como estão na sua planilha)
EXPECTED_COLS = [
  "Data","Dificuldade (1-5)","Status","Aluno(a)","Dia da Semana","Fase do Plano",
  "Matéria (Manhã)","Atividade Detalhada (Manhã)","Teoria Feita (Manhã)","Questões Planejadas (Manhã)","Questões Feitas (Manhã)","% Concluído (Manhã)",
  "Matéria (Tarde)","Atividade Detalhada (Tarde)","Teoria Feita (Tarde)","Questões Planejadas (Tarde)","Questões Feitas (Tarde)","% Concluído (Tarde)",
  "Matéria (Noite)","Atividade Detalhada (Noite)","Teoria Feita (Noite)","Questões Planejadas (Noite)","Questões Feitas (Noite)","% Concluído (Noite)",
  "Exame","Alerta/Comentário","Situação","Prioridade","Ação da IA"
]

# ---------- UTILITÁRIOS para Google Sheets ----------
@st.cache_resource
def get_gspread_client():
    # Espera que você tenha colocado o JSON do service account em st.secrets["gcp_service_account"]
    sa_info = st.secrets.get("gcp_service_account", None)
    if sa_info is None:
        st.error("Serviço GCP não configurado. Adicione o service account JSON em Streamlit secrets com a chave 'gcp_service_account'.")
        st.stop()
    # sa_info pode ser um objeto ou string
    if isinstance(sa_info, str):
        sa = json.loads(sa_info)
    else:
        sa = sa_info
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(sa, scopes=scopes)
    client = gspread.authorize(creds)
    return client

def open_sheet():
    client = get_gspread_client()
    # planilha id ou url
    ss_identifier = st.secrets.get("SPREADSHEET_ID_OR_URL", None)
    if ss_identifier is None:
        st.error("Adicione SPREADSHEET_ID_OR_URL nos Streamlit secrets (ID ou URL da planilha).")
        st.stop()
    # abrir por URL ou id
    try:
        if ss_identifier.startswith("http"):
            sh = client.open_by_url(ss_identifier)
        else:
            sh = client.open_by_key(ss_identifier)
    except Exception as e:
        st.error(f"Erro abrindo planilha: {e}")
        st.stop()
    try:
        worksheet = sh.worksheet(SHEET_TAB_NAME)
    except Exception as e:
        st.error(f"Aba '{SHEET_TAB_NAME}' não encontrada. Verifique SHEET_TAB_NAME.")
        st.stop()
    return worksheet

@st.cache_data(ttl=30)
def load_sheet_df():
    ws = open_sheet()
    values = ws.get_all_records()
    df = pd.DataFrame(values)
    # garantir colunas esperadas
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = None
    # transformar strings de data em datetime.date
    if "Data" in df.columns:
        def to_date(v):
            if pd.isna(v) or v=="":
                return None
            if isinstance(v, (datetime, date)):
                return v.date() if isinstance(v, datetime) else v
            try:
                return parse_date(str(v), dayfirst=True).date()
            except:
                return None
        df["Data"] = df["Data"].apply(to_date)
    return df

# grava apenas as linhas modificadas (comparamos dataframes)
def write_back_changes(df_new, df_old):
    ws = open_sheet()
    header = ws.row_values(1)
    header_map = {h:i+1 for i,h in enumerate(header)}
    changed = []
    for idx in df_new.index:
        # comparar linha por linha
        row_new = df_new.loc[idx]
        row_old = df_old.loc[idx]
        if not row_new.equals(row_old):
            changed.append((idx, row_new))
    if not changed:
        return {"ok": True, "updated":0}
    for idx, row in changed:
        # row index in sheet = idx + 2 (porque header is row1)
        rownum = idx + 2
        # update each column that's changed
        for col in df_new.columns:
            val_new = row[col]
            val_old = df_old.loc[idx][col]
            # pandas NaN handling
            if (pd.isna(val_new) and pd.isna(val_old)) or (val_new==val_old):
                continue
            # convert date to str if needed
            if isinstance(val_new, (datetime, date)):
                cell_val = val_new.strftime("%d/%m/%Y")
            else:
                cell_val = "" if pd.isna(val_new) else str(val_new)
            if col in header_map:
                try:
                    ws.update_cell(rownum, header_map[col], cell_val)
                except Exception as e:
                    st.warning(f"Falha ao atualizar célula (linha {rownum}, col {col}): {e}")
    return {"ok": True, "updated": len(changed)}

# ---------- CÁLCULO do % (mesma lógica que discutimos)
def compute_pct_manha(teoria, planejadas, feitas):
    # teoria: boolean/yes/no; planejadas e feitas: int
    try:
        t = bool(theoria)
    except:
        t = False
    try:
        p = int(planejadas or 0)
    except:
        p = 0
    try:
        f = int(feitas or 0)
    except:
        f = 0
    if p == 0:
        return 100 if t else 0
    else:
        pct = min(100, int((f / p) * 100))
        return pct

# ---------- LLM / IA: tentativa Groq -> OpenAI fallback
def call_llm(prompt, expect_json=False):
    """
    Tenta chamar Groq (se configurado). Se falhar e houver OPENAI_API_KEY, tenta o OpenAI.
    - expect_json=True: pede ao modelo que retorne JSON estrito (usado no optimize)
    Retorna: string OR objeto (se parseado JSON) OR dict fallback {fallbackError: True, message:...}
    """
    # construir prompt especial se expect_json=True
    if expect_json:
        # instrução clara para JSON
        prompt = ("RETORNE SOMENTE UM JSON VÁLIDO (sem texto adicional) NO FORMATO: "
                  "{\"moves\":[{\"subject\":\"...\",\"from\":\"dd/mm/yyyy or null\",\"to\":\"dd/mm/yyyy\",\"period\":\"manha|tarde|noite\",\"reason\":\"...\"}]} \n\n"
                  "Agora analise estas pendências e retorne um JSON:\n\n" + prompt)

    # Tenta GROQ
    groq_key = st.secrets.get("GROQ_API_KEY", None)
    groq_url = st.secrets.get("GROQ_API_URL", "https://api.groq.ai/v1")
    if groq_key:
        try:
            payload = {"prompt": prompt, "max_tokens": 800, "temperature": 0.2}
            headers = {"Authorization": f"Bearer {groq_key}", "Content-Type":"application/json"}
            resp = requests.post(groq_url, headers=headers, json=payload, timeout=25)
            if resp.status_code >=200 and resp.status_code < 300:
                text = resp.text
                # tenta parsear JSON se esperado
                if expect_json:
                    try:
                        return json.loads(text)
                    except:
                        # tenta extrair json embutido no texto
                        jmatch = None
                        import re
                        m = re.search(r'\{[\s\S]*\}', text)
                        if m:
                            try:
                                return json.loads(m.group(0))
                            except:
                                pass
                return text
            else:
                st.warning(f"Groq HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            st.info(f"Groq indisponível: {e}")

    # Fallback: OpenAI (se configurado)
    openai_key = st.secrets.get("OPENAI_API_KEY", None)
    if openai_key:
        try:
            import openai
            openai.api_key = openai_key
            # usar chat completions
            system = "Você é um assistente de estudos. Responda de forma prática e direta."
            messages = [
                {"role":"system","content": system},
                {"role":"user","content": prompt}
            ]
            # tentativa de usar chat completions
            resp = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages, max_tokens=800, temperature=0.2)
            text = ""
            if resp and "choices" in resp and len(resp.choices) > 0:
                text = resp.choices[0].message["content"]
                if expect_json:
                    try:
                        return json.loads(text)
                    except:
                        import re
                        m = re.search(r'\{[\s\S]*\}', text)
                        if m:
                            try:
                                return json.loads(m.group(0))
                            except:
                                pass
                return text
        except Exception as e:
            st.info(f"OpenAI fallback falhou: {e}")

    # se chegou aqui: retornar fallback local
    return {"fallbackError": True, "message": "IA externa indisponível. Execução com fallback local."}

# ---------- Gerar briefing (texto curto e prático) ----------
def generate_briefing_from_rows(rows):
    # rows: lista de dicts com campos {aluno, exame, manhaTask, pctManha ...}
    if not rows:
        return "Sem atividades para hoje."
    prompt = "Dados do dia (resuma e sugira foco):\n"
    for r in rows:
        prompt += f"- {r.get('aluno')}: Exame {r.get('exame')}. Manhã: {r.get('manhaTask')} ({r.get('pctManha')}%). Tarde: {r.get('tardeTask')} ({r.get('pctTarde')}%). Noite: {r.get('noiteTask')} ({r.get('pctNoite')}%).\n"
    prompt += "\nDê um briefing curto (2-4 frases) e ao final 1 recomendação prática (ex: 'faça 15 questões de X agora')."
    resp = call_llm(prompt, expect_json=False)
    if isinstance(resp, dict) and resp.get("fallbackError"):
        # gerar um briefing local simples
        return resp["message"] + "\n\n" + simple_local_briefing(rows)
    if isinstance(resp, str):
        return resp
    # objeto estranho
    return json.dumps(resp, indent=2)

def simple_local_briefing(rows):
    # fallback sem IA: prioridade = menor % concluído entre manhã/tarde/noite
    outs = []
    for r in rows:
        pct = min(int(r.get("pctManha") or 100), int(r.get("pctTarde") or 100), int(r.get("pctNoite") or 100))
        outs.append((pct, r))
    outs.sort(key=lambda x: x[0])
    top = outs[0][1]
    return f"Priorize {top.get('aluno')} - {top.get('manhaTask') or top.get('tardeTask') or top.get('noiteTask')}. Sugestão prática: faça 20 questões do tópico com menor %."

# ---------- Construir pendências e otimização ----------
def build_pendings_from_df(df):
    pendings = []
    today = date.today()
    for idx, row in df.iterrows():
        d = row["Data"]
        status = row.get("Status")
        if not isinstance(d, (date,)) or d >= today:
            continue
        if status in [True, "TRUE", "True", "true", "1", 1]:
            continue
        pendings.append({
            "row_index": idx,
            "date": d.strftime("%d/%m/%Y") if d else None,
            "aluno": row.get("Aluno(a)"),
            "exame": row.get("Exame"),
            "manhaPct": int(row.get("% Concluído (Manhã)") or 0),
            "tardePct": int(row.get("% Concluído (Tarde)") or 0),
            "noitePct": int(row.get("% Concluído (Noite)") or 0),
            "manhaTask": str(row.get("Matéria (Manhã)") or "") + " - " + str(row.get("Atividade Detalhada (Manhã)") or ""),
            "tardeTask": str(row.get("Matéria (Tarde)") or "") + " - " + str(row.get("Atividade Detalhada (Tarde)") or ""),
            "noiteTask": str(row.get("Matéria (Noite)") or "") + " - " + str(row.get("Atividade Detalhada (Noite)") or "")
        })
    return pendings

def optimize_pendings(pendings):
    if not pendings:
        return {"moves": []}
    prompt = "Sugira reagendamento para estas pendências, priorizando provas mais próximas. Responda apenas com JSON no formato: {\"moves\":[{subject, from, to, period, reason}]}\nPendências:\n"
    for p in pendings:
        prompt += f"- {p['date']}: {p['aluno']} - {p['exame']} - Manhã {p['manhaPct']}% ({p['manhaTask']}), Tarde {p['tardePct']}% ({p['tardeTask']}), Noite {p['noitePct']}% ({p['noiteTask']})\n"
    resp = call_llm(prompt, expect_json=True)
    if isinstance(resp, dict) and resp.get("fallbackError"):
        return {"moves": []}
    # se resp for string tentamos parsear
    if isinstance(resp, str):
        try:
            j = json.loads(resp)
            return j
        except:
            # tentar extrair json do texto
            import re
            m = re.search(r'\{[\s\S]*\}', resp)
            if m:
                try:
                    return json.loads(m.group(0))
                except:
                    pass
            return {"moves": []}
    return resp

# ---------- Aplicar moves no dataframe/planilha ----------
def apply_moves_to_sheet(moves, df):
    """
    moves: lista de dicts com subject, from (dd/mm/yyyy or null), to (dd/mm/yyyy), period, reason
    lógica:
      - procura a linha fonte (pela descrição do assunto) e copia para target date no mesmo aluno se achar slot vazio
      - senao cria nova linha ao final com target date e a atividade no período indicado
    """
    ws = open_sheet()
    header = ws.row_values(1)
    header_map = {h:i+1 for i,h in enumerate(header)}
    data = ws.get_all_records()
    # percorre moves
    applied = []
    for m in moves:
        subject = m.get("subject")
        to_str = m.get("to")
        period = (m.get("period") or "manha").lower()
        if not subject or not to_str:
            continue
        # localizar source row (busca textual)
        source_idx = None
        for i, row in enumerate(data):
            man = f"{row.get('Matéria (Manhã)','')} — {row.get('Atividade Detalhada (Manhã)','')}"
            tar = f"{row.get('Matéria (Tarde)','')} — {row.get('Atividade Detalhada (Tarde)','')}"
            night = f"{row.get('Matéria (Noite)','')} — {row.get('Atividade Detalhada (Noite)','')}"
            s = subject.lower()
            if s in man.lower() or s in tar.lower() or s in night.lower():
                source_idx = i+2
                break
        aluno = None
        if source_idx:
            aluno = ws.cell(source_idx, header_map.get("Aluno(a)")).value
        # target date como objeto
        try:
            to_date = datetime.strptime(to_str, "%d/%m/%Y").date()
        except:
            # tentar yyyy-mm-dd
            try:
                to_date = parse_date(to_str).date()
            except:
                to_date = None
        # procurar linha existente com mesma data e aluno
        placed = False
        if to_date and aluno:
            for i, row in enumerate(data):
                cell_date = row.get("Data")
                # normalize date formats
                try:
                    if isinstance(cell_date, str) and cell_date.strip() != "":
                        d = parse_date(cell_date, dayfirst=True).date()
                    elif isinstance(cell_date, (datetime, date)):
                        d = cell_date.date() if isinstance(cell_date, datetime) else cell_date
                    else:
                        d = None
                except:
                    d = None
                if d == to_date and str(row.get("Aluno(a)")) == str(aluno):
                    # tenta inserir no período escolhido se vazio
                    if period.startswith("man"):
                        if not row.get("Atividade Detalhada (Manhã)"):
                            ws.update_cell(i+2, header_map["Atividade Detalhada (Manhã)"], subject)
                            ws.update_cell(i+2, header_map["Ação da IA"], f"Reagendado pela IA para {to_str} (manhã) — {m.get('reason','')}")
                            placed = True
                            break
                    if period.startswith("tar") and not placed:
                        if not row.get("Atividade Detalhada (Tarde)"):
                            ws.update_cell(i+2, header_map["Atividade Detalhada (Tarde)"], subject)
                            ws.update_cell(i+2, header_map["Ação da IA"], f"Reagendado pela IA para {to_str} (tarde) — {m.get('reason','')}")
                            placed = True
                            break
                    if period.startswith("noi") and not placed:
                        if not row.get("Atividade Detalhada (Noite)"):
                            ws.update_cell(i+2, header_map["Atividade Detalhada (Noite)"], subject)
                            ws.update_cell(i+2, header_map["Ação da IA"], f"Reagendado pela IA para {to_str} (noite) — {m.get('reason','')}")
                            placed = True
                            break
        # se não colocou, cria nova linha no fim
        if not placed:
            newrow = [None] * len(header)
            # set Data, Aluno, Atividade Detalhada (manhã)
            if header_map.get("Data") and to_date:
                newrow[header_map["Data"] - 1] = to_date.strftime("%d/%m/%Y")
            if header_map.get("Aluno(a)"):
                newrow[header_map["Aluno(a)"] - 1] = aluno if aluno else ""
            if period.startswith("man"):
                newrow[header_map["Atividade Detalhada (Manhã)"] - 1] = subject
            elif period.startswith("tar"):
                newrow[header_map["Atividade Detalhada (Tarde)"] - 1] = subject
            else:
                newrow[header_map["Atividade Detalhada (Noite)"] - 1] = subject
            newrow[header_map.get("Ação da IA", -1) - 1] = f"Criado pela IA: reagendamento -> {to_str} ({period})"
            ws.append_row(newrow)
            applied.append(m)
    return {"applied": len(applied)}

# ---------- UI ----------
st.title("Cronograma Interativo — Assistente IA (Medicina)")

col1, col2 = st.columns([1, 3])
with col1:
    st.subheader("Controles")
    st.write("Filtros e ações")
    df = load_sheet_df()
    aluno_filter = st.selectbox("Aluno", options=["Todos","Ana","Mateus"], index=0)
    exame_filter = st.text_input("Filtro Exame (opcional)")
    start_date = st.date_input("Data inicio", value=date.today())
    end_date = st.date_input("Data fim", value=date.today())
    if st.button("Recarregar planilha"):
        st.cache_data.clear()
        st.experimental_rerun()
    st.markdown("---")
    if st.button("Recalcular % (local) para visualização"):
        # recalcula percentuais no dataframe preview (não grava ainda)
        def recalc_row(r):
            r["% Concluído (Manhã)"] = compute_pct_manha(r.get("Teoria Feita (Manhã)"), r.get("Questões Planejadas (Manhã)"), r.get("Questões Feitas (Manhã)"))
            r["% Concluído (Tarde)"] = compute_pct_manha(r.get("Teoria Feita (Tarde)"), r.get("Questões Planejadas (Tarde)"), r.get("Questões Feitas (Tarde)"))
            r["% Concluído (Noite)"] = compute_pct_manha(r.get("Teoria Feita (Noite)"), r.get("Questões Planejadas (Noite)"), r.get("Questões Feitas (Noite)"))
            return r
        df = df.apply(recalc_row, axis=1)
        st.success("Recalculado (preview). Clique em 'Salvar alterações' para gravar na planilha.")

    if st.button("Marcar status autom. (linhas com 3x 100%)"):
        # faz atualização direta
        ws = open_sheet()
        header = ws.row_values(1)
        header_map = {h:i+1 for i,h in enumerate(header)}
        cnt = 0
        for i, r in df.iterrows():
            try:
                if int(r.get("% Concluído (Manhã)") or 0) >= 99 and int(r.get("% Concluído (Tarde)") or 0) >= 99 and int(r.get("% Concluído (Noite)") or 0) >= 99:
                    ws.update_cell(i+2, header_map["Status"], True)
                    ws.update_cell(i+2, header_map["Situação"], "Concluído (auto)")
                    cnt += 1
            except:
                pass
        st.success(f"{cnt} linhas marcadas como concluídas.")

with col2:
    st.subheader("Visão geral")
    # filtrar df
    view_df = df.copy()
    if aluno_filter != "Todos":
        view_df = view_df[view_df["Aluno(a)"] == aluno_filter]
    if exame_filter.strip() != "":
        view_df = view_df[view_df["Exame"]].astype(str)
        view_df = df[df["Exame"].astype(str).str.contains(exame_filter, case=False, na=False)]
    # filtrar por data
    def date_in_range(d):
        if not isinstance(d, (date,)):
            return False
        return d >= start_date and d <= end_date
    view_df = view_df[view_df["Data"].apply(lambda x: date_in_range(x) if x is not None else False)]
    st.write(f"Linhas: {len(view_df)}")
    # exibimos editor de dados (Streamlit tem data_editor)
    try:
        edited = st.data_editor(view_df, num_rows="dynamic")
    except Exception:
        edited = st.experimental_data_editor(view_df)

    # Botões para salvar / briefing / otimizar
    colA, colB, colC = st.columns(3)
    with colA:
        if st.button("Salvar alterações"):
            # precisamos mapear edited -> original df e escrever apenas mudanças
            # recompor o df global: substituir apenas as linhas exibidas
            base_df = df.copy()
            # edited has same index as view_df; get mapping
            for i, row in edited.reset_index().iterrows():
                orig_idx = row["index"]
                base_df.loc[orig_idx] = row.drop(labels=["index"])
            res = write_back_changes(base_df, load_sheet_df())
            if res.get("ok"):
                st.success(f"Salvo. Linhas atualizadas: {res.get('updated')}")
                st.cache_data.clear()
            else:
                st.error("Erro ao salvar.")
    with colB:
        if st.button("Pedir Briefing (IA)"):
            # montar dados do dia para briefing
            todays = []
            for i, r in df.iterrows():
                if r["Data"] == date.today():
                    todays.append({
                        "aluno": r.get("Aluno(a)"),
                        "exame": r.get("Exame"),
                        "manhaTask": f"{r.get('Matéria (Manhã)')} — {r.get('Atividade Detalhada (Manhã)')}",
                        "pctManha": int(r.get("% Concluído (Manhã)") or 0),
                        "tardeTask": f"{r.get('Matéria (Tarde)')} — {r.get('Atividade Detalhada (Tarde)')}",
                        "pctTarde": int(r.get("% Concluído (Tarde)") or 0),
                        "noiteTask": f"{r.get('Matéria (Noite)')} — {r.get('Atividade Detalhada (Noite)')}",
                        "pctNoite": int(r.get("% Concluído (Noite)") or 0),
                    })
            briefing = generate_briefing_from_rows(todays)
            st.info("Briefing da IA:")
            st.write(briefing)
    with colC:
        if st.button("Otimizar pendências (IA)"):
            # construir pendings
            pendings = build_pendings_from_df(df)
            st.write(f"Pendências encontradas: {len(pendings)}")
            if len(pendings) == 0:
                st.success("Nenhuma pendência antiga encontrada.")
            else:
                with st.spinner("Pedindo sugestões à IA (JSON)..."):
                    optimized = optimize_pendings(pendings)
                # mostrar moves
                st.write("Sugestões recebidas (moves):")
                st.json(optimized)
                moves = optimized.get("moves", []) if isinstance(optimized, dict) else []
                if moves:
                    if st.button("Aplicar moves sugeridos"):
                        res = apply_moves_to_sheet(moves, df)
                        st.success(f"Ações aplicadas: {res.get('applied')}")
                        st.cache_data.clear()
                        st.experimental_rerun()

st.markdown("---")
st.caption("Desenvolvido para cronograma de Medicina — Streamlit + Google Sheets + IA. Use com cuidado, teste em cópia da planilha.")
