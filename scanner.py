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
            ord, c_clean = c.split('|', 1)
            ordini_selezionati.add(ord.strip().lower())
        else:
            c_clean = c
        codici_validi.append(c_clean.split(' - ')[0].strip().upper())

    prefixes = []
    if "infanzia" in ordini_selezionati:
        prefixes.append("Bollettini/AA/")
    if "primaria" in ordini_selezionati:
        prefixes.append("Bollettini/EE/")
    if "secondaria_i" in ordini_selezionati:
        prefixes.append("Bollettini/MM/")
    if "secondaria_ii" in ordini_selezionati:
        prefixes.append("Bollettini/SS/")

    # Cartelle di estrazione graduatorie per ricavare il totale iscritti reale
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
        root_files = get_all_repo_files(repo)
        
        # 1. INDIVIDUA FILE BOLLETTINO
        bollettino_files = []
        for codice in codici_validi:
            possible_codes = CODICI_EQUIVALENTI.get(codice, set())
            possible_codes.add(codice)
            for f in root_files:
                if any(f.path.startswith(p) for p in prefixes) and f.name.lower().endswith('.csv'):
                    fname = f.name.upper()
                    if any(f"_{pc}.CSV" in fname for pc in possible_codes):
                        bollettino_files.append(f)
                        break
        
        # 2. INDIVIDUA FILE GRADUATORIE (PER OTTENERE IL NUMERO DI ISCRITTI REALI)
        grad_files = []
        for codice in codici_validi:
            possible_codes = CODICI_EQUIVALENTI.get(codice, set())
            possible_codes.add(codice)
            for f in root_files:
                if any(f.path.startswith(p) for p in grad_prefixes) and f.name.lower().endswith('.csv'):
                    fname = f.name.upper()
                    if any(pc in fname for pc in possible_codes):
                        grad_files.append(f)
                        break

        if not bollettino_files:
            return jsonify({"error": "Nessun file bollettino trovato per le classi selezionate."}), 404

        # 3. CONTA CANDIDATI TOTALI PER PROVINCIA DAI FILE GRADUATORIA
        total_candidates = {}
        for file_obj in grad_files:
            try:
                if hasattr(file_obj, 'download_url') and file_obj.download_url:
                    response = requests.get(file_obj.download_url)
                    file_data = response.content
                else:
                    file_data = file_obj.decoded_content
                csv_text = file_data.decode('utf-8-sig', errors='ignore')
                csv_text = clean_csv_text(csv_text)
                df_grad = pd.read_csv(io.StringIO(csv_text), sep=';', dtype=str, skipinitialspace=True)
                df_grad.columns = [str(c).strip().upper() for c in df_grad.columns]
                
                for _, row in df_grad.iterrows():
                    val_prov = str(row.get('UFFICIO PROVINCIALE', '')).strip()
                    if val_prov and val_prov.upper() not in ('NAN', 'NONE'):
                        sigla = to_sigla(val_prov)
                        if sigla:
                            _, nome = PROVINCE_DATA[sigla]
                            val_cog = str(row.get('COGNOME', '')).strip()
                            if val_cog and val_cog.upper() not in ('NAN', 'NONE', ''):
                                total_candidates[nome] = total_candidates.get(nome, 0) + 1
            except Exception as e:
                logger.error(f"Errore lettura graduatoria {file_obj.path}: {e}")
                continue

        # 4. ELABORA BOLLETTINO PER NOMINE, CUT-OFF E POSIZIONI
        results = {}
        for file_obj in bollettino_files:
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

            df.columns = [str(c).strip().upper() for c in df.columns]
            current_prov = None
            current_region = None
            current_prov_selected = False
            
            for _, row in df.iterrows():
                val_prov = str(row.get('UFFICIO PROVINCIALE', '')).strip()
                val_classe = str(row.get('CLASSE DI CONCORSO', '')).strip()
                
                # Ignora righe "NOMINA N 1" come richiesto
                if 'NOMINA' in val_prov.upper() or 'NOMINA' in val_classe.upper():
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
                
                if not val_classe or val_classe in ('nan', 'None'):
                    continue
                    
                is_data = any(cod in val_classe.upper() for cod in codici_validi)
                
                if is_data:
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
                        punt_val = row.get('PUNTEGGIO')
                        punt = pulisci_punteggio(punt_val)
                        if punt is None:
                            continue
                            
                        contratto = str(row.get('TIPO CONTRATTO', '')).strip().upper()
                        cog = str(row.get('COGNOME ASPIRANTE', '')).strip().upper()
                        nom = str(row.get('NOME ASPIRANTE', '')).strip().upper()
                        candidato_id = f"{cog}_{nom}"
                    except (ValueError, TypeError):
                        continue
                        
                    if current_prov not in results:
                        results[current_prov] = {
                            "regione": current_region, 
                            "nomine_totali": 0, "nominati_univoci": set(),
                            "max_posizione": 0, 
                            "min_31_08": None, "min_30_06": None, "min_spezzoni": None
                        }
                        
                    prov_data = results[current_prov]
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

    except Exception as e:
        logger.error(f"Errore critico lettura bollettino: {str(e)}", exc_info=True)
        return jsonify({"error": f"Errore lettura bollettino: {str(e)}"}), 500

    # 5. CALCOLO METRICHE FINALI E OUTPUT
    out_data = []
    for prov, r in results.items():
        tot_cand = total_candidates.get(prov, 0)
        nominati_univoci = len(r["nominati_univoci"])
        
        assorbimento = round((nominati_univoci / tot_cand) * 100, 2) if tot_cand > 0 else 0
        max_pos = r["max_posizione"]
        rinuncia = round(((max_pos - nominati_univoci) / max_pos) * 100, 2) if max_pos > 0 else 0
        
        def fmt(val):
            if val is None: return "N/D"
            s = str(val).replace('.', ',')
            if s.endswith(',0'): s = s.replace(',0', '')
            return s
            
        out_data.append({
            "regione": r['regione'], "provincia": prov, 
            "candidati_totali": tot_cand, "nomine_totali": r["nomine_totali"],
            "nominati_univoci": nominati_univoci, "assorbimento": assorbimento,
            "max_posizione": max_pos, "rinuncia": rinuncia,
            "cut_31_08": fmt(r["min_31_08"]), 
            "cut_30_06": fmt(r["min_30_06"]), 
            "cut_spezzoni": fmt(r["min_spezzoni"])
        })
        
    return jsonify({"data": out_data})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
