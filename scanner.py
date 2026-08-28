import os
import re
import io
import logging
import requests
import base64
import gc
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
from flask import Flask, request, send_file, jsonify
from fpdf import FPDF, XPos, YPos
import pandas as pd
from github import Github
from github.GithubException import UnknownObjectException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DEFAULT_DEV_ORIGINS = [
    "null", "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5000", "http://localhost:5000"
]

@app.after_request
def add_security_headers(response):
    origin = request.headers.get("Origin")
    allowed_env = os.environ.get("ALLOWED_ORIGINS", "")
    allowed_list = [o.strip() for o in allowed_env.split(",") if o.strip()] + DEFAULT_DEV_ORIGINS
    if origin and origin in allowed_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' file:// http://127.0.0.1:* http://localhost:*;"
    return response

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
# Sessione HTTP riutilizzabile (keep-alive: 1 handshake TLS invece di uno per file)
_HTTP_SESSION = requests.Session()
if GITHUB_TOKEN:
    _HTTP_SESSION.headers.update({"Authorization": f"token {GITHUB_TOKEN}"})
REPO_NAME = os.environ.get("REPO_NAME", "tonecraft17/dati-privati-pdf")

g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
if not g:
    logger.error("ATTENZIONE: GITHUB_TOKEN non trovato nelle variabili d'ambiente!")

MAX_CLASSI = 20
MAX_ROWS_PDF = 100000

PROVINCE_DATA = {
    "AG": ("Sicilia", "Agrigento"), "AL": ("Piemonte", "Alessandria"), "AN": ("Marche", "Ancona"),
    "AO": ("Valle d'Aosta", "Aosta"), "AP": ("Marche", "Ascoli Piceno"), "AT": ("Piemonte", "Asti"),
    "AV": ("Campania", "Avellino"), "BA": ("Puglia", "Bari"), "BT": ("Puglia", "Barletta-Andria-Trani"),
    "BL": ("Veneto", "Belluno"), "BN": ("Campania", "Benevento"), "BG": ("Lombardia", "Bergamo"),
    "BI": ("Piemonte", "Biella"), "BO": ("Emilia-Romagna", "Bologna"), "BZ": ("Trentino-Alto Adige", "Bolzano"),
    "BS": ("Lombardia", "Brescia"), "BR": ("Puglia", "Brindisi"), "CA": ("Sardegna", "Cagliari"),
    "CL": ("Sicilia", "Caltanissetta"), "CB": ("Molise", "Campobasso"), "CE": ("Campania", "Caserta"),
    "CT": ("Sicilia", "Catania"), "CZ": ("Calabria", "Catanzaro"), "CH": ("Abruzzo", "Chieti"),
    "AR": ("Toscana", "Arezzo"),
    "CO": ("Lombardia", "Como"), "CS": ("Calabria", "Cosenza"), "CR": ("Lombardia", "Cremona"),
    "KR": ("Calabria", "Crotone"), "CN": ("Piemonte", "Cuneo"), "EN": ("Sicilia", "Enna"),
    "FM": ("Marche", "Fermo"), "FE": ("Emilia-Romagna", "Ferrara"), "FI": ("Toscana", "Firenze"),
    "FG": ("Puglia", "Foggia"), "FC": ("Emilia-Romagna", "Forlì-Cesena"), "FR": ("Lazio", "Frosinone"),
    "GE": ("Liguria", "Genova"), "GO": ("Friuli-Venezia Giulia", "Gorizia"), "GR": ("Toscana", "Grosseto"),
    "IM": ("Liguria", "Imperia"), "IS": ("Molise", "Isernia"), "AQ": ("Abruzzo", "L'Aquila"),
    "SP": ("Liguria", "La Spezia"), "LT": ("Lazio", "Latina"), "LE": ("Puglia", "Lecce"),
    "LC": ("Lombardia", "Lecco"), "LI": ("Toscana", "Livorno"), "LO": ("Lombardia", "Lodi"),
    "LU": ("Toscana", "Lucca"), "MC": ("Marche", "Macerata"), "MN": ("Lombardia", "Mantova"),
    "MS": ("Toscana", "Massa-Carrara"), "MT": ("Basilicata", "Matera"), "ME": ("Sicilia", "Messina"),
    "MI": ("Lombardia", "Milano"), "MO": ("Emilia-Romagna", "Modena"), "MB": ("Lombardia", "Monza e della Brianza"),
    "NA": ("Campania", "Napoli"), "NO": ("Piemonte", "Novara"), "NU": ("Sardegna", "Nuoro"),
    "OR": ("Sardegna", "Oristano"), "PD": ("Veneto", "Padova"), "PA": ("Sicilia", "Palermo"),
    "PR": ("Emilia-Romagna", "Parma"), "PV": ("Lombardia", "Pavia"), "PG": ("Umbria", "Perugia"),
    "PU": ("Marche", "Pesaro e Urbino"), "PE": ("Abruzzo", "Pescara"), "PC": ("Emilia-Romagna", "Piacenza"),
    "PI": ("Toscana", "Pisa"), "PT": ("Toscana", "Pistoia"), "PN": ("Friuli-Venezia Giulia", "Pordenone"),
    "PZ": ("Basilicata", "Potenza"), "PO": ("Toscana", "Prato"), "RG": ("Sicilia", "Ragusa"),
    "RA": ("Emilia-Romagna", "Ravenna"), "RC": ("Calabria", "Reggio Calabria"), "RE": ("Emilia-Romagna", "Reggio Emilia"),
    "RI": ("Lazio", "Rieti"), "RN": ("Emilia-Romagna", "Rimini"), "RM": ("Lazio", "Roma"),
    "RO": ("Veneto", "Rovigo"), "SA": ("Campania", "Salerno"), "SS": ("Sardegna", "Sassari"),
    "SV": ("Liguria", "Savona"), "SI": ("Toscana", "Siena"), "SR": ("Sicilia", "Siracusa"),
    "SO": ("Lombardia", "Sondrio"), "SU": ("Sardegna", "Sud Sardegna"), "TA": ("Puglia", "Taranto"),
    "TE": ("Abruzzo", "Teramo"), "TR": ("Umbria", "Terni"), "TO": ("Piemonte", "Torino"),
    "TP": ("Sicilia", "Trapani"), "TN": ("Trentino-Alto Adige", "Trento"), "TV": ("Veneto", "Treviso"),
    "TS": ("Friuli-Venezia Giulia", "Trieste"), "UD": ("Friuli-Venezia Giulia", "Udine"), "VA": ("Lombardia", "Varese"),
    "VE": ("Veneto", "Venezia"), "VB": ("Piemonte", "Verbano-Cusio-Ossola"), "VC": ("Piemonte", "Vercelli"),
    "VR": ("Veneto", "Verona"), "VV": ("Calabria", "Vibo Valentia"), "VI": ("Veneto", "Vicenza"),
    "VT": ("Lazio", "Viterbo")
}
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

SCUOLE_FALLBACK = {name: 0 for sigla, (region, name) in PROVINCE_DATA.items()}

SEC_I_CLASSI = {"A-01", "A-22", "AA25", "AB25", "AC25", "AD25", "AE25", "A-23", "A-28", "A-30", "A-49", "A-60", "AM01", "AM12", "AM22", "AM2A", "AM2B", "AM2C", "AM2D", "AM2E", "AM2F", "AM2G", "AM30", "AM48", "AM70", "AM71", "A-82", "A-86", "A084", "A085", "IRC", "ADMM"}

SEC_I_MUSICAL_CLASSI = {"AA56", "AB56", "AC56", "AD56", "AE56", "AF56", "AG56", "AH56", "AI56", "AJ56", "AK56", "AL56", "AM56", "AN56"}
SEC_I_MUSICAL_NAMES = {
    "AA56": "Arpa", "AB56": "Chitarra", "AC56": "Clarinetto", "AD56": "Contrabbasso",
    "AE56": "Fagotto", "AF56": "Flauto", "AG56": "Oboe", "AH56": "Pianoforte",
    "AI56": "Sassofono", "AJ56": "Tromba", "AK56": "Trombone", "AL56": "Viola",
    "AM56": "Violino", "AN56": "Violoncello"
}

# Cartelle di estrazione per ogni ordine di scuola e fascia
ESTRAZIONE_AA_I_FASCIA_PREFIX  = "Estrazione_AA_1_Fascia/"  # Infanzia I fascia
ESTRAZIONE_AA_II_FASCIA_PREFIX = "Estrazione_AA_2_Fascia/"  # Infanzia II fascia
ESTRAZIONE_EE_I_FASCIA_PREFIX  = "Estrazione_EE_1_Fascia/"  # Primaria I fascia
ESTRAZIONE_EE_II_FASCIA_PREFIX = "Estrazione_EE_2_Fascia/"  # Primaria II fascia
ESTRAZIONE_MM_I_FASCIA_PREFIX  = "Estrazione_MM_1_Fascia/"  # Secondaria I grado I fascia
ESTRAZIONE_MM_II_FASCIA_PREFIX = "Estrazione_MM_2_Fascia/"  # Secondaria I grado II fascia
ESTRAZIONE_SS_I_FASCIA_PREFIX  = "Estrazione_SS_1_Fascia/"  # Secondaria II grado I fascia
ESTRAZIONE_SS_II_FASCIA_PREFIX = "Estrazione_SS_2_Fascia/"  # Secondaria II grado II fascia

SIGLE_ALT = {
    "PS": "PU",
    "FO": "FC",
}

SEC_I_CSV_FILE_MAP = {
    "A-01": "A-01 (Arte e Immagine).csv", "A-22": "A-22 (Lettere).csv",
    "AA25": "A-25 (AA25 Francese).csv", "AB25": "A-25 (AB25 Inglese Altra Lingua).csv",
    "AC25": "A-25 (AC25 Spagnolo).csv", "AD25": "A-25 (AD25 Tedesco).csv",
    "AE25": "A-25 (AE25 Sloveno).csv", "A-23": "A-23 (Italiano L2).csv",
    "A-28": "A-28 (Matematica e Scienze).csv", "A-30": "A-30 (Musica).csv",
    "A-49": "A-49 (Scienze Motorie).csv", "A-60": "A-60 (Tecnologia).csv",
    "AM01": "A-01 (Arte e Immagine).csv", "AM12": "A-22 (Lettere).csv",
    "AM2A": "A-25 (AA25 Francese).csv", "AM2B": "A-25 (AB25 Inglese Altra Lingua).csv",
    "AM2C": "A-25 (AC25 Spagnolo).csv", "AM2D": "A-25 (AD25 Tedesco).csv",
    "AM2E": "A-25 (AE25 Sloveno).csv", "AM30": "A-30 (Musica).csv",
    "AM48": "A-49 (Scienze Motorie).csv", "IRC": "IRC (Religione Cattolica).csv",
}

