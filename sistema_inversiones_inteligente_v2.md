# Sistema Inteligente de Análisis, Simulación y Descubrimiento de Inversiones

> **v2 — revisión técnica con stack definido en Django**
> Este documento parte del planteamiento original y lo ajusta a una implementación concreta en Django, corrige inconsistencias de formato (bloques de código mal etiquetados como "Plaintext"), y agrega secciones de resiliencia técnica, testing y despliegue que faltaban.

## 1. Visión general

El objetivo del sistema es desarrollar una plataforma que permita analizar activos financieros, simular inversiones, gestionar una cartera, descubrir mercados emergentes y generar recomendaciones explicadas con respaldo en datos, noticias, análisis de expertos y fuentes verificables.

La plataforma no debe plantearse como un sistema que "predice acciones ganadoras", sino como un sistema de apoyo para aprender y tomar decisiones de inversión de manera informada.

> **Objetivo general:**
> Desarrollar una plataforma de análisis, simulación y descubrimiento de oportunidades de inversión basada en datos financieros, fuentes primarias, noticias, análisis de expertos y evaluación de riesgo.

El sistema debe permitir analizar diferentes tipos de activos:

- Acciones individuales.
- Índices bursátiles.
- ETFs.
- Criptomonedas.
- Bonos o instrumentos de renta fija.
- Commodities.
- Mercados emergentes.
- Sectores tecnológicos o económicos en crecimiento.

---

## 2. Enfoque del sistema

El sistema combina cuatro enfoques principales:

1. **Análisis de mercado:** seguimiento de precios, volumen, indicadores técnicos y noticias.
2. **Gestión de cartera:** evaluación de activos actuales, rentabilidad, riesgo y diversificación.
3. **Simulación de inversiones:** estimaciones de escenarios, aportes periódicos y backtesting.
4. **Descubrimiento de oportunidades:** búsqueda exhaustiva de mercados emergentes, sectores nuevos, empresas en crecimiento y criptoactivos relevantes.

Ninguna recomendación se muestra sin explicación. Cada una debe incluir:

- Datos utilizados.
- Fuentes consultadas.
- Fecha de la información.
- Nivel de confiabilidad de las fuentes.
- Motivos de la recomendación.
- Riesgos asociados.
- Posibles escenarios.

---

## 3. Arquitectura general (adaptada a Django)

La arquitectura original planteaba una capa de scraping/ETL genérica sobre PostgreSQL. La versión Django concreta esa capa en apps, tareas periódicas y una capa de caché que hoy es obligatoria por cómo se comporta `yfinance` en producción (ver sección 16.5).

```text
Fuentes externas
│
├── yfinance (precios, históricos, estados financieros, .news)
├── Google News RSS + feedparser (noticias sectoriales/macro)
├── Reportes oficiales / filings (SEC EDGAR, IR de empresas)
├── Indicadores macroeconómicos (World Bank, IMF, OECD)
├── Datos on-chain para cripto
└── Señales sociales (peso bajo, tratadas como ruido)
        │
        ▼
Celery workers + Celery Beat (tareas periódicas de ingesta)
        │
        ▼
Capa de caché (Redis) — evita golpear yfinance/RSS en cada request
        │
        ▼
Capa de normalización y validación (Pydantic/Ninja Schemas o serializers DRF)
        │
        ▼
PostgreSQL + TimescaleDB (hypertables para MarketPrice, TechnicalIndicator)
        │
        ▼
Apps de dominio Django (market, fundamentals, news, portfolio, simulation,
risk, discovery, experts, recommendation)
        │
        ▼
Motor mecánico de scoring (5.1) — corre sobre TODO el universo, sin LLM
        │
        ▼
Filtro de escalado (5.3) — solo el top N por score pasa a la siguiente etapa
        │
        ▼
Agente de verificación (5.2) — Anthropic API con tool use, JSON validado
        │
        ▼
Capa de API (Django Ninja o DRF) + Django Channels (WebSockets)
        │
        ▼
Frontend (Next.js) — dashboard interactivo
```

Puntos clave del cambio de arquitectura:

- **Celery + Celery Beat** reemplazan a los "jobs programados y workers asíncronos" mencionados en el planteamiento original de forma explícita: es el estándar de facto para tareas periódicas en Django y evita reinventar un scheduler.
- **Redis** cumple doble función: broker de Celery y capa de caché para las respuestas de `yfinance`/RSS, algo que en el diseño original no estaba contemplado y es crítico dado que ninguna de las dos fuentes es una API oficial con SLA.
- **Django Admin** se gana "gratis" y es un punto fuerte frente a un stack FastAPI puro: sirve como panel interno para moderar fuentes, revisar analistas verificados, y curar manualmente oportunidades emergentes sin construir UI extra.

---

## 4. Módulos principales

Cada módulo se traduce directamente en una Django app. Se mantiene el contenido funcional original; se agrega la app sugerida entre paréntesis.

### 4.1 Monitor de mercado (`market`)

Recolecta y muestra información actualizada sobre activos financieros. La captura primaria de datos numéricos se delega a `yfinance`.

Debe incluir: precio actual, precio histórico, volumen, variación diaria/semanal/mensual/anual, máximos y mínimos, capitalización de mercado, volatilidad, tendencia.

```text
Ejemplo de activos monitoreados:
AAPL, MSFT, NVDA, TSLA, SPY, VOO, QQQ, BTC, ETH, SOL
```

### 4.2 Indicadores técnicos (`market` o app dedicada `indicators`)

Calcula indicadores a partir de los cierres históricos (`close`) provistos por `yfinance`, transformados con Pandas.

| Indicador | Uso principal |
|---|---|
| SMA 20 | Tendencia de corto plazo |
| SMA 50 | Tendencia de medio plazo |
| SMA 200 | Tendencia de largo plazo |
| RSI | Sobrecompra o sobreventa |
| MACD | Momentum |
| Bollinger Bands | Volatilidad y rango |
| Volumen relativo | Confirmación de movimientos |
| Soportes y resistencias | Zonas de reacción del precio |

```text
Señal positiva si:
- Precio actual > SMA 50
- SMA 50 > SMA 200
- RSI entre 45 y 70
- Volumen actual > promedio de 20 días
```

### 4.3 Análisis fundamental (`fundamentals`)

Evalúa la situación financiera de una empresa. `yfinance` actúa como pipeline de extracción contable, tomando balances, cuentas de resultados y flujos de caja de los últimos 4 años fiscales disponibles.

El planteamiento original se quedaba corto acá: mencionaba ingresos, márgenes, deuda y PER, pero un analista profesional trabaja con un tablero de cinco bloques completo. Se detalla abajo, con nota de cuáles indicadores vienen directo en el `.info` de `yfinance` y cuáles hay que calcular.

**Bloque 1 — Múltiplos de precio (valoración relativa)**

