import os
import re
import io
import logging
import requests
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

SEC_I_CLASSI = {"AB24", "A011", "A012", "A013", "A014", "A015", "A016", "A017", "A018", "A019", "A020", "A021", "A022", "A023", "A024", "A026", "A027", "A028", "A031", "A032", "A034", "A036", "A037", "A038", "A040", "A041", "A042", "A044", "A045", "A046", "A047", "A050", "A051", "A052", "A053", "A054", "A057", "A058", "A059", "A060", "A061", "A062", "A063", "A064", "A065", "A066", "A076", "A077", "A078", "A084", "A085", "AA55", "AA56", "AB55", "AB56", "AC55", "AC56", "AD55", "AD56", "ADMM", "AE55", "AE56", "AF55", "AF56", "AG56", "AH55", "AH56", "AI55", "AI56", "AJ55", "AJ56", "AK55", "AK56", "AL55", "AL56", "AM01", "AM2A", "AM2B", "AM2C", "AM2D", "AM2E", "AM2F", "AM2G", "AM12", "AM30", "AM48", "AM55", "AM56", "AM70", "AM71", "AN55", "AN56", "AO55", "AP55", "AQ55", "AR55", "AS01", "AS2A", "AS2B", "AS2C", "AS2D", "AS2E", "AS2I", "AS2L", "AS2N", "AS12", "AS30", "AS48", "AS55", "AT55", "AU55", "AW55", "A-01", "A-12", "A-23", "A-28", "A-30", "A-48", "A-60", "AA22", "AB22", "AC22", "AD22", "AE22", "IRC"}

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
    "A011": "A-01 (Arte e Immagine).csv", "A019": "A-12 (Lettere).csv", "A020": "A-12 (Lettere).csv",
    "A016": "A-22 (AA22 Francese).csv", "A018": "A-22 (AB22 IngleseAltra Lingua).csv",
    "A023": "A-22 (AC22 Spagnolo).csv", "A024": "A-22 (AD22 Tedesco).csv",
    "A021": "A-28 (Matematica e Scienze).csv", "A013": "A-30 (Musica).csv",
    "A015": "A-48 (Scienze Motorie).csv", "A014": "A-60 (Tecnologia).csv",
    "A028": "A-28 (Matematica e Scienze).csv", "A060": "A-60 (Tecnologia).csv",
    "A-01": "A-01 (Arte e Immagine).csv", "A-12": "A-12 (Lettere).csv",
    "AA22": "A-22 (AA22 Francese).csv", "AB22": "A-22 (AB22 IngleseAltra Lingua).csv",
    "AC22": "A-22 (AC22 Spagnolo).csv", "AD22": "A-22 (AD22 Tedesco).csv",
    "AE22": "A-22 (AE22 Sloveno).csv", "A-23": "A-23 (Italiano L2).csv",
    "A-28": "A-28 (Matematica e Scienze).csv", "A-30": "A-30 (Musica).csv",
    "A-48": "A-48 (Scienze Motorie).csv", "A-60": "A-60 (Tecnologia).csv",
    "AM01": "A-01 (Arte e Immagine).csv", "AM12": "A-12 (Lettere).csv",
    "AM2A": "A-22 (AA22 Francese).csv", "AM2B": "A-22 (AB22 IngleseAltra Lingua).csv",
    "AM2C": "A-22 (AC22 Spagnolo).csv", "AM2D": "A-22 (AD22 Tedesco).csv",
    "AM2E": "A-22 (AE22 Sloveno).csv", "AM30": "A-30 (Musica).csv",
    "AM48": "A-48 (Scienze Motorie).csv", "IRC": "IRC (Religione Cattolica).csv",
}