# ====================================================================
# REGISTRO UNICO CLASSI DI CONCORSO (una sola denominazione per grado+fascia)
#   label : voce UNICA del menu a tendina
#   alias : TUTTI i codici con cui la classe compare nei NOMI dei FILE
#           (estrazioni E bollettini), vecchi e nuovi
#   extra_estrazione : traduzioni legacy valide SOLO per le cartelle
#           Estrazione_* (comportamento pre-esistente, non toccare)
#   scuole: file CSV in "Numero scuole ..." | "MUSICALI" | "TOTALI_MM"
# Le fasce I/II sono già gestite dalle cartelle: nessuna duplicazione.
# ====================================================================
CLASSI_REGISTRY = {
    "infanzia": {
        "AAAA": {"label": "AAAA - Scuola dell'infanzia", "alias": {"AAAA"}},
        "AAHN": {"label": "AAHN - Sostegno (Minorati dell'udito)", "alias": {"AAHN"}},
        "AAIN": {"label": "AAIN - Sostegno (Minorati della vista)", "alias": {"AAIN"}},
        "AALN": {"label": "AALN - Sostegno (Minorati psicofisici)", "alias": {"AALN"}},
        "ADAA": {"label": "ADAA - Sostegno (Scuola dell'infanzia)", "alias": {"ADAA"}},
        "AAPN": {"label": "AAPN - Sostegno (Minorati dell'udito)", "alias": {"AAPN"}}, # AGGIUNTO
        "AARN": {"label": "AARN - Sostegno (Minorati della vista)", "alias": {"AARN"}}, # AGGIUNTO
    },
    "primaria": {
        "EEEE": {"label": "EEEE - Scuola primaria", "alias": {"EEEE"}},
        "ADEE": {"label": "ADEE - Sostegno (Scuola primaria)", "alias": {"ADEE"}},
        "EEEM": {"label": "EEEM - Educazione motoria (Scuola primaria)", "alias": {"EEEM"}},
        "EEHN": {"label": "EEHN - Sostegno (Minorati dell'udito)", "alias": {"EEHN"}},
        "EEIN": {"label": "EEIN - Sostegno (Minorati della vista)", "alias": {"EEIN"}},
        "EELN": {"label": "EELN - Sostegno (Minorati psicofisici)", "alias": {"EELN"}},
        "EEIL": {"label": "EEIL - Sostegno", "alias": {"EEIL"}}, # AGGIUNTO
        "EEPN": {"label": "EEPN - Sostegno", "alias": {"EEPN"}}, # AGGIUNTO
        "EERN": {"label": "EERN - Sostegno", "alias": {"EERN"}}, # AGGIUNTO
        "EECN": {"label": "EECN - Sostegno", "alias": {"EECN"}}, # AGGIUNTO
        "EEDN": {"label": "EEDN - Sostegno", "alias": {"EEDN"}}, # AGGIUNTO
        "EEEN": {"label": "EEEN - Sostegno", "alias": {"EEEN"}}, # AGGIUNTO
        "EEQN": {"label": "EEQN - Sostegno", "alias": {"EEQN"}}, # AGGIUNTO
        "EECH": {"label": "EECH - Sostegno", "alias": {"EECH"}}, # AGGIUNTO
        "EEZJ": {"label": "EEZJ - Sostegno", "alias": {"EEZJ"}}, # AGGIUNTO
    },
    "secondaria_i": {
        "ADMM": {"label": "ADMM - Sostegno Sec. I grado", "alias": {"ADMM"}, "scuole": "TOTALI_MM"},
        "A-01": {"label": "A-01 - Arte e immagine", "alias": {"A-01", "AM01", "A001"}, "scuole": "A-01 (Arte e Immagine).csv"},
        "A-22": {"label": "A-22 - Lettere (Italiano, Storia, Geografia)", "alias": {"A-22", "AM12", "AM22", "A022"}, "scuole": "A-12 (Lettere).csv"},
        "AA25": {"label": "AA25 - Lingua e cultura francese", "alias": {"AA25", "AM2A", "A025", "A25"}, "scuole": "A-25 (AA25 Francese).csv"},
        "AB25": {"label": "AB25 - Lingua e cultura inglese", "alias": {"AB25", "AM2B", "A-25", "A025", "A25"}, "scuole": "A-25 (AB25 Inglese Altra Lingua).csv"},
        "AC25": {"label": "AC25 - Lingua e cultura spagnola", "alias": {"AC25", "AM2C", "A025"}, "scuole": "A-25 (AC25 Spagnolo).csv"},
        "AD25": {"label": "AD25 - Lingua e cultura tedesca", "alias": {"AD25", "AM2D", "A025"}, "scuole": "A-25 (AD25 Tedesco).csv"},
        "AE25": {"label": "AE25 - Lingua e cultura slovena", "alias": {"AE25", "AM2E", "A025"}, "scuole": "A-25 (AE25 Sloveno).csv"},
        "AM2F": {"label": "AM2F - Lingua straniera (Potenziamento)", "alias": {"AM2F"}},
        "AM2G": {"label": "AM2G - Lingua straniera (Potenziamento)", "alias": {"AM2G"}},
        "A-23": {"label": "A-23 - Italiano L2", "alias": {"A-23", "A023"}, "scuole": "A-23 (Italiano L2).csv"},
        "A-28": {"label": "A-28 - Matematica e Scienze", "alias": {"A-28", "AM28", "A028", "A28"}, "scuole": "A-28 (Matematica e Scienze).csv"},
        "A-30": {"label": "A-30 - Musica", "alias": {"A-30", "AM30", "A030"}, "scuole": "A-30 (Musica).csv"},
        "A-49": {"label": "A-49 - Scienze Motorie", "alias": {"A-49", "A049"}, "scuole": "A-49 (Scienze Motorie).csv"},
        "A-60": {"label": "A-60 - Tecnologia", "alias": {"A-60", "AM60", "A060"}, "scuole": "A-60 (Tecnologia).csv"},
        "AM70": {"label": "AM70 - Potenziamento (AM70)", "alias": {"AM70", "A070", "A70"}},
        "AM71": {"label": "AM71 - Potenziamento (AM71)", "alias": {"AM71", "A077", "A77"}},
        "A-82": {"label": "A-82 - Lingua e cultura friulana", "alias": {"A-82", "A082"}},
        "A-86": {"label": "A-86 - Lingua e cultura sarda", "alias": {"A-86", "A086"}},
        "A084": {"label": "A084 - Francese L2", "alias": {"A084", "A-84", "A84"}},
        "A085": {"label": "A085 - Tedesco L2", "alias": {"A085", "A-85", "A85"}},
        "A-12": {"label": "A-12 - Lettere (Vecchio ordinamento)", "alias": {"A-12", "A012"}},
        "A-25": {"label": "A-25 - Lingua straniera (Vecchio ordinamento)", "alias": {"A-25", "A025"}},
        "A-56": {"label": "A-56 - Sostegno", "alias": {"A-56", "A056"}},
        "A-70": {"label": "A-70 - Potenziamento", "alias": {"A-70", "A070"}},
        "A-77": {"label": "A-77 - Potenziamento", "alias": {"A-77", "A077"}},
        "IRC":  {"label": "IRC - Religione Cattolica", "alias": {"IRC"}, "scuole": "IRC (Religione Cattolica).csv"},
    },
    "secondaria_ii": {
        "ADSS": {"label": "ADSS - Sostegno Sec. II grado", "alias": {"ADSS", "A029"}},
        "A017": {"label": "A017 - Disegno e storia dell'arte", "alias": {"A017", "A-17", "A17"}, "scuole": "A-17 (Disegno e storia dell'arte).csv"},
        "A027": {"label": "A027 - Matematica e fisica", "alias": {"A027", "A-27", "A27"}, "scuole": "A-27 (Matematica e fisica).csv"},
        "A054": {"label": "A054 - Storia dell'arte", "alias": {"A054", "A-54", "A54"}, "scuole": "A-54 (Storia dell'arte).csv"},
        "IRC":  {"label": "IRC - Religione Cattolica", "alias": {"IRC"}, "scuole": "IRC (Religione Cattolica).csv"},
    }
}

# File "Numero scuole II grado": codice NUOVO (menu) -> codice VECCHIO (nome file)
# mappati per DENOMINAZIONE identica (fonte: SEC_II_CSV_FILE_MAP)
SEC_II_SCUOLE_MAP = {
    "A017": "A-17 (Disegno e storia dell'arte).csv",
    "A002": "A-02 (Design metalli, oreficeria, pietre).csv",
    "A003": "A-03 (Design della ceramica).csv",
    "A004": "A-04 (Design del libro).csv",
    "A005": "A-05 (Design del tessuto e della moda).csv",
    "A006": "A-06 (Design del vetro).csv",
    "A007": "A-07 (Discipline audiovisive).csv",
    "A008": "A-08 (Discipline geometriche, architettura, scenotecnica).csv",
    "A009": "A-09 (Discipline grafiche, pittoriche, scenografiche).csv",
    "A010": "A-10 (Discipline grafico-pubblicitarie).csv",
    "A011": "A-11 (Lettere e latino).csv",
    "A012": "A-12 (Discipline letterarie).csv",
    "A013": "A-13 (Lettere, latino e greco - Liceo Classico).csv",
    "A014": "A-14 (Discipline plastiche e scultoree).csv",
    "A015": "A-15 (Discipline sanitarie).csv",
    "A016": "A-16 (Modellazione odontotecnica).csv",
    "A018": "A-18 (Filosofia e scienze umane).csv",
    "A019": "A-19 (Filosofia e storia).csv",
    "A020": "A-20 (Fisica).csv",
    "A021": "A-21 (Geografia).csv",
    "A023": "A-23 (Italiano L2).csv",
    "A024": "A-24 (Lingue e culture straniere).csv",
    "A026": "A-26 (Matematica).csv",
    "A027": "A-27 (Matematica e fisica).csv",
    "A030": "A-30 (Musica).csv",
    "A031": "A-31 (Scienze degli alimenti).csv",
    "A032": "A-32 (Scienze della geologia e della mineralogia).csv",
    "A033": "A-33 (Scienze e tecnologie aeronautiche).csv",
    "A034": "A-34 (Scienze e tecnologie chimiche).csv",
    "A035": "A-35 (Tecnologie calzaturiere e della moda).csv",
    "A036": "A-36 (Scienze e tecnologie della logistica).csv",
    "A037": "A-37 (Tecnologie delle costruzioni e rappresentazione grafica).csv",
    "A038": "A-38 (Costruzioni aeronautiche).csv",
    "A039": "A-39 (Costruzioni navali).csv",
    "A040": "A-40 (Scienze e tecnologie elettriche ed elettroniche).csv",
    "A041": "A-41 (Scienze e tecnologie informatiche).csv",
    "A042": "A-42 (Scienze e tecnologie meccaniche).csv",
    "A043": "A-43 (Scienze e tecnologie nautiche).csv",
    "A044": "A-44 (Tecnologie tessili, abbigliamento e moda).csv",
    "A045": "A-45 (Scienze economico-aziendali).csv",
    "A046": "A-46 (Scienze giuridico-economiche).csv",
    "A047": "A-47 (Scienze matematiche applicate).csv",
    "A048": "A-48 (Scienze motorie e sportive).csv",
    "A050": "A-50 (Scienze naturali, chimiche e biologiche).csv",
    "A051": "A-51 (Tecnologie agrarie).csv",
    "A052": "A-52 (Tecnologie delle produzioni animali).csv",
    "A053": "A-53 (Storia della musica).csv",
    "A054": "A-54 (Storia dell'arte).csv",
    "A057": "A-57 (Tecnica della danza classica).csv",
    "A058": "A-58 (Tecnica della danza contemporanea).csv",
    "A059": "A-59 (Tecniche di accompagnamento alla danza).csv",
    "A061": "A-61 (Tecnologie e tecniche delle comunicazioni multimediali).csv",
    "A062": "A-62 (Tecnologie e tecniche per la grafica).csv",
    "A063": "A-63 (Tecnologie musicali).csv",
    "A064": "A-64 (Teoria, analisi e composizione).csv",
}

SEC_II_CSV_FILE_MAP = {
    "A-17": "A-17 (Disegno e storia dell'arte).csv", "A-02": "A-02 (Design metalli, oreficeria, pietre).csv",
    "A-05": "A-05 (Design del tessuto e della moda).csv", "A-07": "A-07 (Discipline audiovisive).csv",
    "A-08": "A-08 (Discipline geometriche, architettura, scenotecnica).csv", "A-09": "A-09 (Discipline grafiche, pittoriche, scenografiche).csv",
    "A-10": "A-10 (Discipline grafico-pubblicitarie).csv", "A-11": "A-11 (Lettere e latino).csv",
    "A-12": "A-12 (Discipline letterarie).csv", "A-13": "A-13 (Lettere, latino e greco - Liceo Classico).csv",
    "A-14": "A-14 (Discipline plastiche e scultoree).csv", "A-15": "A-15 (Discipline sanitarie).csv",
    "A-16": "A-16 (Modellazione odontotecnica).csv", "A-18": "A-18 (Filosofia e scienze umane).csv",
    "A-19": "A-19 (Filosofia e storia).csv", "A-20": "A-20 (Fisica).csv", "A-21": "A-21 (Geografia).csv",
    "A-24 (AA)": "A-24 (AA - Francese).csv", "A-24 (AB)": "A-24 (AB - Inglese Altra Lingua).csv",
    "A-24 (AC)": "A-24 (AC - Spagnolo).csv", "A-24 (AD)": "A-24 (AD - Tedesco).csv",
    "A-24 (AE)": "A-24 (AE - Sloveno).csv", "A-23": "A-23 (Italiano L2).csv",
    "A-24": "A-24 (Lingue e culture straniere).csv",
    "A-26": "A-26 (Matematica).csv", "A-27": "A-27 (Matematica e fisica).csv", "A-30": "A-30 (Musica).csv",
    "A-31": "A-31 (Scienze degli alimenti).csv", "A-32": "A-32 (Scienze della geologia e della mineralogia).csv",
    "A-33": "A-33 (Scienze e tecnologie aeronautiche).csv", "A-34": "A-34 (Scienze e tecnologie chimiche).csv",
    "A-35": "A-35 (Tecnologie calzaturiere e della moda).csv", "A-36": "A-36 (Scienze e tecnologie della logistica).csv",
    "A-37": "A-37 (Tecnologie delle costruzioni e rappresentazione grafica).csv",
    "A-38": "A-38 (Costruzioni aeronautiche).csv", "A-39": "A-39 (Costruzioni navali).csv",
    "A-40": "A-40 (Scienze e tecnologie elettriche ed elettroniche).csv", "A-41": "A-41 (Scienze e tecnologie informatiche).csv",
    "A-42": "A-42 (Scienze e tecnologie meccaniche).csv", "A-43": "A-43 (Scienze e tecnologie nautiche).csv",
    "A-44": "A-44 (Tecnologie tessili, abbigliamento e moda).csv", "A-45": "A-45 (Scienze economico-aziendali).csv",
    "A-46": "A-46 (Scienze giuridico-economiche).csv", "A-47": "A-47 (Scienze matematiche applicate).csv",
    "A-48": "A-48 (Scienze motorie e sportive).csv", "A-50": "A-50 (Scienze naturali, chimiche e biologiche).csv",
    "A-51": "A-51 (Tecnologie agrarie).csv", "A-52": "A-52 (Tecnologie delle produzioni animali).csv",
    "A-53": "A-53 (Storia della musica).csv", "A-54": "A-54 (Storia dell'arte).csv",
    "A-57": "A-57 (Tecnica della danza classica).csv", "A-58": "A-58 (Tecnica della danza contemporanea).csv",
    "A-59": "A-59 (Tecniche di accompagnamento alla danza).csv",
    "A-61": "A-61 (Tecnologie e tecniche delle comunicazioni multimediali).csv",
    "A-62": "A-62 (Tecnologie e tecniche per la grafica).csv", "A-63": "A-63 (Tecnologie musicali).csv",
    "A-64": "A-64 (Teoria, analisi e composizione).csv", "IRC": "IRC (Religione Cattolica).csv",
}

# Popolamento dinamico delle classi di Strumento Musicale (A-55) per evitare ridondanze
_STRUMENTI_ALL = [("AA","Arpa"),("AB","Chitarra"),("AC","Clarinetto"),("AD","Contrabbasso"),
                  ("AE","Fagotto"),("AF","Flauto"),("AG","Oboe"),("AH","Pianoforte"),
                  ("AI","Sassofono"),("AJ","Tromba"),("AK","Trombone"),("AL","Viola"),
                  ("AM","Violino"),("AN","Violoncello"),
                  ("AO", "Basso tuba"), ("AP", "Canto"), ("AQ", "Clarinetto basso"),
                  ("AR", "Corno"), ("AS", "Flicorno"), ("AT", "Mandolino"),
                  ("AU", "Organo"), ("AV", "Percussioni"), ("AW", "Tastiera elettronica")]
for _p, _n in _STRUMENTI_ALL:
    SEC_II_CSV_FILE_MAP[f"{_p}55"] = "A-55 (Strumento musicale).csv"
