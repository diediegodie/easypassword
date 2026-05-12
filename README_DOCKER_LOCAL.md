# Setup Local com Docker Compose — EasyPassword V1

## Pré-requisitos

- Docker >= 20.10
- Docker Compose >= 2.0
- Terminal shell (bash, zsh)

## Arquitetura Local

```
┌─────────────┐
│  Frontend   │ :4200
│  (Nginx)    │
└──────┬──────┘
       │
       ├──────────────────┐
       │                  │
┌──────▼───────┐  ┌───────▼─────┐
│   Backend    │  │   Database  │
│  (FastAPI)   │  │ (PostgreSQL)│
│   :8000      │  │   :5432     │
└──────┬───────┘  └─────────────┘
       │
       └──────────────────┐
                          │
                  ┌───────▼──────┐
                  │    Cache     │
                  │   (Redis)    │
                  │   :6379      │
                  └──────────────┘
```

## Passos Iniciais

### 1. Preparar arquivo .env na raiz do projeto

```bash
cd /home/diediegodie/documentos/github/projetos/easypassword
cp src/infra/.env.example .env
```

**Editar `.env` com valores desejados (opcional para desenvolvimento local):**
```
DB_USER=easypassword
DB_PASSWORD=dev_local_password
DB_NAME=easypassword_dev
APP_ENV=development
SECRET_KEY=dev_key_local_only
DEBUG=true
NODE_ENV=development
```

### 2. Subir todos os serviços com um comando

```bash
cd src/infra/docker
docker-compose up --build
```

**O que acontece:**
- Ambas as imagens Docker são buildadas
- Os 4 containers sobem na ordem de dependência
- Health checks garantem que os serviços estão prontos
- Logs aparecem em tempo real no terminal

### 3. Verificar status em outro terminal

```bash
cd src/infra/docker
docker-compose ps
```

**Saída esperada:**
```
NAME                     STATUS
easypassword_frontend    Up (healthy)
easypassword_backend     Up (healthy)
easypassword_postgres    Up (healthy)
easypassword_redis       Up (healthy)
```

### 4. Acessar os serviços

- **Frontend (UI):** http://localhost:4200
- **Backend (API):** http://localhost:8000
- **Backend Health Check:** http://localhost:8000/health
- **PostgreSQL:** localhost:5432 (psql ou client)
- **Redis:** localhost:6379 (redis-cli)

### 5. Ver logs de um serviço específico

```bash
# Logs do backend
docker-compose logs backend

# Logs em tempo real
docker-compose logs -f backend

# Últimas 100 linhas
docker-compose logs --tail=100 backend
```

## Operações Comuns

### Parar serviços (mantém dados)

```bash
docker-compose down
```

### Limpar tudo (remove volumes = perda de dados)

```bash
docker-compose down -v
```

### Rebuild de uma imagem específica

```bash
docker-compose build backend --no-cache
docker-compose up -d backend
```

### Executar comando dentro de um container

```bash
# Exemplos úteis
docker-compose exec backend bash
docker-compose exec postgres psql -U easypassword -d easypassword
docker-compose exec redis redis-cli
```

## Troubleshooting

### Erro: "port 4200 already in use"

Redirecionar em `docker-compose.override.yml`:
```yaml
services:
  frontend:
    ports:
      - "3000:80"  # usa 3000 em vez de 4200
```

### Erro: "Cannot connect to backend health check"

```bash
# Verificar logs do backend
docker-compose logs backend

# Restartar backend
docker-compose restart backend
```

### Erro: "psql: error: FATAL: Ident authentication failed"

Aguarde alguns segundos, PostgreSQL pode estar ainda inicializando. Tente novamente.

### Dados de volume parecem ter desaparecido

Volumes são nomeados. Verificar com:
```bash
docker volume ls | grep easypassword
```

## Variáveis de Ambiente

Todas as variáveis devem ser definidas em `.env` na raiz do projeto:

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DB_USER` | easypassword_user | Usuário PostgreSQL |
| `DB_PASSWORD` | dev_password | Senha PostgreSQL (deve ser alterada em produção) |
| `DB_NAME` | easypassword | Nome do banco de dados |
| `APP_ENV` | development | Ambiente (development/production) |
| `SECRET_KEY` | (vazio) | Chave secreta da aplicação (MUDE EM PRODUÇÃO) |
| `DEBUG` | true | Habilitar modo debug (false em produção) |
| `NODE_ENV` | development | Ambiente Node.js |

## Segurança

⚠️ **IMPORTANTE:**
- O arquivo `.env` está em `.gitignore` — nunca será commitado
- O `.env.example` contém apenas placeholders; não coloque segredos reais lá
- Em produção (Render), use secrets gerenciados pela plataforma
- Nunca use mesmas credenciais entre desenvolvimento e produção

## Performance

### Em macOS/Windows
- Volumes podem ser mais lentos que em Linux
- Primeira execução (`--build`) pode levar 2-5 minutos
- Builds subsequentes são mais rápidos (cache de camadas Docker)

### Em Linux
- Performance é nativa
- Builds iniciais levam ~1-2 minutos

## Próximos Passos

1. Após validar local, proceda com Fase 1 (Backend Base)
2. Implemente migrations de banco em `alembic/versions/`
3. Desenvolvimento iterativo: `docker-compose up` + edição de código
4. Para deploy: veja [RENDER.md](../render/README.md)

---

**Documentação atualizada:** 12 de maio de 2026  
**Versão:** V1 Local Setup  
**Stack:** Python 3.12 + Node.js 20 + PostgreSQL 16 + Redis 7