| Indicador | Fórmula | Qué mide | ¿Disponible directo en `yfinance`? |
|---|---|---|---|
| PER | Precio / BPA | Años para recuperar la inversión al ritmo actual de beneficios | Sí (`trailingPE`, `forwardPE`) |
| PEG | PER / crecimiento esperado del BPA | Ajusta el PER al crecimiento; ≈1 es precio justo, <1 sugiere infravaloración | Parcial — requiere `earningsGrowth` para calcularlo |
| P/VC (P/B) | Precio / Valor contable por acción | Compara contra activos netos; clave en bancos e inmobiliarias | Sí (`priceToBook`) |
| P/Ventas (P/S) | Precio / Ventas por acción | Útil para empresas de alto crecimiento sin beneficios aún | Sí (`priceToSalesTrailing12Months`) |
| Dividend Yield | Dividendo anual / Precio | Retorno en efectivo por sostener la acción | Sí (`dividendYield`) |
| FCF Yield | FCF por acción / Precio | Retorno real en caja disponible para repartir | No — se calcula con `freeCashflow` / `marketCap` |

**Bloque 2 — Múltiplos de valor de empresa (Enterprise Value)**

EV = Capitalización bursátil + Deuda total − Caja. Es una métrica más pura que el precio de la acción porque neutraliza cómo se financia la empresa.

| Indicador | Qué mide |
|---|---|
| EV/EBITDA | El ratio rey en fusiones y adquisiciones; permite comparar empresas con distinta estructura de deuda |
| EV/EBIT | Similar, resta depreciaciones; útil en industriales con mucho gasto en mantener maquinaria |
| EV/FCF | El más estricto: costo de adquirir el negocio vs. caja real que produce cada año |
| EV/Ventas | Se usa cuando EBITDA es negativo pero interesa la cuota de mercado y facturación bruta |

`yfinance` trae `enterpriseToEbitda` y `enterpriseToRevenue` directo en `.info`; EV/EBIT y EV/FCF requieren cálculo propio a partir del EV y los estados financieros.

**Bloque 3 — Ratios de rentabilidad (calidad del negocio)**

| Indicador | Fórmula | Interpretación |
|---|---|---|
| ROE | Beneficio neto / Fondos propios | >15% sostenido = señal de ventaja competitiva |
| ROA | Beneficio neto / Activos totales | Eficiencia general usando todo lo que la empresa posee |
| ROIC | NOPAT / (Fondos propios + Deuda) | El favorito de los analistas top: rentabilidad del capital operativo sin importar de dónde vino |
| Margen bruto | (Ventas − Costo de bienes vendidos) / Ventas | Ej. ~70% en software = producir cuesta poco vs. precio de venta |
| Margen operativo | EBIT / Ventas | Rentabilidad después de salarios, alquileres, marketing |
| Margen neto | Beneficio neto / Ventas | Lo que queda limpio al final |

`yfinance` da `returnOnEquity` y `returnOnAssets` directo; ROIC y los tres márgenes se calculan a partir de los estados financieros (`income_stmt`, `balance_sheet`).

**Bloque 4 — Liquidez y solvencia (riesgo financiero)**

| Indicador | Fórmula | Umbral de alerta |
|---|---|---|
| Ratio de liquidez (current ratio) | Activos corrientes / Pasivos corrientes | Debe ser mayor a 1 |
| Prueba ácida (quick ratio) | (Activos corrientes − Inventarios) / Pasivos corrientes | Más estricto: excluye inventario difícil de liquidar rápido |
| Deuda neta / EBITDA | (Deuda total − Caja) / EBITDA | Mayor a 3–4 empieza a ser peligroso |
| Cobertura de intereses | EBIT / Gastos por intereses | Menor a 2, la empresa trabaja casi solo para pagarle al banco |
| Deuda / Patrimonio | Pasivos totales / Fondos propios | Cuánto dinero de terceros usa vs. de accionistas |

`yfinance` trae `currentRatio`, `quickRatio` y `debtToEquity` directo; Deuda Neta/EBITDA y cobertura de intereses se calculan combinando `.info` con los estados financieros.

**Bloque 5 — Modelos absolutos (valoración intrínseca)**

- **DCF (Descuento de Flujos de Caja):** proyecta el efectivo que la empresa generará a 5-10 años y lo trae al presente descontándolo a una tasa (WACC). Si el DCF resultante es mayor que la cotización actual, la acción está potencialmente infravalorada. Es el cálculo más pesado del módulo — no viene de ninguna fuente gratuita, hay que construirlo con `pandas`/`numpy` a partir de flujos de caja históricos y proyecciones.
- **WACC:** no es un múltiplo directo sino la tasa que alimenta el DCF; combina el costo de la deuda y la rentabilidad exigida por los accionistas.

Estos dos son los más caros de calcular bien (dependen de supuestos de crecimiento y riesgo) y son los que más se benefician de que el motor de recomendaciones muestre explícitamente los supuestos usados, en línea con la regla central de auditabilidad (sección 18).

### 4.4 Noticias y sentimiento (`news`)

Ingesta dual como base: método nativo `.news` de `yfinance` para actualidad corporativa de tickers individuales, y consultas parametrizadas a Google News RSS (vía `feedparser`) para tendencias agregadas, industrias o macroeconomía en múltiples idiomas.

Esto era insuficiente para el objetivo de "full noticias" — consumo exhaustivo de prensa y opinión de mercado. La sección 8.6 detalla las fuentes adicionales (agregadores de noticias, sentimiento ya calculado, consenso de analistas) que conviene sumar a la ingesta para que el módulo no dependa de un único proveedor gratuito.

Campos por noticia: `ticker/palabra_clave`, `fuente`, `autor`, `fecha`, `título`, `resumen`, `url`, `sentimiento`, `impacto_estimado`, `categoría`.

Categorías: resultados financieros, nuevos productos, regulación, demandas/investigaciones, fusiones y adquisiciones, cambios de directiva, contratos importantes, riesgo geopolítico, innovación tecnológica.

### 4.5 Cartera (`portfolio`)

Registra y analiza la cartera del usuario: activo, tipo, cantidad, precio promedio de compra, precio actual, valor actual, ganancia/pérdida, porcentaje en cartera, fecha de compra, comisiones, moneda, sector, país, nivel de riesgo.

### 4.6 Simulación de inversiones (`simulation`)

Responde preguntas del tipo "¿qué pasa si invierto X en Y durante N años?", con variables de entrada (capital inicial, aporte mensual, horizonte, activo/cartera, rendimiento y volatilidad esperados, escenarios optimista/medio/pesimista) y salidas (valor futuro estimado, ganancia/pérdida, rentabilidad acumulada/anualizada, riesgo estimado, mejor/peor escenario, comparación contra otros activos).

### 4.7 Backtesting (`simulation`, submódulo)

Prueba estrategias con datos históricos, alimentados directamente desde las matrices temporales de `yfinance`.

| Métrica | Significado |
|---|---|
| Retorno acumulado | Ganancia total de la estrategia |
| Rentabilidad anualizada | Rendimiento promedio anual |
| Volatilidad | Nivel de variación del precio |
| Max drawdown | Mayor caída desde un máximo |
| Win rate | Porcentaje de operaciones ganadoras |
| Sharpe ratio | Retorno ajustado al riesgo |
| Profit factor | Ganancias totales / pérdidas totales |

