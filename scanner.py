import os
import re
import io
import logging
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
MAX_ROWS_PDF = 500

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
    "VT": ("Lazio", "Viterbo"
)}
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

SCUOLE_MUSICALI = {
    "Agrigento": 54, "Alessandria": 9, "Ancona": 18, "Aosta": 0, "Arezzo": 13,
    "Ascoli Piceno": 10, "Asti": 4, "Avellino": 65, "Bari": 44, "Barletta-Andria-Trani": 10,
    "Belluno": 13, "Benevento": 36, "Bergamo": 22, "Biella": 5, "Bologna": 23,
    "Bolzano": 3, "Brescia": 25, "Brindisi": 26, "Cagliari": 18, "Caltanissetta": 28,
    "Campobasso": 25, "Caserta": 63, "Catania": 61, "Catanzaro": 36, "Chieti": 15,
    "Como": 14, "Cosenza": 112, "Cremona": 15, "Crotone": 26, "Cuneo": 12,
    "Enna": 21, "Fermo": 13, "Ferrara": 7, "Firenze": 28, "Foggia": 43,
    "Forlì-Cesena": 8, "Frosinone": 38, "Gallura Nord-Est Sardegna": 0, "Genova": 16, "Gorizia": 3,
    "Grosseto": 9, "Imperia": 2, "Isernia": 16, "L'Aquila": 21, "La Spezia": 10,
    "Latina": 22, "Lecce": 57, "Lecco": 7, "Livorno": 12, "Lodi": 3,
    "Lucca": 17, "Macerata": 9, "Mantova": 9, "Massa-Carrara": 10, "Matera": 21,
    "Medio Campidano": 0, "Messina": 36, "Milano": 51, "Modena": 6, "Monza e della Brianza": 14,
    "Napoli": 116, "Novara": 10, "Nuoro": 10, "Ogliastra": 0, "Oristano": 6,
    "Padova": 36, "Palermo": 107, "Parma": 10, "Pavia": 7, "Perugia": 18,
    "Pesaro e Urbino": 16, "Pescara": 20, "Piacenza": 10, "Pisa": 12, "Pistoia": 12,
    "Pordenone": 3, "Potenza": 38, "Prato": 13, "Ragusa": 23, "Ravenna": 5,
    "Reggio Calabria": 44, "Reggio Emilia": 4, "Rieti": 19, "Rimini": 5, "Roma": 69,
    "Rovigo": 25, "Salerno": 80, "Sassari": 40, "Savona": 4, "Siena": 9,
    "Siracusa": 23, "Sondrio": 11, "Sulcis Iglesiente": 0, "Taranto": 26, "Teramo": 15,
    "Terni": 5, "Torino": 49, "Trapani": 38, "Trento": 0, "Treviso": 51,
    "Trieste": 6, "Udine": 6, "Varese": 17, "Venezia": 29, "Verbano-Cusio-Ossola": 6,
    "Vercelli": 9, "Verona": 26, "Vibo Valentia": 38, "Vicenza": 43, "Viterbo": 18
}

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_string(s):
    return re.sub(r'[\s_-]+', '', str(s)).upper()

def pulisci_punteggio(valore):
    """
    Converte stringhe sporche come '83 | 50' in 83.5 (float per i calcoli).
    Mantiene i decimali senza arrotondamenti.
    """
    s = str(valore).strip()
    if not s or s.lower() in ['nan', 'none', '*', '-', '']:
        return None
        
    s = s.replace('*', '')
    
    # Se il punteggio ha la barra (es. "83 | 50"), ricostruiamo il decimale -> "83.50"
    if ' | ' in s:
        parti = s.split(' | ')
        intero = parti[0].strip().replace(',', '.')
        decimale = parti[1].strip()
        s = f"{intero}.{decimale}"
    else:
        # Sostituisce la virgola con il punto per i normali decimali "83,5" -> "83.5"
        s = s.replace(',', '.')
        
    # Estrae il numero decimale pulito
    match = re.search(r'(\d+\.?\d*)', s)
    if match:
        return float(match.group(1))
    return None

def clean_csv_text(raw_text):
    """
    Pulisce il testo grezzo del CSV.
    Rimuove eventuali numeri di riga iniziali (es. "1 | ") che causano 
    errori nel parsing di Pandas, e gestisce la BOM (UTF-8 BOM).
    """
    text = raw_text.lstrip('\ufeff')
    # Rimuove pattern del tipo "123 | " all'inizio di ogni riga
    text = re.sub(r'^\d+\s*\|\s*', '', text, flags=re.MULTILINE)
    return text