CODICI_EQUIVALENTI = {
    "A011": {"A011", "A-01", "AM01"}, "A-01": {"A011", "A-01", "AM01"}, "AM01": {"A011", "A-01", "AM01"},
    "A019": {"A019", "A020", "A-12", "AM12"}, "A020": {"A019", "A020", "A-12", "AM12"},
    "A-12": {"A019", "A020", "A-12", "AM12"}, "AM12": {"A019", "A020", "A-12", "AM12"},
    "A016": {"A016", "AA22", "AM2A"}, "AA22": {"A016", "AA22", "AM2A"}, "AM2A": {"A016", "AA22", "AM2A"},
    "A018": {"A018", "AB22", "AM2B"}, "AB22": {"A018", "AB22", "AM2B"}, "AM2B": {"A018", "AB22", "AM2B"},
    "A023": {"A023", "A-23", "AC22", "AM2C"}, "A-23": {"A023", "A-23", "AC22", "AM2C"}, "AC22": {"A023", "AC22", "AM2C"}, "AM2C": {"A023", "AC22", "AM2C"},
    "A024": {"A024", "AD22", "AM2D"}, "AD22": {"A024", "AD22", "AM2D"}, "AM2D": {"A024", "AD22", "AM2D"},
    "AE22": {"AE22", "AM2E"}, "AM2E": {"AE22", "AM2E"},
    "A013": {"A013", "A-30", "AM30"}, "A-30": {"A013", "A-30", "AM30"}, "AM30": {"A013", "A-30", "AM30"},
    "A015": {"A015", "A-48", "AM48"}, "A-48": {"A015", "A-48", "AM48"}, "AM48": {"A015", "A-48", "AM48"},
    "A021": {"A021", "A-28", "A028"}, "A-28": {"A021", "A-28", "A028"}, "A028": {"A021", "A-28", "A028"},
    "A014": {"A014", "A-60", "A060"}, "A-60": {"A014", "A-60", "A060"}, "A060": {"A014", "A-60", "A060"},
    "A012": {"A012", "A046", "A047"}, 
    "A076": {"A076", "A030", "A031"}, 
    "IRC":  {"IRC", "A079", "A080", "A081", "A083"}, 
}

SEC_II_FOLDER = "Numero scuole II grado"
SEC_II_PREFIX = SEC_II_FOLDER + "/"

SEC_II_MUSICAL_CLASSI = {
    "A-55", "AA55", "AB55", "AC55", "AD55", "AE55", "AF55", "AG55", "AH55",
    "AI55", "AJ55", "AK55", "AL55", "AM55", "AN55", "AO55", "AP55", "AQ55",
    "AR55", "AS55", "AT55", "AU55", "AV55", "AW55",
}

