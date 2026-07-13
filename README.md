# Sistema Inteligente de Análisis, Simulación y Descubrimiento de Inversiones

Backend Django del sistema descrito en [`sistema_inversiones_inteligente_v2.md`](sistema_inversiones_inteligente_v2.md).
Herramienta **educativa y de apoyo**: no reemplaza el criterio personal ni el asesoramiento
financiero profesional (sección 20 del documento).

## Stack

- **Django 6 + Django Ninja** (API REST con OpenAPI automática en `/api/docs`)
- **PostgreSQL** (desplegada en Railway; soporte TimescaleDB condicional para hypertables)
- **Celery + Celery Beat** con Redis como broker (tareas periódicas de ingesta)
- **yfinance** (precios, fundamentales, noticias, consenso) detrás de una interfaz
  swapeable con caché, reintentos con backoff y métrica de errores 429 (sección 16.5)
- **Google News RSS + feedparser** (noticias sectoriales/macro y motor discovery)
- **Anthropic API (Claude) con tool use** — agente de verificación (sección 5.2)
- **pandas / numpy** (indicadores, DCF, backtesting) · **VADER** (sentimiento)
- **pytest-django + factory_boy + responses** (83 tests, sin tocar la red)

## Apps de dominio

| App | Qué hace (sección del doc) |
|---|---|
| `accounts` | Registro/login/logout/me por sesión de Django (email como identificador) |
| `core` | EvidenceSource + score de confiabilidad de fuentes A+–E (9, 15.5) |
| `market` | Assets, precios OHLCV, indicadores técnicos SMA/RSI/MACD/Bollinger (4.1, 4.2) |
| `news` | Ingesta dual yfinance+RSS, categorías, sentimiento, impacto (4.4) |
| `fundamentals` | 5 bloques de ratios + DCF/WACC con supuestos persistidos (4.3) |
| `portfolio` | Carteras, posiciones, P/L, pesos, rebalanceo (4.5, 4.9) |
| `simulation` | Simulador de aportes con escenarios + backtesting SMA cross (4.6, 4.7) |
| `risk` | Volatilidad, drawdown, beta, correlaciones, score de riesgo (4.8) |
| `recommendation` | Score mecánico 5.1 + agente Anthropic 5.2 + pipeline dos etapas 5.3 |
| `experts` | Consenso de analistas con dispersión y alertas; expertos verificables (10, 11) |
| `discovery` | Nichos emergentes vía RSS + Emerging Market Score + reportes (6, 13, 14) |

## Puesta en marcha (desarrollo)

```powershell
# 1. Dependencias
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Configuración
copy .env.example .env
#    Editar .env: DATABASE_URL ya apunta a la BD (Railway) o a Docker local.
#    Sin Redis: dejar CACHE_URL=locmemcache:// (ya viene así).

# 3. Base de datos
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser   # para /admin

# 4. Datos iniciales (red: yfinance + Google News)
.\.venv\Scripts\python.exe manage.py seed_assets
.\.venv\Scripts\python.exe manage.py refresh_all       # pipeline completo (sección 17)

# 5. Servidor
.\.venv\Scripts\python.exe manage.py runserver
#    API:    http://127.0.0.1:8000/api/docs
#    Admin:  http://127.0.0.1:8000/admin
```

### Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Corren en SQLite en memoria con caché local y sin red (los proveedores externos
se mockean). Incluyen tests de regresión del scoring: cambiar un score ante
entradas fijas debe ser una decisión explícita (sección 16.6).

## Comandos de gestión

| Comando | Qué hace |
|---|---|
| `seed_assets [--no-network]` | Crea la watchlist de `.env` y sincroniza metadatos |
| `ingest_prices [--tickers A,B] [--period 2y]` | Histórico OHLCV + indicadores técnicos |
| `ingest_news [--tickers A,B]` | Noticias yfinance + Google News RSS |
| `sync_fundamentals [--tickers]` | Estados contables + 5 bloques de ratios + DCF |
| `sync_consensus [--tickers]` | Consenso de analistas + dispersión + alertas |
| `compute_risk [--tickers]` | Volatilidad, drawdown, beta, correlaciones |
| `run_scoring [--escalate] [--async-agent]` | Score mecánico 5.1 (+ agente 5.2 en el top N) |
| `run_discovery` | Escaneo de nichos emergentes + reportes |
| `refresh_all [--tickers] [--escalate]` | Todo lo anterior en orden (flujo sección 17) |

