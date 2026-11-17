# Bot manual and setup guide

[Español](bot.md) · **English**

What each program does and how to run your own bot. The repository map is in the [README](../README.en.md).

Code, configuration and messages are in Spanish. Key terms: *activo* = asset, *cartera* = portfolio, *seguimiento* = tracking, *señal* = signal, *alarma* = alarm, *recordatorio* = reminder, *sombra* = shadow, *registro* = log, *informe* = report, *diario* = daily.

## Contents

1. [Data](#data)
2. [Alerts: rules per asset](#alerts-rules-per-asset)
3. [Messages](#messages)
4. [Market variables and exposure matrix](#market-variables-and-exposure-matrix)
5. [Reports](#reports)
6. [Language model](#language-model)
7. [Discipline: limits, log and shadow portfolio](#discipline-limits-log-and-shadow-portfolio)
8. [Step-by-step setup](#step-by-step-setup)
9. [Scheduling the runs](#scheduling-the-runs)
10. [Adapting the system to your portfolio](#adapting-the-system-to-your-portfolio)
11. [Dependencies](#dependencies)

Everything configurable has an example value (mine): anything you don't change stays that way.

## Data

- **Prices:** Yahoo Finance (`yfinance`), daily closes adjusted for dividends. **Macro series:** FRED, no key needed.
- Every download is saved to `datos/<ticker>_<period>.csv` (a folder ignored by git). If a download fails, that copy is used with a warning; with `FINANZAS_SIN_RED=1` the copies are always used, which is useful for working offline.
- **Conversion to euros:** `nucleo.datos.cambio_eurusd()` takes the history from FRED (DEXUSEU, New York noon) and fills in the latest days, which FRED has not yet published, with Yahoo. Since around 2011 Yahoo dates its FX candles at the start of the London day (its value for day $t$ is that of the night of $t-1$), so that tail is shifted by one candle (`alinear_fx`).

## Alerts: rules per asset

The rules are yours: each asset in `bot/config.py` is an `Activo(name, ticker, divisa=…, …)` on any Yahoo Finance ticker (stocks, ETFs, indices, currencies, commodities, crypto), and can have four kinds of rule. All of them use **conditions** from `nucleo/indicadores.py`, evaluated on daily closes (in euros if the asset has a `divisa`):

| Rule | Purpose | Alert |
|---|---|---|
| `seguimiento` | Context information (by default, `SEGUIMIENTO`: short vs medium and medium vs long-term trends) | 🔔 when any condition changes |
| `senal` | Strategy for a position | 🟢 entry when it becomes true, 🔴 exit when it stops being true |
| `en_cartera` | Date of the actual purchase | The position is IN until the first exit after that date, even if it was bought before the condition held |
| `alarma` | Situations that call for a review | 🚨 when it becomes true (with an optional `recordatorio`), ✅ when it stops |

In addition, `posicion` states which row of `control/cartera.csv` the rule belongs to (the weekly report warns if the position is no longer in the portfolio but the rule is still there), and `continuo=True` marks assets that trade around the clock (crypto).

Available conditions (extensible with a new class in `nucleo/indicadores.py` plus its test in `tests/`):

| Condition | True when… |
|---|---|
| `Cruce(a, b)` | the `a`-session average is above the `b`-session average (`a=1` is the price) |
| `Nivel(x, encima=True)` | the price is above (or below) `x` |
| `Variacion(-0.03)` / `Variacion(0.1, ventana=5)` | the price falls 3 % or more in one session / rises 10 % or more in 5 sessions |
| `CaidaDesdeMaximo(0.2, 252)` | the price has fallen 20 % or more from its 252-session high |
| `MaximoMovil(252)` | the close is above the maximum of the previous 252 closes (new one-year high) |
| `MinimoMovil(60)` | the close is below the minimum of the previous 60 closes |
| `SinNuevoMinimo(5, 60)` | at least 5 sessions have passed since the last 60-session low |
| `No(c)` | `c` is false |
| `Todas((c1, c2, …), descripcion=(yes, no))` | all are true (`descripcion`, optional, is the message text) |
| `Alguna((c1, c2, …), descripcion=(yes, no))` | at least one is true |

Examples:

```python
Activo("Apple", "AAPL", alarma=Nivel(250))                                     # price goes above $250
Activo("Nasdaq 100", "QQQ", alarma=Variacion(-0.03))                           # falls 3 % or more in a day
Activo("Bitcoin", "BTC-USD", continuo=True, alarma=MaximoMovil(252))           # new one-year high
Activo("Oro", "GLD", seguimiento={"Corto": Cruce(6, 20), "Largo": Cruce(70, 200)})   # custom trends
```

A position with a strategy and an early exit:

```python
Activo("Tierras raras (€)", "REMX", divisa="EURUSD=X",
       senal=Cruce(6, 70), en_cartera="2026-06-01", posicion="VanEck Rare Earth",
       alarma=Todas((No(Cruce(6, 70)), MinimoMovil(60))))
```

**When it is evaluated.** Closed candles only: for stocks, the day's session (no new session on weekends and holidays); for crypto, the previous day's candle, which closes at 00:00 UTC. The bot keeps no state: each run rebuilds the averages from the history. If a run is skipped, that change is not reported, but the weekly summary shows the correct state.

## Messages

- 🚨 **Alarm** / ✅ **Alarm over**: the alarm condition becomes true or stops being true, with its reminder.
- 🟢 **ENTRY signal**: the strategy condition becomes true for an asset with no position.
- 🟢 **Trend confirmed**: the condition becomes true while already in the position; from then on, the exit is when it stops being true.
- 🔴 **EXIT signal**: the condition stops being true for the first time after the entry.
- 🔔 **Trend change**: a tracking condition changes. The day's changes are grouped together.
- 📋 **Summary**: on `DIA_RESUMEN` (Friday by default), the state of every condition, of the positions (🟢 IN, 🔴 OUT with the exit date, ⚪ no position) and active alarms.
- ⚠️ **Stale data**: an asset's last candle is more than 5 days old.
- 🔑 **Renew the token**: if you set `TOKEN_CADUCA`, starting 14 days before it expires.
- ❌ **Error**: something failed; the run shows up red in GitHub Actions.

## Market variables and exposure matrix

The method is fixed; the variables are configuration. `control/variables.toml` defines:

- **`[variables]`**: the state variables, each with its source (`fred` or `yahoo`), its code, how its change is measured (`dif` for rates and spreads, `log` for prices), whether it enters the matrix and, optionally, a short name and what a rise means (passed to the model that classifies news).
- **`[diarias]`**: proxies with fresh daily data, used to check whether a variable actually moved on the day of a story (FRED publishes with a lag). They can be a ticker or a **basket** (`[cestas]`: weighted sum of log changes).
- **`[factores]`**: reference assets that explain a position better than the general variables (for example, lithium for a rare-earths ETF). They are tracked in the weekly report and guide the daily brief.
- **`[parametros]`**: sample start and regime-change date.

From the variables, `python -m nucleo.exposiciones` computes the **exposure matrix** (`analisis/exposiciones.csv`): for each portfolio asset and each variable, how much the asset moves in a week when the variable moves by one standard deviation. It gives two readings: the **typical effect** (simple regression, including how the other variables usually move at the same time; used by the daily brief for news) and the **direct exposure** (multiple regression, holding the others fixed; used by the weekly report to attribute the week). The full method is documented in [`nucleo/exposiciones.py`](../nucleo/exposiciones.py).

Regenerate the matrix when you change the variables or the portfolio, and every quarter. `python -m nucleo.universo` checks that the file is well formed and that everything agrees; if the matrix does not match the current variables, the programs say so instead of failing without explanation.

## Reports

| Report | Contents |
|---|---|
| 📰 **Daily brief** (`bot/diario.py`) | Headlines from the feeds in `config.FUENTES_RSS` since the last Wall Street close. The model (temperature 0, no web search) only groups and classifies them by state variable; the code decides with fixed rules: the variable must have actually moved ($\lvert z \rvert \ge 1.5$ on its daily proxy; if it has no daily data, the model's surprise flag is used) and have a typical effect on the portfolio of at least 0.1 % per weekly standard deviation. Up to 3 stories with their $z$, the estimated effect on the portfolio, the affected positions and the sources. If the API fails (for example, no credit left), it warns on Telegram. Consistency test: `python bot/diario.py --prueba 3`. |
| 📊 **Weekly report** (`bot/informe.py`) | Profile limits, shadow portfolio, portfolio consistency (only if something does not match), notable variables (unusual move or extreme level over 5 years), how much of the portfolio's week each variable explains, sector factors for each position and the week's events (`control/calendario.csv`). Series with no data for the week yet (FRED publishes with a lag) are flagged and left out of the calculation. Pure computation, no AI. |

The state-variable framework, the exposure matrix and the news-filtering protocol are in [`conocimiento/mercado.md`](../conocimiento/mercado.md) (in Spanish).

## Language model

Only the daily brief uses it, and only to group and classify headlines. It is configured in `bot/config.py`:

| Option | What it is | Default |
|---|---|---|
| `DIARIO_PROVEEDOR` | `"anthropic"` or `"openai"`; the latter works with any OpenAI-compatible API | `"anthropic"` |
| `DIARIO_MODELO` | Model name at that provider | `"claude-sonnet-4-5"` |
| `DIARIO_URL` | API URL; `None` = the provider's official one | `None` |
| `DIARIO_CLAVE` | Name of the environment variable (and GitHub secret) holding the key | the provider's usual one |
| `DIARIO_PARAMETROS` | Extra or replaced request fields; `None` removes one | `{}` |
| `DIARIO_INVERSOR`, `DIARIO_EJEMPLOS` | Who the investor is and examples of story → position, for the model's instructions | generic |

Examples:

```python
# OpenAI
DIARIO_PROVEEDOR, DIARIO_MODELO, DIARIO_CLAVE = "openai", "gpt-4o-mini", "OPENAI_API_KEY"
# Google Gemini (OpenAI-compatible API)
DIARIO_PROVEEDOR, DIARIO_MODELO = "openai", "gemini-2.5-flash"
DIARIO_URL, DIARIO_CLAVE = "https://generativelanguage.googleapis.com/v1beta/openai", "LLM_API_KEY"
# Ollama on your computer (no key; local testing only, GitHub Actions cannot reach it)
DIARIO_PROVEEDOR, DIARIO_MODELO, DIARIO_URL = "openai", "llama3.1", "http://localhost:11434/v1"
# OpenAI reasoning models, which accept neither temperature nor max_tokens
DIARIO_PARAMETROS = {"temperature": None, "max_tokens": None, "max_completion_tokens": 4000}
```

The `diario` workflow passes the `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `LLM_API_KEY` secrets to the program: create the one named in `DIARIO_CLAVE`. Model names change over time; if one is retired, the brief warns on Telegram with a hint of what to change.

## Discipline: limits, log and shadow portfolio

| Tool | What it does | How to use it |
|---|---|---|
| **Limits** (`nucleo/limites.py`) | Checks the weights in `control/cartera.csv` against the profile limits (crypto + speculation ≤ 15 %, ≤ 8 % per speculative position). Warns "close" from 90 % of a limit. | Part of the weekly report. Locally, `python -m nucleo.limites "ETH=+1.5" "Vanguard U.S. 500=-1.5"` simulates a trade before making it. |
| **Decision log** (`nucleo/registro.py`) | Every alert and every story in the daily brief (including the discarded ones, as a control) is logged with the expected price direction, the variable and its $z$. | `python analisis/evaluar_registro.py`: what the price did afterwards. With few rows nothing can be concluded. |
| **Shadow portfolio** (`nucleo/sombra.py`, `SOMBRA` in `bot/config.py`) | Tracks ideas without real money, with an exit rule from day one: a condition from `indicadores.py`, maximum drawdown from the peak, `stop` (fixed drop from the entry price) or a time limit. Costs are deducted (`coste` is mandatory). | Add a `Sombra(...)` to `SOMBRA`; it appears in the weekly report. Locally, `python bot/informe.py --sombra`. |
| **Costs** (`nucleo/costes.py`) | Commissions per platform (in the example: ETFs at 0.12 %, minimum €1, maximum €25, FX conversion 0.30 %; funds free of charge). | `python -m nucleo.costes 5000` or `python -m nucleo.costes 100 divisa`. |

## Step-by-step setup

First, try it locally with `--demo` (see the [README](../README.en.md#quick-start)): it prints the messages instead of sending them and does not write to `registro/`.

### 1. Copy the repository

Fork it on GitHub (or create a repository from a copy). If you are going to enter your real weights, make it **private**. Euro amounts are never versioned: if you want to keep them, use a `*.local.*` file, which is in `.gitignore`.

### 2. Create the Telegram bot

1. In Telegram, open a chat with **@BotFather**, send `/newbot` and follow the instructions. You will get the bot's **token** (something like `123456789:AA…`).
2. Open a chat with your new bot and send it any message.
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in your browser: in the response, `"chat":{"id": …}` is your **chat_id**.

### 3. (Optional) Language model key

Only needed for the daily brief. By default it uses Anthropic: create a key at [console.anthropic.com](https://console.anthropic.com) and add credit. For another provider, see [Language model](#language-model). Each brief is a single call with at most 80 headlines.

### 4. Add the secrets

In your repository: *Settings → Secrets and variables → Actions → New repository secret*:

| Secret | Used by |
|---|---|
| `TELEGRAM_BOT_TOKEN` | all |
| `TELEGRAM_CHAT_ID` | all |
| `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` or `LLM_API_KEY`, whichever `DIARIO_CLAVE` names) | daily brief |

Locally, copy `.env.example` to `.env` and fill it in (`.env` is in `.gitignore`).

### 5. Test it

*Actions → alertas → Run workflow*, ticking «resumen», should send you the status summary of each asset. Do the same with `informe` and `diario`.

The `alertas` and `diario` workflows commit `registro/` when they finish (they need `permissions: contents: write`, which they already have). So before pushing from your machine, run `git pull --rebase`.

## Scheduling the runs

The workflows only have `workflow_dispatch` (manual launch or via the API). There are two ways to schedule them:

**Option A: GitHub's `schedule` (the simplest).** Add it to the `on:` block of each workflow, for example in `alertas.yml`:

```yaml
on:
  schedule:
    - cron: "15 22 * * *"   # every day at 22:15 UTC
  workflow_dispatch:
```

Note that GitHub does not guarantee the time. In my case it delayed runs by several hours or skipped them, which is why I use option B.

**Option B: cron-job.org (exact time).** [cron-job.org](https://console.cron-job.org) is free and triggers the workflow with the same call as the *Run workflow* button:

1. On GitHub, create a **fine-grained token** (*Settings → Developer settings → Fine-grained tokens*) with access **only to your repository** and the **Actions: Read and write** permission. It cannot touch the code or read the secrets.
2. On cron-job.org, create one job per workflow:
   - URL: `https://api.github.com/repos/<user>/<repo>/actions/workflows/<workflow>.yml/dispatches` (always `https`: cron-job.org does not follow redirects).
   - Method `POST`; body `{"ref":"main"}`.
   - Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <token>`, `X-GitHub-Api-Version: 2022-11-28`, `Content-Type: application/json`.
   - Expected response: `204`. Turn on email notification on failure.
3. Put the token's expiry date in `TOKEN_CADUCA` (`bot/config.py`): the alerts will remind you 14 days in advance. If the token expires, the bot stops running without any warning.

The schedule is up to you, with two constraints imposed by the programs:

- **`alertas`**: after the US close (16:00 in New York: 21:00 UTC, or 20:00 UTC during US daylight saving time) and before 00:00 UTC. It compares the latest candle with the current UTC date: if it runs after midnight UTC, it will not report that day's stock-market changes.
- **`diario`**: it reads the headlines published since the previous business day's Wall Street close, so it makes sense before the open.

The `informe` can run on any day; it summarises the last full week. Example schedule (Europe/Madrid): `diario` Monday to Friday at 06:20; `informe` on Mondays at 06:40; `alertas` every day at 23:15. The day of the alerts' weekly summary is `DIA_RESUMEN` in `bot/config.py` (Friday by default).

## Adapting the system to your portfolio

| If you change… | Do this |
|---|---|
| A position | Its row in `control/cartera.csv` (name, block, weight, short name, Yahoo ticker that proxies it, currency) and its strategy in `control/cartera.md`. Then run `python -m nucleo.exposiciones` to regenerate the matrix. |
| A bot rule | `bot/config.py` (with `posicion=` if it belongs to a portfolio position). |
| A kind of condition | A class in `nucleo/indicadores.py` with `serie()`, `describir()` and `sesiones`, plus its test in `tests/`. |
| A state variable, a daily proxy or a sector factor | `control/variables.toml`; then `python -m nucleo.exposiciones`. It is worth explaining why in `conocimiento/mercado.md`. |
| The profile limits | `nucleo/limites.py` and `control/perfil.md`. |
| Commissions | `nucleo/costes.py`. |
| News sources | `FUENTES_RSS` in `bot/config.py`. |
| The language model | `DIARIO_*` in `bot/config.py` (see [Language model](#language-model)). |
| A new file read by the code | Its path in `nucleo/rutas.py`, and nowhere else. |

After any change: `python -m nucleo.universo` (does everything agree?) and `python tests/test_reglas.py`. The test `test_coherencia_de_los_archivos_reales` checks that the portfolio, the variables, the matrix and the bot's rules agree with one another.

Maintenance: `control/calendario.csv` every quarter, and the exposure matrix every quarter or whenever a new asset is added.

## Dependencies

`requirements.txt` lists what the bot uses (and installs the `nucleo` package in editable mode); `requirements.lock` pins the exact versions (Python 3.12, Linux) installed by the workflows, so that a new release of `yfinance` or `pandas` cannot break the bot without any code change. To update them:

```bash
uv pip compile requirements.txt --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --no-emit-package finanzas --upgrade -o requirements.lock
```

On every push, the `tests` workflow runs `tests/` with those versions. It is separate from the bot's workflows so that a broken test cannot block the alerts.