### 4.8 Riesgo (`risk`)

Calcula volatilidad, max drawdown, beta, correlación entre activos, concentración por activo/sector/país, exposición a cripto/tecnología/mercados emergentes.

### 4.9 Rebalanceo (`portfolio`, submódulo)

Sugiere ajustes para acercar la cartera actual a una distribución objetivo, comparando pesos actuales contra pesos objetivo y generando una lista de acciones (reducir/aumentar exposición).

---

## 5. Motor de recomendaciones (`recommendation`)

Genera recomendaciones explicables, no órdenes absolutas. Esta sección se divide en tres capas: la mecánica (rápida y barata), el agente de verificación (razonamiento sobre el conjunto de datos), y el ranking de oportunidades que las combina de forma escalonada para controlar costo.

### 5.1 Capa mecánica

| Puntaje | Señal |
|---|---|
| 80–100 | Compra fuerte |
| 65–79 | Compra moderada |
| 50–64 | Mantener / observar |
| 35–49 | Riesgo alto |
| 0–34 | Evitar / venta |

```text
Puntaje total =
30% análisis técnico
25% noticias y sentimiento (ingesta mixta Google News / yfinance / fuentes 8.6)
25% fundamentos contables (bloques 1-5 de la sección 4.3)
20% riesgo
```

Esta fórmula es determinista y corre sobre todo el universo de activos vía Celery sin costo de LLM. Es intencionalmente simple: sirve como primer filtro, no como veredicto final.

### 5.2 Agente de verificación y decisión final

La fórmula ponderada de 5.1 tiene un límite estructural: es lineal y no puede detectar contradicciones entre bloques de información (ej. fundamentos sólidos pero tres noticias de regulación negativa en la última semana, o score técnico alto con consenso de analistas muy disperso). Para eso se agrega una capa de razonamiento sobre el conjunto de datos ya consolidado, antes de que una recomendación se muestre como de "alta convicción".

**Cómo funciona:**

1. Para un activo dado, el sistema arma un snapshot estructurado con: score técnico, los cinco bloques de ratios fundamentales (sección 4.3), el digest de noticias reciente ya clasificado (sentimiento/impacto/categoría), el consenso de analistas (sección 11) y las métricas de riesgo (sección 4.8) — todo con sus `EvidenceSource` y niveles de confiabilidad ya calculados (sección 9).
2. Ese snapshot se pasa a un agente implementado con la **API de Anthropic (Claude), usando tool use**, no como un único prompt gigante. El agente tiene herramientas del tipo `get_fundamentals(ticker)`, `get_news_digest(ticker, dias)`, `get_analyst_consensus(ticker)`, `get_technical_snapshot(ticker)`, `get_risk_metrics(ticker)` — así decide qué necesita revisar en vez de recibir todo de una sola vez, y el mismo agente puede volver a correr cuando los datos se actualizan sin rediseñar el prompt.
3. La salida es JSON estructurado y validado (Pydantic/Ninja Schema), no texto libre: `señal_final`, `confianza`, `score_ajustado` (puede diferir del mecánico), `justificación` (en lenguaje natural, anclada a los datos recuperados), `contradicciones_detectadas` (lista explícita, ej. "fundamentos sólidos pero deterioro reciente en sentimiento de noticias regulatorias"), `fuentes_citadas`.
4. **Guardrails:** el agente solo puede citar fuentes que efectivamente estén en el snapshot (no puede inventar datos), y su salida pasa por una validación posterior que descarta cualquier frase absoluta prohibida por la sección 20 ("compra segura", "ganancia garantizada", etc.) antes de persistirse.
5. El score del agente **no reemplaza silenciosamente** al mecánico: ambos se guardan. Si divergen de forma significativa, esa divergencia es en sí misma una señal que se muestra al usuario — coherente con la regla central de que nada se recomienda sin poder auditarse (sección 18).

### 5.3 Ranking de oportunidades (escalado en dos etapas)

Esto responde directamente a la idea de un ranking de acciones con mayor valor de oportunidad: correr el agente (LLM) sobre todo el universo de activos en cada actualización sería caro e innecesario, así que el diseño es en dos etapas:

```text
Etapa 1 (barata, corre sobre todo el universo — S&P 500 + watchlist + cripto):
  Celery Beat dispara el cálculo mecánico (5.1) para cada activo.
  Resultado: ranking preliminar ordenado por score mecánico.

Etapa 2 (cara, escalada — solo el top N):
  Los activos que superan un umbral (ej. score > 65) o quedan en el
  top 20-50 del ranking preliminar se escalan al agente (5.2) para
  verificación profunda.
  Resultado: ranking final con score_ajustado, confianza y
  contradicciones detectadas, listo para el dashboard.
```

Esto mantiene el costo de la API de Anthropic acotado y predecible sin importar cuántos activos siga el sistema — el gasto crece con el tamaño del "top N" que se decida escalar, no con el universo completo.

Ejemplo de salida (capa mecánica):

```text
Activo: MSFT
Señal: Compra moderada
Puntaje: 72/100

Motivos:
- Tendencia técnica positiva.
- Buen desempeño en ingresos relacionados con nube.
- Opinión de analistas mayormente favorable.
- Riesgo medio por valoración elevada.

Conclusión:
Activo interesante para seguimiento o exposición moderada, pero no libre de riesgo.
```

---

## 6. Motor de descubrimiento de mercados emergentes (`discovery`)

Busca oportunidades más allá de los activos consolidados. El motor construye URLs de Google News RSS con operadores de búsqueda avanzada (ej. `q="quantum+computing"+AND+investment`) y `feedparser` procesa el XML para mapear la frecuencia de menciones de nuevas tecnologías y startups asociadas.

Identifica: sectores emergentes, empresas pequeñas con crecimiento acelerado, criptomonedas/protocolos nuevos con adopción real, países con mejora macroeconómica, commodities con demanda creciente, startups cercanas a salir a bolsa, ETFs nuevos, tecnologías con inversión creciente, cambios regulatorios que abren mercados.

```text
Ejemplos de mercados emergentes a analizar:
IA aplicada a salud, chips especializados, energía nuclear modular,
litio y baterías, ciberseguridad, biotecnología, tokenización de
activos reales, stablecoins, infraestructura de datos, fintech en
países emergentes, mercados latinoamericanos
```

---

## 7. Búsqueda exhaustiva de información

Búsqueda exhaustiva no significa confiar en cualquier fuente. Significa: buscar en muchas fuentes, priorizar fuentes primarias, validar la calidad de cada fuente, cruzar información, guardar evidencia, mostrar siempre la fuente, identificar riesgos y sesgos.

```text
Pipeline recomendado:
1. Detectar tendencia o tema emergente.
2. Identificar activos relacionados.
3. Buscar fuentes primarias (balances en yfinance / reportes oficiales).
4. Buscar fuentes secundarias confiables (medios e indexación en Google News RSS).
5. Revisar señales sociales o alternativas.
6. Validar información cruzada.
7. Calcular score de oportunidad.
8. Generar reporte explicable.
```