def get_all_repo_files(repo, path=""):
    """Scansiona tutto il repo per trovare i file csv in qualsiasi sottocartella."""
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
    
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = get_all_repo_files(repo)
        logger.info(f"Trovati {len(root_files)} file totali nel repository.")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    NOME_TO_SIGLA = {nome.upper().replace(" ", "").replace("'", ""): sigla for sigla, (region, nome) in PROVINCE_DATA.items()}

    def to_sigla(val):
        v = str(val).strip().upper().replace(" ", "").replace("'", "")
        if v in PROVINCE_DATA: return v
        if v in NOME_TO_SIGLA: return NOME_TO_SIGLA[v]
        for nome, sigla in NOME_TO_SIGLA.items():
            if nome in v: return sigla
        return None

    for codice in codici_validi:
        fascia_norm = normalize_string(fascia_richiesta) if fascia_richiesta else ""
        codice_upper = codice.upper()
        
        expected_prefix = f"RISULTATO_ESTRAZIONE_{codice_upper}_"
        
        file_da_elaborare = []
        nomi_file_visti = set()
        
        for f in root_files:
            if hasattr(f, 'type') and f.type != 'file':
                continue
            if f.name.startswith('~$'):
                continue
                
            # MATCH ESATTO SUL PREFISSO DEL NOME FILE - ORA CERCA SOLO .CSV
            if f.name.upper().startswith(expected_prefix) and f.name.lower().endswith('.csv'):
                if f.name in nomi_file_visti:
                    continue
                    
                if fascia_norm:
                    file_fascia_part = f.name.upper()[len(expected_prefix):].replace('.CSV', '')
                    file_fascia_norm = normalize_string(file_fascia_part)
                    if file_fascia_norm == fascia_norm:
                        file_da_elaborare.append(f)
                        nomi_file_visti.add(f.name)
                else:
                    file_da_elaborare.append(f)
                    nomi_file_visti.add(f.name)

        if not file_da_elaborare:
            logger.warning(f"Nessun file trovato per il codice: {codice}")
            continue

        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(0, 10, text=sanitize_for_fpdf(f"Classe di Concorso: {codice}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

        try:
            lista_dati = []
            for file_trovato in file_da_elaborare:
                try:
                    file_content = repo.get_contents(file_trovato.path)
                    file_data = file_content.decoded_content
                    
                    # Decodifica e pulisce il testo del CSV
                    csv_text = file_data.decode('utf-8-sig', errors='ignore')
                    csv_text = clean_csv_text(csv_text)

                    try:
                        csv_io = io.StringIO(csv_text)
                        # dtype=str previene che 1 diventi 1.0 o che numeri con virgola si rompano
                        df_temp = pd.read_csv(csv_io, sep=';', dtype=str) 
                    except Exception as e:
                        logger.error(f"ERRORE LETTURA CSV per {file_trovato.name}: {e}", exc_info=True)
                        continue
                    
                    fascia_nome = file_trovato.name.split(codice)[-1].replace("_", " ").replace(".csv", "").strip().upper()
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
                return  3
            
            lista_dati.sort(key=lambda x: get_fascia_order(x[1]))

            for df, nome_fascia in lista_dati:
                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]

                df.rename(columns={
                    'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE': 'CODICE GRADUATORIA',
                    'ORDINE SCUOLA GRADUATORIA': 'ORDINE SCUOLA'
                }, inplace=True, errors='ignore')

                # ============================================================
                # FILTRO RIGOROSO: MANTIENI SOLO LA CLASSE SELEZIONATA
                # ============================================================
                col_classe = None
                for col in df.columns:
                    col_upper = str(col).strip().upper()
                    if col_upper in {
                        'CODICE GRADUATORIA',
                        'CODICE GRADUATORIA DI INCLUSIONE E DESCRIZIONE',
                        'CLASSE DI CONCORSO'
                    }:
                        col_classe = col
                        break

                if col_classe and not df.empty:
                    def contiene_classe_esatta(valore, classe_target):
                        if pd.isna(valore):
                            return False
                        testo = str(valore).upper().strip()
                        testo = testo.replace('-', ' ')
                        testo = testo.replace('_', ' ')
                        testo = re.sub(r'\s+', ' ', testo)
                        codici = re.findall(
                            r'(?<![A-Z0-9])'
                            r'(?:A\d{3}|A[A-Z]\d{2}|ADMM|ADSS|ADEE|ADAA)'
                            r'(?![A-Z0-9])',
                            testo
                        )
                        codici = {c.upper() for c in codici}
                        return classe_target.upper() in codici

                    prima = len(df)
                    df = df[
                        df[col_classe].apply(
                            lambda x: contiene_classe_esatta(x, codice_upper)
                        )
                    ].copy()
                    dopo = len(df)
                    logger.info(f"[{codice_upper}] FILTRO CLASSE: {prima} -> {dopo}")
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

                useless_cols = [
                    'CODICE TIPOLOGIA LINGUA GRADUATORIA DI INCLUSIONE',
                    'INCLUSIONE CON RISERVA',
                    'COGNOME',
                    'NOME',
                    'ORIGINE'
                ]
                df.columns = df.columns.astype(str).str.strip()
                df = df.drop(columns=[c for c in useless_cols if c in df.columns], errors='ignore')

                # BUG FIX: Cerca la colonna specifica del punteggio TOTALE, non la prima che contiene "punteggio"
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
                        
                        num_scuole = SCUOLE_MUSICALI.get(nome_esteso, 0)
                        num_candidati = int(count)
                        rapporto = round(num_scuole / num_candidati, 4) if num_candidati > 0 else 0
                        
                        top_candidate = "N/D"
                        bottom_candidate = "N/D"
                        median_score = 0.0
                        
                        if col_punteggio_sep:
                            prov_df = df[df[col_ufficio] == sigla_str].copy()
                            # Usa la nuova funzione per estrarre TUTTO il numero, decimali inclusi
                            prov_df['punteggio_num'] = prov_df[col_punteggio_sep].apply(pulisci_punteggio)
                            prov_df = prov_df.dropna(subset=['punteggio_num'])
                            
                            if not prov_df.empty:
                                idx_max = prov_df['punteggio_num'].idxmax()
                                idx_min = prov_df['punteggio_num'].idxmin()
                                max_score = float(prov_df.loc[idx_max, 'punteggio_num'])
                                min_score = float(prov_df.loc[idx_min, 'punteggio_num'])
                                median_score = float(prov_df['punteggio_num'].median())
                                
                                # Formatta mantenendo la virgola e i decimali reali (es. 83,5 o 83,50)
                                top_candidate = str(max_score).replace('.', ',')
                                bottom_candidate = str(min_score).replace('.', ',')
                                # Se il numero è intero (es. 168.0), rimuove il ",0"
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
                            if top_candidate != "N/D": stats_data[nome_esteso]["top"] = top_candidate
                            if bottom_candidate != "N/D": stats_data[nome_esteso]["bottom"] = bottom_candidate
                            if median_score > 0: stats_data[nome_esteso]["median"] = median_score

                pdf.set_font("Helvetica", 'B', 12)
                pdf.cell(0, 10, text=sanitize_for_fpdf(nome_fascia), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
                pdf.ln(2)

                if len(df) > MAX_ROWS_PDF:
                    df = df.head(MAX_ROWS_PDF)
                    pdf.set_font("Helvetica", 'I', 8)
                    pdf.cell(0, 6, text=sanitize_for_fpdf(f"Avviso: Mostrati solo i primi {MAX_ROWS_PDF} record per motivi di spazio."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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

    if not trovato_almeno_uno:
        pdf.cell(0, 10, text="Nessun dato disponibile per i filtri selezionati.", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    pdf_bytes = pdf.output()

    import base64
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

    return jsonify({
        "pdf_base64": pdf_base64,
        "stats": stats_data
    })


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

    codici_validi = [c.split(' - ')[0].strip().upper() for c in classi_selezionate]

    try:
        repo = g.get_repo(REPO_NAME)
        root_files = get_all_repo_files(repo)
        # Aggiornato per cercare il file CSV del bollettino
        file_obj = next((f for f in root_files if f.name.upper() == "RISULTATO_ESTRAZIONE_BOLLETTINI.CSV"), None)
        if not file_obj:
            return jsonify({"error": "File Risultato_Estrazione_Bollettini.csv non trovato nel repository."}), 404
        
        file_data = file_obj.decoded_content
        csv_text = file_data.decode('utf-8-sig', errors='ignore')
        csv_text = clean_csv_text(csv_text)
        df = pd.read_csv(io.StringIO(csv_text), sep=';', dtype=str)
    except Exception as e:
        return jsonify({"error": f"Errore lettura bollettino: {str(e)}"}), 500

    df.columns = [str(c).strip() for c in df.columns]
    
    results = {}
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
                    
                # Usa la funzione di pulizia per mantenere i decimali
                punt = pulisci_punteggio(punt_val)
                if punt is None:
                    continue
                    
            except (ValueError, TypeError):
                continue

            if current_prov not in results:
                results[current_prov] = {
                    "regione": current_region,
                    "nomine_totali": 0,
                    "nomine_f1": 0,
                    "nomine_f2": 0,
                    "min_f1": None,
                    "min_f2": None
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
            matched_prov = False
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
                    matched_prov = True
                    break

    out_data = []
    for prov, r in results.items():
        assorb_f1 = round((r["nomine_f1"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        prob_f1 = round((r["nomine_f1"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        prob_f2 = round((r["nomine_f2"] / r["nomine_totali"]) * 100, 2) if r["nomine_totali"] > 0 else 0
        
        # Formattazione finale che mantiene la virgola e i decimali reali, senza forzare .00
        min_f1_str = str(r['min_f1']).replace('.', ',') if r['min_f1'] is not None else "N/D"
        min_f2_str = str(r['min_f2']).replace('.', ',') if r['min_f2'] is not None else "N/D"
        if min_f1_str.endswith(',0'): min_f1_str = min_f1_str.replace(',0', '')
        if min_f2_str.endswith(',0'): min_f2_str = min_f2_str.replace(',0', '')
        
        out_data.append({
            "regione": r['regione'],
            "provincia": prov,
            "nomine_totali": r["nomine_totali"],
            "min_f1": min_f1_str,
            "min_f2": min_f2_str,
            "assorbimento_f1": assorb_f1,
            "prob_f1": prob_f1,
            "prob_f2": prob_f2,
            "nomine_f1": r["nomine_f1"],
            "nomine_f2": r["nomine_f2"]
        })

    return jsonify({"data": out_data})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