# Strumenti musicali: univoci e con nome (xx56 Sec I, xx55 Sec II)
_STRUMENTI = [("AA","Arpa"),("AB","Chitarra"),("AC","Clarinetto"),("AD","Contrabbasso"),
              ("AE","Fagotto"),("AF","Flauto"),("AG","Oboe"),("AH","Pianoforte"),
              ("AI","Sassofono"),("AJ","Tromba"),("AK","Trombone"),("AL","Viola"),
              ("AM","Violino"),("AN","Violoncello")]
for _p, _n in _STRUMENTI:
    CLASSI_REGISTRY["secondaria_i"][f"{_p}56"] = {"label": f"{_p}56 - {_n}", "alias": {f"{_p}56"}, "scuole": "MUSICALI"}
    CLASSI_REGISTRY["secondaria_ii"][f"{_p}55"] = {"label": f"{_p}55 - {_n}", "alias": {f"{_p}55"}, "scuole": "A-55 (Strumento musicale).csv"}

# Strumenti musicali estesi (solo Sec. II grado): AO-AW
_STRUMENTI_ESTESI = [
    ("AO", "Basso tuba"), ("AP", "Canto"), ("AQ", "Clarinetto basso"),
    ("AR", "Corno"), ("AS", "Flicorno"), ("AT", "Mandolino"),
    ("AU", "Organo"), ("AV", "Percussioni"), ("AW", "Tastiera elettronica"),
]
for _p, _n in _STRUMENTI_ESTESI:
    CLASSI_REGISTRY["secondaria_ii"][f"{_p}55"] = {
        "label": f"{_p}55 - {_n}", "alias": {f"{_p}55"}, "scuole": "A-55 (Strumento musicale).csv"
    }
# Nota: Rimosso il ciclo per BA02-BN02 (ITP Strumento Musicale inesistente)

# Codici Sec. II con denominazione nota (file presenti in Estrazione_SS_*)
_SEC_II_NOMI = {
    "A017":"A017 - Disegno e storia dell'arte",
    "A002":"A002 - Design metalli, oreficeria, pietre","A003":"A003 - Design della ceramica",
    "A004":"A004 - Design del libro","A005":"A005 - Design del tessuto e della moda",
    "A006":"A006 - Design del vetro","A007":"A007 - Discipline audiovisive",
    "A008":"A008 - Discipline geometriche, architettura, scenotecnica","A009":"A009 - Discipline grafiche, pittoriche, scenografiche",
    "A010":"A010 - Discipline grafico-pubblicitarie","A011":"A011 - Lettere e latino",
    "A012":"A012 - Discipline letterarie","A013":"A013 - Lettere, latino e greco - Liceo Classico",
    "A014":"A014 - Discipline plastiche e scultoree","A015":"A015 - Discipline sanitarie",
    "A016":"A016 - Modellazione odontotecnica","A018":"A018 - Filosofia e scienze umane",
    "A019":"A019 - Filosofia e storia","A020":"A020 - Fisica","A021":"A021 - Geografia",
    "A023":"A023 - Italiano L2","A024":"A024 - Lingue e culture straniere",
    "A026":"A026 - Matematica","A027":"A027 - Matematica e fisica",
    "A030":"A030 - Musica","A031":"A031 - Scienze degli alimenti","A032":"A032 - Scienze della geologia e della mineralogia",
    "A033":"A033 - Scienze e tecnologie aeronautiche","A034":"A034 - Scienze e tecnologie chimiche",
    "A035":"A035 - Tecnologie calzaturiere e della moda","A036":"A036 - Scienze e tecnologie della logistica",
    "A037":"A037 - Tecnologie delle costruzioni e rappresentazione grafica","A038":"A038 - Costruzioni aeronautiche",
    "A039":"A039 - Costruzioni navali","A040":"A040 - Scienze e tecnologie elettriche ed elettroniche",
    "A041":"A041 - Scienze e tecnologie informatiche","A042":"A042 - Scienze e tecnologie meccaniche",
    "A043":"A043 - Scienze e tecnologie nautiche","A044":"A044 - Tecnologie tessili, abbigliamento e moda",
    "A045":"A045 - Scienze economico-aziendali","A046":"A046 - Scienze giuridico-economiche",
    "A047":"A047 - Scienze matematiche applicate","A048":"A048 - Scienze motorie e sportive",
    "A050":"A050 - Scienze naturali, chimiche e biologiche","A051":"A051 - Tecnologie agrarie",
    "A052":"A052 - Tecnologie delle produzioni animali","A053":"A053 - Storia della musica",
    "A054":"A054 - Storia dell'arte","A057":"A057 - Tecnica della danza classica",
    "A058":"A058 - Tecnica della danza contemporanea","A059":"A059 - Tecniche di accompagnamento alla danza e teoria, pratica musicale per la danza",
    "A061":"A061 - Tecnologie e tecniche delle comunicazioni multimediali","A062":"A062 - Tecnologie e tecniche per la grafica",
    "A063":"A063 - Tecnologie musicali","A064":"A064 - Teoria, analisi e composizione",
    "A082":"A082 - Lingua e cultura friulana","A086":"A086 - Lingua e cultura sarda",
    "AS12":"AS12 - Lettere (Potenziamento)","AS2A":"AS2A - Lingua e cultura francese (Potenziamento)",
    "AS2B":"AS2B - Lingua e cultura inglese (Potenziamento)","AS2C":"AS2C - Lingua e cultura spagnola (Potenziamento)",
    "AS2D":"AS2D - Lingua e cultura tedesca (Potenziamento)","AS2E":"AS2E - Lingua e cultura slovena (Potenziamento)",
    "AS2F":"AS2F - Lingua e cultura russa (Potenziamento)","AS2H":"AS2H - Lingua e cultura araba (Potenziamento)",
    "AS2I":"AS2I - Lingua e cultura cinese (Potenziamento)","AS2J":"AS2J - Lingua e cultura giapponese (Potenziamento)",
    "AS2K":"AS2K - Lingua e cultura coreana (Potenziamento)","AS2L":"AS2L - Lingua e cultura hindi (Potenziamento)",
    "AS2M":"AS2M - Lingua e cultura persiana (Potenziamento)","AS2N":"AS2N - Lingua e cultura portoghese (Potenziamento)",
    "AS30":"AS30 - Musica (Potenziamento)","AS48":"AS48 - Scienze motorie e sportive (Potenziamento)",
    "AS71":"AS71 - Educazione civica e cittadinanza (Potenziamento)",
}

# CICLO CRUCIALE: Popola CLASSI_REGISTRY con tutte le classi di II grado
for _c, _l in _SEC_II_NOMI.items():
    CLASSI_REGISTRY["secondaria_ii"].setdefault(_c, {"label": _l, "alias": {_c}})

# Codici ITP (Tabella B - D.P.R. 19/2016): denominazione specifica
_SEC_II_ITP_NOMI = {
    "B001": "B001 - Attività pratiche speciali",
    "B002": "B002 - Conversazione in lingua straniera",
    "B003": "B003 - Laboratorio di fisica",
    "B004": "B004 - Laboratorio di chimica",
    "B005": "B005 - Laboratorio di scienze della terra e mineralogia",
    "B006": "B006 - Laboratorio di odontotecnica",
    "B007": "B007 - Laboratorio di epidemiologia e igiene",
    "B008": "B008 - Laboratorio di ceramica",
    "B009": "B009 - Laboratorio di disegno geometrico",
    "B010": "B010 - Laboratorio di tecnologie e tecniche di rappresentazione grafica",
    "B011": "B011 - Laboratorio di agraria",
    "B012": "B012 - Laboratorio di scienze e tecnologie chimiche e microbiologiche",
    "B013": "B013 - Laboratorio di tecnologia meccanica",
    "B014": "B014 - Laboratorio di tecnologia elettrica ed elettronica",
    "B015": "B015 - Laboratorio di elettronica",
    "B016": "B016 - Laboratorio di informatica",
    "B017": "B017 - Laboratorio di lavorazione del legno",
    "B018": "B018 - Laboratorio di lavorazione dei metalli",
    "B019": "B019 - Laboratorio di lavorazione del vetro",
    "B020": "B020 - Laboratorio di lavorazione delle materie plastiche",
    "B021": "B021 - Laboratorio di enogastronomia e ospitalità alberghiera",
    "B022": "B022 - Laboratorio di servizi commerciali",
    "B023": "B023 - Laboratorio di servizi socio-sanitari",
    "B024": "B024 - Laboratorio di lavorazione delle pelli e del cuoio",
    "B025": "B025 - Laboratorio di disegno di modelli e taglio",
    "B026": "B026 - Laboratorio di confezione",
    "B027": "B027 - Laboratorio di lavorazione dei prodotti agricoli",
    "B028": "B028 - Laboratorio di tecniche di allevamento",
    "B029": "B029 - Laboratorio di tecniche di coltivazione",
    "B030": "B030 - Laboratorio di tecnologie della pesca",
    "B031": "B031 - Laboratorio di conduzione del mezzo navale",
    "B032": "B032 - Laboratorio di elaborazione digitale delle immagini e dei suoni",
    "B033": "B033 - Laboratorio di tecniche audiovisive",
}
for _c, _l in _SEC_II_ITP_NOMI.items():
    CLASSI_REGISTRY["secondaria_ii"].setdefault(_c, {"label": _l, "alias": {_c}})

# Collega i file scuole anche alle voci generate sopra
for _c, _f in SEC_II_SCUOLE_MAP.items():
    _e = CLASSI_REGISTRY["secondaria_ii"].get(_c)
    if _e is not None and not _e.get("scuole"):
        _e["scuole"] = _f

def get_registry_entry(ordine_classe, codice):
    # Normalizza rimuovendo spazi e trattini per un confronto più robusto
    cod = str(codice).strip().upper()
    cod_norm = cod.replace("-", "") 
    registry = CLASSI_REGISTRY.get((ordine_classe or "").lower(), {})
    
    if cod in registry:
        return cod, registry[cod]
    
    for key, e in registry.items():
        # Controlla sia il codice esatto sia la versione senza trattino
        aliases_norm = {a.replace("-", "") for a in e["alias"]}
        if cod in e["alias"] or cod_norm in aliases_norm:
            return key, e
            
    return cod, {"label": cod, "alias": {cod}, "extra_estrazione": set(), "scuole": None}

SEC_II_FOLDER = "Numero scuole II grado"
SEC_II_PREFIX = SEC_II_FOLDER + "/"

SEC_II_MUSICAL_CLASSI = {
    "A-55", "AA55", "AB55", "AC55", "AD55", "AE55", "AF55", "AG55", "AH55",
    "AI55", "AJ55", "AK55", "AL55", "AM55", "AN55", "AO55", "AP55", "AQ55",
    "AR55", "AS55", "AT55", "AU55", "AV55", "AW55",
}



_SCUOLE_CSV_CACHE = {}
_SCUOLE_SEC_II_CSV_CACHE = {}
_SCUOLE_REGOLARE_CACHE = None
_SCUOLE_MUSICALI_CACHE = None
SCUOLE_REGOLARI_PATH = "Numero scuole I grado/Scuole_Statali_Totali_MM.txt"
SCUOLE_MUSICALI_PATH = "Numero scuole I grado/Riepilogo_Scuole_Musicali.txt"

NOME_TO_SIGLA = {}
REGIONI_NORM = set()
for sigla, (region, nome) in PROVINCE_DATA.items():
    region_norm = region.upper().replace(" ", "").replace("-", "").replace("'", "").replace(".", "")
    region_norm = region_norm.replace('À', 'A').replace('È', 'E').replace('Ì', 'I').replace('Ò', 'O').replace('Ù', 'U')
    REGIONI_NORM.add(region_norm)
    nome_norm = nome.upper().replace(" ", "").replace("'", "").replace("-", "").replace(".", "")
    nome_norm = nome_norm.replace('À', 'A').replace('È', 'E').replace('Ì', 'I').replace('Ò', 'O').replace('Ù', 'U')
    NOME_TO_SIGLA[nome_norm] = sigla

def to_sigla(val):
    if pd.isna(val):
        return None
    v = str(val).strip().upper().replace(" ", "").replace("'", "").replace("-", "").replace(".", "")
    v = v.replace('À', 'A').replace('Á', 'A').replace('È', 'E').replace('É', 'E')
    v = v.replace('Ì', 'I').replace('Í', 'I').replace('Ò', 'O').replace('Ó', 'O')
    v = v.replace('Ù', 'U').replace('Ú', 'U').replace('Ü', 'U')
    if v in REGIONI_NORM:
        return None
    if v in SIGLE_ALT:
        return SIGLE_ALT[v]
    if v in PROVINCE_DATA:
        return v
    if v in NOME_TO_SIGLA:
        return NOME_TO_SIGLA[v]
    
    # NEW: Match per prefisso (es. 'BARLETTA' -> 'Barletta-Andria-Trani' -> BT)
    if len(v) >= 4:
        for nome, sigla in NOME_TO_SIGLA.items():
            if nome.startswith(v):
                return sigla
    
    # Logica esistente: cerca nome completo come sottostringa di v
    best_match = None
    best_len = 0
    for nome, sigla in NOME_TO_SIGLA.items():
        if nome in v and len(nome) > best_len:
            is_inside_region = False
            for region_norm in REGIONI_NORM:
                if nome in region_norm and region_norm in v:
                    is_inside_region = True
                    break
            if not is_inside_region:
                best_match = sigla
                best_len = len(nome)
    return best_match

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_string(s):
    return re.sub(r'[\s_-]+', '', str(s)).upper()

def normalize_fascia(s):
    s = str(s).upper().strip()
    s = s.replace('1', 'I').replace('2', 'II').replace('3', 'III')
    return re.sub(r'[\s_-]+', '', s)