---

## 8. Fuentes de información

### 8.1 Fuentes primarias (mayor confiabilidad)
SEC EDGAR, reportes oficiales de empresas, Investor Relations, estados financieros auditados, bancos centrales, reguladores financieros, World Bank, IMF, OECD, whitepapers técnicos, GitHub oficial de proyectos tecnológicos o cripto, documentación oficial de protocolos.

### 8.2 Fuentes profesionales
Bloomberg Terminal, LSEG/Refinitiv, FactSet, Morningstar, S&P Capital IQ, Moody's, Fitch, S&P Global Ratings, MSCI, I/B/E/S Estimates.

### 8.3 Medios financieros confiables
Reuters, Bloomberg, Financial Times, Wall Street Journal, CNBC, MarketWatch, Yahoo Finance, Nasdaq, CoinDesk, The Block.

### 8.4 Señales sociales y alternativas (peso bajo)
X/Twitter, Reddit, YouTube, Substack, Discords públicos, Telegram, Hacker News, Product Hunt, Google Trends, App Store/Play Store rankings, LinkedIn hiring trends.

### 8.5 Arquitectura práctica del MVP: el combo abierto y gratuito

Para evitar bloqueos y costos de APIs institucionales durante las primeras fases, la captura combina directamente:

- **`yfinance`**: descarga precios históricos, volúmenes, dividendos y reportes financieros crudos de empresas de EE.UU. y Europa, estructurados en DataFrame.
- **Google News RSS + `feedparser`**: canales XML por país e idioma, priorizando medios financieros reconocidos y filtrando blogs promocionales.

**Nota de realismo importante (no estaba en el planteamiento original):** `yfinance` no es una API oficial de Yahoo, sino una librería que scrapea endpoints web. Esto significa errores `429 Too Many Requests` y bloqueos temporales de IP son parte normal de operar con volumen, no una excepción. Ver sección 16.5 para la estrategia de mitigación.

### 8.6 Fuentes ampliadas: noticias, sentimiento y consenso de analistas (sección nueva)

`yfinance` + Google News RSS alcanzan para un MVP, pero no dan un consumo "full" de prensa ni opinión profesional consolidada. Para eso conviene sumar, de forma incremental (ver roadmap):

**Agregadores de noticias con tier gratuito:**
- **NewsAPI.org** — agrega miles de fuentes, tier gratuito limitado en volumen.
- **Finnhub.io** — noticias por compañía + tier gratuito generoso para un proyecto de este tamaño.
- **Alpha Vantage News & Sentiment API** — trae el sentimiento ya calculado y asociado a ticker, lo cual puede complementar (no necesariamente reemplazar) el clasificador propio del módulo 4.4.
- **Benzinga** — noticias + calendario de resultados, tier gratuito limitado, tier de pago con ratings de analistas.

**Consenso y opinión de analistas profesionales:**
- `yfinance` ya trae de forma nativa `Ticker.recommendations` y datos de precio objetivo — es el punto de partida más barato y ya cubierto por la sección 11, vale la pena explotarlo antes de sumar fuentes de pago.
- **MarketBeat** y **TipRanks** — consenso de analistas y ratings; buena parte de la data de resumen es de acceso público, útil para cruzar contra lo que ya trae `yfinance`.
- **Finviz** — screener + noticias + ratings agregados en una sola vista, útil para el motor de descubrimiento (sección 6) más que para el detalle por ticker.

**Señales sociales estructuradas (peso bajo, igual que 8.4, pero con dato ya cuantificado):**
- **StockTwits API** — stream de mensajes con sentimiento bull/bear etiquetado por los propios usuarios; a diferencia de X/Reddit "crudo", ya viene con una señal numérica aprovechable.
- **Reddit vía PRAW** — r/wallstreetbets, r/stocks, r/investing; útil sobre todo para detectar picos de atención retail, no como fundamento de una recomendación.

**Nota de secuenciación:** no conviene integrar todo esto de golpe. El roadmap (sección 19) lo distribuye entre la Versión 4 (ingesta ampliada de noticias) y la Versión 5 (agente + consenso institucional), para no acoplar el MVP a media docena de APIs externas desde el día uno.

---

## 9. Sistema de confiabilidad de fuentes

| Nivel | Tipo de fuente | Peso |
|---|---|---|
| A+ | Reporte oficial, regulador, filing SEC | Muy alto |
| A | Banco de inversión, proveedor institucional | Alto |
| B | Medio financiero reconocido | Medio |
| C | Analista independiente verificable | Medio-bajo |
| D | Redes sociales o foros | Bajo |
| E | Fuente anónima o promocional | Muy bajo |

```text
Score de confiabilidad =
40% tipo de fuente
20% credenciales del autor
15% historial
15% transparencia metodológica
10% independencia o conflicto de interés
```

---

## 10. Módulo de expertos y analistas certificados (`experts`)

Recolecta análisis de personas o instituciones confiables, validando: quién hizo el análisis, dónde trabaja, certificaciones verificables, registro en entidad reguladora, historial disciplinario, metodología, conflictos de interés, coincidencia con el consenso de mercado.

Fuentes para validar expertos: FINRA BrokerCheck, SEC Investment Adviser Public Disclosure, CFA Institute, sitios oficiales de firmas financieras, reportes institucionales, páginas de research de bancos de inversión.

---

## 11. Consenso de analistas

El sistema diferencia entre opinión individual y consenso, mostrando: número de analistas por recomendación (comprar/mantener/vender), precio objetivo promedio/máximo/mínimo, nivel de dispersión, cambios recientes de recomendación.

`yfinance` ya expone esto de forma nativa (`Ticker.recommendations`, precio objetivo) sin costo adicional — es la base para el MVP. Las fuentes de la sección 8.6 (MarketBeat, TipRanks) sirven para cruzar y detectar discrepancias entre proveedores, no como reemplazo. Este consenso es uno de los insumos que recibe el agente de verificación (sección 5.2): una dispersión alta entre analistas es exactamente el tipo de señal que el agente debe mencionar explícitamente en vez de promediarla y esconderla en un solo número.

---

## 12. Análisis especial para criptoactivos

En cripto el sistema debe ser más estricto por el mayor riesgo de manipulación, baja liquidez y proyectos sin fundamentos. Analiza: TVL, usuarios activos, volumen real, liquidez, tokenomics, calendario de desbloqueos, auditorías, actividad de GitHub, concentración de holders, uso real del protocolo, integraciones, historial de exploits, riesgo regulatorio, riesgo de rug pull.

> Regla importante: un token no debe recomendarse solo porque subió de precio. Primero debe analizarse si existe adopción real, liquidez, seguridad, equipo identificable y sostenibilidad del proyecto.

---

## 13. Score para mercados emergentes (`discovery`)

