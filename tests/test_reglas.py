"""Pruebas de las reglas del bot con precios inventados cuyo resultado se conoce de antemano.

Ejecutar:  python tests/test_reglas.py        (o  pytest tests/ , si está instalado)
No necesitan red, yfinance ni claves. Si cambias o añades una condición en nucleo/indicadores.py,
añade aquí su prueba con una serie inventada.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bot"))  # programas del bot (config, alertas, diario)
from nucleo import costes, limites, sombra  # noqa: E402
from nucleo.indicadores import (Alguna, CaidaDesdeMaximo, Cruce, MaximoMovil, MinimoMovil, Nivel, No,  # noqa: E402
                                SinNuevoMinimo, Todas, Variacion)
from nucleo.sombra import Sombra  # noqa: E402


def serie(valores, inicio="2026-01-01"):
    return pd.Series(np.asarray(valores, dtype=float), index=pd.bdate_range(inicio, periods=len(valores)))


# --- indicadores.py ---------------------------------------------------------------

def test_cruce_primer_dia_al_alza():
    # 70 sesiones planas a 100 y luego +1 por sesión. Calculado a mano: la SMA6 supera a la SMA70
    # en cuanto el último precio sube: el primer True está en la sesión 71 (índice 70).
    p = serie([100] * 70 + [101 + i for i in range(30)])
    s = Cruce(6, 70).serie(p)
    assert len(s) == len(p) - 70 + 1                      # sin NaN: solo desde que existe la SMA70
    assert not s.iloc[:-30].any() or s.index[s].min() == p.index[70]
    assert s.index[s].min() == p.index[70]
    # comprobación independiente con numpy
    for i in (70, 85, 99):
        assert (p.iloc[i - 5:i + 1].mean() > p.iloc[i - 69:i + 1].mean()) == bool(s.loc[p.index[i]])


def test_cruce_igual_no_cuenta():
    s = Cruce(6, 70).serie(serie([100] * 80))
    assert not s.any()                                    # medias iguales: la condición es «mayor que»


def test_cruce_describir():
    assert Cruce(6, 70).describir(True) == "SMA6 cruza por encima de SMA70"
    assert Cruce(1, 200).describir(False) == "precio cruza por debajo de SMA200"
    assert Cruce(6, 70).sesiones == 70


def test_nivel():
    p = serie([9, 10, 11])
    assert list(Nivel(10).serie(p)) == [False, False, True]           # estrictamente por encima
    assert list(Nivel(10, encima=False).serie(p)) == [True, False, False]
    assert Nivel(10).describir(True) == "el precio supera 10"
    assert Nivel(10).describir(False) == "el precio cae por debajo de 10"


def test_caida_desde_maximo():
    p = serie([100, 120, 100, 97, 95])
    s = CaidaDesdeMaximo(0.20).serie(p)                               # 20 % desde 120 = 96 o menos
    assert list(s) == [False, False, False, False, True]              # 97 → −19,2 %; 95 → −20,8 %
    # con ventana de 2 sesiones el máximo ya no es 120 en la última: 100→99 no es una caída del 20 %
    assert not CaidaDesdeMaximo(0.20, ventana=2).serie(serie([120, 100, 99])).iloc[-1]


def test_no_y_todas():
    p = serie([9, 10, 11, 12])
    a, b = Nivel(10), Nivel(11)
    assert list(No(a).serie(p)) == [True, True, False, False]
    assert list(Todas((a, b)).serie(p)) == [False, False, False, True]
    assert Todas((Cruce(6, 70), Nivel(1))).sesiones == 70
    assert No(a).describir(True) == a.describir(False)


def test_sin_nuevo_minimo():
    # 4 sesiones a 100, mínimo a 90 (sesión 4), luego 95, 96, 97, 98, 99: con ventana 5 y dias=3,
    # el último cierre en mínimo es la sesión 4; se cumple desde la sesión 7 (3 sesiones después).
    p = serie([100, 100, 100, 100, 90, 95, 96, 97, 98, 99])
    s = SinNuevoMinimo(dias=3, ventana=5).serie(p)
    assert list(s.index[s]) == [p.index[7], p.index[8], p.index[9]]
    assert not s.loc[p.index[6]]
    # un nuevo mínimo reinicia la cuenta
    q = serie([100, 100, 100, 100, 90, 95, 96, 97, 98, 80, 85, 86])
    t = SinNuevoMinimo(dias=3, ventana=5).serie(q)
    assert not t.loc[q.index[9]] and not t.loc[q.index[11]]
    assert SinNuevoMinimo(5, 60).sesiones == 65
    assert "sin nuevo mínimo" in SinNuevoMinimo(5, 60).describir(True)


def test_alguna():
    p = serie([9, 10, 11, 12])
    a, b = Nivel(10), Nivel(11, encima=False)
    # Nivel(10): [F, F, T, T]; Nivel(11, abajo): [T, T, F, F]  → alguna = siempre; con las dos hacia arriba:
    assert list(Alguna((a, b)).serie(p)) == [True, True, True, True]
    assert list(Alguna((Nivel(10), Nivel(11))).serie(p)) == [False, False, True, True]
    assert Alguna((Cruce(6, 70), Nivel(1))).sesiones == 70


# --- sombra.py --------------------------------------------------------------------

def test_sombra_caida_max_y_ejecucion_al_dia_siguiente():
    p = serie(np.r_[np.linspace(100, 130, 30), np.linspace(130, 95, 30)])
    r = sombra.evaluar(Sombra("t", "X", "2026-01-01", caida_max=0.10, coste=0.0), p)
    primera = p[(p / p.cummax() - 1) <= -0.10].index[0].date()
    assert r["estado"] == "cerrada" and r["senal"] == primera
    assert r["salida"] > r["senal"]                                   # se ejecuta en la sesión siguiente


def test_sombra_stop_desde_la_entrada_no_sube_con_el_precio():
    # sube a 130 y baja a 100: caída del 23 % desde el máximo pero 0 % desde la entrada → con stop 12 % NO sale;
    # sigue bajando a 87 (−13 % desde la entrada) → sale.
    p = serie(np.r_[np.linspace(100, 130, 10), np.linspace(130, 100, 10), np.linspace(100, 87, 10), [86, 85]])
    r = sombra.evaluar(Sombra("t", "X", "2026-01-01", stop=0.12, coste=0.0), p)
    primera = p[(p / p.iloc[0] - 1) <= -0.12].index[0].date()
    assert r["estado"] == "cerrada" and r["senal"] == primera and primera > p.index[19].date()
    assert "precio de entrada" in r["motivo"]


def test_sombra_exige_salida_y_coste():
    p = serie([100] * 5)
    for s in (Sombra("t", "X", "2026-01-01", coste=0.0), Sombra("t", "X", "2026-01-01", plazo=3)):
        try:
            sombra.evaluar(s, p)
        except ValueError:
            continue
        raise AssertionError("debía fallar sin salida o sin coste")


def test_sombra_neto_descuenta_coste():
    p = serie([100, 110, 110])
    r = sombra.evaluar(Sombra("t", "X", "2026-01-01", plazo=100, coste=0.01), p)
    assert abs(r["bruto"] - 0.10) < 1e-12 and abs(r["neto"] - 0.09) < 1e-12 and r["estado"] == "abierta"


def test_sombra_senal_sale_en_el_primer_cruce_a_la_baja():
    # sube (cruza al alza), luego cae (cruza a la baja): debe salir en la caída, no antes
    p = serie([100] * 70 + [101 + i for i in range(20)] + [120 - 3 * i for i in range(30)])
    r = sombra.evaluar(Sombra("t", "X", "2026-01-01", senal=Cruce(6, 70), coste=0.0), p)
    assert r["estado"] == "cerrada" and "debajo" in r["motivo"]
    assert r["senal"] > p.index[89].date()                                   # después del máximo, no durante la subida


# --- limites.py y costes.py -------------------------------------------------------

LIMITES_PRUEBA = [{"tipo": "maximo_conjunto", "bloques": ["cripto", "especulacion"], "valor": 15},
                  {"tipo": "maximo_posicion", "bloques": ["especulacion"], "valor": 8},
                  {"tipo": "minimo_conjunto", "bloques": ["ahorro"], "valor": 85}]
NOMBRES_PRUEBA = {"ahorro": "Ahorro", "cripto": "Cripto", "especulacion": "Especulación"}


def test_limites():
    df = pd.DataFrame({"activo": ["A", "B", "C"], "peso": [86.0, 8.5, 5.5], "bloque": ["ahorro", "especulacion", "cripto"]})
    r = limites.calcular(df, LIMITES_PRUEBA)
    assert abs(r[0]["valor"] - 14.0) < 1e-9 and (r[1]["posicion"], r[1]["valor"]) == ("B", 8.5)
    texto = "\n".join(limites.lineas(df, LIMITES_PRUEBA, NOMBRES_PRUEBA, 0.9))
    assert "· Cripto + especulación: 14,0 % de 15,0 % ⚠️ cerca" in texto
    assert "· Mayor especulación (B): 8,5 % de 8,0 % 🚨 supera" in texto
    assert "· Ahorro: 86,0 % (mínimo 85,0 %) ✅" in texto
    nuevo = limites.aplicar(df, {"A": -1.0, "C": +1.0})
    assert abs(nuevo["peso"].sum() - 100) < 1e-9 and abs(limites.calcular(nuevo, LIMITES_PRUEBA)[0]["valor"] - 15.0) < 1e-9


def test_perfil_detecta_errores():
    from nucleo import perfil
    malo = {"bloques": {"a": "A"}, "limites": [{"tipo": "maximo_raro", "bloques": ["b"], "valor": "x"}],
            "comisiones": {"p": {"porcentaje": "mucho"}}}
    p = " | ".join(perfil.problemas(malo))
    for texto in ["tipo 'maximo_raro'", "bloques que no están", "no tiene `valor`", "'p' tiene valores no numéricos"]:
        assert texto in p, (texto, p)
    assert perfil.problemas() == []                                   # el perfil real está bien escrito


def test_costes():
    etf = {"porcentaje": 0.0012, "minimo": 1.0, "maximo": 25.0, "cambio_divisa": 0.0030}
    assert costes.comision(etf, 100) == 1.0                           # mínimo
    assert abs(costes.comision(etf, 5000) - 6.0) < 1e-9               # 0,12 %
    assert costes.comision(etf, 50000) == 25.0                        # máximo
    assert abs(costes.comision(etf, 5000, divisa_ajena=True) - 21.0) < 1e-9   # +0,30 % = 15
    coste, frac = costes.ida_y_vuelta(etf, 5000)
    assert abs(coste - 12.0) < 1e-9 and abs(frac - 0.0024) < 1e-12
    assert costes.ida_y_vuelta({"porcentaje": 0.0}, 1000) == (0.0, 0.0)
    assert costes.comision("x", 100, tarifas={"x": {"porcentaje": 0.01}}) == 1.0    # por nombre, sin máximo


# --- datos.py: alineación del tipo de cambio -----------------------------------------

def test_alinear_fx_asigna_la_vela_siguiente():
    from nucleo import datos
    fx = serie([1.10, 1.12, 1.11, 1.15])
    a = datos.alinear_fx(fx)
    assert list(a.round(2)) == [1.12, 1.11, 1.15, 1.15]                  # t ← t+1; la última se queda
    assert list(a.index) == list(fx.index)


def test_cambio_eurusd_une_fred_y_cola_de_yahoo(monkeypatch=None):
    from nucleo import datos
    yahoo = serie([1.00, 1.01, 1.02, 1.03, 1.04, 1.05])                  # vela de Yahoo (inicio del día)
    fred = serie([1.005, 1.015, 1.025])                                   # FRED: solo hasta el 3.er día
    viejo = (datos._cierres, datos.fred)
    datos._cierres, datos.fred = (lambda t, p: yahoo), (lambda c: fred)
    try:
        e = datos.cambio_eurusd()
    finally:
        datos._cierres, datos.fred = viejo
    assert list(e.iloc[:3]) == list(fred)                                 # histórico: FRED
    assert list(e.iloc[3:].round(2)) == [1.04, 1.05, 1.05]                # cola: Yahoo alineado
    assert e.index.is_monotonic_increasing and not e.index.duplicated().any()


# --- diario.py: reglas de relevancia ---------------------------------------------------

def _diario():
    import diario
    exp = pd.DataFrame({"activo": ["A", "B"], "variable": ["Estrés de crédito"] * 2,
                        "efecto_actual": [-0.008, 0.004], "lectura": ["−−", "++"]})
    pesos = pd.Series({"A": 90.0, "B": 10.0})
    return diario, exp, pesos


def test_diario_exige_movimiento_medido():
    diario, exp, pesos = _diario()
    n = {"variable": "Estrés de crédito", "direccion": "sube", "sorpresa": True, "impacto": "alto"}
    assert diario.evaluar(n, exp, pesos, {"Estrés de crédito": 0.4})[0] is False     # no se movió
    ok, efecto, pos, _, signo, z = diario.evaluar(n, exp, pesos, {"Estrés de crédito": 2.0})
    assert ok and efecto == -1 and signo == 1 and "A ↓" in pos and "B ↑" in pos
    # la dirección es la del dato, aunque el titular diga lo contrario
    ok, efecto, *_ , signo, _ = diario.evaluar({**n, "direccion": "baja"}, exp, pesos, {"Estrés de crédito": 2.0})
    assert ok and signo == 1 and efecto == -1


def test_diario_sin_dato_usa_sorpresa_del_modelo():
    diario, exp, pesos = _diario()
    n = {"variable": "Estrés de crédito", "direccion": "baja", "sorpresa": False, "impacto": "alto"}
    assert diario.evaluar(n, exp, pesos, {})[0] is False                              # descontado
    ok, efecto, *_ = diario.evaluar({**n, "sorpresa": True}, exp, pesos, {})
    assert ok and efecto == 1                                                         # menos estrés: sube


def test_diario_descarta_efecto_despreciable():
    diario, exp, pesos = _diario()
    exp = exp.assign(efecto_actual=[-0.0005, 0.0004])                                 # < 0,1 % por σ en la cartera
    n = {"variable": "Estrés de crédito", "direccion": "sube", "sorpresa": True, "impacto": "alto"}
    r = diario.evaluar(n, exp, pesos, {"Estrés de crédito": 3.0})
    assert r[0] is False and "despreciable" in r[3]



def test_aviso_token():
    import alertas
    from datetime import date
    assert alertas.aviso_token(date(2027, 10, 1), "2027-11-01", 14) is None          # aún falta
    assert "X-GitHub-Api-Version" in alertas.aviso_token(date(2027, 10, 31), "2027-10-31", 14)
    assert "14 días" in alertas.aviso_token(date(2027, 10, 18), "2027-11-01", 14)    # empieza el aviso
    assert "caduca hoy" in alertas.aviso_token(date(2027, 11, 1), "2027-11-01", 14)
    assert alertas.aviso_token(date(2027, 11, 1), None) is None                       # sin token configurado


def test_modo_demo_imprime_en_vez_de_enviar(capsys=None):
    import io
    from contextlib import redirect_stdout
    import telegram
    salida = io.StringIO()
    previo = telegram.DEMO
    telegram.DEMO = True
    try:
        with redirect_stdout(salida):
            telegram.enviar("🔔 <b>Oro</b> &amp; plata")              # sin red: si intentara enviar, fallaría
    finally:
        telegram.DEMO = previo
    assert "🔔 Oro & plata" in salida.getvalue()


def test_minimo_movil():
    # 5 sesiones: 10, 8, 9, 7, 7. Mínimo de las 3 sesiones anteriores (sin contar la de hoy):
    # i=3 -> min(10,8,9)=8, precio 7 < 8 -> True; i=4 -> min(8,9,7)=7, precio 7 no es < 7 -> False.
    p = serie([10, 8, 9, 7, 7])
    s = MinimoMovil(3).serie(p)
    assert list(s.index) == list(p.index[3:])             # sin NaN: solo desde que hay 3 sesiones previas
    assert list(s) == [True, False]
    assert MinimoMovil(60).sesiones == 61
    assert MinimoMovil(60).describir(True) == "el precio cierra por debajo de su mínimo de 60 sesiones"


def test_todas_con_descripcion_propia():
    c = Todas((Nivel(1), Nivel(2)), descripcion=("sí", "no"))
    assert c.describir(True) == "sí" and c.describir(False) == "no"
    assert Todas((Nivel(1),)).describir(True).startswith("se cumplen todas")   # sin descripción: la automática


def _caida(n_plano=150, n_sube=40, n_baja=60):
    """150 sesiones planas a 100, sube a 130 y cae hasta 80: acaba con SMA6 < SMA70 y por debajo de todos los suelos."""
    return serie([100.0] * n_plano + list(np.linspace(100, 130, n_sube)) + list(np.linspace(130, 80, n_baja)))


def test_salida_previa_igual_que_calculo_independiente():
    p = _caida()
    cond = Todas((No(Cruce(6, 70)), MinimoMovil(60)))
    s = cond.serie(p)
    for i in range(70, len(p)):
        esperado = (p.iloc[i - 5:i + 1].mean() < p.iloc[i - 69:i + 1].mean()) and p.iloc[i] < p.iloc[i - 60:i].min()
        assert bool(s.loc[p.index[i]]) == esperado, i
    assert bool(s.iloc[-1])                                # al final de la caída salta


def test_alarma_de_posicion_solo_vale_dentro(monkeypatch=None):
    import alertas
    from nucleo.reglas import Activo
    p = _caida()
    hoy = p.index[-1].date()
    alertas.precios = lambda *a, **k: p                    # sin red: precios inventados
    alarma = Todas((No(Cruce(6, 70)), MinimoMovil(60)))
    baja = Cruce(6, 70).serie(p)
    cruce_baja = baja.index[(baja.shift(1, fill_value=False) & ~baja).values][0]      # primer cruce a la baja de la caída
    # Entrada DESPUÉS del cruce a la baja y sin cruce al alza posterior: sigue DENTRO y la alarma vale.
    dentro = Activo("T", "T", senal=Cruce(6, 70), en_cartera=str((cruce_baja + pd.Timedelta(days=3)).date()), alarma=alarma)
    e = alertas.evaluar(dentro, hoy)
    assert e["estado"] == "dentro" and e["alarma"] is True
    # Entrada ANTES del cruce a la baja: la salida 6/70 ya ocurrió (FUERA) y la alarma ya no aplica.
    fuera = Activo("T", "T", senal=Cruce(6, 70), en_cartera=str((cruce_baja - pd.Timedelta(days=20)).date()), alarma=alarma)
    e = alertas.evaluar(fuera, hoy)
    assert e["estado"] == "salida" and e["alarma"] is None and e["alarma_cambio"] is None
    # Sin posición: la alarma funciona siempre.
    sin = Activo("T", "T", alarma=alarma)
    assert alertas.evaluar(sin, hoy)["alarma"] is True


def test_reglas_mal_escritas_dan_un_error_claro():
    from nucleo.reglas import Activo
    Activo("Oro", "GLD", alarma=Todas((Cruce(6, 20), No(MinimoMovil(60)))), recordatorio="texto")  # bien escrita
    casos = {
        "sin paréntesis": dict(alarma=Nivel),
        "Cruce sin paréntesis": dict(alarma=No(Cruce)),
        "dobles paréntesis": dict(alarma=Todas(Cruce(6, 70))),
        "AAAA-MM-DD": dict(en_cartera="1/6/2026"),
        "no es una condición": dict(senal=250),
        "recordatorio pero no alarma": dict(recordatorio="texto"),
        "seguimiento debe ser": dict(seguimiento=[Cruce(6, 70)]),
    }
    for esperado, kw in casos.items():
        try:
            Activo("Oro", "GLD", **kw)
        except ValueError as e:
            assert esperado in str(e) and "'Oro'" in str(e), (esperado, str(e))
        else:
            raise AssertionError(f"no detecta: {esperado}")


def test_coherencia_de_los_archivos_reales():
    """cartera.csv, FACTORES, la matriz y las reglas del bot cuadran (falla si se renombra algo en un solo sitio)."""
    import pandas as pd
    from config import ACTIVOS as REGLAS
    from nucleo.rutas import MATRIZ
    from nucleo.universo import coherencia
    problemas = coherencia(REGLAS, pd.read_csv(MATRIZ))
    assert problemas == [], problemas


def test_coherencia_detecta_errores():
    from nucleo.reglas import Activo
    from nucleo.universo import coherencia
    filas = [{"activo": "A", "bloque": "ahorro", "peso": "60", "corto": "", "ticker": "SPY", "divisa": "", "aproximacion": ""},
             {"activo": "B", "bloque": "otro", "peso": "30", "corto": "", "ticker": "", "divisa": "", "aproximacion": ""}]
    reglas = [Activo("X", "X", en_cartera="2026-01-01"),                       # sin posicion
              Activo("Y", "Y", posicion="Vendida", en_cartera="2026-01-01")]   # posición que ya no está
    matriz = pd.DataFrame({"activo": ["A"]})
    p = " | ".join(coherencia(reglas, matriz, filas=filas))
    for texto in ["bloque 'otro'", "'B' no tiene ticker", "suman 90.0", "'X' tiene en_cartera", "'Vendida'",
                  "sin filas para ['B']"]:
        assert texto in p, (texto, p)


# --- condiciones añadidas para alertas habituales ----------------------------------------

def test_variacion():
    p = serie([100, 101, 95, 96, 110])
    assert list(Variacion(-0.05).serie(p)) == [False, True, False, False]          # 95/101 − 1 = −5,9 %
    assert list(Variacion(0.10, ventana=2).serie(p)) == [False, False, True]       # 110/95 − 1 = +15,8 %
    assert Variacion(-0.05).describir(True) == "el precio cae un 5 % o más en la última sesión"
    assert Variacion(0.1, 5).sesiones == 6


def test_maximo_movil():
    p = serie([100, 101, 95, 96, 110])
    assert list(MaximoMovil(3).serie(p)) == [False, True]                           # 96 < 101; 110 > máx(101, 95, 96)
    assert MaximoMovil(3).describir(True) == "el precio cierra por encima de su máximo de 3 sesiones"


# --- configuración de variables (control/variables.toml) ----------------------------------

def test_variables_toml_valido():
    from nucleo.universo import CESTAS, DIARIAS, VARIABLES, problemas_variables
    assert problemas_variables() == []
    for ticker, _, var, _ in DIARIAS.values():                                     # cada aproximación apunta a algo real
        assert var is None or var in VARIABLES
        assert ticker in CESTAS or "CESTA" not in ticker


def test_variables_toml_detecta_errores():
    from nucleo.universo import problemas_variables
    variables = {"A": {"fuente": "bloomberg", "codigo": "X", "cambio": "dif"},
                 "B": {"fuente": "fred", "cambio": "pct", "matriz": False}}
    diarias = {"d": {"ticker": "T", "cambio": "log", "variable": "Z", "signo": 2}}
    p = " | ".join(problemas_variables(variables, diarias, {"vacía": {}}))
    for texto in ["fuente 'bloomberg'", "'B' no tiene codigo", "cambio 'pct'", "variable 'Z'", "signo 2",
                  "cesta 'vacía'"]:
        assert texto in p, (texto, p)


# --- matriz de exposición (nucleo/exposiciones.py) ------------------------------------------

def test_matriz_recupera_exposiciones_conocidas():
    from nucleo import exposiciones as ex
    rng = np.random.default_rng(0)
    idx = pd.date_range("2015-01-02", periods=600, freq="W-FRI")
    z = pd.DataFrame(rng.standard_normal((600, 2)), index=idx, columns=["v1", "v2"])
    rent = pd.DataFrame({"A": 0.01 * z.v1 + 0.002 * rng.standard_normal(600),      # depende de v1, no de v2
                         "B": -0.005 * z.v2 + 0.002 * rng.standard_normal(600)}, index=idx)
    est = ex.estimaciones(rent, z)
    m = ex.matriz(est, fecha="2026-01-01").set_index(["activo", "variable"])
    assert abs(m.loc[("A", "v1"), "parcial_actual"] - 0.01) < 0.001
    assert m.loc[("A", "v1"), "lectura"] == "+++" and m.loc[("A", "v2"), "lectura"] == "0"
    assert m.loc[("B", "v2"), "lectura"] == "−−"                                    # −0,5 %: entre 0,4 % y 1 %
    assert set(m.columns) >= {"efecto_actual", "parcial_actual", "lectura", "lectura_parcial", "estable"}


# --- modelo de factores (nucleo/factores.py) ---------------------------------------------------

def test_ortogonalizar():
    from nucleo import factores as fa
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2020-01-01", periods=500)
    a = rng.standard_normal(500)
    F = pd.DataFrame({"A": a, "B": 0.5 * a + rng.standard_normal(500)}, index=idx)   # B lleva medio A dentro
    Fo, C, propia = fa.ortogonalizar(F)
    assert np.allclose(Fo["A"], F["A"] - F["A"].mean())                              # el primero no cambia
    assert abs(Fo.corr().loc["A", "B"]) < 1e-12                                      # quedan incorrelados
    assert abs(C.loc["B", "A"] - 0.5) < 0.1 and propia["A"] == 1                      # recupera lo que había dentro
    assert abs(propia["B"] - 1 / 1.25) < 0.1                                          # var propia 1 de 1,25
    y = pd.Series(2 * F.A - F.B + 0.1 * rng.standard_normal(500), index=idx)
    assert abs(fa.ajustar(y, F)[1] - fa.ajustar(y, Fo)[1]) < 1e-12                    # mismo R²
    Fo2, _, _ = fa.ortogonalizar(F, ["B", "A"])                                      # el orden decide quién se
    assert np.allclose(Fo2["B"], F["B"] - F["B"].mean())                             # queda la parte común


def test_especificos_solo_recogen_lo_que_no_explican_los_generales():
    from nucleo import factores as fa
    rng = np.random.default_rng(4)
    idx = pd.bdate_range("2020-01-01", periods=400)
    g = pd.DataFrame({"G": rng.standard_normal(400)}, index=idx)
    previo = fa.factores
    fa.factores = lambda defs, todos=False, alternativas=False: (
        pd.DataFrame({"S": 0.8 * g.G + rng.standard_normal(400)}, index=idx), {})
    try:
        E, _ = fa.especificos("X", g, definiciones={"S": {"tipo": "precio", "ticker": "S"}})
    finally:
        fa.factores = previo
    assert abs(np.corrcoef(E["S"], g.G)[0, 1]) < 1e-12                               # limpio del general
    assert fa.especificos("X", g, definiciones={})[0].empty                          # sin específicos, vacío


def test_especifico_compartido_conserva_la_correlacion():
    """Si dos posiciones comparten un específico, el modelo reproduce su correlación; si solo lo tiene una, se pierde
    (la parte común queda como riesgo propio, que el modelo trata como independiente)."""
    from nucleo import factores as fa
    rng = np.random.default_rng(5)
    n = 3000
    g = pd.DataFrame({"G": rng.standard_normal(n)})
    comun = rng.standard_normal(n)                                     # p. ej., el bitcoin
    y = pd.DataFrame({"X": 0.3 * g.G + comun + 0.3 * rng.standard_normal(n),
                      "Y": 0.2 * g.G + comun + 0.3 * rng.standard_normal(n)})
    Fo, _, _ = fa.ortogonalizar(pd.concat([g, pd.Series(comun, name="S")], axis=1))

    def correlacion_modelo(cols_x, cols_y):
        B = pd.DataFrame({a: fa.ajustar(y[a], Fo[c])[0].reindex(Fo.columns).fillna(0) for a, c in
                          (("X", cols_x), ("Y", cols_y))})
        D = np.diag([(y[a] - Fo @ B[a]).var() for a in "XY"])
        S = B.T.values @ Fo.cov().values @ B.values + D
        return S[0, 1] / np.sqrt(S[0, 0] * S[1, 1])

    real = y.corr().loc["X", "Y"]
    assert abs(correlacion_modelo(["G", "S"], ["G", "S"]) - real) < 0.02           # compartido: la reproduce
    assert correlacion_modelo(["G", "S"], ["G"]) < real - 0.5                       # solo en X: se pierde


def test_conversion_exacta():
    from nucleo import factores as fa
    idx = pd.bdate_range("2024-01-01", periods=6)
    precio = pd.Series([100, 101, 99, 102, 103, 101.0], index=idx)              # en dólares
    fx = pd.Series([1.10, 1.12, 1.08, 1.08, 1.11, 1.05], index=idx)             # dólares por euro
    previo = (fa.precios, fa.cambio)
    fa.precios = lambda t, d=None, periodo="2y": precio / fx if d else precio
    fa.cambio = lambda d, periodo="max": fx
    try:
        activos = {"X": ("X", "EURUSD=X"), "Y": ("Y", None)}
        Rl = fa.rentabilidades_activos(activos, moneda="local")
        Ri = fa.rentabilidades_activos(activos, moneda="inversor")
        K = fa.conversion_divisa(activos)
    finally:
        fa.precios, fa.cambio = previo
    assert np.allclose((Rl + K - Ri).dropna(), 0)                                  # r_tuya = r_local + conversión
    assert np.allclose(K["X"].dropna(), -np.log(fx).diff().dropna()) and (K["Y"] == 0).all()


# --- proveedor del modelo de lenguaje (bot/llm.py) -------------------------------------------

def test_llm_peticion_anthropic():
    import llm
    url, cab, cuerpo = llm.peticion("sis", "usu", proveedor="anthropic", modelo="m", clave="k")
    assert url == "https://api.anthropic.com/v1/messages" and cab["x-api-key"] == "k"
    assert cuerpo["system"] == "sis" and cuerpo["messages"] == [{"role": "user", "content": "usu"}]
    assert cuerpo["temperature"] == 0
    assert llm.texto_respuesta("anthropic", {"content": [{"type": "text", "text": " {} "}]}) == "{}"


def test_llm_peticion_compatible_openai():
    import llm
    url, cab, cuerpo = llm.peticion("sis", "usu", proveedor="openai", modelo="m", clave="k",
                                    url="http://localhost:11434/v1/",
                                    parametros={"max_tokens": None, "max_completion_tokens": 900})
    assert url == "http://localhost:11434/v1/chat/completions" and cab["authorization"] == "Bearer k"
    assert cuerpo["messages"][0] == {"role": "system", "content": "sis"}
    assert "max_tokens" not in cuerpo and cuerpo["max_completion_tokens"] == 900    # None quita, el resto sustituye
    _, cab, _ = llm.peticion("s", "u", proveedor="openai", modelo="m")              # sin clave (modelo local)
    assert "authorization" not in cab
    assert llm.texto_respuesta("openai", {"choices": [{"message": {"content": "hola"}}]}) == "hola"


def test_llm_proveedor_desconocido():
    import llm
    try:
        llm.peticion("s", "u", proveedor="otro", modelo="m")
    except ValueError as e:
        assert "anthropic" in str(e)
    else:
        raise AssertionError("debería fallar")


if __name__ == "__main__":
    pruebas = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    fallos = 0
    for nombre, f in pruebas:
        try:
            f()
            print(f"ok    {nombre}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"FALLA {nombre}: {type(e).__name__}: {e}")
    print(f"\n{len(pruebas) - fallos}/{len(pruebas)} pruebas correctas")
    sys.exit(1 if fallos else 0)