def pulisci_punteggio(valore):
    s = str(valore).strip()
    if not s or s.lower() in ['nan', 'none', '*', '-', '']:
        return None
    s = s.replace('*', '')
    if ' | ' in s:
        parti = s.split(' | ')
        intero = parti[0].strip().replace(',', '.')
        decimale = parti[1].strip()
        s = f"{intero}.{decimale}"
    else:
        s = s.replace(',', '.')
    match = re.search(r'(\d+\.?\d*)', s)
    if match:
        return float(match.group(1))
    return None

def parse_score(s):
    if s == "N/D" or s is None:
        return None
    try:
        return float(str(s).replace(',', '.'))
    except (ValueError, TypeError):
        return None

def clean_csv_text(raw_text):
    text = raw_text.replace('\ufeff', '')
    text = re.sub(r'^\d+\s*\|\s*', '', text, flags=re.MULTILINE)
    return text

def get_scuole_dict(repo, is_musical=False):
    global _SCUOLE_REGOLARE_CACHE, _SCUOLE_MUSICALI_CACHE
    if is_musical:
        if _SCUOLE_MUSICALI_CACHE is not None:
            return _SCUOLE_MUSICALI_CACHE
        file_path = SCUOLE_MUSICALI_PATH
        tipo = "Musicali"
    else:
        if _SCUOLE_REGOLARE_CACHE is not None:
            return _SCUOLE_REGOLARE_CACHE
        file_path = SCUOLE_REGOLARI_PATH
        tipo = "Regolari (MM)"
    try:
        logger.info(f"Lettura file scuole ({tipo}): {file_path}")
        file_content = repo.get_contents(file_path)
        raw_bytes = file_content.decoded_content
        text = raw_bytes.decode('utf-8', errors='ignore')

        text = text.replace('\ufeff', '').replace('\r\n', '\n').replace('\r', '\n')

        lines_all = [l for l in text.split('\n')]
        logger.info(f"=== DEBUG FILE ({tipo}) ===")
        logger.info(f"Totale righe: {len(lines_all)} | Lunghezza testo: {len(text)} caratteri")
        for i, line in enumerate(lines_all[:20]):
            logger.info(f"  Riga {i} [{len(line)} chars]: |{line}|")
        logger.info(f"=== FINE DEBUG ===")

        scuole_dict = {}
        for line in lines_all:
            line = line.strip()
            if not line:
                continue
            if 'scuole' in line.lower():
                parts = re.split(r'scuole\s*:', line, flags=re.IGNORECASE)
                if len(parts) > 1:
                    prov_part = parts[1]
                    matches = re.findall(r'([a-zA-ZÀ-ÿ\'\-\.\s]+?)\s+(\d+)', prov_part)
                    for match in matches:
                        prov_raw = match[0].strip().strip(',').strip()
                        num_str = match[1]
                        sigla = to_sigla(prov_raw)
                        if sigla:
                            _, nome = PROVINCE_DATA[sigla]
                            scuole_dict[nome] = int(num_str)

        logger.info(f"Strategy 0 (formato 'scuole:'): {len(scuole_dict)} province.")
        for line in lines_all:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            m = re.match(r'^([A-Z]{2})\s*[:;\t,\s\-|]+\s*(\d+)', line)
            if m:
                sigla_raw = m.group(1).upper()
                if sigla_raw in PROVINCE_DATA:
                    _, nome = PROVINCE_DATA[sigla_raw]
                    scuole_dict[nome] = int(m.group(2))
                    continue
            m = re.match(r'^([a-zA-ZÀ-ÿ\'\-\.\s]{3,}?)\s*[:;\t,\s\-|]+\s*(\d+)', line)
            if m:
                prov_raw = m.group(1).strip()
                sigla = to_sigla(prov_raw)
                if sigla:
                    _, nome = PROVINCE_DATA[sigla]
                    scuole_dict[nome] = int(m.group(2))
                    continue

        logger.info(f"Strategy 1 (riga-per-riga sigla/nome): {len(scuole_dict)} province.")

        if not scuole_dict:
            logger.info("Strategy 1 fallita. Provo formato CSV...")
            for sep in [';', ',', '\t', '|']:
                try:
                    csv_io = io.StringIO(text)
                    df_temp = pd.read_csv(csv_io, sep=sep, dtype=str, skipinitialspace=True)
                    if len(df_temp.columns) >= 2 and len(df_temp) > 0:
                        logger.info(f"CSV (sep='{sep}', con header): {len(df_temp)} righe. Colonne: {list(df_temp.columns)}")
                        for idx in range(min(5, len(df_temp))):
                            logger.info(f"  Row {idx}: {list(df_temp.iloc[idx].values)}")
                        prov_col = None
                        num_col = None
                        for col in df_temp.columns:
                            col_upper = str(col).upper().strip()
                            if any(k in col_upper for k in ['PROVINC', 'UFFICIO', 'SEDE', 'COMUNE', 'TERRITORIO', 'SIGLA']):
                                prov_col = prov_col or col
                            if any(k in col_upper for k in ['NUMERO', 'SCUOLE', 'TOTALE', 'N.', 'N ', 'COUNT', 'QUANTITA']):
                                num_col = num_col or col
                        if prov_col and num_col:
                            for _, row in df_temp.iterrows():
                                prov_val = str(row[prov_col]).strip()
                                num_val = str(row[num_col]).strip()
                                sigla = to_sigla(prov_val)
                                if sigla:
                                    _, nome = PROVINCE_DATA[sigla]
                                    match_num = re.search(r'(\d+)', num_val)
                                    if match_num:
                                        scuole_dict[nome] = int(match_num.group(1))
                            logger.info(f"CSV header: prov_col='{prov_col}', num_col='{num_col}' -> {len(scuole_dict)} province")
                        if not scuole_dict:
                            csv_io2 = io.StringIO(text)
                            df_temp2 = pd.read_csv(csv_io2, sep=sep, dtype=str, skipinitialspace=True, header=None)
                            if len(df_temp2.columns) >= 2 and len(df_temp2) > 0:
                                logger.info(f"CSV (sep='{sep}', senza header): {len(df_temp2)} righe, {len(df_temp2.columns)} colonne")
                                for idx in range(min(5, len(df_temp2))):
                                    logger.info(f"  Row {idx}: {list(df_temp2.iloc[idx].values)}")
                                best_dict = {}
                                for ci in range(len(df_temp2.columns)):
                                    for ni in range(len(df_temp2.columns)):
                                        if ci == ni:
                                            continue
                                        temp_dict = {}
                                        for _, row in df_temp2.iterrows():
                                            prov_val = str(row.iloc[ci]).strip()
                                            num_val = str(row.iloc[ni]).strip()
                                            sigla = to_sigla(prov_val)
                                            if sigla:
                                                match_num = re.search(r'(\d+)', num_val)
                                                if match_num:
                                                    _, nome = PROVINCE_DATA[sigla]
                                                    temp_dict[nome] = int(match_num.group(1))
                                        if len(temp_dict) > len(best_dict):
                                            best_dict = temp_dict
                                            logger.info(f"  CSV col{ci}+col{ni}: {len(best_dict)} province")
                                scuole_dict = best_dict
                        if scuole_dict:
                            break
                except Exception as e:
                    logger.debug(f"CSV sep='{sep}' fallito: {e}")
                    continue

        if not scuole_dict:
            logger.info("Strategy 2 fallita. Provo regex generica su tutto il testo...")
            all_matches = re.findall(r'\b([A-Z]{2})\b[\s:;\t,\-|]+(\d+)', text)
            logger.info(f"Regex sigla+numero: trovati {len(all_matches)} match: {all_matches[:10]}...")
            for sigla_raw, num_str in all_matches:
                sigla_raw = sigla_raw.upper()
                if sigla_raw in PROVINCE_DATA:
                    _, nome = PROVINCE_DATA[sigla_raw]
                    scuole_dict[nome] = int(num_str)

            if not scuole_dict:
                all_matches = re.findall(r'([a-zA-ZÀ-ÿ\'\-\.\s]{4,})\s*[:;\t,\-|]\s*(\d+)', text)
                logger.info(f"Regex nome+numero: trovati {len(all_matches)} match: {all_matches[:5]}...")
                for prov_raw, num_str in all_matches:
                    sigla = to_sigla(prov_raw.strip())
                    if sigla:
                        _, nome = PROVINCE_DATA[sigla]
                        scuole_dict[nome] = int(num_str)

        if not scuole_dict:
            logger.error(f"!!! NESSUN DATO TROVATO nel file ({tipo}) !!!")
            logger.error(f"Contenuto file (primi 1000 caratteri):")
            logger.error(text[:1000])
            result_dict = SCUOLE_FALLBACK
        else:
            logger.info(f"Dizionario scuole {tipo} caricato: {len(scuole_dict)} province.")
            for i, (nome, num) in enumerate(list(scuole_dict.items())[:5]):
                logger.info(f"  {nome}: {num}")
            result_dict = scuole_dict

        if is_musical:
            _SCUOLE_MUSICALI_CACHE = result_dict
            return _SCUOLE_MUSICALI_CACHE
        else:
            _SCUOLE_REGOLARE_CACHE = result_dict
            return _SCUOLE_REGOLARE_CACHE
    except Exception as e:
        logger.error(f"Errore critico nel caricamento del file scuole ({tipo}): {e}", exc_info=True)
        return SCUOLE_FALLBACK

def get_scuole_dict_from_csv(repo, codice, csv_filename=None):
    global _SCUOLE_CSV_CACHE
    if csv_filename is None:
        csv_filename = SEC_I_CSV_FILE_MAP.get(codice)
    if not csv_filename:
        return None
    if csv_filename in _SCUOLE_CSV_CACHE:
        return _SCUOLE_CSV_CACHE[csv_filename]
    file_path = f"Numero scuole I grado/{csv_filename}"
    try:
        logger.info(f"Lettura file CSV scuole per classe {codice}: {file_path}")
        file_content = repo.get_contents(file_path)
        raw_text = file_content.decoded_content.decode('utf-8-sig', errors='ignore')
        text = clean_csv_text(raw_text)
        df = None
        for sep in [';', ',', '\t', '|']:
            try:
                csv_io = io.StringIO(text)
                df_temp = pd.read_csv(csv_io, sep=sep, dtype=str, skipinitialspace=True)
                if len(df_temp.columns) >= 2:
                    df = df_temp
                    logger.info(f"CSV {codice} parsato con separatore '{sep}': {len(df)} righe, colonne: {list(df.columns)}")
                    break
            except Exception:
                continue
        scuole_dict = {}
        if df is not None and len(df.columns) >= 2:
            prov_col = None
            num_col = None
            for col in df.columns:
                col_upper = str(col).upper().strip()
                if any(k in col_upper for k in ['PROVINC', 'UFFICIO', 'SEDE', 'COMUNE', 'TERRITORIO']):
                    prov_col = prov_col or col
                if any(k in col_upper for k in ['NUMERO', 'SCUOLE', 'TOTALE', 'N.', 'N ', 'COUNT', 'QUANTITA']):
                    num_col = num_col or col
            if not prov_col:
                prov_col = df.columns[0]
            if not num_col:
                num_col = df.columns[1]
            logger.info(f"Colonna provincia: '{prov_col}', Colonna numero: '{num_col}'")
            for _, row in df.iterrows():
                prov_val = str(row[prov_col]).strip()
                num_val = str(row[num_col]).strip()
                sigla = to_sigla(prov_val)
                if sigla:
                    _, nome = PROVINCE_DATA[sigla]
                    match = re.search(r'(\d+)', num_val)
                    if match:
                        scuole_dict[nome] = int(match.group(1))
        else:
            logger.warning(f"Parse CSV standard fallito per {codice}, provo parser testuale.")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                matches = re.findall(r'([a-zA-ZÀ-ÿ\'\-\.\s]+?)\s+[:\-]?\s*(\d+)', line)
                for match in matches:
                    prov_raw = match[0].strip().strip(',').strip(':')
                    num_str = match[1]
                    sigla = to_sigla(prov_raw)
                    if sigla:
                        _, nome = PROVINCE_DATA[sigla]
                        scuole_dict[nome] = int(num_str)
        if not scuole_dict:
            logger.warning(f"Nessun dato trovato nel CSV scuole per {codice}. Uso fallback a 0.")
            result_dict = SCUOLE_FALLBACK
        else:
            logger.info(f"Dizionario scuole CSV per {codice} caricato: {len(scuole_dict)} province trovate.")
            result_dict = scuole_dict
        _SCUOLE_CSV_CACHE[csv_filename] = result_dict
        return result_dict
    except Exception as e:
        logger.error(f"Errore critico nel caricamento del CSV scuole per {codice} ({csv_filename}): {e}")
        return None