```text
Emerging Market Score =
20% crecimiento del sector
15% señales de adopción
15% inversión institucional
15% fundamentos
10% momentum de precio
10% noticias y regulación
10% actividad tecnológica
5% riesgo
```

| Mercado | Score | Riesgo | Horizonte |
|---|---|---|---|
| IA en salud | 82 | Alto | 5-10 años |
| Ciberseguridad industrial | 76 | Medio | 3-5 años |
| Tokenización de activos reales | 71 | Muy alto | 5+ años |
| Litio | 64 | Alto | Cíclico |
| Memecoins | 28 | Extremo | Especulativo |

---

## 14. Reporte de oportunidad emergente

Cada oportunidad detectada genera un reporte con: nombre, tipo, activos relacionados, tesis, evidencia, riesgos, horizonte, nivel de riesgo, score, conclusión. (Ver ejemplo completo en el planteamiento original — estructura conservada sin cambios porque ya era sólida.)

---

## 15. Estructura de datos (modelos Django)

Se mantiene el modelo de datos original; los nombres ya son directamente utilizables como modelos de Django (`models.Model`), respetando snake_case en los campos.

### 15.1 Asset
`id, ticker, nombre, tipo, sector, país, moneda, exchange, descripción`

### 15.2 MarketPrice (hypertable de TimescaleDB)
`id, asset_id (FK), datetime, open, high, low, close, volume`

### 15.3 TechnicalIndicator
`id, asset_id (FK), datetime, sma_20, sma_50, sma_200, rsi, macd, volatility, relative_volume`

### 15.4 News
`id, asset_id (FK), title, summary, source, author, url, published_at, sentiment, impact_score, category`

### 15.5 EvidenceSource
`id, url, source_name, source_type, author, published_at, retrieved_at, related_asset, relevant_excerpt, reliability_score, reliability_level`

### 15.6 Recommendation
`id, asset_id (FK), signal, score, explanation, risks, created_at, evidence_sources (M2M a EvidenceSource)`

### 15.7 Portfolio
`id, user_id (FK a settings.AUTH_USER_MODEL), name, base_currency, created_at`

### 15.8 PortfolioPosition
`id, portfolio_id (FK), asset_id (FK), quantity, average_price, current_price, current_value, weight, profit_loss`

### 15.9 Simulation
`id, portfolio_id (FK, nullable), scenario_name, initial_capital, monthly_contribution, time_horizon, expected_return, volatility, final_estimated_value, optimistic_value, pessimistic_value`

### 15.10 AgentReview (nuevo — sección 5.2)
`id, asset_id (FK), mechanical_score, agent_score, confidence, signal, justification, contradictions_detected (JSON), evidence_sources (M2M a EvidenceSource), model_used, created_at`

Vincula con `Recommendation` vía `asset_id`; permite mostrar en el dashboard tanto el score mecánico como el ajustado por el agente, y su divergencia, sin que uno pise al otro.

**Nota técnica:** `MarketPrice` y `TechnicalIndicator` son los candidatos naturales a hypertable de TimescaleDB por volumen de escritura e inserciones en el tiempo; el resto de los modelos funciona bien como tablas relacionales estándar de PostgreSQL sin necesidad de extensión.

---

## 16. Stack técnico recomendado (Django)

### 16.1 Backend

- **Django**: framework principal. Da de entrada el ORM, sistema de migraciones, y — muy relevante para este proyecto — **Django Admin**, que sirve como panel de curaduría interna (moderar fuentes, gestionar analistas verificados, revisar oportunidades emergentes) sin construir UI adicional.
- **Capa de API — dos opciones válidas, no hace falta elegir una sola desde el día uno:**
  - **Django Ninja**: sintaxis basada en type hints y Pydantic v2, muy parecida a FastAPI. Dado que ya trabajás con FastAPI + Pydantic en el bot de Telegram de Avícola Sofía, la curva de adaptación es mínima. Soporta endpoints async nativamente y genera documentación OpenAPI automática, algo útil para un sistema con módulos de simulación que pueden tardar en responder.
  - **Django REST Framework (DRF)**: más maduro, con diez años de ecosistema (`django-filter`, `drf-spectacular`, `djangorestframework-simplejwt`). Conviene para las partes más CRUD-dominantes del sistema (cartera, posiciones) donde `ModelViewSet` + router ahorra código.
  - **Recomendación concreta**: arrancar con Django Ninja para los endpoints nuevos (recomendaciones, simulaciones, descubrimiento) por la afinidad con tu experiencia previa en FastAPI, y usar DRF solo si en el camino necesitás algo muy específico de su ecosistema (por ejemplo permisos a nivel de objeto con `django-guardian`). Ambos pueden convivir montados en distintos prefijos de `urls.py` sin conflicto.
- **Celery + Celery Beat**: reemplaza la idea original de "jobs programados y workers asíncronos" con algo concreto y probado. Celery Beat dispara tareas periódicas (refrescar precios, correr el motor de descubrimiento, recalcular scores) y los workers las ejecutan en paralelo sin bloquear la API.
- **Redis**: doble rol — broker de Celery y caché de resultados de `yfinance`/RSS (ver 16.5).
- **Django Channels**: para los WebSockets del dashboard (alertas en tiempo real, actualización de precios en vivo).
- **Pandas / NumPy**: cálculo de indicadores técnicos, igual que en el planteamiento original.
- **Scikit-learn**: modelos básicos de scoring y clasificación de sentimiento.
- **feedparser**: parseo de los canales RSS de Google News.
- **Anthropic API (Claude) con tool use**: motor del agente de verificación (sección 5.2). Se invoca desde una tarea Celery (`escalate_to_agent`), nunca de forma síncrona en el request del usuario, precisamente porque solo corre sobre el "top N" del ranking escalado (5.3) y puede tardar más que una llamada REST normal.

### 16.2 Base de datos

- **PostgreSQL** como almacenamiento relacional core.
- **TimescaleDB** como extensión para las hypertables de series temporales (`MarketPrice`, `TechnicalIndicator`). Django no tiene soporte nativo para hypertables, así que la creación de estas tablas específicas se maneja con una migración de datos (`RunSQL`) en lugar de dejarlo 100% al ORM estándar.

### 16.3 Frontend

El planteamiento original dejaba "React o Next.js" abierto. Para un dashboard financiero con gráficos interactivos, datos en tiempo real y necesidad de SEO nulo (es una app privada, no un sitio público), la recomendación es:

- **Next.js (App Router) + TypeScript**: separado del backend Django, consumiendo la API vía Ninja/DRF. TypeScript importa acá porque los tipos de dominio (Asset, Recommendation, Simulation) son ricos y se benefician de chequeo estático, sobre todo si después el proyecto crece en colaboradores.
- **TanStack Query** para el fetching/caché de datos del lado del cliente (encaja bien con los datos que cambian con frecuencia moderada, como precios y recomendaciones).
- **Zustand** para estado global ligero (selección de activo actual, filtros de cartera) — más simple que Redux para el tamaño de este proyecto.
- **TradingView Lightweight Charts** para los gráficos de precio/velas (se mantiene del planteamiento original, es la opción correcta para este caso).
- **Recharts o Plotly** para gráficos de cartera, simulaciones y riesgo.
- **Tailwind CSS + shadcn/ui** para componentes de UI consistentes sin reinventar cada formulario/tabla.