SEC_II_CSV_FILE_MAP = {
    "A-01": "A-01 (Disegno e storia dell'arte).csv", "A-02": "A-02 (Design metalli, oreficeria, pietre).csv",
    "A-05": "A-05 (Design del tessuto e della moda).csv", "A-07": "A-07 (Discipline audiovisive).csv",
    "A-08": "A-08 (Discipline geometriche, architettura, scenotecnica).csv", "A-09": "A-09 (Discipline grafiche, pittoriche, scenografiche).csv",
    "A-11": "A-11 (Lettere e latino).csv", "A-12": "A-12 (Discipline letterarie).csv",
    "A-13": "A-13 (Lettere, latino e greco - Liceo Classico).csv", "A-14": "A-14 (Discipline plastiche e scultoree).csv",
    "A-15": "A-15 (Discipline sanitarie).csv", "A-16": "A-16 (Modellazione odontotecnica).csv",
    "A-18": "A-18 (Filosofia e scienze umane).csv", "A-19": "A-19 (Filosofia e storia).csv",
    "A-20": "A-20 (Fisica).csv", "A-21": "A-21 (Geografia).csv",
    "A-22 (AA)": "A-22 (AA - Francese).csv", "A-22 (AB)": "A-22 (AB - IngleseAltra Lingua).csv",
    "A-22 (AC)": "A-22 (AC - Spagnolo).csv", "A-22 (AD)": "A-22 (AD - Tedesco).csv",
    "A-22 (AE)": "A-22 (AE - Sloveno).csv", "A-23": "A-23 (Italiano L2).csv",
    "A-24": "A-24 (Lingue e culture dell'Asia orientale e sud-orientale).csv", "A-26": "A-26 (Matematica).csv",
    "A-27": "A-27 (Matematica e fisica).csv", "A-30": "A-30 (Musica).csv",
    "A-31": "A-31 (Scienze degli alimenti).csv", "A-32": "A-32 (Scienze della geologia e della mineralogia).csv",
    "A-33": "A-33 (Scienze e tecnologie aeronautiche).csv", "A-34": "A-34 (Scienze e tecnologie chimiche).csv",
    "A-36": "A-36 (Scienze e tecnologie della logistica).csv", "A-37": "A-37 (Tecnologie delle costruzioni e rappresentazione grafica).csv",
    "A-38": "A-38 (Costruzioni aeronautiche).csv", "A-39": "A-39 (Costruzioni navali).csv",
    "A-40": "A-40 (Scienze e tecnologie elettriche ed elettroniche).csv", "A-41": "A-41 (Scienze e tecnologie informatiche).csv",
    "A-42": "A-42 (Scienze e tecnologie meccaniche).csv", "A-43": "A-43 (Scienze e tecnologie nautiche).csv",
    "A-44": "A-44 (Tecnologie tessili, abbigliamento e moda).csv", "A-45": "A-45 (Scienze economico-aziendali).csv",
    "A-46": "A-46 (Scienze giuridico-economiche).csv", "A-47": "A-47 (Diritto ed economia politica).csv",
    "A-48": "A-48 (Scienze motorie e sportive).csv", "A-50": "A-50 (Scienze naturali, chimiche e biologiche).csv",
    "A-51": "A-51 (Tecnologie agrarie).csv", "A-52": "A-52 (Tecnologie di produzioni animali).csv",
    "A-53": "A-53 (Storia).csv", "A-54": "A-54 (Storia dell'arte).csv",
    "A-57": "A-57 (Tecnica della danza classica).csv", "A-58": "A-58 (Tecnica della danza contemporanea).csv",
    "A-60": "A-60 (Storia della musica e della danza).csv", "A-61": "A-61 (Tecnologie e tecniche delle comunicazioni multimediali).csv",
    "A-62": "A-62 (Tecnologie e tecniche per la grafica).csv", "A-63": "A-63 (Tecnologie musicali).csv",
    "A-64": "A-64 (Teoria, analisi e composizione).csv", "IRC": "IRC (Religione Cattolica).csv",
    "AM55": "A-55 (Strumento musicale).csv", "AN55": "A-55 (Strumento musicale).csv",
    "AA55": "A-55 (Strumento musicale).csv", "AB55": "A-55 (Strumento musicale).csv",
    "AC55": "A-55 (Strumento musicale).csv", "AD55": "A-55 (Strumento musicale).csv",
    "AE55": "A-55 (Strumento musicale).csv", "AF55": "A-55 (Strumento musicale).csv",
    "AG55": "A-55 (Strumento musicale).csv", "AH55": "A-55 (Strumento musicale).csv",
    "AI55": "A-55 (Strumento musicale).csv", "AJ55": "A-55 (Strumento musicale).csv",
    "AK55": "A-55 (Strumento musicale).csv", "AL55": "A-55 (Strumento musicale).csv",
    "AO55": "A-55 (Strumento musicale).csv", "AP55": "A-55 (Strumento musicale).csv",
    "AQ55": "A-55 (Strumento musicale).csv", "AR55": "A-55 (Strumento musicale).csv",
    "AS55": "A-55 (Strumento musicale).csv", "AT55": "A-55 (Strumento musicale).csv",
    "AU55": "A-55 (Strumento musicale).csv", "AW55": "A-55 (Strumento musicale).csv",
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

def get_scuole_dict_from_csv(repo, codice):
    global _SCUOLE_CSV_CACHE
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

def get_scuole_dict_sec_ii_from_csv(repo, codice):
    global _SCUOLE_SEC_II_CSV_CACHE
    codice_upper = codice.upper()
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

def get_all_repo_files(repo, path=""):
    contents = repo.get_contents(path)
    files = []
    for content in contents:
        if content.type == "dir":
            files.extend(get_all_repo_files(repo, content.path))
        else:
            files.append(content)
    return files

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
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = get_all_repo_files(repo)
        logger.info(f"Trovati {len(root_files)} file totali nel repository.")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    dizionario_scuole_altro = SCUOLE_FALLBACK

    logger.info(f"Regioni richieste: {regioni_richieste}")
    logger.info(f"Province nomi ricevute: {province_nomi}")
    
    province_sigle = []
    for prov in province_nomi:
        sigla = PROVINCE_SIGLE.get(prov)
        if sigla:
            province_sigle.append(sigla)
        else:
            logger.warning(f"Provincia '{prov}' NON trovata in PROVINCE_SIGLE!")
    
    logger.info(f"Province sigle finali: {province_sigle}")

    for codice_raw in codici_validi:
        if '|' in codice_raw:
            ordine_classe, codice = codice_raw.split('|', 1)
            ordine_classe = ordine_classe.strip().lower()
        else:
            ordine_classe = None
            codice = codice_raw

        codice_upper = codice.upper()
        fascia_norm = normalize_fascia(fascia_richiesta) if fascia_richiesta else ""

        is_sec_ii = (ordine_classe == "secondaria_ii")

        if is_sec_ii:
            codici_ricerca = {codice_upper}
            if codice_upper == "A001":
                codici_ricerca.add("A017")
            elif codice_upper == "ADSS":
                codici_ricerca.add("A030")
            elif codice_upper == "A027":
                codici_ricerca.add("A031")
            elif codice_upper == "A054":
                codici_ricerca.add("A076")
            if '-' in codice_upper:
                cod_no_dash = codice_upper.replace('-', '')
                codici_ricerca.add(cod_no_dash)
                if re.match(r'^A\d{2}$', cod_no_dash):
                    codici_ricerca.add('A0' + cod_no_dash[-2:])
        else:
            codici_ricerca = CODICI_EQUIVALENTI.get(codice_upper, {codice_upper})
        
        logger.info(f"[{codice_upper}] Codici ricerca: {codici_ricerca} | Ordine: {ordine_classe}")

        if is_sec_ii:
            csv_scuole = get_scuole_dict_sec_ii_from_csv(repo, codice_upper)
            if csv_scuole is not None:
                scuole_dict = csv_scuole
                logger.info(f"[{codice_upper}] [SEC II] Usato file CSV Sec II per numero scuole.")
            else:
                scuole_dict = dizionario_scuole_altro
                logger.info(f"[{codice_upper}] [SEC II] Nessun CSV trovato, fallback a 0.")
        elif codice_upper == "ADMM":
            scuole_dict = get_scuole_dict(repo, is_musical=False)
            logger.info(f"[{codice_upper}] Usato file MM (Scuole_Statali_Totali_MM.txt) per numero scuole.")
        elif codice_upper in SEC_I_MUSICAL_CLASSI:
            scuole_dict = get_scuole_dict(repo, is_musical=True)
            logger.info(f"[{codice_upper}] Usato file scuole musicali (Riepilogo_Scuole_Musicali.txt).")
        elif codice_upper in SEC_I_CLASSI or codice_upper in SEC_I_CSV_FILE_MAP:
            csv_scuole = get_scuole_dict_from_csv(repo, codice_upper)
            if csv_scuole is not None:
                scuole_dict = csv_scuole
                logger.info(f"[{codice_upper}] Usato file CSV specifico per numero scuole.")
            else:
                scuole_dict = dizionario_scuole_altro
                logger.info(f"[{codice_upper}] Nessun CSV, fallback a 0.")
        else:
            scuole_dict = dizionario_scuole_altro

        # ====================================================================
        # Selezione cartella di ricerca file estrazione in base a ordine + fascia
        # ====================================================================
        is_infanzia  = (ordine_classe == "infanzia")
        is_primaria  = (ordine_classe == "primaria")
        is_sec_i_codice = (not is_sec_ii and (
                           codice_upper in SEC_I_CLASSI or
                           codice_upper in SEC_I_MUSICAL_CLASSI or
                           codice_upper in SEC_I_CSV_FILE_MAP or
                           codice_upper == "ADMM"))
        is_sec_i_ordine = (ordine_classe == "secondaria_i") or is_sec_i_codice

        fascia_upper = (fascia_richiesta or "").upper().strip()
        is_i_fascia_selected  = (fascia_upper in ("I_FASCIA", "1_FASCIA", "IFASCIA"))
        is_ii_fascia_selected = (fascia_upper in ("II_FASCIA", "2_FASCIA", "IIFASCIA"))

        # ---- INFANZIA ----
        if is_infanzia and is_i_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_AA_I_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_AA_I_FASCIA_PREFIX}' (Infanzia + I Fascia). {len(files_to_search)} candidati.")
        elif is_infanzia and is_ii_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_AA_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_AA_II_FASCIA_PREFIX}' (Infanzia + II Fascia). {len(files_to_search)} candidati.")
        elif is_infanzia and not fascia_richiesta:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_AA_I_FASCIA_PREFIX) or f.path.startswith(ESTRAZIONE_AA_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca in '{ESTRAZIONE_AA_I_FASCIA_PREFIX}' + '{ESTRAZIONE_AA_II_FASCIA_PREFIX}' (Infanzia - Tutte le fasce). {len(files_to_search)} candidati.")

        # ---- PRIMARIA ----
        elif is_primaria and is_i_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_EE_I_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_EE_I_FASCIA_PREFIX}' (Primaria + I Fascia). {len(files_to_search)} candidati.")
        elif is_primaria and is_ii_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_EE_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_EE_II_FASCIA_PREFIX}' (Primaria + II Fascia). {len(files_to_search)} candidati.")
        elif is_primaria and not fascia_richiesta:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_EE_I_FASCIA_PREFIX) or f.path.startswith(ESTRAZIONE_EE_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca in '{ESTRAZIONE_EE_I_FASCIA_PREFIX}' + '{ESTRAZIONE_EE_II_FASCIA_PREFIX}' (Primaria - Tutte le fasce). {len(files_to_search)} candidati.")

        # ---- SECONDARIA I GRADO ----
        elif is_sec_i_ordine and is_i_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_MM_I_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_MM_I_FASCIA_PREFIX}' (Sec I + I Fascia). {len(files_to_search)} candidati.")
        elif is_sec_i_ordine and is_ii_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_MM_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_MM_II_FASCIA_PREFIX}' (Sec I + II Fascia). {len(files_to_search)} candidati.")
        elif is_sec_i_ordine and not fascia_richiesta:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_MM_I_FASCIA_PREFIX) or f.path.startswith(ESTRAZIONE_MM_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca in '{ESTRAZIONE_MM_I_FASCIA_PREFIX}' + '{ESTRAZIONE_MM_II_FASCIA_PREFIX}' (Sec I - Tutte le fasce). {len(files_to_search)} candidati.")

        # ---- SECONDARIA II GRADO ----
        elif is_sec_ii and is_i_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_SS_I_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_SS_I_FASCIA_PREFIX}' (Sec II + I Fascia). {len(files_to_search)} candidati.")
        elif is_sec_ii and is_ii_fascia_selected:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_SS_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca SOLO in '{ESTRAZIONE_SS_II_FASCIA_PREFIX}' (Sec II + II Fascia). {len(files_to_search)} candidati.")
        elif is_sec_ii and not fascia_richiesta:
            files_to_search = [f for f in root_files if f.path.startswith(ESTRAZIONE_SS_I_FASCIA_PREFIX) or f.path.startswith(ESTRAZIONE_SS_II_FASCIA_PREFIX)]
            logger.info(f"[{codice_upper}] Ricerca in '{ESTRAZIONE_SS_I_FASCIA_PREFIX}' + '{ESTRAZIONE_SS_II_FASCIA_PREFIX}' (Sec II - Tutte le fasce). {len(files_to_search)} candidati.")

        # ---- FALLBACK: ricerca in root escludendo tutte le cartelle di estrazione ----
        else:
            all_prefixes = (
                ESTRAZIONE_AA_I_FASCIA_PREFIX, ESTRAZIONE_AA_II_FASCIA_PREFIX,
                ESTRAZIONE_EE_I_FASCIA_PREFIX, ESTRAZIONE_EE_II_FASCIA_PREFIX,
                ESTRAZIONE_MM_I_FASCIA_PREFIX, ESTRAZIONE_MM_II_FASCIA_PREFIX,
                ESTRAZIONE_SS_I_FASCIA_PREFIX, ESTRAZIONE_SS_II_FASCIA_PREFIX,
            )
            files_to_search = [f for f in root_files if not any(f.path.startswith(p) for p in all_prefixes)]
            logger.info(f"[{codice_upper}] Ricerca in root (escluse cartelle estrazioni fascia). {len(files_to_search)} candidati.")

        # ====================================================================
        # Ricerca file di estrazione
        # ====================================================================
        file_da_elaborare = []
        nomi_file_visti = set()
        logger.info(f"[{codice_upper}] Inizio analisi di {len(files_to_search)} file candidati. Fascia richiesta normalizzata: '{fascia_norm}'")
        
        for f in files_to_search:
            if hasattr(f, 'type') and f.type != 'file':
                continue
            if f.name.startswith('~$'):
                continue
                
            for cod_ric in codici_ricerca:
                if is_sec_ii:
                    cod_ric_no_dash = cod_ric.replace('-', '')
                    if re.match(r'^A\d{2}$', cod_ric_no_dash):
                        cod_ric_no_dash = 'A0' + cod_ric_no_dash[-2:]
                    prefix = f"RISULTATO_ESTRAZIONE_{cod_ric_no_dash}_"
                else:
                    prefix = f"RISULTATO_ESTRAZIONE_{cod_ric}_"
                
                f_name_upper = f.name.upper()
                
                # Log di debug per ogni file e codice cercato
                logger.info(f"  -> File: '{f.name}' | Prefix cercato: '{prefix}' | Inizia con prefix: {f_name_upper.startswith(prefix)}")
                
                if f_name_upper.startswith(prefix) and f.name.lower().endswith('.csv'):
                    if f.name in nomi_file_visti:
                        break
                    if fascia_norm:
                        file_fascia_part = f_name_upper[len(prefix):].replace('.CSV', '')
                        file_fascia_norm = normalize_fascia(file_fascia_part)
                        
                        # Log di debug per il confronto fascia
                        logger.info(f"     -> Estrazione fascia da nome file: '{file_fascia_part}' | Normalizzata: '{file_fascia_norm}' | Confronto con: '{fascia_norm}' | Match: {file_fascia_norm == fascia_norm}")
                        
                        if file_fascia_norm == fascia_norm:
                            file_da_elaborare.append(f)
                            nomi_file_visti.add(f.name)
                    else:
                        file_da_elaborare.append(f)
                        nomi_file_visti.add(f.name)
                    break

        logger.info(f"[{codice_upper}] Trovati {len(file_da_elaborare)} file CSV da elaborare.")
        if not file_da_elaborare:
            logger.warning(f"Nessun file trovato per il codice: {codice}")
            continue

        pdf.set_font("Helvetica", 'B', 12)
        if codice_upper in SEC_I_MUSICAL_NAMES:
            display_classe = f"Classe di Concorso: {codice} - {SEC_I_MUSICAL_NAMES[codice_upper]}"
        else:
            display_classe = f"Classe di Concorso: {codice}"
        pdf.cell(0, 10, text=sanitize_for_fpdf(display_classe), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        try:
            lista_dati = []
            for file_trovato in file_da_elaborare:
                try:
                    if hasattr(file_trovato, 'download_url') and file_trovato.download_url:
                        response = requests.get(file_trovato.download_url)
                        file_data = response.content
                    else:
                        file_content = repo.get_contents(file_trovato.path)
                        file_data = file_content.decoded_content
                    csv_text = file_data.decode('utf-8-sig', errors='ignore')
                    csv_text = clean_csv_text(csv_text)
                    try:
                        csv_io = io.StringIO(csv_text)
                        df_temp = pd.read_csv(csv_io, sep=';', dtype=str, skipinitialspace=True)
                    except Exception as e:
                        logger.error(f"ERRORE LETTURA CSV per {file_trovato.name}: {e}", exc_info=True)
                        continue
                    fascia_nome = "DETTAGLI"
                    for cod_ric in codici_ricerca:
                        if cod_ric in file_trovato.name:
                            parti = file_trovato.name.split(cod_ric)
                            if len(parti) > 1:
                                raw_fascia = parti[-1].replace("_", " ").replace(".csv", "").strip().upper()
                                if "1" in raw_fascia or "I" in raw_fascia:
                                    fascia_nome = "I FASCIA"
                                elif "2" in raw_fascia or "II" in raw_fascia:
                                    fascia_nome = "II FASCIA"
                                elif "3" in raw_fascia or "III" in raw_fascia:
                                    fascia_nome = "III FASCIA"
                                else:
                                    fascia_nome = raw_fascia
                                break
                    if not fascia_nome:
                        fascia_nome = "DETTAGLI"
                    lista_dati.append((df_temp, fascia_nome))
                except Exception as e:
                    logger.error(f"Errore lettura file {file_trovato.name}: {str(e)}")
            if not lista_dati:
                continue

            def get_fascia_order(fascia_str):
                f = str(fascia_str).upper()
                if 'I FASCIA' in f or '1 FASCIA' in f: return 0
                if 'II FASCIA' in f or '2 FASCIA' in f: return 1
                if 'III FASCIA' in f or '3 FASCIA' in f: return 2
                return 3
            lista_dati.sort(key=lambda x: get_fascia_order(x[1]))

            for df, nome_fascia in lista_dati:
                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
                df.rename(columns={
                    'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE': 'CODICE GRADUATORIA',
                    'ORDINE SCUOLA GRADUATORIA': 'ORDINE SCUOLA'
                }, inplace=True, errors='ignore')
                col_classe = None
                for col in df.columns:
                    col_upper = str(col).strip().upper()
                    if col_upper in {'CODICE GRADUATORIA', 'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE', 'CLASSE DI CONCORSO'}:
                        col_classe = col
                        break
                if col_classe and not df.empty:
                    def contiene_classe_esatta(valore, codici_target):
                        if pd.isna(valore):
                            return False
                        testo = str(valore).upper().strip().replace('-', ' ').replace('_', ' ')
                        testo = re.sub(r'\s+', ' ', testo)
                        codici_trovati = re.findall(
                            r'(?<![A-Z0-9])(?:A\d{3}|A[A-Z]\d{2}|A[A-Z]\d[A-Z]|A[A-Z]{3}|IRC)(?![A-Z0-9])',
                            testo
                        )
                        codici_trovati = {c.upper() for c in codici_trovati}
                        return any(c in codici_trovati for c in codici_target)
                    prima = len(df)
                    df = df[df[col_classe].apply(lambda x: contiene_classe_esatta(x, codici_ricerca))].copy()
                    dopo = len(df)
                    logger.info(f"[{codice_upper}] FILTRO CLASSE (codici: {codici_ricerca}): {prima} -> {dopo}")
                else:
                    logger.warning(f"[{codice_upper}] Colonna classe non trovata. Uso solo filtro nome file.")

                col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                col_cognome = next((col for col in df.columns if 'COGNOME' in str(col).upper()), None)
                
                if col_ufficio:
                    df['_sigla_prov'] = df[col_ufficio].apply(to_sigla)
                    df = df.dropna(subset=['_sigla_prov'])
                    if province_sigle:
                        df = df[df['_sigla_prov'].isin(province_sigle)]
                    df[col_ufficio] = df['_sigla_prov']
                    df = df.drop(columns=['_sigla_prov'])
                else:
                    df = pd.DataFrame()
                if col_cognome and not df.empty:
                    df = df[~df[col_cognome].astype(str).str.strip().isin(['*', '', 'nan', 'None'])]
                    df = df.dropna(subset=[col_cognome])
                if df.empty:
                    continue

                useless_cols = ['CODICE TIPOLOGIA LINGUA GRADUATORIA DI INCLUSIONE', 'INCLUSIONE CON RISERVA', 'COGNOME', 'NOME', 'ORIGINE']
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
                                if nome_esteso not in province_scores:
                                    province_scores[nome_esteso] = []
                                province_scores[nome_esteso].extend(prov_df['punteggio_num'].tolist())
                                idx_max = prov_df['punteggio_num'].idxmax()
                                idx_min = prov_df['punteggio_num'].idxmin()
                                max_score = float(prov_df.loc[idx_max, 'punteggio_num'])
                                min_score = float(prov_df.loc[idx_min, 'punteggio_num'])
                                median_score = float(prov_df['punteggio_num'].median())
                                top_candidate = str(max_score).replace('.', ',')
                                bottom_candidate = str(min_score).replace('.', ',')
                                if top_candidate.endswith(',0'): top_candidate = top_candidate.replace(',0', '')
                                if bottom_candidate.endswith(',0'): bottom_candidate = bottom_candidate.replace(',0', '')
                        if nome_esteso not in stats_data:
                            stats_data[nome_esteso] = {
                                "scuole": num_scuole, "candidati": num_candidati, "rapporto": rapporto,
                                "regione": region_name, "top": top_candidate, "bottom": bottom_candidate, "median": median_score
                            }
                        else:
                            stats_data[nome_esteso]["candidati"] += num_candidati
                            stats_data[nome_esteso]["rapporto"] = round(stats_data[nome_esteso]["scuole"] / stats_data[nome_esteso]["candidati"], 4)
                            if top_candidate != "N/D":
                                existing_top = parse_score(stats_data[nome_esteso]["top"])
                                new_top = parse_score(top_candidate)
                                if existing_top is None or (new_top is not None and new_top > existing_top):
                                    stats_data[nome_esteso]["top"] = top_candidate
                            if bottom_candidate != "N/D":
                                existing_bottom = parse_score(stats_data[nome_esteso]["bottom"])
                                new_bottom = parse_score(bottom_candidate)
                                if existing_bottom is None or (new_bottom is not None and new_bottom < existing_bottom):
                                    stats_data[nome_esteso]["bottom"] = bottom_candidate

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
                    if len(unique_vals) <= 1 and not is_ufficio_col and not is_keep_col:
                        cols_to_drop.append(col)
                    if 'pdf' in str(col).lower() or 'csv' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower() or 'origine' in str(col).lower():
                        cols_to_drop.append(col)
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
                    if current_line:
                        lines.append(current_line)
                    if not lines: lines = [""]
                    if len(lines) > 2:
                        lines = [lines[0], " ".join(lines[1:])]
                    while len(lines) < 2:
                        lines.append("")
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
                        if reg_changed:
                            spazio_necessario += 10
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
                        char_lim = max(1, int(col_widths[col] / 2.0))
                        if len(valore) > char_lim:
                            valore = valore[:char_lim-3] + "..."
                        align = 'L'
                        pdf.cell(col_widths[col], row_height, valore, border=1, align=align)
                    pdf.ln(row_height)
            pdf.ln(8)
            trovato_almeno_uno = True
        except Exception as e:
            logger.error(f"Errore elaborazione file: {str(e)}", exc_info=True)
            pdf.set_font("Helvetica", 'I', 10)
            pdf.cell(0, 10, text=sanitize_for_fpdf(f"Errore interno durante l'elaborazione della classe {codice}."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(5)

    import statistics
    for prov, scores in province_scores.items():
        if prov in stats_data and scores:
            try:
                stats_data[prov]["median"] = float(statistics.median(scores))
            except statistics.StatisticsError:
                pass
        elif prov in stats_data:
            stats_data[prov]["median"] = 0.0

    if not trovato_almeno_uno:
        pdf.cell(0, 10, text="Nessun dato disponibile per i filtri selezionati.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf_bytes = pdf.output()
    import base64
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    logger.info(f"Generazione PDF completata. Stats inviate: {len(stats_data)} province.")
    return jsonify({"pdf_base64": pdf_base64, "stats": stats_data})

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
    if fascia_richiesta.upper() == 'II_FASCIA':
        fascia_filter = 'F2'
    elif fascia_richiesta.upper() == 'I_FASCIA':
        fascia_filter = 'F1'
    else:
        fascia_filter = ''

    codici_validi = []
    ordini_selezionati = set()
    for c in classi_selezionate:
        if '|' in c:
            ord, c = c.split('|', 1)
            ordini_selezionati.add(ord.strip().lower())
        codici_validi.append(c.split(' - ')[0].strip().upper())

    # Mappatura ordini di scuola -> cartelle bollettini specifiche
    prefixes = []
    if "infanzia" in ordini_selezionati:
        prefixes.append("Bollettini/AA/")
    if "primaria" in ordini_selezionati:
        prefixes.append("Bollettini/EE/")
    if "secondaria_i" in ordini_selezionati:
        prefixes.append("Bollettini/MM/")
    if "secondaria_ii" in ordini_selezionati:
        prefixes.append("Bollettini/SS/")

    try:
        repo = g.get_repo(REPO_NAME)
        root_files = get_all_repo_files(repo)
        
        # Filtra solo i file CSV che iniziano con i prefissi delle cartelle selezionate
        file_objs = [f for f in root_files if any(f.path.startswith(p) for p in prefixes) and f.name.lower().endswith('.csv')]
        
        if not file_objs:
            return jsonify({"error": "Nessun file bollettino trovato per gli ordini di scuola selezionati."}), 404
            
        results = {}
        # Elabora ogni file trovato nelle cartelle specifiche
        for file_obj in file_objs:
            try:
                if hasattr(file_obj, 'download_url') and file_obj.download_url:
                    response = requests.get(file_obj.download_url)
                    file_data = response.content
                else:
                    file_data = file_obj.decoded_content
                csv_text = file_data.decode('utf-8-sig', errors='ignore')
                csv_text = clean_csv_text(csv_text)
                df = pd.read_csv(io.StringIO(csv_text), sep=';', dtype=str, skipinitialspace=True)
            except Exception as e:
                logger.error(f"Errore lettura bollettino {file_obj.path}: {e}")
                continue

            df.columns = [str(c).strip() for c in df.columns]
            current_prov = None
            current_region = None
            current_prov_selected = False
            
            for _, row in df.iterrows():
                val_classe = str(row.get('Classe di concorso', '')).strip()
                if not val_classe or val_classe in ('nan', 'None'):
                    continue
                is_nomina = val_classe.upper().startswith('NOMINA')
                is_data = any(cod in val_classe.upper() for cod in codici_validi)
                if is_data:
                    if not current_prov_selected or current_prov is None:
                        continue
                    fascia_raw = str(row.get('Fascia', '')).strip().upper()
                    if fascia_raw not in ('F1', 'F2'):
                        continue
                    if fascia_filter and fascia_raw != fascia_filter:
                        continue
                    try:
                        pos_val = row.get('Posizione')
                        if pd.isna(pos_val) or pos_val == '' or pos_val == '*':
                            continue
                        pos = int(float(pos_val))
                        punt_val = row.get('Punteggio')
                        if pd.isna(punt_val) or punt_val == '' or punt_val == '*':
                            continue
                        punt = pulisci_punteggio(punt_val)
                        if punt is None:
                            continue
                    except (ValueError, TypeError):
                        continue
                    if current_prov not in results:
                        results[current_prov] = {
                            "regione": current_region, "nomine_totali": 0, "nomine_f1": 0,
                            "nomine_f2": 0, "min_f1": None, "min_f2": None
                        }
                    prov_data = results[current_prov]
                    prov_data["nomine_totali"] += 1
                    if fascia_raw == "F1":
                        prov_data["nomine_f1"] += 1
                        if prov_data["min_f1"] is None or punt < prov_data["min_f1"]:
                            prov_data["min_f1"] = punt
                    elif fascia_raw == "F2":
                        prov_data["nomine_f2"] += 1
                        if prov_data["min_f2"] is None or punt < prov_data["min_f2"]:
                            prov_data["min_f2"] = punt
                elif not is_nomina:
                    for sigla, (region, nome) in PROVINCE_DATA.items():
                        if val_classe.upper() == nome.upper():
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

    except Exception as e:
        return jsonify({"error": f"Errore lettura bollettino: {str(e)}"}), 500

    out_data = []
    for prov, r in results.items():
        assorb_f1 = round((r["nomine_f1"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        prob_f1 = round((r["nomine_f1"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        prob_f2 = round((r["nomine_f2"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        min_f1_str = str(r['min_f1']).replace('.', ',') if r['min_f1'] is not None else "N/D"
        min_f2_str = str(r['min_f2']).replace('.', ',') if r['min_f2'] is not None else "N/D"
        if min_f1_str.endswith(',0'): min_f1_str = min_f1_str.replace(',0', '')
        if min_f2_str.endswith(',0'): min_f2_str = min_f2_str.replace(',0', '')
        out_data.append({
            "regione": r['regione'], "provincia": prov, "nomine_totali": r["nomine_totali"],
            "min_f1": min_f1_str, "min_f2": min_f2_str, "assorbimento_f1": assorb_f1,
            "prob_f1": prob_f1, "prob_f2": prob_f2, "nomine_f1": r["nomine_f1"], "nomine_f2": r["nomine_f2"]
        })
    return jsonify({"data": out_data})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