def get_scuole_dict_sec_ii_from_csv(repo, codice, csv_filename=None):
    global _SCUOLE_SEC_II_CSV_CACHE
    codice_upper = codice.upper()
    if not csv_filename:
        if codice_upper in SEC_II_MUSICAL_CLASSI:
            csv_filename = "A-55 (Strumento musicale).csv"
        else:
            csv_filename = SEC_II_CSV_FILE_MAP.get(codice_upper) or SEC_II_CSV_FILE_MAP.get(codice)
    if not csv_filename:
        return None
    if csv_filename in _SCUOLE_SEC_II_CSV_CACHE:
        return _SCUOLE_SEC_II_CSV_CACHE[csv_filename]
    file_path = f"{SEC_II_PREFIX}{csv_filename}"
    try:
        logger.info(f"[SEC II] Lettura file CSV scuole per classe {codice}: {file_path}")
        file_content = repo.get_contents(file_path)
        raw_text = file_content.decoded_content.decode('utf-8-sig', errors='ignore')
        text = clean_csv_text(raw_text)
        df = None
        for sep in [';', ',', '\t', '|']:
            try:
                csv_io = io.StringIO(text)
                df_temp = pd.read_csv(csv_io, sep=sep, dtype=str, skipinitialspace=True)
                if len(df_temp.columns) >= 2:
                    df = df_temp
                    logger.info(f"[SEC II] CSV {codice} parsato con sep '{sep}': {len(df)} righe, colonne: {list(df.columns)}")
                    break
            except Exception:
                continue
        scuole_dict = {}
        if df is not None and len(df.columns) >= 2:
            prov_col = None
            num_col = None
            for col in df.columns:
                col_upper = str(col).upper().strip()
                if any(k in col_upper for k in ['PROVINC', 'UFFICIO', 'SEDE', 'COMUNE', 'TERRITORIO', 'SIGLA']):
                    prov_col = prov_col or col
                if any(k in col_upper for k in ['NUMERO', 'SCUOLE', 'TOTALE', 'N.', 'N ', 'COUNT', 'QUANTITA']):
                    num_col = num_col or col
            if not prov_col:
                prov_col = df.columns[0]
            if not num_col:
                num_col = df.columns[1]
            logger.info(f"[SEC II] Colonna provincia: '{prov_col}', Colonna numero: '{num_col}'")
            for _, row in df.iterrows():
                prov_val = str(row[prov_col]).strip()
                num_val = str(row[num_col]).strip()
                sigla = to_sigla(prov_val)
                if sigla:
                    _, nome = PROVINCE_DATA[sigla]
                    match = re.search(r'(\d+)', num_val)
                    if match:
                        scuole_dict[nome] = int(match.group(1))
        else:
            logger.warning(f"[SEC II] Parse CSV standard fallito per {codice}, provo parser testuale.")
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                matches = re.findall(r'([a-zA-ZÀ-ÿ\'\-\.\s]+?)\s+[:\-]?\s*(\d+)', line)
                for match in matches:
                    prov_raw = match[0].strip().strip(',').strip(':')
                    num_str = match[1]
                    sigla = to_sigla(prov_raw)
                    if sigla:
                        _, nome = PROVINCE_DATA[sigla]
                        scuole_dict[nome] = int(num_str)
        if not scuole_dict:
            logger.warning(f"[SEC II] Nessun dato trovato nel CSV scuole per {codice}. Uso fallback a 0.")
            result_dict = SCUOLE_FALLBACK
        else:
            logger.info(f"[SEC II] Dizionario scuole CSV per {codice} caricato: {len(scuole_dict)} province trovate.")
            result_dict = scuole_dict
        _SCUOLE_SEC_II_CSV_CACHE[csv_filename] = result_dict
        return result_dict
    except Exception as e:
        logger.error(f"[SEC II] Errore critico nel caricamento del CSV scuole per {codice} ({csv_filename}): {e}")
        return None

def get_files_from_folders(repo, folder_paths):
    """Ottiene i file SOLO dalle cartelle richieste (2-4 chiamate API invece di centinaia)."""
    files = []
    for folder_path in folder_paths:
        folder_path = folder_path.rstrip('/')
        try:
            contents = repo.get_contents(folder_path)
            for content in contents:
                if content.type == 'file' and not content.name.startswith('~$'):
                    files.append(content)
            logger.info(f"Cartella '{folder_path}': {len([c for c in contents if c.type == 'file'])} file.")
        except UnknownObjectException:
            logger.warning(f"Cartella non trovata: {folder_path}")
        except Exception as e:
            logger.error(f"Errore accesso cartella {folder_path}: {e}")
    return files

# ====================================================================
# FUNZIONE HELPER: DOWNLOAD ROBUSTO PER GESTIRE GIT LFS (DEBUG VERSION)
# ====================================================================
# ============ CACHE GLOBALE DOWNLOAD (condivisa tra le 2 route) ============
_FILE_BYTES_CACHE = OrderedDict()          # path -> bytes
_FILE_CACHE_BYTES = 0
_FILE_CACHE_MAX = 40 * 1024 * 1024         # max 40 MB (Render 512MB: sicuro)
_FILE_CACHE_LOCK = threading.Lock()

def _cache_get(path):
    with _FILE_CACHE_LOCK:
        if path in _FILE_BYTES_CACHE:
            _FILE_BYTES_CACHE.move_to_end(path)
            return _FILE_BYTES_CACHE[path]
    return None

def _cache_put(path, data):
    global _FILE_CACHE_BYTES
    with _FILE_CACHE_LOCK:
        if path in _FILE_BYTES_CACHE:
            return
        _FILE_BYTES_CACHE[path] = data
        _FILE_CACHE_BYTES += len(data)
        while _FILE_CACHE_BYTES > _FILE_CACHE_MAX and _FILE_BYTES_CACHE:
            _, old = _FILE_BYTES_CACHE.popitem(last=False)
            _FILE_CACHE_BYTES -= len(old)
def prefetch_files_parallel(repo, file_objs, max_workers=4):
    """Scarica in parallelo i file mancanti riempiendo la cache.
    Non altera contenuti né ordine: chi legge dopo trova cache HIT,
    in caso di fallimento il download robusto sequenziale resta come fallback."""
    to_download = [f for f in file_objs if _cache_get(f.path) is None]
    if not to_download:
        logger.info("[PREFETCH] Tutti i file già in cache.")
        return

    def _fetch(f):
        try:
            url = getattr(f, 'download_url', None)
            if url:
                resp = _HTTP_SESSION.get(url, headers={"Accept": "application/vnd.github.v3.raw"}, timeout=60)
                if resp.status_code == 200 and len(resp.content) > 50:
                    _cache_put(f.path, resp.content)
                    return True
            raw_url = f"https://raw.githubusercontent.com/{repo.full_name}/{repo.default_branch}/{f.path}"
            resp = _HTTP_SESSION.get(raw_url, timeout=60)
            if resp.status_code == 200:
                _cache_put(f.path, resp.content)
                return True
        except Exception as e:
            logger.warning(f"[PREFETCH] Errore su {f.path}: {e}")
        return False

    logger.info(f"[PREFETCH] Download parallelo di {len(to_download)} file ({max_workers} worker)...")
    ok = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        for success in ex.map(_fetch, to_download):
            if success: ok += 1
    logger.info(f"[PREFETCH] Completato: {ok}/{len(to_download)} file in cache.")

def download_github_file_robust(repo, file_obj):
    cached = _cache_get(file_obj.path)
    if cached is not None:
        logger.info(f"[DOWNLOAD] Cache HIT: {file_obj.path} ({len(cached)} bytes)")
        return cached

    size = getattr(file_obj, 'size', 0) or 0
    encoding = getattr(file_obj, 'encoding', 'base64')

    # Metodo 1: SOLO se base64 e piccolo (i file LFS/none falliscono sempre: lo saltiamo)
    if encoding == 'base64' and size <= 1_500_000:
        try:
            content = repo.get_contents(file_obj.path, ref=repo.default_branch)
            raw = content.decoded_content
            if raw and not raw.startswith(b'version https://git-lfs') and len(raw) > 50:
                _cache_put(file_obj.path, raw)
                return raw
        except Exception as e:
            logger.warning(f"[DOWNLOAD] Metodo 1 fallito per {file_obj.path}: {e}")

    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    # Metodo 2: download_url
    try:
        if getattr(file_obj, 'download_url', None):
            resp = _HTTP_SESSION.get(file_obj.download_url,
                                headers={**headers, "Accept": "application/vnd.github.v3.raw"},
                                timeout=60)
            if resp.status_code == 200 and len(resp.content) > 50:
                _cache_put(file_obj.path, resp.content)
                return resp.content
    except Exception as e:
        logger.warning(f"[DOWNLOAD] Metodo 2 fallito per {file_obj.path}: {e}")

    # Metodo 3: raw.githubusercontent
    try:
        raw_url = f"https://raw.githubusercontent.com/{repo.full_name}/{repo.default_branch}/{file_obj.path}"
        resp =_HTTP_SESSION.get(raw_url, headers=headers, timeout=60)
        if resp.status_code == 200:
            _cache_put(file_obj.path, resp.content)
            return resp.content
    except Exception as e:
        logger.warning(f"[DOWNLOAD] Metodo 3 fallito per {file_obj.path}: {e}")

    logger.error(f"[DOWNLOAD] TUTTI i metodi falliti per {file_obj.path}")
    return None

# ====================================================================
# HEALTH CHECK (per warm-up Render e monitoraggio)
# ====================================================================
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "ready": g is not None}), 200