**Alternativa más simple a considerar:** si en algún momento el equipo se reduce a una sola persona (vos) manteniendo todo, Django + HTMX + Alpine.js es una opción legítima que evita mantener dos codebases separados (Python + TypeScript), a costa de menos fluidez en las partes muy interactivas (por ejemplo, el simulador con sliders en tiempo real). Dado que el dashboard tiene gráficos financieros interactivos y WebSockets, Next.js sigue siendo la opción más adecuada, pero vale la pena tenerlo en mente si el scope del proyecto se achica.

### 16.4 Infraestructura y DevOps

- **Docker Compose** para desarrollo local: contenedores separados para Django, Celery worker, Celery Beat, Redis, Postgres/TimescaleDB, y Next.js.
- **GitHub Actions** para CI (tests + linting) — encaja con que ya usás GitHub para tus otros proyectos.
- **django-environ** para manejo de variables de entorno/secrets.
- **Nginx** como reverse proxy en producción, sirviendo estáticos de Django y haciendo proxy al backend y al frontend.

### 16.5 Resiliencia frente a fuentes externas no oficiales (sección nueva)

Esto no estaba cubierto en el planteamiento original y es importante porque el sistema entero depende de `yfinance` y de Google News RSS, ninguna de las dos con SLA:

- `yfinance` no es una API oficial: scrapea endpoints web de Yahoo Finance. En uso continuo o de alto volumen es normal recibir errores `429 Too Many Requests` y bloqueos temporales de IP, no una excepción rara.
- **Mitigación recomendada:**
  - Caché agresiva en Redis con TTLs distintos según el tipo de dato (precio intradía: minutos; fundamentales: horas/días).
  - Backoff exponencial + reintentos en las tareas de Celery que llaman a `yfinance`.
  - Aislar las llamadas a `yfinance` detrás de una interfaz propia (`MarketDataProvider`) para poder swapear a un proveedor de pago (Polygon.io, Alpha Vantage, Finnhub) sin tocar el resto del sistema si el volumen crece y el scraping deja de ser viable.
  - Monitorear la tasa de errores 429 como métrica de salud del sistema, no solo como log de error suelto.
- Aplica el mismo criterio, en menor medida, a Google News RSS: es gratuito pero no garantiza disponibilidad ni formato estable a largo plazo.

### 16.6 Testing

No estaba contemplado en el planteamiento original y es fácil de subestimar en un sistema que toma decisiones basadas en datos externos:

- **pytest-django** como runner de tests.
- **factory_boy** para generar datos de prueba (assets, precios, noticias) sin depender de la red.
- **responses** o **VCR.py** para mockear las llamadas HTTP a `yfinance`/RSS en los tests, evitando que el test suite dependa de que Yahoo esté disponible.
- Tests de regresión específicos para el motor de scoring: dado un set fijo de indicadores/fundamentos/noticias de entrada, el score de salida no debería cambiar entre versiones sin que sea una decisión explícita.

---

## 17. Flujo de una recomendación

```text
1. El sistema recibe o actualiza datos numéricos del activo (yfinance,
   vía tarea Celery periódica, pasando primero por la capa de caché).
2. Calcula los indicadores técnicos básicos (Pandas: SMA, RSI, MACD).
3. Consulta noticias de actualidad corporativa (yfinance.news) y
   sectoriales (Google News RSS vía feedparser).
4. Busca y procesa los fundamentos contables de los balances guardados.
5. Revisa el consenso global de analistas de mercado institucionales.
6. Evalúa la procedencia de cada fuente y calcula el score de confiabilidad.
7. Calcula el score ponderado final unificado.
8. Identifica de forma algorítmica los riesgos sectoriales o de sobreponderación.
9. Genera el texto explicativo con el desglose en lenguaje natural legible.
10. Publica el resultado por WebSocket (Django Channels) y lo persiste
    para que el dashboard lo muestre con fuentes, links y timestamps.
```

Ejemplo:

```text
Activo: NVDA
Señal: Mantener / observar
Score: 68/100

Motivos:
- Fuerte tendencia de largo plazo.
- Alta demanda relacionada con IA.
- Opinión institucional favorable.
- Valoración exigente.
- Alta sensibilidad a expectativas futuras.

Riesgos:
- Caída si no cumple expectativas de crecimiento.
- Dependencia del ciclo de inversión en IA.
- Posibles restricciones regulatorias.

Fuentes:
- Reportes oficiales de la empresa.
- Consenso de analistas.
- Noticias financieras confiables.
- Datos técnicos de mercado.
```

---

## 18. Reglas centrales del sistema

- Ninguna recomendación puede mostrarse sin fuentes explícitas.
- Ninguna fuente puede mostrarse sin su nivel de confiabilidad previamente calculado.
- Ningún analista debe considerarse certificado sin verificación regulatoria formal.
- Toda recomendación debe incluir riesgos claros y explícitos.
- Toda información ingresada debe contar con su fecha exacta de publicación o consulta.
- Las redes sociales se tratan estrictamente como señales débiles de mercado.
- Las fuentes primarias contables tienen mayor peso algorítmico que las opiniones en prensa.
- El sistema separa de forma estricta los datos empíricos, las opiniones y la conclusión final.
- Las simulaciones se muestran como estimaciones estadísticas hipotéticas, jamás como garantías de rendimiento futuro.
- El usuario debe poder auditar de forma visual y transparente el "por qué" el sistema recomienda o descarta un activo.

---

## 19. Roadmap sugerido (Django)

**Versión 1 — Base del sistema y extracción de precios**
- Proyecto Django inicializado con apps `market`, `portfolio` (esqueleto).
- PostgreSQL + TimescaleDB configurados; hypertable de `MarketPrice`.
- Integración de `yfinance` con caché en Redis desde el día uno (no como optimización tardía).
- Dashboard básico en Next.js con TradingView Lightweight Charts y cálculo local de SMA/RSI/MACD.

**Versión 2 — Ingesta automática de prensa y recomendaciones simples**
- App `news` con `feedparser` sobre Google News RSS, corrida por Celery Beat.
- Motor de scoring técnico rudimentario (Compra/Venta/Mantener).
- Registro de alertas de prensa con timestamps.

**Versión 3 — Cartera y simulaciones cuantitativas**
- App `portfolio` completa (registro manual de posiciones, comisiones).
- App `simulation`: simulador de aportes recurrentes con escenarios optimista/pesimista.
- Backtesting básico sobre cruces de medias.

**Versión 4 — Análisis avanzado de noticias y sentimiento**
- Clasificación de sentimiento (modelo local o API externa) integrada como tarea Celery.
- Ajuste del score general según impacto estimado por noticia.
- Ingesta ampliada de noticias (sección 8.6): NewsAPI/Finnhub como agregadores adicionales, sin depender solo de Google News RSS.
- Ratios fundamentales completos (bloques 1-5 de la sección 4.3) calculados y persistidos, no solo los básicos del planteamiento original.

