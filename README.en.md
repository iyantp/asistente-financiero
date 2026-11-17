# Financial assistant

[![tests](https://github.com/iyantp/asistente-financiero/actions/workflows/tests.yml/badge.svg)](https://github.com/iyantp/asistente-financiero/actions/workflows/tests.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![MIT license](https://img.shields.io/badge/license-MIT-green)

[Español](README.md) · **English**

An assistant that watches your investments and messages you on Telegram **only when something that matters happens**. It runs by itself on GitHub, with no computer left on and no server of your own, and does three things:

1. **Alerts with your own rules.** "Tell me if gold falls 15 % from its high", "if the S&P 500 drops below its 200-session average", "if bitcoin makes a one-year high". What you would do with a paid service such as TradingView, on any Yahoo Finance asset.
2. **A filtered news brief.** Every morning it reads the headlines from the sources you choose and sends you only the ones that affect what you hold, with the reason why. An AI sorts the headlines; fixed rules decide what matters to you, so it is predictable.
3. **A system to understand what moves your portfolio.** It measures how the big market variables (interest rates, the dollar, inflation, oil…) affect each of your assets, and how your assets relate to one another. Every Monday a report explains what moved your portfolio that week.

> Everything personal is configuration: your portfolio, your rules, your sources, your variables and the AI provider. What you see here is **an example configuration**, with a typical made-up portfolio: anything you don't change stays as it is. Nothing here is financial advice.

## Why it exists

It started from two goals. First, to build my own alerts and notifications, tailored to what I find useful, without paying for a service. Second, to automate information: to receive only the news and data that affect what I hold.

The second is the hard one. Financial news is a mess: dozens of items a day, many contradicting each other, almost all sounding important, and very few saying what they change for you. Is a rise in oil bad for an index fund? Is a more hawkish Federal Reserve bad for gold? It depends, and what it depends on is rarely explained.

So the assistant does not decide on how striking a headline is. It asks three questions of each one:

1. **Which market variable does it move?** Interest rates, the dollar, inflation, oil… An AI translates the headline into a variable and a direction. That is all the AI does.
2. **Did it really move?** This is checked against the day's data: the news only counts if that variable moved well beyond normal. What the market already expected moves nothing, however loud it is.
3. **Does it affect you?** Years of history measure how much each of your assets moves when that variable moves. If your portfolio does not react to it, the news is discarded.

The last two questions are answered by data, not by the AI or by whoever wrote the article, so the filter is predictable and can be checked. Each item arrives with its reason (which variable, how much it moved, which of your positions rise or fall with it), and the loud headlines that get discarded are listed at the end with the reason ("the variable barely moved", "negligible effect on your portfolio"). Over time you also learn how the pieces of the market fit together. And everything is logged, including what was discarded, to measure over the months whether the filter gets it right.

## How it understands the market

The assistant does not follow "all the news". It uses two kinds of variables:

- **General variables**, which move every asset: the world stock market, interest rates, credit, inflation, the dollar, commodities…
- **Specific variables** for one or a few particular assets, covering what the general ones miss: miners and the Chinese stock market for a lithium fund, or the Nasdaq for bitcoin.

Using historical data, it measures how much each of your assets moves when each variable moves. That gives three things:
- **Which news affects you:** a story only gets through if it moves a variable that moves your portfolio, and if that variable actually moved.
- **What explains your week:** Monday's report splits the portfolio's move across the variables.
- **Why your assets move together,** which matters for knowing whether you are really diversified.

The variables in this repository are mine, as an example; the method works with whichever you choose. The technical detail is in the [appendix](#technical-appendix).

## Try it

You need Python 3.10 or later. The demo downloads prices from the internet; no Telegram account or keys are needed.

```bash
git clone https://github.com/iyantp/asistente-financiero.git
cd asistente-financiero
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot/alertas.py --demo
python bot/informe.py --demo
```

On Windows, the fourth line is `.venv\Scripts\activate`. The last two print the alerts and the weekly report for the example portfolio. The news brief needs an AI key (by default, `ANTHROPIC_API_KEY`): `python bot/diario.py --demo`.

Code, configuration and messages are in Spanish, as it started as a personal tool. Key terms: *activo* = asset, *cartera* = portfolio, *alarma* = alarm, *seguimiento* = tracking, *señal* = signal, *informe* = report, *diario* = daily.

## Make it yours

| What | Where |
|---|---|
| Your portfolio: positions, weights and the currency of each | `control/cartera.csv` (a table: edit it in Excel or any editor) |
| Your theses and exit conditions, in free text (the news brief takes them into account) | `control/cartera.md` |
| Your alert rules | `bot/config.py` |
| Your news sources | `bot/config.py` (`FUENTES_RSS`) |
| The AI provider (Anthropic, OpenAI, Gemini, a model on your computer…) | `bot/config.py` (`DIARIO_*`) |
| Your market variables: general ones and those specific to an asset | `control/variables.toml` and `control/especificos.csv` |
| Your portfolio blocks, risk limits and broker commissions | `control/perfil.toml` |
| The week's events (Fed, ECB, CPI…) | `control/calendario.csv` |
| When each message arrives | Whichever scheduler you use (see the guide) |
| Instructions for an AI to maintain all of the above | `ia/asistente-financiero/SKILL.md` (see [Day to day](#day-to-day)) |

### Your alert rules

Each rule is one line in `bot/config.py`, which is built for exactly that: at the top it has a cheat sheet with every condition, and below it the rules, kept apart from everything else. For example:

```python
# Apple's price goes above $250
Activo("Apple", "AAPL", alarma=Nivel(250)),

# The Nasdaq 100 falls 3 % or more in a day
Activo("Nasdaq 100", "QQQ", alarma=Variacion(-0.03)),

# Gold is 15 % or more below its one-year high
Activo("Oro", "GLD", alarma=CaidaDesdeMaximo(0.15)),

# Bitcoin hits a one-year high (it trades every day)
Activo("Bitcoin", "BTC-USD", continuo=True, alarma=MaximoMovil(252)),

# The S&P 500, measured in euros, loses its 200-session average
Activo("S&P 500 (€)", "SPY", divisa="EURUSD=X", alarma=No(Cruce(1, 200))),
```

Conditions can be combined ("this and that", "this or that"). An asset can also have **tracking** (alerts you when a trend changes) and a **strategy** with a purchase date (alerts you on entry and exit).

You can write the rules by hand or ask an AI for them in plain language ("alert me if gold falls 10 % from its high"): the repository includes the instructions it needs to do it properly (see [Day to day](#day-to-day)). If a rule is badly written, `python -m nucleo.universo` tells you which one and why, and `python bot/alertas.py --demo` shows the alerts that would go out today. All the conditions are in the [manual](docs/bot.en.md#alerts-rules-per-asset); if one is missing, it is added as a new piece without touching the others.

### Running your own bot

The step-by-step guide is in [`docs/bot.en.md`](docs/bot.en.md#step-by-step-setup). In short:
1. Click **Use this template → Create a new repository** and choose **Private**, so your portfolio is not on display. (A *fork* of a public repository is always public.)
2. Create a Telegram bot with @BotFather.
3. Save the bot's token, your chat number and, if you want the news brief, your AI key as repository *secrets*.
4. Enter your portfolio and your rules.
5. Launch it from the *Actions* tab and schedule it.

## Day to day

Once it is set up, the bot runs on its own: every night it checks your rules, every morning it sends you the news that affects you, and every Monday the report. The only thing you have to do is **keep your portfolio up to date**, because the news filter, the report and the limits are computed from it. The bot uses whatever is on GitHub, so each change counts from the moment you push it.

**The easiest way: ask an AI.** Open the repository with an assistant that can work with files (Claude, Codex, Cursor, Copilot…) and tell it what you would tell a person:

- "I sold half my gold; the portfolio is now worth €12,000 and the gold €600."
- "Alert me if bitcoin falls 10 % in a week."
- "I want to add an emerging-markets fund at 5 %; does it break any limit?"

The repository includes instructions for the AI ([`ia/asistente-financiero/SKILL.md`](ia/asistente-financiero/SKILL.md); [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) point to them, so Claude Code and most assistants read them on their own). With them, the AI knows which file to touch in each case, recalculates the weights, checks your limits and the cost of the trade, writes the rule, verifies that everything agrees and leaves the change ready to push. It never stores euro amounts: the portfolio is kept as weights. In the Claude app you can also upload that folder as a *skill*. The instructions are in Spanish, like the code; the AI answers in your language.

**No AI and nothing to install.** Edit `control/cartera.csv` or `bot/config.py` directly on github.com (the pencil button) and save. When the change is pushed, a workflow (`matriz`) recomputes what depends on the portfolio and checks that everything agrees; if something is wrong, the run turns red and GitHub emails you.

**Every quarter:** add the dates of the upcoming central-bank meetings and inflation releases to `control/calendario.csv`, and go over your notes in `control/cartera.md`.

## Limitations

- Prices come from Yahoo Finance, which is not an official source: days are sometimes missing. Macroeconomic series (interest rates, expected inflation, credit spreads) come from [FRED](https://fred.stlouisfed.org), the free public database of the Federal Reserve Bank of St. Louis. The bot warns you when an asset's data goes stale.
- The relationships between variables and assets change over time. They are for filtering and understanding, not for forecasting.
- It takes months of use before you can measure whether the alerts are right (the system logs them so this can be checked).
- The example rules illustrate the system; they are not recommendations.

## Development

The code was written with AI assistance (Claude): the system design, the rules, the variable framework and the validation decisions are mine, and every change was checked with tests and real data before being used.

[MIT](LICENSE) license.

---

## Technical appendix

### A. How the effect of the variables is measured

**In production: the exposure matrix** (`nucleo/exposiciones.py`, `python -m nucleo.exposiciones`). The general variables are defined in `control/variables.toml`, and the specific factors in `control/especificos.csv`. For each portfolio asset and each general variable, the matrix estimates from weekly data in euros how much the asset moves when the variable moves by one standard deviation, in two readings:
- **Typical effect**, $\gamma_k$: simple regression, including how the other variables usually move at the same time. The daily brief uses it for news.
- **Direct exposure**, $\beta_k$: multiple regression, holding the others fixed. The weekly report uses it to attribute the week.

They are related by $\gamma_k = \sum_j \beta_j \rho_{jk}$. Inference: Newey-West $t$-statistics, with a $|t| > 2.58$ threshold.

**Under construction: a risk factor model** (`control/factores.toml`, `nucleo/factores.py`), in the style of Barra's models or Two Sigma's *Factor Lens*. Each asset is described as

$$r_{a,t} = \alpha_a + \sum_k \beta_{a,k}\, f_{k,t} + \varepsilon_{a,t},$$

which also gives the correlation between assets, $\Sigma = B\,\Omega\,B^\top + D$. Compared with the matrix:
- **Tradable factors with daily data** (ETFs and differences between ETFs) instead of macroeconomic series published with a lag.
- **Orthogonalisation in a chosen order** (Gram-Schmidt), so that overlapping factors, such as the euro and the dollar, do not split the credit unstably.
- **Specific factors** shared by the positions they explain and cleaned of the general ones. If a position had its factor to itself, the part it shares with others would be left as its own risk and their correlation would be lost (for bitcoin and ether, the model would give 0.13 instead of the actual 0.82).
- **Exact currency conversion,** instead of estimating it as one more factor.

Still to come: time-varying exposures, shrinking the estimates towards reference values, separating correlations in calm and stressed markets (VIX, MOVE and credit spread), and validating the model against what happens next.

### B. Design decisions

- **The language model classifies; the code decides.** The daily brief runs the model at temperature 0, without web search and on a closed list of headlines; the model returns JSON with the affected variable, direction and impact of each story. A story only gets through if its variable actually moved that day: the latest change of its daily proxy must satisfy $|z_t| \ge 1.5$, where $z_t = (\Delta x_t - \overline{\Delta x})/s_{\Delta x}$ against the previous 252 sessions. Its typical effect on the portfolio must also be at least 0.1 % per standard deviation. `python bot/diario.py --prueba 3` measures how consistent the classification is.
- **Independent of the AI provider.** `bot/llm.py` talks to the Anthropic API and to any OpenAI-compatible API using only `requests`.
- **Validating the data, not just the code.** Two examples:
  - Yahoo dates FX candles at the start of the London day, so the EUR/USD value for day $t$ is really that of the night of $t-1$: the correlation of daily changes with FRED is 0.19 on the same date and 0.77 with the next candle. This is fixed in `nucleo.datos.alinear_fx`.
  - URTH (MSCI World) barely traded in 2012–2014: 151 unchanged days in 2012 and a 0.29 correlation with the S&P 500. Its data is only used from 2015.
- **Measuring whether alerts are useful.** Every alert and every classified story, including the discarded ones as a control group, is logged in `registro/decisiones.csv` with the expected direction of the price. `analisis/evaluar_registro.py` later measures what the price actually did.
- **Ideas before money.** The shadow portfolio (`nucleo/sombra.py`) tracks ideas in simulation, with their exit rule from day one and real trading costs (`nucleo/costes.py`).
- **A single source of truth and consistency checks.** Each piece of configuration lives in one place. `python -m nucleo.universo` checks that the portfolio, variables and matrix agree; the tests and the weekly report also check the bot's rules.
- **Reliable execution.** GitHub Actions' `schedule` delayed or skipped runs, so the workflows are triggered by [cron-job.org](https://cron-job.org) through the GitHub API, with a minimum-permission token. The alerts warn before the token expires.
- **Reproducibility.** Exact versions in `requirements.lock`; tests with no network or keys on every push; a `--demo` mode; an offline mode (`FINANZAS_SIN_RED=1`) with local copies of the data.

### C. Architecture

```mermaid
flowchart LR
    subgraph SRC[Data sources]
        direction TB
        Y[Yahoo Finance<br/>prices]
        F[FRED<br/>rates, inflation, credit]
        R[RSS<br/>headlines]
    end
    TU([You, by hand or with an AI<br/>see «Day to day»])
    subgraph CFG[Your configuration]
        direction TB
        CA[control/cartera.csv · cartera.md · perfil.toml<br/>positions, theses and limits]
        VA[control/variables.toml · especificos.csv<br/>general and specific variables]
        CB[bot/config.py<br/>alert rules · RSS feeds<br/>language model]
    end
    N[nucleo/ · shared calculations<br/>downloads the data, evaluates the rules,<br/>limits, costs and log]
    M[(Effect of the variables<br/>on each asset)]
    subgraph BOT[bot/ · on GitHub Actions]
        direction TB
        A[alertas.py<br/>daily]
        D[diario.py<br/>Monday to Friday]
        I[informe.py<br/>Mondays]
    end
    subgraph OUT[Services and outputs]
        direction TB
        T[Telegram]
        RG[(registro/<br/>every alert, to measure<br/>later whether it was right)]
        LLM[Language model<br/>Anthropic, OpenAI or compatible]
        HUECO[" "]:::oculto
    end
    classDef oculto fill:none,stroke:none,color:transparent

    TU --> CFG
    Y & F --> N
    CA & VA --> N
    N --> M
    N --> BOT
    CB --> BOT
    M --> D & I
    R --> D
    D <-->|only groups and classifies| LLM
    BOT --> T
    A & D --> RG
```

Dependencies go one way only: `bot/` and `analisis/` use `nucleo/`, and `nucleo/` uses neither.

```
├── control/         your configuration: cartera.csv (positions), cartera.md (theses), perfil.toml (blocks, limits,
│                    commissions), variables.toml and especificos.csv (variables), calendario.csv (events),
│                    factores.toml (factor model, under construction)
├── bot/             programs that run unattended
│   ├── config.py        alert rules, shadow portfolio, RSS feeds and language model
│   ├── alertas.py · diario.py · informe.py
│   ├── llm.py           language model call (Anthropic or OpenAI-compatible)
│   └── telegram.py      sending (or printing to the console in demo mode)
├── nucleo/          shared library (installable Python package)
│   ├── datos.py         prices (Yahoo) and series (FRED), currency conversion, local copies
│   ├── indicadores.py   alert conditions
│   ├── reglas.py        the Activo type, which checks that every rule is well written
│   ├── universo.py      reads the portfolio, variables and specific factors; consistency check
│   ├── perfil.py        reads blocks, limits and commissions
│   ├── exposiciones.py  exposure matrix (in production)
│   ├── factores.py      factor model (under construction)
│   ├── sombra.py · limites.py · costes.py · registro.py · backtest.py
│   └── rutas.py         the only place with file paths
├── analisis/        exposure matrix and decision-log evaluation
├── registro/        what the bot writes (empty here)
├── tests/           tests with no network or keys
├── docs/            bot manual and setup guide
├── ia/              instructions for an AI to maintain the configuration (AGENTS.md and CLAUDE.md point here)
└── .github/workflows/  alerts, daily brief and weekly report (scheduled); matrix and tests (on push)
```

### D. Useful commands

```bash
python tests/test_reglas.py          # tests (no network)
python -m nucleo.universo            # does the configuration agree? (bot rules included)
python -m nucleo.exposiciones        # regenerates the exposure matrix
python -m nucleo.limites             # allocation by block and risk limits
python -m nucleo.costes 5000         # cost of buying and selling €5,000 of an ETF
python bot/informe.py --sombra       # shadow portfolio
python bot/diario.py --prueba 3      # consistency of the news classification
```
