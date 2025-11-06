# Contagem/Marcação de Pessoas em Imagens (YOLOv8)

Este projeto detecta e marca todas as pessoas (classe COCO "person") em uma imagem usando os modelos YOLOv8 da Ultralytics. Gera uma imagem anotada com caixas (e, quando disponível, contornos/segmentação), além de metadata em JSON e, opcionalmente, CSV.

## Instalação

- Requisitos: Python 3.8+
- Recomenda-se usar um ambiente virtual.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Pacotes principais: `ultralytics`, `opencv-python`, `pillow`, `numpy`.

Observações:
- Os pesos `yolov8n.pt` e `yolov8n-seg.pt` são baixados automaticamente pela Ultralytics na primeira execução.
- Se houver GPU disponível, o script tenta utilizá-la (via `--device cuda` ou auto-detecção).

## Uso (Imagem Única)

Com o ambiente ativado:

```bash
python count_people.py --input caminho/para/imagem.jpg
```

Opções úteis:
- `--output_dir` Diretório de saída (padrão: pasta do input)
- `--mode {seg,bbox}` Modo de anotação: `seg` (contornos/máscaras) ou `bbox` (somente caixas). Padrão: `seg`
- `--conf FLOAT` Confiança mínima (padrão: 0.25)
- `--thickness INT` Espessura das linhas (padrão: 3)
- `--label/--no-label` Exibir ou não rótulos com índice/confiança (padrão: exibir)
- `--device` `cpu`, `cuda`, `cuda:0`, etc. (padrão: auto)
- `--no-csv` Não exportar CSV

Exemplos:
```bash
# Segmentação com rótulos
python count_people.py --input exemplo.jpg

# Somente caixas, confiança mínima 0.35 e sem rótulos
python count_people.py --input exemplo.jpg --mode bbox --conf 0.35 --no-label

# Especificando diretório de saída e dispositivo
python count_people.py --input exemplo.jpg --output_dir out --device cuda:0
```

## Uso (Pasta de Imagens)

O script também aceita uma pasta em `--input` (não recursivo). Todos os arquivos `.jpg/.jpeg/.png` do primeiro nível serão processados.

```bash
# CPU
python count_people.py --input caminho/para/pasta --output_dir out

# Apple Silicon (GPU via Metal)
python count_people.py --input caminho/para/pasta --output_dir out --device mps
```

Se `--output_dir` não for informado, será criada uma subpasta `out` dentro da pasta de entrada. Ao final, será impresso um resumo com o total processado.

## Saídas

Ao processar `imagem.jpg`, são gerados no diretório escolhido:
- Imagem anotada: `imagem_marked.jpg` (ou `.png` em fallback)
- Metadata JSON: `imagem_marked_meta.json`
- CSV com caixas: `imagem_marked_boxes.csv` (se não desativado)

O JSON inclui contagem total, parâmetros usados e lista de detecções com `bbox` e, no modo `seg`, os polígonos das máscaras.

## Estrutura principal

- `count_people.py` Script CLI que:
  - Lê a imagem corrigindo EXIF
  - Executa YOLOv8 (`yolov8n` ou `yolov8n-seg`) restringindo à classe "person"
  - Desenha caixas e contornos
  - Exporta imagem, JSON e opcionalmente CSV

## Dicas e solução de problemas

- Caso a importação de `ultralytics` falhe, confirme a instalação e, se necessário:
  ```bash
  pip install --upgrade pip setuptools wheel
  pip install ultralytics
  ```
- Para usar GPU, instale versões de PyTorch compatíveis com CUDA conforme a documentação da Ultralytics/PyTorch e use `--device cuda`.

---

Autor: você

---

## Integração com Banco de Dados (Postgres)

Opcionalmente, os resultados podem ser armazenados em um Postgres (incluindo imagem de entrada, imagem anotada e metadados). A tabela utilizada é `images`:

```
images(
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ,
  input_filename TEXT,
  output_filename TEXT,
  metadata JSONB,
  input_image BYTEA,
  output_image BYTEA,
  hash TEXT UNIQUE
)
```

Variáveis de ambiente necessárias:
- `DB_HOST`, `DB_PORT` (padrão 5432), `DB_NAME`, `DB_USER`, `DB_PASSWORD`

Como habilitar pelo CLI:
- Se as variáveis acima estiverem definidas, o armazenamento em DB é habilitado automaticamente; use `--no-db-store` para desabilitar.
- Para forçar, use `--db-store`.

Exemplos:
```bash
export DB_HOST=localhost DB_PORT=5432 DB_NAME=peopledb DB_USER=peopleuser DB_PASSWORD=peoplepass
python count_people.py --input seq_000001.jpg --output_dir out --db-store
python count_people.py --input caminho/para/pasta --output_dir out --db-store
```

Deduplicação: é calculado um hash SHA-256 da imagem de entrada e usado para evitar salvar duplicados.

## Docker Compose (DB + API + UI)

Um ambiente completo está disponível via Docker Compose, incluindo Postgres, uma API FastAPI e uma UI em Streamlit.

Subir tudo:
```bash
docker compose up -d
```

Serviços:
- DB (Postgres): `localhost:5432` (banco `peopledb`, user `peopleuser`, senha `peoplepass`)
- API (FastAPI): `http://localhost:8000`
- UI (Streamlit): `http://localhost:8501`

## API (FastAPI)

Arquivo: `api.py`

Endpoints principais:
- `POST /process`
  - Form-data: `file` (imagem)
  - Query: `mode=seg|bbox` (padrão `seg`), `conf` (0..1)
  - Retorno: bytes `image/jpeg` com a imagem anotada
  - Headers: `X-Image-Id` (id no DB), `X-Duplicate=true|false`

- `GET /images/{id}`
  - Retorno: bytes `image/jpeg` da imagem anotada armazenada

Exemplo com `curl`:
```bash
curl -s -X POST -F "file=@seq_000001.jpg" http://localhost:8000/process -o annotated.jpg -D -
```

## UI (Streamlit)

Arquivo: `streamlit_app.py`

Abra `http://localhost:8501`, faça upload da imagem e veja o resultado no retorno. Por padrão, a UI fala com a API no `http://api:8000` (quando via Compose). Para rodar localmente sem Compose:

```bash
export API_URL=http://localhost:8000
streamlit run streamlit_app.py
```

### Rodar tudo com um comando (sem Docker)

Pré-requisito: dependências instaladas na venv (`.venv`).

No Windows:

```bash
run.bat
```

Ou:

```bash
.\.venv\Scripts\python.exe run_all.py
```

Isso sobe a API em `http://127.0.0.1:8000` e a UI em `http://127.0.0.1:8501` automaticamente.

## Observações de desempenho

- Em Apple Silicon, use `--device mps` no CLI para acelerar no macOS.
- Dentro do container, a API roda em CPU por padrão (`API_DEVICE=cpu`).