**Versión 5 — Verificación de expertos, consenso institucional y agente de decisión**
- App `experts` con filtros de procedencia institucional.
- Cálculo de dispersión del consenso de Wall Street y alertas ante cambios drásticos, cruzando `yfinance` con MarketBeat/TipRanks (8.6).
- Agente de verificación (5.2) sobre Anthropic API con tool use, corriendo como tarea Celery escalada (5.3), con persistencia en `AgentReview`.
- Dashboard de ranking de oportunidades mostrando score mecánico vs. score ajustado por el agente y sus divergencias.

**Versión 6 — Motor de descubrimiento de mercados emergentes**
- App `discovery`: búsquedas avanzadas iterativas en RSS para nichos emergentes.
- Reportes automáticos de oportunidades vinculando prensa con tickers.

**Versión 7 — Sistema avanzado y automatización completa**
- Motor de rebalanceo automático con simulación de impacto fiscal de comisiones.
- Indicadores macroeconómicos globales.
- Alertas vía Django Channels y reportes ejecutivos en PDF descargables.
- Endurecimiento de la capa de resiliencia (16.5): métricas de error 429, posible evaluación de un proveedor de pago si el volumen lo justifica.

---

## 20. Consideraciones importantes

Este sistema debe usarse como herramienta educativa y de apoyo. No reemplaza el criterio personal ni el asesoramiento financiero profesional.

Las recomendaciones se expresan con prudencia: "señal de compra moderada", "candidato para seguimiento", "riesgo alto", "conviene analizar más", "no hay consenso suficiente", "oportunidad emergente especulativa".

No se deben usar bajo ninguna circunstancia frases absolutas o impositivas como "compra seguro", "ganancia garantizada", "esta acción va a subir", "no hay riesgo".

---

## 21. Nombre del proyecto

Nombre oficial y recomendado por arquitectura:

**Sistema Inteligente de Análisis, Simulación y Descubrimiento de Inversiones**

(Alternativas en inglés: Investment Portfolio Intelligence, Market Discovery Engine, Smart Portfolio Intelligence, Financial Opportunity Radar. Alternativas en español: Asistente Inteligente de Inversión, Radar de Oportunidades Financieras.)

---

## 22. Conclusión

El sistema propuesto permite aprender sobre inversión activa y pasiva, analizar acciones, índices, criptomonedas y mercados emergentes, simular escenarios de inversión, gestionar una cartera y recibir recomendaciones explicadas.

Su principal valor no está solo en decir qué comprar o vender, sino en explicar de manera clara y auditable:

- ¿Por qué esta inversión puede ser interesante?
- ¿Qué datos empíricos la respaldan?
- ¿Qué fuentes y URLs de prensa se usaron como evidencia?
- ¿Qué tan confiables son esas fuentes según el score interno?
- ¿Qué riesgos latentes existen a nivel sectorial?
- ¿Cómo impacta esta compra en la diversificación de la cartera actual?
- ¿Qué pasaría bajo distintos escenarios económicos futuros simulados?

Con este enfoque, la plataforma funciona como una herramienta de aprendizaje, análisis y toma de decisiones, basada en evidencia verificable y sin especulación ciega.

---

## Anexo: resumen de cambios respecto al planteamiento original