# ====================================================================
# ROUTE 1: GENERA PDF E STATISTICHE BASE
# ====================================================================
@app.route('/genera-pdf', methods=['POST', 'OPTIONS'])
def genera_pdf():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    if not g:
        return jsonify({"error": "Server non configurato correttamente (Token GitHub mancante)."}), 500
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Payload non valido."}), 400
    classi_selezionate = data.get('classi')
    province_nomi = data.get('province', [])
    regioni_richieste = data.get('regioni', [])
    fascia_richiesta = data.get('fascia', '').strip()
    anno_richiesto = data.get('anno', 'N/D').strip()
    if not isinstance(province_nomi, list) or not isinstance(regioni_richieste, list):
        return jsonify({"error": "Formato regioni/province non valido."}), 400
    if regioni_richieste and not province_nomi:
        for sigla, (region, nome) in PROVINCE_DATA.items():
            if region in regioni_richieste and nome not in province_nomi:
                province_nomi.append(nome)
    if not isinstance(classi_selezionate, list) or not classi_selezionate:
        return jsonify({"error": "Nessuna classe selezionata."}), 400
    if len(classi_selezionate) > MAX_CLASSI:
        return jsonify({"error": f"Numero massimo di classi consentito: {MAX_CLASSI}"}), 400
        
    province_sigle = []
    for prov in province_nomi:
        sigla = PROVINCE_SIGLE.get(prov)
        if sigla:
            province_sigle.append(sigla)
            
    codici_validi = []
    for codice in classi_selezionate:
        identificativo = codice.split(' - ')[0].strip()
        if not identificativo:
            return jsonify({"error": "Uno o più codici classe non sono validi."}), 400
        codici_validi.append(identificativo)

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    pdf.set_font("Helvetica", 'B', 14)
    pdf.cell(0, 10, text=sanitize_for_fpdf("Graduatorie provinciali di supplenza"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font("Helvetica", size=10)
    safe_anno = sanitize_for_fpdf(anno_richiesto.upper() if anno_richiesto != 'N/D' else 'N/D')
    pdf.cell(0, 10, text=f"Anno: {safe_anno}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    safe_regioni = sanitize_for_fpdf(", ".join(regioni_richieste).upper() if regioni_richieste else 'TUTTE')
    safe_province = sanitize_for_fpdf(", ".join(province_nomi).upper() if province_nomi else 'TUTTE')
    filtro_luogo = f"Regioni: {safe_regioni} | Province: {safe_province}"
    pdf.cell(0, 10, text=filtro_luogo, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(5)
    
    trovato_almeno_uno = False
    stats_data = {}
    province_scores = {}
    # --- Limite province per evitare OOM su Render (512MB) ---
    MAX_PROVINCE_PER_REQUEST = 50
    if len(province_nomi) > MAX_PROVINCE_PER_REQUEST:
        return jsonify({"error": f"Troppe province ({len(province_nomi)}). Massimo {MAX_PROVINCE_PER_REQUEST} per richiesta."}), 400

    # --- Fascia: calcolata UNA VOLTA, vale per tutti i codici ---
    fascia_upper = (fascia_richiesta or "").upper().strip()
    is_i_fascia_selected = (fascia_upper in ("I_FASCIA", "1_FASCIA", "IFASCIA"))
    is_ii_fascia_selected = (fascia_upper in ("II_FASCIA", "2_FASCIA", "IIFASCIA"))

    # --- Pre-calcola ordine_classe per ogni codice per sapere quali cartelle servono ---
    ordine_to_prefix = {
        "infanzia":      ("Estrazione_AA_1_Fascia/", "Estrazione_AA_2_Fascia/"),
        "primaria":      ("Estrazione_EE_1_Fascia/", "Estrazione_EE_2_Fascia/"),
        "secondaria_i":  ("Estrazione_MM_1_Fascia/", "Estrazione_MM_2_Fascia/"),
        "secondaria_ii": ("Estrazione_SS_1_Fascia/", "Estrazione_SS_2_Fascia/"),
    }

    needed_folders = set()
    codici_precomputed = []  # lista di (codice_raw, ordine_classe)
    for cr in codici_validi:
        if '|' in cr:
            oc, cod = cr.split('|', 1)
            oc = oc.strip().lower()
        else:
            oc, cod = None, cr
        codici_precomputed.append((cr, oc, cod))
        prefixes = ordine_to_prefix.get(oc)
        if not prefixes:
            continue
        f1p, f2p = prefixes
        if is_i_fascia_selected:
            needed_folders.add(f1p)
        elif is_ii_fascia_selected:
            needed_folders.add(f2p)
        else:
            needed_folders.add(f1p)
            needed_folders.add(f2p)

    # --- Scarica SOLO le cartelle necessarie (2-4 chiamate API max) ---
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = get_files_from_folders(repo, list(needed_folders))
        logger.info(f"Scaricati {len(root_files)} file da {len(needed_folders)} cartelle.")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    dizionario_scuole_altro = SCUOLE_FALLBACK

    logger.info(f"Regioni richieste: {regioni_richieste}")
    logger.info(f"Province nomi ricevuti: {province_nomi}")
    
    province_sigle = []
    for prov in province_nomi:
        sigla = PROVINCE_SIGLE.get(prov)
        if sigla:
            province_sigle.append(sigla)
        else:
            logger.warning(f"Provincia '{prov}' NON trovata in PROVINCE_SIGLE!")
    
    logger.info(f"Province sigle finali: {province_sigle}")

    for codice_raw, ordine_classe, codice in codici_precomputed:

        codice_upper = codice.upper()
        fascia_norm = normalize_string(fascia_richiesta) if fascia_richiesta else ""

        is_sec_ii = (ordine_classe == "secondaria_ii")

        # --- Alias UNIVOCI per grado (fonte unica: CLASSI_REGISTRY) ---
        ordine_key = ("secondaria_ii" if is_sec_ii else (ordine_classe or "")).lower()
        codice_canonico, entry = get_registry_entry(ordine_key, codice_upper)
        codici_ricerca = {c.upper() for c in entry["alias"]}
        codici_ricerca |= {c.upper() for c in entry.get("extra_estrazione", set())}
        if not codici_ricerca:
            codici_ricerca = {codice_upper}
        if is_sec_ii and '-' in codice_upper:
            codici_ricerca.add(codice_upper.replace('-', ''))
        
        logger.info(f"[{codice_upper}] Codici ricerca: {codici_ricerca} | Ordine: {ordine_classe}")

        scuole_spec = entry.get("scuole")
        if is_sec_ii:
            csv_scuole = get_scuole_dict_sec_ii_from_csv(repo, codice_upper, csv_filename=scuole_spec)
            scuole_dict = csv_scuole if csv_scuole is not None else dizionario_scuole_altro
        elif scuole_spec == "MUSICALI":
            scuole_dict = get_scuole_dict(repo, is_musical=True)
        elif scuole_spec == "TOTALI_MM":
            scuole_dict = get_scuole_dict(repo, is_musical=False)
        elif scuole_spec:
            csv_scuole = get_scuole_dict_from_csv(repo, codice_upper, csv_filename=scuole_spec)
            scuole_dict = csv_scuole if csv_scuole is not None else dizionario_scuole_altro
        else:
            scuole_dict = dizionario_scuole_altro
        is_sec_i_codice = (not is_sec_ii and (
                           codice_upper in SEC_I_CLASSI or
                           codice_upper in SEC_I_MUSICAL_CLASSI or
                           codice_upper in SEC_I_CSV_FILE_MAP or
                           codice_upper == "ADMM"))

        prefixes = ordine_to_prefix.get(ordine_classe, ("", ""))
        f1_prefix, f2_prefix = prefixes
        
        if is_i_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(f1_prefix)]
        elif is_ii_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(f2_prefix)]
        elif not fascia_richiesta:
            files_to_search = [f for f in root_files if f.path.startswith(f1_prefix) or f.path.startswith(f2_prefix)]
        else:
            files_to_search = [f for f in root_files if not f.path.startswith(f1_prefix) and not f.path.startswith(f2_prefix)]

        file_da_elaborare = []
        nomi_file_visti = set()
        for cod_ric in codici_ricerca:
            # Rendiamo il confronto case-insensitive e ignoriamo gli spazi nel nome file
            target_prefix = f"RISULTATO_ESTRAZIONE_{cod_ric}_".upper().replace(" ", "")
            target_exact = f"RISULTATO_ESTRAZIONE_{cod_ric}.CSV".upper().replace(" ", "")
            
            for f in files_to_search:
                if hasattr(f, 'type') and f.type != 'file': continue
                if f.name.startswith('~$'): continue
                
                # Puliamo il nome del file da spazi per un match robusto
                fname_clean = f.name.upper().replace(" ", "")
                
                match_found = (fname_clean.startswith(target_prefix) or fname_clean == target_exact) and fname_clean.endswith('.CSV')
                
                if match_found:
                    if f.name not in nomi_file_visti:
                        file_da_elaborare.append(f)
                        nomi_file_visti.add(f.name)
                    break # Trovato il file per questo codice, passa al prossimo codice

        if not file_da_elaborare:
            logger.warning(f"Nessun file trovato per il codice: {codice}")
            continue
                # I file di questa classe servono subito: prefetch parallelo (cache HIT nel loop sotto)
        prefetch_files_parallel(repo, file_da_elaborare)

        pdf.set_font("Helvetica", 'B', 12)
        display_classe = f"Classe di Concorso: {entry.get('label', codice)}"
        pdf.cell(0, 10, text=sanitize_for_fpdf(display_classe), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        try:
            lista_dati = []
            for file_trovato in file_da_elaborare:
                try:
                    file_data = download_github_file_robust(repo, file_trovato)
                    if file_data is None:
                        logger.error(f"[PDF] Impossibile scaricare il file {file_trovato.name}")
                        continue
                        
                    csv_text = file_data.decode('utf-8-sig', errors='ignore')
                    csv_text = clean_csv_text(csv_text)
                    
                    if csv_text.strip().startswith("404") or len(csv_text) < 50:
                        logger.error(f"[PDF] Contenuto invalido per {file_trovato.name}: '{csv_text[:50]}'")
                        continue
                        
                    # OTTIMIZZAZIONE RAM: Salviamo solo il testo, non il DataFrame!
                    fascia_nome = "DETTAGLI"
                    for cod_ric in codici_ricerca:
                        if cod_ric in file_trovato.name:
                            parti = file_trovato.name.split(cod_ric)
                            if len(parti) > 1:
                                fascia_nome = parti[-1].replace("_", " ").replace(".csv", "").strip().upper()
                                break
                    if not fascia_nome: fascia_nome = "DETTAGLI"
                    lista_dati.append((csv_text, fascia_nome))
                except Exception as e:
                    logger.error(f"Errore lettura file {file_trovato.name}: {str(e)}")
            if not lista_dati: continue

            def get_fascia_order(fascia_str):
                f = str(fascia_str).upper()
                if 'I FASCIA' in f or '1 FASCIA' in f: return 0
                if 'II FASCIA' in f or '2 FASCIA' in f: return 1
                if 'III FASCIA' in f or '3 FASCIA' in f: return 2
                return 3
            lista_dati.sort(key=lambda x: get_fascia_order(x[1]))

            for csv_text, nome_fascia in lista_dati:
                # OTTIMIZZAZIONE RAM: Leggiamo il DataFrame adesso e lo eliminiamo a fine ciclo
                try:
                    csv_io = io.StringIO(csv_text)
                    colonne_da_escludere = ['CODICE FISCALE', 'SESSO', 'DATA NASCITA', 'COMUNE NASCITA', 'PROVINCIA NASCITA', 'INDIRIZZO', 
                                            'CODICE TIPOLOGIA LINGUA GRADUATORIA DI INCLUSIONE', 'INCLUSIONE CON RISERVA', 
                                            'NOME', 'ORIGINE', 'INDICATORE DI PREFERENZE']
                    df = pd.read_csv(csv_io, sep=';', dtype=str, skipinitialspace=True, 
                                          usecols=lambda c: c.strip().upper() not in colonne_da_escludere)
                except Exception as e:
                    logger.error(f"ERRORE LETTURA CSV per {file_trovato.name}: {e}", exc_info=True)
                    continue

                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
                df.rename(columns={'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE': 'CODICE GRADUATORIA', 'ORDINE SCUOLA GRADUATORIA': 'ORDINE SCUOLA'}, inplace=True, errors='ignore')
                col_classe = None
                for col in df.columns:
                    col_upper = str(col).strip().upper()
                    if col_upper in {'CODICE GRADUATORIA', 'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE', 'CLASSE DI CONCORSO'}:
                        col_classe = col
                        break
                if col_classe and not df.empty:
                    def contiene_classe_esatta(valore, codici_target):
                        if pd.isna(valore): return False
                        testo = str(valore).upper().strip()
                        # Normalizziamo testo e target rimuovendo spazi e trattini per un confronto sicuro
                        testo_norm = re.sub(r'[\s_-]+', '', testo)
                        
                        for codice in codici_target:
                            codice_norm = re.sub(r'[\s_-]+', '', str(codice).upper())
                            if not codice_norm: continue
                            # Verifica se il codice normalizzato è presente come parola intera nel testo
                            if re.search(r'(?<![A-Z0-9])' + re.escape(codice_norm) + r'(?![A-Z0-9])', testo_norm):
                                return True
                        return False
                    prima = len(df)
                    df = df[df[col_classe].apply(lambda x: contiene_classe_esatta(x, codici_ricerca))].copy()
                    dopo = len(df)
                    logger.info(f"[{codice_upper}] FILTRO CLASSE: {prima} -> {dopo}")

                col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                col_cognome = next((col for col in df.columns if 'COGNOME' in str(col).upper()), None)
                
                if col_ufficio:
                    df['_sigla_prov'] = df[col_ufficio].apply(to_sigla)
                    df = df.dropna(subset=['_sigla_prov'])
                    if province_sigle: df = df[df['_sigla_prov'].isin(province_sigle)]
                    df[col_ufficio] = df['_sigla_prov']
                    df = df.drop(columns=['_sigla_prov'])
                else:
                    df = pd.DataFrame()
                if col_cognome and not df.empty:
                    df = df[~df[col_cognome].astype(str).str.strip().isin(['*', '', 'nan', 'None'])]
                    df = df.dropna(subset=[col_cognome])
                if df.empty: continue

                useless_cols = ['CODICE TIPOLOGIA LINGUA GRADUATORIA DI INCLUSIONE', 'INCLUSIONE CON RISERVA', 'COGNOME', 'NOME', 'ORIGINE', 'INDICATORE DI PREFERENZE']
                df.columns = df.columns.astype(str).str.strip()
                df = df.drop(columns=[c for c in useless_cols if c in df.columns], errors='ignore')
                col_punteggio_sep = None
                for col in df.columns:
                    col_upper = str(col).upper().strip()
                    if col_upper == 'PUNTEGGIO TOTALE':
                        col_punteggio_sep = col
                        break
                if not col_punteggio_sep:
                    col_punteggio_sep = next((col for col in df.columns if 'PUNTEGGIO' in str(col).upper() or 'TOTALE' in str(col).upper() or 'VOTO' in str(col).upper()), None)

                if col_ufficio:
                    counts = df[col_ufficio].value_counts()
                    for sigla, count in counts.items():
                        sigla_str = str(sigla).upper()
                        region_name, nome_esteso = PROVINCE_DATA.get(sigla_str, ("", sigla_str))
                        num_scuole = scuole_dict.get(nome_esteso, 0)
                        num_candidati = int(count)
                        rapporto = round(num_scuole / num_candidati, 4) if num_candidati > 0 else 0
                        top_candidate = "N/D"
                        bottom_candidate = "N/D"
                        median_score = 0.0
                        if col_punteggio_sep:
                            prov_df = df[df[col_ufficio] == sigla_str].copy()
                            prov_df['punteggio_num'] = prov_df[col_punteggio_sep].apply(pulisci_punteggio)
                            prov_df = prov_df.dropna(subset=['punteggio_num'])
                            if not prov_df.empty:
                                if codice_upper not in province_scores: province_scores[codice_upper] = {}
                                if nome_esteso not in province_scores[codice_upper]: province_scores[codice_upper][nome_esteso] = []
                                province_scores[codice_upper][nome_esteso].extend(prov_df['punteggio_num'].tolist())
                                idx_max = prov_df['punteggio_num'].idxmax()
                                idx_min = prov_df['punteggio_num'].idxmin()
                                max_score = float(prov_df.loc[idx_max, 'punteggio_num'])
                                min_score = float(prov_df.loc[idx_min, 'punteggio_num'])
                                median_score = float(prov_df['punteggio_num'].median())
                                top_candidate = str(max_score).replace('.', ',')
                                bottom_candidate = str(min_score).replace('.', ',')
                                if top_candidate.endswith(',0'): top_candidate = top_candidate.replace(',0', '')
                                if bottom_candidate.endswith(',0'): bottom_candidate = bottom_candidate.replace(',0', '')
                        
                        if codice_upper not in stats_data: stats_data[codice_upper] = {}
                        if nome_esteso not in stats_data[codice_upper]:
                            stats_data[codice_upper][nome_esteso] = {"scuole": num_scuole, "candidati": num_candidati, "rapporto": rapporto, "regione": region_name, "top": top_candidate, "bottom": bottom_candidate, "median": median_score}
                        else:
                            stats_data[codice_upper][nome_esteso]["candidati"] += num_candidati
                            stats_data[codice_upper][nome_esteso]["rapporto"] = round(stats_data[codice_upper][nome_esteso]["scuole"] / stats_data[codice_upper][nome_esteso]["candidati"], 4)
                            if top_candidate != "N/D":
                                existing_top = parse_score(stats_data[codice_upper][nome_esteso]["top"])
                                new_top = parse_score(top_candidate)
                                if existing_top is None or (new_top is not None and new_top > existing_top): stats_data[codice_upper][nome_esteso]["top"] = top_candidate
                            if bottom_candidate != "N/D":
                                existing_bottom = parse_score(stats_data[codice_upper][nome_esteso]["bottom"])
                                new_bottom = parse_score(bottom_candidate)
                                if existing_bottom is None or (new_bottom is not None and new_bottom < existing_bottom): stats_data[codice_upper][nome_esteso]["bottom"] = bottom_candidate

                pdf.set_font("Helvetica", 'B', 12)
                pdf.cell(0, 10, text=sanitize_for_fpdf(nome_fascia), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
                pdf.ln(2)
                if len(df) > MAX_ROWS_PDF:
                    df = df.head(MAX_ROWS_PDF)
                    pdf.set_font("Helvetica", 'I', 8)
                    pdf.cell(0, 6, text=sanitize_for_fpdf(f"Avviso: Mostrati solo i primi {MAX_ROWS_PDF} record."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

                def is_empty(val):
                    v = str(val).strip().lower()
                    return v in ['nan', '*', 'none', '', '-']
                cols_to_drop = []
                keep_cols = ['CODICE GRADUATORIA', 'FASCIA', 'ORDINE SCUOLA']
                for col in df.columns:
                    unique_vals = [val for val in df[col].unique() if not is_empty(val)]
                    col_upper = str(col).upper()
                    is_ufficio_col = 'UFFICIO' in col_upper or 'PROVINCIA' in col_upper
                    is_keep_col = col_upper in [c.upper() for c in keep_cols]
                    if len(unique_vals) <= 1 and not is_ufficio_col and not is_keep_col: cols_to_drop.append(col)
                    if 'pdf' in str(col).lower() or 'csv' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower() or 'origine' in str(col).lower(): cols_to_drop.append(col)
                df = df.drop(columns=cols_to_drop, errors='ignore')

                def format_val(val):
                    s = str(val).strip()
                    if s.lower() in ['nan', 'none', ''] or s == '*': return "-"
                    if s.endswith('.0'):
                        try:
                            f = float(s)
                            if f.is_integer(): return str(int(f))
                        except ValueError: pass
                    return s

                col_widths = {}
                total_width = 0
                for col in df.columns:
                    words = str(col).split()
                    longest_word = max(len(w) for w in words) if words else 1
                    min_width_header = max(longest_word * 2.2, 15)
                    max_len_content = len(str(col))
                    for val in df[col].head(100):
                        val_str = format_val(val)
                        if len(val_str) > max_len_content: max_len_content = len(val_str)
                    width = min(max_len_content * 2.2, 50)
                    width = max(width, min_width_header)
                    if str(col).upper() in ['UFFICIO PROVINCIALE', 'UFFICIO', 'PROVINCIA']: width = max(width, 25)
                    if str(col).upper() in ['COGNOME', 'NOME']: width = max(width, 35)
                    if 'TOTALE' in str(col).upper() or 'PUNTEGGIO' in str(col).upper(): width = max(width, 25)
                    if 'POSIZIONE' in str(col).upper(): width = max(width, 20)
                    col_widths[col] = width
                    total_width += width
                page_width = 277
                if total_width > 0:
                    scale = page_width / total_width
                    for col in col_widths: col_widths[col] *= scale
                    total_width_scaled = sum(col_widths.values())
                else:
                    total_width_scaled = 0
                pdf.set_font("Helvetica", 'B', 9)
                line_height = 5
                max_lines = 2
                max_header_height = max_lines * line_height
                header_texts = {}
                for col in df.columns:
                    char_limit = max(1, int(col_widths[col] / 2.0))
                    words = str(col).split()
                    lines = []
                    current_line = ""
                    for word in words:
                        if len(current_line) + len(word) + 1 <= char_limit:
                            current_line = (current_line + " " + word).strip()
                        else:
                            lines.append(current_line)
                            current_line = word
                    if current_line: lines.append(current_line)
                    if not lines: lines = [""]
                    if len(lines) > 2: lines = [lines[0], " ".join(lines[1:])]
                    while len(lines) < 2: lines.append("")
                    header_texts[col] = "\n".join(lines)

                def draw_table_header(add_spacer=False):
                    y_start = pdf.get_y()
                    for col in df.columns:
                        x_start = pdf.get_x()
                        text = header_texts[col]
                        pdf.multi_cell(col_widths[col], line_height, text, border=1, align='L')
                        pdf.set_xy(x_start + col_widths[col], y_start)
                    pdf.set_y(y_start + max_header_height)
                    if add_spacer:
                        pdf.cell(total_width_scaled, line_height, text="", border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

                draw_table_header(add_spacer=False)
                current_prov_sigla = None
                current_region = None
                prov_full_name = None
                pdf.set_font("Helvetica", size=9)
                row_height = 7
                
                # OTTIMIZZAZIONE ESTREMA CICLO PDF
                col_char_lims = {}
                for col in df.columns:
                    col_char_lims[col] = max(1, int(col_widths[col] / 2.0))

                for _, row in df.iterrows():
                    prov_changed = False
                    reg_changed = False
                    if col_ufficio:
                        prov_sigla = format_val(row[col_ufficio]).upper()
                        if prov_sigla != current_prov_sigla:
                            prov_changed = True
                            current_prov_sigla = prov_sigla
                            region_name, prov_full_name = PROVINCE_DATA.get(prov_sigla, ("", prov_sigla))
                            if region_name and region_name != current_region:
                                reg_changed = True
                                current_region = region_name
                    if prov_changed:
                        spazio_necessario = 20
                        if reg_changed: spazio_necessario += 10
                        if pdf.get_y() + spazio_necessario + row_height > 190:
                            pdf.add_page()
                            draw_table_header(add_spacer=True)
                            pdf.set_font("Helvetica", size=9)
                        else:
                            pdf.ln(4)
                        if reg_changed and region_name:
                            pdf.set_font("Helvetica", 'B', 12)
                            pdf.cell(0, 7, text=sanitize_for_fpdf(region_name.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
                        if prov_full_name:
                            pdf.set_font("Helvetica", 'B', 10)
                            pdf.cell(0, 6, text=sanitize_for_fpdf(prov_full_name.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
                            pdf.ln(2)
                        pdf.set_font("Helvetica", size=9)
                    if pdf.get_y() + row_height > 190:
                        pdf.add_page()
                        draw_table_header(add_spacer=True)
                        pdf.set_font("Helvetica", size=9)
                    for col in df.columns:
                        valore = sanitize_for_fpdf(format_val(row[col]))
                        char_lim = col_char_lims[col]
                        if len(valore) > char_lim:
                            valore = valore[:char_lim-3] + "..."
                        align = 'L'
                        pdf.cell(col_widths[col], row_height, valore, border=1, align=align)
                    pdf.ln(row_height)
            
            # --- PULIZIA MEMORIA (ANTI-CRASH) ---
            del df
            del csv_text
            gc.collect()
            # ------------------------------------
            
            pdf.ln(8)
            trovato_almeno_uno = True
        except Exception as e:
            logger.error(f"Errore elaborazione file: {str(e)}", exc_info=True)
            pdf.set_font("Helvetica", 'I', 10)
            pdf.cell(0, 10, text=sanitize_for_fpdf(f"Errore interno durante l'elaborazione della classe {codice}."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)

    import statistics
    for codice, provs in province_scores.items():
        for prov, scores in provs.items():
            if prov in stats_data.get(codice, {}) and scores:
                try:
                    stats_data[codice][prov]["median"] = float(statistics.median(scores))
                except statistics.StatisticsError:
                    pass
            elif prov in stats_data.get(codice, {}):
                stats_data[codice][prov]["median"] = 0.0

    if not trovato_almeno_uno:
        pdf.cell(0, 10, text="Nessun dato disponibile per i filtri selezionati.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    
    import base64
    pdf_base64 = base64.b64encode(pdf.output()).decode('utf-8')
    logger.info(f"Generazione PDF completata. Stats inviate per {len(stats_data)} classi.")
    return jsonify({"pdf_base64": pdf_base64, "stats": stats_data})


# ====================================================================
# ROUTE 2: GENERA BOLLETTINO E METRICHE AVANZATE (RAGGRUPPATO PER CLASSE)
# ====================================================================
@app.route('/genera-bollettino', methods=['POST', 'OPTIONS'])
def genera_bollettino():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200
    if not g:
        return jsonify({"error": "Server non configurato correttamente (Token GitHub mancante)."}), 500
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Payload non valido."}), 400
        
    classi_selezionate = data.get('classi', [])
    province_nomi = data.get('province', [])
    regioni_richieste = data.get('regioni', [])
    fascia_richiesta = data.get('fascia', '').strip()

    if regioni_richieste and not province_nomi:
        for sigla, (region, nome) in PROVINCE_DATA.items():
            if region in regioni_richieste and nome not in province_nomi:
                province_nomi.append(nome)
                
    prov_set = {p.upper().replace(" ", "").replace("'", "").replace("-", "") for p in province_nomi}
    reg_set = {r.upper() for r in regioni_richieste}
    
    if fascia_richiesta.upper() == 'II_FASCIA': fascia_filter = 'F2'
    elif fascia_richiesta.upper() == 'I_FASCIA': fascia_filter = 'F1'
    else: fascia_filter = ''

    codici_validi = []          # lista di (ordine, codice)
    ordini_selezionati = set()
    for c in classi_selezionate:
        if '|' in c:
            ord, c_clean = c.split('|', 1)
            ord = ord.strip().lower()
            ordini_selezionati.add(ord)
        else:
            ord, c_clean = None, c
        codici_validi.append((ord, c_clean.split(' - ')[0].strip().upper()))
    prefixes = []
    if "infanzia" in ordini_selezionati: prefixes.append("Bollettini/AA/")
    if "primaria" in ordini_selezionati: prefixes.append("Bollettini/EE/")
    if "secondaria_i" in ordini_selezionati: prefixes.append("Bollettini/MM/")
    if "secondaria_ii" in ordini_selezionati: prefixes.append("Bollettini/SS/")

    grad_prefixes = []
    if "infanzia" in ordini_selezionati:
        if fascia_filter in ('', 'F1'): grad_prefixes.append("Estrazione_AA_1_Fascia/")
        if fascia_filter in ('', 'F2'): grad_prefixes.append("Estrazione_AA_2_Fascia/")
    if "primaria" in ordini_selezionati:
        if fascia_filter in ('', 'F1'): grad_prefixes.append("Estrazione_EE_1_Fascia/")
        if fascia_filter in ('', 'F2'): grad_prefixes.append("Estrazione_EE_2_Fascia/")
    if "secondaria_i" in ordini_selezionati:
        if fascia_filter in ('', 'F1'): grad_prefixes.append("Estrazione_MM_1_Fascia/")
        if fascia_filter in ('', 'F2'): grad_prefixes.append("Estrazione_MM_2_Fascia/")
    if "secondaria_ii" in ordini_selezionati:
        if fascia_filter in ('', 'F1'): grad_prefixes.append("Estrazione_SS_1_Fascia/")
        if fascia_filter in ('', 'F2'): grad_prefixes.append("Estrazione_SS_2_Fascia/")

    try:
        repo = g.get_repo(REPO_NAME)
        # FIX: get_all_repo_files non esisteva. SOLO le cartelle necessarie, solo metadati.
        root_files = get_files_from_folders(repo, list(set(prefixes + grad_prefixes)))
        logger.info(f"[BOLLETTINO] Scaricati {len(root_files)} metadati da {len(set(prefixes + grad_prefixes))} cartelle.")

        def codice_da_nome(nome_file):
            # "Risultato_Estrazione_<COD>_I_Fascia.csv" oppure "Risultato_Estrazione_<COD>.csv"
            base = nome_file.rsplit('.', 1)[0]
            parti = base.split('_')
            return parti[2].strip().upper() if len(parti) >= 3 else None
                # Indicizzazione UNA volta sola: codice -> file (evita riscansioni per ogni classe)
        def build_file_index(files, prefixes_list):
            idx = {}
            for f in files:
                if any(f.path.startswith(p) for p in prefixes_list) and f.name.lower().endswith('.csv'):
                    cf = codice_da_nome(f.name)
                    if cf:
                        idx.setdefault(cf, []).append(f)
            return idx
        bollettino_index = build_file_index(root_files, prefixes)
        grad_index = build_file_index(root_files, grad_prefixes)

        # 1. INDIVIDUA FILE BOLLETTINO (alias dal REGISTRO, per grado, match esatto)
        bollettino_files = []
        for ord_cls, codice in codici_validi:
            _, entry = get_registry_entry(ord_cls, codice)
            possible = {c.upper() for c in entry["alias"]} | {codice}
            trovati = list(dict.fromkeys(
                f for pc in possible for f in bollettino_index.get(pc, [])
            ))
            for f in trovati:
                bollettino_files.append({"codice": codice, "file": f})
                logger.info(f"[BOLLETTINO] {codice}: trovato {f.name}")
            if not trovati:
                logger.warning(f"[BOLLETTINO] Nessun file bollettino per {codice} (alias: {sorted(possible)}). Classe saltata.")

        if not bollettino_files:
            logger.error("[BOLLETTINO] Nessun file bollettino trovato per le classi selezionate.")
            return jsonify({"error": "Nessun file bollettino trovato per le classi selezionate."}), 404

        # 2. INDIVIDUA FILE GRADUATORIE (alias dal REGISTRO, per grado, match esatto)
        grad_files_per_classe = {}
        for ord_cls, codice in codici_validi:
            _, entry = get_registry_entry(ord_cls, codice)
            possible = {c.upper() for c in entry["alias"]} | {codice}
            for pc in possible:
                for f in grad_index.get(pc, []):
                    grad_files_per_classe.setdefault(codice, set()).add(f)
                    logger.info(f"[BOLLETTINO] {codice}: graduatoria {f.name}")

        # 3. CONTA CANDIDATI TOTALI PER PROVINCIA (KEYED BY CLASSE - nessun fallback errato)
        total_candidates = {}
        logger.info(f"[COUNT DEBUG] Classi con file graduatorie: {list(grad_files_per_classe.keys())}")

        for classe_key, files_classe in grad_files_per_classe.items():
            # Dedup tra varianti stesso-contenuto (es. A023 + AM2C): 1 posizione = 1 candidato
            posizioni_viste = set()
            prefetch_files_parallel(repo, files_classe)
            for file_obj in sorted(files_classe, key=lambda x: x.name):
                logger.info(f"--- [COUNT DEBUG] Inizio lettura file: {file_obj.name} (classe {classe_key}) ---")
                try:
                    file_data = download_github_file_robust(repo, file_obj)
                    if file_data is None:
                        logger.error(f"[BOLLETTINO] Impossibile scaricare graduatoria {file_obj.path}")
                        continue

                    csv_text = file_data.decode('utf-8-sig', errors='ignore')
                    csv_text = clean_csv_text(csv_text)

                    if csv_text.strip().startswith("404") or len(csv_text) < 50:
                        logger.error(f"[BOLLETTINO] [COUNT DEBUG] Contenuto invalido per {file_obj.name}: '{csv_text[:100]}'")
                        if "version https://git-lfs" in csv_text:
                            logger.error(f"[BOLLETTINO] [COUNT DEBUG] ATTENZIONE: file Git LFS Pointer non scaricato!")
                        continue

                    try:
                        df_grad = pd.read_csv(io.StringIO(csv_text), sep=';', dtype=str, skipinitialspace=True,
                                              usecols=lambda c: c.strip().upper() in ['UFFICIO PROVINCIALE', 'COGNOME', 'POSIZIONE', 'POSIZIONE GRADUATORIA'])
                        # Rinomina la colonna se ha il nome lungo, per uniformarla
                        if 'POSIZIONE GRADUATORIA' in df_grad.columns:
                            df_grad.rename(columns={'POSIZIONE GRADUATORIA': 'POSIZIONE'}, inplace=True)
                    except Exception as e_parse:
                        logger.error(f"[BOLLETTINO] [COUNT DEBUG] Errore parsing pandas per {file_obj.name}: {e_parse}")
                        continue

                    df_grad.columns = [str(c).strip().upper() for c in df_grad.columns]

                    if 'UFFICIO PROVINCIALE' in df_grad.columns:
                        df_grad['UFFICIO PROVINCIALE'] = df_grad['UFFICIO PROVINCIALE'].replace('', pd.NA).ffill().fillna('')

                    if 'UFFICIO PROVINCIALE' not in df_grad.columns or 'COGNOME' not in df_grad.columns:
                        logger.warning(f"[BOLLETTINO] [COUNT DEBUG] Colonne obbligatorie mancanti in {file_obj.name}. File saltato.")
                        continue

                    has_posizione = 'POSIZIONE' in df_grad.columns
                    if not has_posizione:
                        logger.warning(f"[BOLLETTINO] [COUNT DEBUG] Colonna POSIZIONE assente in {file_obj.name}: dedup non attiva su questo file.")

                    rows_counted_total = 0
                    rows_counted_roma = 0

                    # --- CONTEGGIO VETTORIALE (al posto di iterrows) ---
                    uff = df_grad['UFFICIO PROVINCIALE'].fillna('').astype(str).str.strip()
                    cog = df_grad['COGNOME'].fillna('').astype(str).str.strip()
                    mask = (~uff.str.upper().isin(['', 'NAN', 'NONE'])) & \
                           (~cog.str.upper().isin(['', 'NAN', 'NONE', '*', 'COGNOME', 'NOMINATI', 'UFFICIO PROVINCIALE', 'CLASSE DI CONCORSO']))

                    cols_needed = ['UFFICIO PROVINCIALE'] + (['POSIZIONE'] if has_posizione else [])
                    sub = df_grad.loc[mask, cols_needed].copy()
                    sub['_sigla'] = sub['UFFICIO PROVINCIALE'].map(to_sigla)

                    # DEBUG province non riconosciute (vedi punto 6 - tenere finché caso Roma non risolto)
                    if sub['_sigla'].isna().any():
                        strani = sub.loc[sub['_sigla'].isna(), 'UFFICIO PROVINCIALE'].unique()[:10]
                        logger.warning(f"[COUNT DEBUG] Valori UFFICIO non riconosciuti in {file_obj.name}: {list(strani)}")

                    sub = sub.dropna(subset=['_sigla'])
                    sub['_nome'] = sub['_sigla'].map(lambda s: PROVINCE_DATA[s][1])

                    if has_posizione:
                        # FIX: fillna('') prima di astype(str) per evitare che NaN rimanga float
                        pos_arr = sub['POSIZIONE'].fillna('').astype(str).str.strip().to_numpy()
                        nomi_arr = sub['_nome'].to_numpy()
                        keep = []
                        for nome_v, pos_v in zip(nomi_arr, pos_arr):
                            # FIX: str(pos_v) per gestire eventuali float residui
                            pos_str = str(pos_v).strip().upper()
                            if pos_str in ('', 'NAN', 'NONE', '*', 'NAN.0'):
                                keep.append(True); continue
                            firma = (nome_v, pos_str)
                            if firma in posizioni_viste:
                                keep.append(False)
                            else:
                                posizioni_viste.add(firma); keep.append(True)
                        sub = sub.loc[keep]

                    vc = sub['_nome'].value_counts()
                    for nome_v, n_v in vc.items():
                        total_candidates[(classe_key, nome_v)] = total_candidates.get((classe_key, nome_v), 0) + int(n_v)
                    rows_counted_total = int(vc.sum())
                    rows_counted_roma = int(vc.get('Roma', 0))

                    logger.info(f"[COUNT DEBUG] File {file_obj.name} processato. Righe valide totali conteggiate: {rows_counted_total}. Di cui Roma: {rows_counted_roma}")
                    logger.info(f"--- [COUNT DEBUG] Fine lettura file: {file_obj.name} ---\n")

                    # --- PULIZIA MEMORIA: del immediato (refcount), gc rinviato a fine classe ---
                    del df_grad
                    del csv_text

                except Exception as e:
                    logger.error(f"[BOLLETTINO] Errore lettura graduatoria {file_obj.path}: {e}")
                    continue

            del posizioni_viste
            gc.collect()   # UNA raccolta per classe invece che per file (su 0.1 CPU ogni collect costa 100-300ms)

        logger.info(f"[COUNT DEBUG] Riepilogo finale total_candidates: {total_candidates}")
        logger.info(f"[BOLLETTINO] DEBUG: Totale candidati letti da graduatorie: {len(total_candidates)} province.")
                # Prefetch parallelo di tutti i bollettini (usati tra poco nella sezione 4)
        prefetch_files_parallel(repo, [b["file"] for b in bollettino_files])

        # 4. ELABORA BOLLETTINO RAGGRUPPANDO PER CLASSE
        results = {}
        for b_entry in bollettino_files:
            codice = b_entry["codice"]
            file_obj = b_entry["file"]
            try:
                file_data = download_github_file_robust(repo, file_obj)
                if file_data is None:
                    logger.error(f"[BOLLETTINO] Download fallito per {file_obj.name}, salto classe {codice}")
                    continue
                
                csv_text = file_data.decode('utf-8-sig', errors='ignore')
                csv_text = clean_csv_text(csv_text)
                
                if csv_text.strip().startswith("404") or len(csv_text) < 50:
                    logger.error(f"[BOLLETTINO] File {file_obj.name} contiene errore HTTP invece del CSV.")
                    continue
                
                logger.info(f"[BOLLETTINO] DEBUG: Lettura file {file_obj.name}. Dimensioni testo: {len(csv_text)} caratteri.")
                
                # OTTIMIZZAZIONE RAM: Carichiamo solo le colonne strettamente necessarie per le nomine
                colonne_bollettino = ['UFFICIO PROVINCIALE', 'CLASSE DI CONCORSO', 'CODICE SCUOLA', 'FASCIA', 'POSIZIONE', 'COGNOME ASPIRANTE', 'NOME ASPIRANTE', 'PUNTEGGIO', 'TIPO CONTRATTO']
                df = pd.read_csv(io.StringIO(csv_text), sep=';', dtype=str, skipinitialspace=True, 
                                usecols=lambda c: c.strip().upper() in colonne_bollettino)
                logger.info(f"[BOLLETTINO] Elaborazione bollettino per {codice}. Righe totali lette: {len(df)}")
            except Exception as e:
                logger.error(f"[BOLLETTINO] Errore lettura bollettino {file_obj.path}: {e}")
                continue

            df.columns = [str(c).strip().upper() for c in df.columns]
            
            current_prov = None
            current_region = None
            current_prov_selected = False
            
            if codice not in results: results[codice] = {}
            
            debug_mismatch_global = 0

            anomalie_count = 0


            for _, row in df.iterrows():
                val_prov_raw = str(row.get('UFFICIO PROVINCIALE', '')).strip()
                val_classe = str(row.get('CLASSE DI CONCORSO', '')).strip()
                codice_scuola = str(row.get('CODICE SCUOLA', '')).strip().upper()

                val_prov = val_prov_raw
                if codice_scuola and codice_scuola not in ('NAN', 'NONE') and len(codice_scuola) >= 2:
                    sigla_from_scuola = codice_scuola[:2]
                    if sigla_from_scuola in PROVINCE_DATA:
                        val_prov = sigla_from_scuola
                        
                        sigla_from_raw = to_sigla(val_prov_raw)
                        if sigla_from_raw and sigla_from_raw != sigla_from_scuola and debug_mismatch_global < 10:
                            logger.info(f"[VALIDATION FIX] UFFICIO diceva '{val_prov_raw}' ({sigla_from_raw}), ma Scuola '{codice_scuola}' -> Usata {sigla_from_scuola}.")
                            debug_mismatch_global += 1

                if 'NOMINA' in val_prov.upper() or 'NOMINA' in val_classe.upper():
                    continue

                if not val_classe or val_classe in ('nan', 'None'):
                    continue

                if not val_prov or val_prov in ('nan', 'None', ''):
                    current_prov_selected = False
                    continue

                if val_prov and val_prov not in ('nan', 'None'):
                    for sigla, (region, nome) in PROVINCE_DATA.items():
                        if val_prov.upper() == nome.upper() or to_sigla(val_prov) == sigla:
                            prov_norm = nome.upper().replace(" ", "").replace("'", "").replace("-", "")
                            if (prov_set and prov_norm in prov_set) or \
                               (not prov_set and reg_set and region.upper() in reg_set) or \
                               (not prov_set and not reg_set):
                                current_prov = nome
                                current_region = region
                                current_prov_selected = True
                            else:
                                current_prov = nome
                                current_region = region
                                current_prov_selected = False
                            break

                if not current_prov_selected or current_prov is None:
                    continue
                    
                fascia_raw = str(row.get('FASCIA', '')).strip().upper()
                if fascia_raw not in ('F1', 'F2'):
                    continue
                if fascia_filter and fascia_raw != fascia_filter:
                    continue
                    
                try:
                    pos_val = row.get('POSIZIONE')
                    if pd.isna(pos_val) or pos_val == '' or pos_val == '*':
                        continue
                    pos = int(float(pos_val))
                    
                    cog = str(row.get('COGNOME ASPIRANTE', '')).strip().upper()
                    nom = str(row.get('NOME ASPIRANTE', '')).strip().upper()

                    parole_chiave_pdf = ["CLASSE DI CONCORSO", "INFANZIA", "PRIMARIA", "NOMINATI", "UFFICIO PROVINCIALE", "MILO"]
                    if any(parola in cog for parola in parole_chiave_pdf) or any(parola in nom for parola in parole_chiave_pdf):
                        anomalie_count += 1
                        if anomalie_count <= 3:
                            logger.warning(f"[ANOMALIA PDF SCARTATA] Intestazione rilevata (altre soppresse).")
                        continue
                        
                    punt_val = row.get('PUNTEGGIO')
                    punt = pulisci_punteggio(punt_val)
                    if punt is None:
                        continue
                        
                    contratto = str(row.get('TIPO CONTRATTO', '')).strip().upper()
                    codice_scuola = str(row.get('CODICE SCUOLA', '')).strip().upper()
                    
                    candidato_id = f"{fascia_raw}_{pos}"
                    
                except (ValueError, TypeError):
                    continue
                    
                if current_prov not in results[codice]:
                    results[codice][current_prov] = {
                        "regione": current_region, 
                        "nomine_totali": 0, "nominati_univoci": set(),
                        "max_posizione": 0, 
                        "min_31_08": None, "min_30_06": None, "min_spezzoni": None
                    }
                    
                prov_data = results[codice][current_prov]
                prov_data["nomine_totali"] += 1
                prov_data["nominati_univoci"].add(candidato_id)
                
                if pos > prov_data["max_posizione"]:
                    prov_data["max_posizione"] = pos
                    
                if 'ANNUALE' in contratto:
                    if prov_data["min_31_08"] is None or punt < prov_data["min_31_08"]:
                        prov_data["min_31_08"] = punt
                elif 'TERMINE' in contratto or 'FINO AL' in contratto:
                    if prov_data["min_30_06"] is None or punt < prov_data["min_30_06"]:
                        prov_data["min_30_06"] = punt
                elif 'SPEZZONE' in contratto:
                    if prov_data["min_spezzoni"] is None or punt < prov_data["min_spezzoni"]:
                        prov_data["min_spezzoni"] = punt

            # --- PULIZIA MEMORIA ---
            del df
            del csv_text
            gc.collect()
            # ----------------------

    except Exception as e:
        logger.error(f"[BOLLETTINO] Errore critico: {str(e)}", exc_info=True)
        return jsonify({"error": f"Errore lettura bollettino: {str(e)}"}), 500

    logger.info(f"[BOLLETTINO] DEBUG: Risultati bollettino elaborati per {len(results)} classi.")
    for codice, res in results.items():
        logger.info(f"[BOLLETTINO] DEBUG: Classe {codice}: {len(res)} province con nomine.")

    # 5. CALCOLO METRICHE E OUTPUT RAGGRUPPATO
    out_data = {}
    for codice, res in results.items():
        out_data[codice] = []
        for prov, r in res.items():
            tot_cand = total_candidates.get((codice, prov), 0)
            nominati_univoci = len(r["nominati_univoci"])
            
            assorbimento = round((nominati_univoci / tot_cand) * 100, 2) if tot_cand > 0 else 0
            max_pos = r["max_posizione"]
            rinuncia = round(((max_pos - nominati_univoci) / max_pos) * 100, 2) if max_pos > 0 else 0
            
            def fmt(val):
                if val is None: return "N/D"
                s = str(val).replace('.', ',')
                if s.endswith(',0'): s = s.replace(',0', '')
                return s
                
            out_data[codice].append({
                "regione": r['regione'], "provincia": prov, 
                "candidati_totali": tot_cand, "nomine_totali": r["nomine_totali"],
                "nominati_univoci": nominati_univoci, "assorbimento": assorbimento,
                "max_posizione": max_pos, "rinuncia": rinuncia,
                "cut_31_08": fmt(r["min_31_08"]), 
                "cut_30_06": fmt(r["min_30_06"]), 
                "cut_spezzoni": fmt(r["min_spezzoni"])
            })

    # RIEPILOGO FINALE PER VERIFICA GLOBALE
    logger.info("=== RIEPILOGO FINALE NOMINE (Tutte le Province) ===")
    for codice, res_list in out_data.items():
        for item in res_list:
            logger.info(f"[RIEPILOGO] Classe: {codice} | Prov: {item['provincia']} | Candidati: {item['candidati_totali']} | Nominati: {item['nominati_univoci']} | MaxPos: {item['max_posizione']}")
    logger.info("===================================================")
        
    return jsonify({"data": out_data})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
