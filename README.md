# Focus OS 🚀

Sistema de cronograma inteligente com IA para otimização de estudos.

## Estrutura do Projeto

- `backend/`: API FastAPI com integração Google Sheets
  - `main.py`: Ponto de entrada da API
  - `requirements.txt`: Dependências do Python
  - `.env`: Variáveis de ambiente do backend
- `frontend/`: Interface Next.js moderna
  - Login cinemático
  - Dashboard imersivo
  - Componentes interativos

## Começando

1. Clone o repositório
2. Configure as variáveis de ambiente:
   ```
   cp .env.example .env
   ```

3. Instale as dependências do backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # ou venv\Scripts\activate no Windows
   pip install -r requirements.txt
   ```

4. Instale as dependências do frontend:
   ```bash
   cd frontend
   npm install
   ```

5. Execute o projeto:
   ```bash
   # Terminal 1 - Backend
   cd backend
   uvicorn main:app --reload

   # Terminal 2 - Frontend
   cd frontend
   npm run dev
   ```