| Área | Original | v2 |
|---|---|---|
| Framework backend | FastAPI (mencionado en stack) | Django + Django Ninja (o DRF donde convenga) |
| ORM | SQLAlchemy | Django ORM |
| Tareas periódicas | "Jobs programados y workers asíncronos" (genérico) | Celery + Celery Beat, explícito |
| Caché | No mencionado | Redis, obligatorio dado el comportamiento real de yfinance |
| Panel interno | No mencionado | Django Admin |
| Resiliencia ante fuentes externas | No mencionado | Sección 16.5 nueva, con mitigación concreta |
| Testing | No mencionado | Sección 16.6 nueva (pytest-django, factory_boy, VCR/responses) |
| Frontend | "React o Next.js" (abierto) | Next.js + TypeScript + TanStack Query + Zustand, con alternativa HTMX si el proyecto se achica |
| Formato del documento | Bloques de código mal etiquetados como "Plaintext" | Corregido a bloques ```text reales |
| Análisis fundamental | PER, márgenes y deuda básicos | 5 bloques completos: múltiplos de precio, EV, rentabilidad, liquidez/solvencia, modelos absolutos (DCF/WACC) |
| Fuentes de noticias/analistas | yfinance + Google News RSS | + NewsAPI, Finnhub, Alpha Vantage News, MarketBeat, TipRanks, StockTwits (sección 8.6) |
| Decisión final | Solo fórmula ponderada mecánica | + Agente de verificación (Anthropic API, tool use) sobre el top N escalado, con score ajustado y contradicciones detectadas explícitas |
| Ranking de oportunidades | No existía como módulo propio | Nuevo: escalado en dos etapas (mecánico sobre todo el universo → agente solo sobre el top N) para controlar costo |

---

## Anexo B — Estado de implementación, pendientes y mejoras

> **Actualizado: 2026-07-09**, tras el primer build completo del backend
> (commit `eb91e80`, 83 tests en verde, pipeline verificado end-to-end contra
> la base PostgreSQL de Railway con datos reales de yfinance y Google News).
> Este anexo es la lista de trabajo viva: marcar y recortar a medida que se avance.

### B.1 Implementado y verificado ✔

- ✔ **V1–V6 del roadmap (sección 19)** completas en el backend Django:
  las 10 apps (`core`, `market`, `news`, `fundamentals`, `portfolio`,
  `simulation`, `risk`, `recommendation`, `experts`, `discovery`) con modelos,
  servicios, API Django Ninja (`/api/docs`), Django Admin, tareas Celery
  definidas, comandos de gestión y suite de tests sin red.
- ✔ Score mecánico 5.1 + agente 5.2 (código y tests con mocks) + pipeline dos
  etapas 5.3 con umbral y top N configurables.
- ✔ Reglas centrales (18) y lenguaje prudente (20) aplicados: evidencia con
  confiabilidad A+–E obligatoria, riesgos explícitos, guardrail de frases
  prohibidas sobre la salida del agente, cap de cripto sin fundamentos (12).
- ✔ Resiliencia 16.5: caché con TTL por tipo de dato, backoff exponencial ante
  429, métrica en `/api/health`, interfaz `MarketDataProvider` swapeable.
- ✔ Migración TimescaleDB condicional (hoy no-op en Railway; se activa sola si
  algún día la base tiene la extensión).

### B.2 Pendientes del propio roadmap (no implementado aún) ☐

**Versión 7 (sección 19):**
- ☐ **Django Channels / WebSockets**: alertas en tiempo real y el paso 10 del
  flujo (sección 17). Hoy el resultado se persiste y se sirve por REST.
- ☐ **Rebalanceo automático con impacto fiscal y comisiones** (hoy existe la
  versión simple 4.9: sugerencias por desvío de peso objetivo, sin fiscalidad).
- ☐ **Indicadores macroeconómicos globales** (World Bank, IMF, OECD — 8.1).
- ☐ **Reportes ejecutivos en PDF descargables.**
- ☐ Endurecimiento 16.5: dashboard/alertado de la tasa de 429 (hoy es un
  contador) y evaluación de proveedor de pago (Polygon/Finnhub) si el volumen
  crece — el swap ya es trivial gracias a la interfaz.

**Fuentes ampliadas 8.6 (el doc las asigna a V4/V5; siguen sin integrar):**
- ☐ NewsAPI.org, Finnhub y Alpha Vantage News & Sentiment como agregadores
  adicionales (hoy: solo yfinance `.news` + Google News RSS).
- ☐ MarketBeat / TipRanks para **cruzar** el consenso contra yfinance y
  detectar discrepancias entre proveedores (sección 11).
- ☐ StockTwits API y Reddit vía PRAW (señales sociales ya cuantificadas,
  siempre con peso bajo — 8.4).
- ☐ Finviz como screener para alimentar el motor discovery.

**Fuera del backend:**
- ☐ **Frontend Next.js completo (16.3)**: TypeScript + TanStack Query +
  Zustand + TradingView Lightweight Charts + Tailwind/shadcn. La API REST con
  OpenAPI ya está lista para consumirse.

### B.3 Infraestructura y operación pendiente ☐

- ☐ **`ANTHROPIC_API_KEY` sin cargar en `.env`** → el agente 5.2 todavía no
  corrió en vivo (está demostrado con tests mockeados). Al cargarla:
  `python manage.py run_scoring --escalate`.
- ☐ **Redis + Celery Beat inactivos**: en esta máquina falta WSL2/Docker
  (la instalación de Docker Desktop falló por eso). Pasos: `wsl --install`
  como administrador → reiniciar → Docker Desktop → `docker compose up -d redis`
  → worker `--pool=solo` + beat. Mientras tanto `refresh_all` cubre la cadencia
  a demanda. Alternativa sin Docker: Redis gestionado en Railway.
- ✔ **Autenticación de la API** (2026-07-13): app `accounts` con registro/
  login/logout/me por **sesión de Django** (email como identificador; cookie +
  CSRF, sin JWT). Los routers `portfolio` y `simulation` exigen sesión
  (`django_auth`) y filtran por `request.user`; `Simulation`/`BacktestRun`
  ganaron FK `user` (migración `simulation/0002`) y validan que la cartera
  vinculada sea propia. `get_default_user()` eliminado. El resto de routers
  (datos de mercado compartidos) sigue público. Pendiente menor: crear
  superusuario para `/admin` (`createsuperuser`) y reasignar/limpiar las
  carteras del viejo usuario `local`.
- ☐ **CI (GitHub Actions, 16.4)**: no configurada; el repo git es local y sin
  remote. Falta workflow de tests + lint (ruff) al pushear.
- ☐ **Despliegue a producción del backend**: DEBUG=False, `ALLOWED_HOSTS`,
  estáticos, Nginx/gunicorn o servicio en Railway. Hoy corre como dev server.
- ☐ **Backups/retención de la BD Railway** y rotación de credenciales
  (la URL con password vive solo en `.env`, fuera de git).

### B.4 Mejoras conocidas sobre lo ya implementado (deuda técnica honesta)

- **Sentimiento**: VADER es un léxico en inglés → titulares en español tienden
  a neutral (default conservador). Mejora V4: modelo multilingüe local o el
  sentimiento ya calculado de Alpha Vantage como complemento.
- **Cripto (12)**: implementado como penalización de riesgo + cap sin
  fundamentos. Faltan las métricas on-chain reales del doc: TVL, usuarios
  activos, tokenomics, desbloqueos, auditorías, actividad GitHub, concentración
  de holders (requieren APIs tipo DeFiLlama/Etherscan/GitHub).
- **Experts (10)**: la verificación contra FINRA BrokerCheck / SEC IAPD es
  100 % manual vía admin. Falta el flujo asistido (links prellenados, campos de
  chequeo) y la captura de análisis individuales de expertos con su historial.
- **Discovery (6/13)**: la extracción de tickers es por regex
  (`NYSE/NASDAQ: XXX`, `$XXX`) y solo vincula activos ya cargados; el resto
  queda como candidato para curaduría. Los componentes "adopción" e "inversión
  institucional" del score 13 son proxies de prensa (documentado en el código).
  Mejorable con NER, screener externo y datos de flujos reales.
- **Confiabilidad (9)**: los factores credenciales/historial/transparencia/
  independencia arrancan neutrales (50) y se curan a mano; falta poblarlos por
  autor/medio con datos reales para que el 60 % no-tipo de la fórmula trabaje.
- **Backtesting (4.7)**: una sola estrategia (cruce SMA 50/200) y sin costos de
  transacción/slippage. Agregar estrategias (RSI, momentum, DCA) y fricciones.
- **Simulación (4.6)**: escenarios deterministas (r ± σ). Mejora: Monte Carlo
  con percentiles (p5/p50/p95) manteniendo el disclaimer.
- **DCF/WACC (4.3 bloque 5)**: supuestos globales (rf 4,2 %, ERP 5 %, costo de
  deuda default 5 %). Mejorable: costo de deuda efectivo por empresa (intereses
  reales/deuda), tasa libre de riesgo viva y sensibilidad del fair value.
- **Escala del universo**: hoy 10 tickers de watchlist. Para S&P 500 completo:
  descarga multi-ticker en lote, rate limiting más agresivo y probablemente el
  proveedor de pago de B.2.
- **Consenso (11)**: sumar `upgrades_downgrades` de yfinance para alertas de
  cambios de recomendación individuales, además del snapshot agregado.
- **Divergencia mecánico vs agente (5.2 punto 5)**: se muestra en
  `/api/recommendation/ranking`, pero falta la **alerta explícita** cuando
  supera un umbral (el doc la trata como señal en sí misma).
- **Multimoneda**: la cartera asume USD; falta conversión FX para posiciones en
  otras monedas (campo `currency` ya existe).
- **Noticias**: `impact_score` es heurístico (categoría × |sentimiento| ×
  confiabilidad); V4 pide refinar el ajuste del score general por noticia.

### B.5 Desvíos deliberados respecto del texto original (documentados)

- **Intradía no se persiste**: `MarketPrice` guarda solo barras diarias; lo
  intradía se sirve en vivo desde la caché del provider (mantiene limpia la
  serie y el constraint único). Revisar si el dashboard lo exige.
- **Paso 10 de la sección 17** publica por REST (no WebSocket) hasta V7.
- **Capa de API**: solo Django Ninja; DRF no se incorporó porque no hizo falta
  (el propio doc lo dejaba como opcional).
- **Panel interno**: Django Admin cumple el rol de curaduría previsto, sin UI
  extra.