## El agente de verificación (sección 5.2)

Requiere `ANTHROPIC_API_KEY` en `.env` (modelo configurable con `AGENT_MODEL`,
default `claude-opus-4-8`). Corre **solo** sobre el top N del ranking mecánico
(`AGENT_SCORE_THRESHOLD`, `AGENT_TOP_N`) para mantener el costo acotado (5.3):

```powershell
.\.venv\Scripts\python.exe manage.py run_scoring --escalate
```

El veredicto se persiste en `AgentReview` **sin pisar** el score mecánico; la
divergencia entre ambos se expone en `/api/recommendation/ranking`. Guardrails:
el agente solo puede citar evidencia que recibió en la sesión, y su justificación
pasa por el filtro de frases prohibidas de la sección 20 antes de guardarse.

## Celery (tareas periódicas)

Necesita Redis (broker). Con Docker: `docker compose up -d redis` y en `.env`
comentar `CACHE_URL` para volver a Redis como caché. Luego, en dos terminales:

```powershell
.\.venv\Scripts\celery.exe -A config worker --pool=solo -l info   # worker (Windows: pool solo)
.\.venv\Scripts\celery.exe -A config beat -l info                 # scheduler
```

Cadencia definida en `config/settings.py` → `CELERY_BEAT_SCHEDULE`: precios cada
15 min, noticias cada hora, fundamentales/riesgo/consenso/scoring diarios,
discovery semanal. Sin Celery, `refresh_all` hace lo mismo bajo demanda.

## Infraestructura

- **Base de datos**: PostgreSQL en Railway (configurada en `.env`). La migración
  `market/0002` detecta TimescaleDB: si está disponible convierte `MarketPrice` y
  `TechnicalIndicator` en hypertables; si no (Railway estándar), sigue con tablas
  normales sin perder funcionalidad.
- **Docker (opcional)**: `docker-compose.yml` levanta TimescaleDB + Redis locales.
  En esta máquina falta WSL2 para Docker Desktop; pasos: `wsl --install` como
  administrador → reiniciar → instalar Docker Desktop → `docker compose up -d`.
- **Resiliencia yfinance (16.5)**: caché con TTL por tipo de dato, backoff
  exponencial ante 429, contador de errores expuesto en `/api/health`, e interfaz
  `MarketDataProvider` para swapear a Polygon/Finnhub sin tocar el resto.

## Reglas centrales implementadas (sección 18)

- Ninguna recomendación sin fuentes explícitas → M2M a `EvidenceSource`.
- Ninguna fuente sin confiabilidad calculada → fórmula sección 9 en `core`.
- Riesgos claros y explícitos en cada recomendación → campo `risks` obligatorio.
- Cripto con reglas más estrictas → cap de score sin fundamentos (sección 12).
- Simulaciones como estimaciones hipotéticas → disclaimers en todas las salidas.
- Sin frases absolutas ("compra segura", "ganancia garantizada") → guardrail
  con filtro regex aplicado a la salida del agente antes de persistir (sección 20).

## Autenticación (multi-usuario)

La API usa **sesión de Django** (cookie + CSRF, sin JWT): `POST /api/auth/register`
(crea la cuenta con email + contraseña y deja la sesión iniciada), `POST /api/auth/login`,
`POST /api/auth/logout` y `GET /api/auth/me` (además siembra la cookie `csrftoken`).
Los routers `portfolio` y `simulation` exigen sesión y cada usuario ve **solo lo
suyo**; los datos de mercado compartidos (market, news, fundamentals, risk,
recommendation, experts, discovery) siguen públicos. En mutaciones hay que enviar
el header `X-CSRFToken` con el valor de la cookie (el frontend ya lo hace).

## Pendientes conocidos (roadmap V7 del doc)

- WebSockets (Django Channels) para alertas en tiempo real.
- Rebalanceo con impacto fiscal de comisiones.
- Indicadores macro globales y reportes PDF.
- Fuentes ampliadas 8.6 (NewsAPI, Finnhub, TipRanks…) para cruzar consenso.
- Recuperación/cambio de contraseña y verificación de email (hoy solo alta y login).
