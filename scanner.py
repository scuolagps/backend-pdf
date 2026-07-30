import os
import re
import io
import logging
from flask import Flask, request, send_file, jsonifyimport os
import re
import io
import logging
from flask import Flask, request, send_file, jsonify
from fpdf import FPDF
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
REPO_NAME = os.environ.get("REPO_NAME", "TuoUsernameGithub/dati-privati-pdf")

g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
if not g:
    logger.error("ATTENZIONE: GITHUB_TOKEN non trovato nelle variabili d'ambiente!")

CODICE_CLASSE_PATTERN = re.compile(r'^[A-Z0-9]{1,10}$')
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
    "VT": ("Lazio", "Viterbo")
}
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

# Dizionario delle scuole per il calcolo del grafico
SCUOLE_MUSICALI = {
    "Agrigento": 54, "Alessandria": 9, "Ancona": 18, "Aosta": 0, "Ascoli Piceno": 10,
    "Asti": 4, "Avellino": 65, "Bari": 44, "Barletta-Andria-Trani": 10, "Belluno": 13,
    "Benevento": 36, "Bergamo": 22, "Biella": 5, "Bologna": 23, "Bolzano": 3,
    "Brescia": 25, "Brindisi": 26, "Cagliari": 18, "Caltanissetta": 28, "Campobasso": 25,
    "Caserta": 63, "Catania": 61, "Catanzaro": 36, "Chieti": 15, "Como": 14,
    "Cosenza": 112, "Cremona": 15, "Crotone": 26, "Cuneo": 12, "Enna": 21,
    "Fermo": 13, "Ferrara": 7, "Firenze": 28, "Foggia": 43, "Forlì-Cesena": 0,
    "Frosinone": 38, "Genova": 16, "Gorizia": 0, "Grosseto": 9, "Imperia": 2,
    "Isernia": 16, "L'Aquila": 21, "La Spezia": 10, "Latina": 22, "Lecce": 57,
    "Lecco": 7, "Livorno": 12, "Lodi": 3, "Lucca": 17, "Macerata": 9,
    "Mantova": 9, "Massa-Carrara": 10, "Matera": 21, "Messina": 36, "Milano": 51,
    "Modena": 6, "Monza e della Brianza": 14, "Napoli": 116, "Novara": 10, "Nuoro": 10,
    "Oristano": 6, "Padova": 36, "Palermo": 107, "Parma": 10, "Pavia": 7,
    "Perugia": 18, "Pesaro e Urbino": 0, "Pescara": 20, "Piacenza": 0, "Pisa": 12,
    "Pistoia": 12, "Pordenone": 0, "Potenza": 38, "Prato": 13, "Ragusa": 23,
    "Ravenna": 5, "Reggio Calabria": 44, "Reggio Emilia": 4, "Rieti": 19, "Rimini": 5,
    "Roma": 69, "Rovigo": 25, "Salerno": 80, "Sassari": 40, "Savona": 4,
    "Siena": 9, "Siracusa": 23, "Sondrio": 11, "Taranto": 26, "Teramo": 15,
    "Terni": 5, "Torino": 49, "Trapani": 38, "Trento": 0, "Treviso": 51,
    "Trieste": 0, "Udine": 0, "Varese": 17, "Venezia": 29, "Verbano-Cusio-Ossola": 6,
    "Vercelli": 9, "Verona": 26, "Vibo Valentia": 38, "Vicenza": 43, "Viterbo": 18
}

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_string(s):
    return re.sub(r'[\s_-]+', '', str(s)).upper()

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

    if not isinstance(province_nomi, list) or not isinstance(regioni_richieste, list):
        return jsonify({"error": "Formato regioni/province non valido."}), 400
    if not isinstance(classi_selezionate, list) or not classi_selezionate:
        return jsonify({"error": "Nessuna classe selezionata."}), 400
    if len(classi_selezionate) > MAX_CLASSI:
        return jsonify({"error": f"Numero massimo di classi consentito: {MAX_CLASSI}"}), 400

    province_sigle = []
    for prov in province_nomi:
        sigla = PROVINCE_SIGLE.get(prov)
        if sigla:
            province_sigle.append(sigla)
    # --- DEBUG 1: Vediamo cosa arriva dal frontend ---
    logger.info(f"DEBUG 1: Filtri ricevuti -> Classi: {classi_selezionate} | Province Nomi: {province_nomi} | Sigle generate: {province_sigle} | Fascia: '{fascia_richiesta}' (Normalizzata: '{normalize_string(fascia_richiesta)}')")
    codici_validi = []
    for codice in classi_selezionate:
        identificativo = codice.split(' - ')[0].strip()
        if not identificativo:
            return jsonify({"error": "Uno o più codici classe non sono validi."}), 400
        codici_validi.append(identificativo)

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=sanitize_for_fpdf("Report Estrazione Dati Filtrati"), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    
    safe_regioni = sanitize_for_fpdf(", ".join(regioni_richieste).upper() if regioni_richieste else 'TUTTE')
    safe_province = sanitize_for_fpdf(", ".join(province_nomi).upper() if province_nomi else 'TUTTE')
    filtro_luogo = f"Regioni: {safe_regioni} | Province: {safe_province}"
    pdf.cell(0, 10, txt=filtro_luogo, ln=True, align='C')
    pdf.ln(5)

    trovato_almeno_uno = False
    stats_data = {} 
    all_dfs = []
    
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = repo.get_contents("")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    for codice in codici_validi:
        fascia_norm = normalize_string(fascia_richiesta) if fascia_richiesta else ""
        codice_norm = normalize_string(codice)
        
        file_da_elaborare = []
        nomi_visti = set() # Fix per evitare duplicati
        for f in root_files:
            nome_file_norm = normalize_string(f.name)
            # --- DEBUG 2: Vediamo come matchano i file ---
            if codice_norm in nome_file_norm and nome_file_norm.endswith(".XLSX") and f.name not in nomi_visti:
                nomi_visti.add(f.name)
                logger.info(f"DEBUG 2: Trovato file pertinente: '{f.name}' (Normalizzato: '{nome_file_norm}')")
                
                # Se il tuo file si chiama solo "AM56_I_Fascia.xlsx", non contiene "RISULTATOESTRAZIONE"
                # e quindi il filtro originale lo scartava! Usiamo questo più permissivo:
                parte_dopo_codice = nome_file_norm.split(codice_norm)[-1]
                
                if fascia_norm:
                    if parte_dopo_codice == fascia_norm + ".XLSX":
                        logger.info(f"DEBUG 2: -> File AMMESSO per la fascia '{fascia_norm}'")
                        file_da_elaborare.append(f)
                    else:
                        logger.info(f"DEBUG 2: -> File SCARTATO. La parte dopo il codice è '{parte_dopo_codice}' ma la fascia cercata è '{fascia_norm}.XLSX'")
                else:
                    file_da_elaborare.append(f)
                if fascia_norm:
                    parte_dopo_codice = nome_file_norm.split(codice_norm)[1]
                    if parte_dopo_codice == fascia_norm + ".XLSX":
                        file_da_elaborare.append(f)
                else:
                    file_da_elaborare.append(f)

        if not file_da_elaborare:
            continue

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Classe di Concorso: {codice}"), ln=True)
        pdf.ln(2)

        try:
            # Scarichiamo tutti i file trovati
            lista_dati = []
            logger.info(f"DEBUG: File da elaborare per {codice}: {[f.name for f in file_da_elaborare]}")
            for file_trovato in file_da_elaborare:
                try:
                    file_content = repo.get_contents(file_trovato.path)
                    file_data = file_content.decoded_content
                    
                    if len(file_data) > 10 * 1024 * 1024: 
                        logger.warning(f"File {file_trovato.name} troppo grande. Salto.")
                        continue
                        
                    excel_io = io.BytesIO(file_data)
                    df_temp = pd.read_excel(excel_io, engine='openpyxl')
                    # --- DEBUG 3: Vediamo se l'Excel si legge e quante righe ha ---
                    logger.info(f"DEBUG 3: File '{file_trovato.name}' letto. Righe totali nel foglio Excel: {len(df_temp)}")
                    
                    # Estrai il nome della fascia dal nome del file
                    # Es: "Risultato_Estrazione_AM56_I fascia.xlsx" -> "I FASCIA"
                    fascia_nome = file_trovato.name.split(codice)[-1].replace("_", " ").replace(".xlsx", "").strip().upper()
                    if not fascia_nome:
                        fascia_nome = "DETTAGLI"
                        
                    lista_dati.append((df_temp, fascia_nome))
                except Exception as e:
                    logger.error(f"Errore lettura file {file_trovato.name}: {str(e)}")
            
            if not lista_dati:
                continue

            # Elaboriamo un file (e quindi una fascia) alla volta
            for df, nome_fascia in lista_dati:
                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
                logger.info(f"DEBUG: Inizio stampa PDF per fascia '{nome_fascia}' con {len(df)} righe.")

                if province_sigle:
                    col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                    
                    # --- DEBUG 4: Vediamo cosa contiene la colonna provincia ---
                    if col_ufficio:
                        valori_unici = df[col_ufficio].astype(str).str.strip().str.upper().unique()
                        logger.info(f"DEBUG 4: Colonna trovata: '{col_ufficio}'. Valori presenti nel file: {valori_unici}")
                        
                        df[col_ufficio] = df[col_ufficio].astype(str).str.strip().str.upper()
                        df = df[df[col_ufficio].isin(province_sigle)]
                        df = df[df[col_ufficio].str.len() == 2]
                        
                        logger.info(f"DEBUG 4: Righe rimaste dopo il filtro provincia (cercavi {province_sigle}): {len(df)}")
                    else:
                        logger.warning("DEBUG 4: Nessuna colonna 'UFFICIO' o 'PROVINCIA' trovata nel file Excel!")
                        df = pd.DataFrame()

                if df.empty:
                    continue

                # --- CALCOLO STATISTICHE RAPPORTO S/C E PUNTEGGI ---
                col_ufficio_sep = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                # Cerchiamo la colonna del punteggio
                col_punteggio_sep = next((col for col in df.columns if 'PUNTEGGIO' in str(col).upper() or 'TOTALE' in str(col).upper() or 'VOTO' in str(col).upper()), None)
                
                if col_ufficio_sep:
                    counts = df[col_ufficio_sep].value_counts()
                    for sigla, count in counts.items():
                        sigla_str = str(sigla).upper()
                        region_name, nome_esteso = PROVINCE_DATA.get(sigla_str, ("", sigla_str))
                        
                        num_scuole = SCUOLE_MUSICALI.get(nome_esteso, 0)
                        num_candidati = int(count)
                        
                        if num_candidati > 0:
                            rapporto = round(num_scuole / num_candidati, 4)
                        else:
                            rapporto = 0
                            
                        # Inizializziamo i dati punteggio
                        top_candidate = "N/D"
                        bottom_candidate = "N/D"
                        median_score = 0.0
                        
                        if col_punteggio_sep:
                            prov_df = df[df[col_ufficio_sep] == sigla_str].copy()
                            # Pulizia punteggio: gestisce virgole e spazi per renderli numerici
                            prov_df['punteggio_num'] = prov_df[col_punteggio_sep].astype(str).str.replace(',', '.').str.extract(r'(\d+\.?\d*)')[0]
                            prov_df = prov_df.dropna(subset=['punteggio_num'])
                            prov_df['punteggio_num'] = pd.to_numeric(prov_df['punteggio_num'], errors='coerce')
                            prov_df = prov_df.dropna(subset=['punteggio_num'])
                            
                            if not prov_df.empty:
                                idx_max = prov_df['punteggio_num'].idxmax()
                                idx_min = prov_df['punteggio_num'].idxmin()
                                
                                col_cognome = next((c for c in prov_df.columns if 'COGNOME' in str(c).upper()), None)
                                col_nome = next((c for c in prov_df.columns if str(c).strip().upper() == 'NOME'), None)
                                
                                def get_name(row):
                                    name = ""
                                    if col_cognome and pd.notna(row.get(col_cognome)): name += str(row[col_cognome]) + " "
                                    if col_nome and pd.notna(row.get(col_nome)): name += str(row[col_nome])
                                    return name.strip() or "N/D"
                                    
                                max_name = get_name(prov_df.loc[idx_max])
                                min_name = get_name(prov_df.loc[idx_min])
                                
                                max_score = float(prov_df.loc[idx_max, 'punteggio_num'])
                                min_score = float(prov_df.loc[idx_min, 'punteggio_num'])
                                median_score = float(prov_df['punteggio_num'].median())
                                
                                top_candidate = f"{max_name} ({max_score:.2f})"
                                bottom_candidate = f"{min_name} ({min_score:.2f})"
                                
                        if nome_esteso not in stats_data:
                            stats_data[nome_esteso] = {
                                "scuole": num_scuole,
                                "candidati": num_candidati,
                                "rapporto": rapporto,
                                "regione": region_name,
                                "top": top_candidate,
                                "bottom": bottom_candidate,
                                "median": median_score
                            }
                        else:
                            stats_data[nome_esteso]["candidati"] += num_candidati
                            stats_data[nome_esteso]["rapporto"] = round(stats_data[nome_esteso]["scuole"] / stats_data[nome_esteso]["candidati"], 4)
                            if top_candidate != "N/D":
                                stats_data[nome_esteso]["top"] = top_candidate
                            if bottom_candidate != "N/D":
                                stats_data[nome_esteso]["bottom"] = bottom_candidate
                            if median_score > 0:
                                stats_data[nome_esteso]["median"] = median_score
                # ----------------------------------------------------

                # --- INTESTAZIONE FASCIA ---
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, txt=sanitize_for_fpdf(nome_fascia), ln=True, align='L')
                pdf.ln(2)

                if len(df) > MAX_ROWS_PDF:
                    df = df.head(MAX_ROWS_PDF)
                    pdf.set_font("Arial", 'I', 8)
                    pdf.cell(0, 6, txt=sanitize_for_fpdf(f"Avviso: Mostrati solo i primi {MAX_ROWS_PDF} record per motivi di spazio."), ln=True)

                def is_empty(val):
                    v = str(val).strip().lower()
                    return v in ['nan', '*', 'none', '', '-']
                
                cols_to_drop = []
                for col in df.columns:
                    unique_vals = [val for val in df[col].unique() if not is_empty(val)]
                    
                    # FIX: Non scartare mai la colonna UFFICIO/PROVINCIA, serve per i raggruppamenti nel PDF!
                    col_upper = str(col).upper()
                    is_ufficio_col = 'UFFICIO' in col_upper or 'PROVINCIA' in col_upper
                    
                    if len(unique_vals) <= 1 and not is_ufficio_col:
                        cols_to_drop.append(col)
                        
                    if 'pdf' in str(col).lower() or 'xls' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower():
                        cols_to_drop.append(col)
                        
                df = df.drop(columns=cols_to_drop, errors='ignore')

                def format_val(val):
                    s = str(val).strip()
                    if s.lower() in ['nan', 'none', ''] or s == '*':
                        return "-"
                    if s.endswith('.0'):
                        try:
                            f = float(s)
                            if f.is_integer():
                                return str(int(f))
                        except ValueError:
                            pass
                    return s

                col_widths = {}
                total_width = 0
                for col in df.columns:
                    max_len = len(str(col))
                    for val in df[col].head(100):
                        val_str = format_val(val)
                        if len(val_str) > max_len:
                            max_len = len(val_str)
                    
                    width = min(max_len * 2.2, 50)
                    if str(col).upper() in ['UFFICIO PROVINCIALE', 'UFFICIO', 'PROVINCIA']:
                        width = 20 
                    if str(col).upper() in ['COGNOME', 'NOME']:
                        width = max(width, 35)
                    if 'TOTALE' in str(col).upper() or 'PUNTEGGIO' in str(col).upper():
                        width = max(width, 25)
                    if 'POSIZIONE' in str(col).upper():
                        width = max(width, 20)
                        
                    width = max(width, 15)
                    col_widths[col] = width
                    total_width += width

                page_width = 277
                if total_width > page_width:
                    scale = page_width / total_width
                    for col in col_widths:
                        col_widths[col] *= scale

                pdf.set_font("Arial", 'B', 9)
                line_height = 5
                
                max_lines = 1
                header_lines_map = {}
                for col in df.columns:
                    char_limit = max(1, int(col_widths[col] / 1.8))
                    text = sanitize_for_fpdf(str(col))
                    lines = 0
                    current_line_len = 0
                    for word in text.split():
                        if current_line_len + len(word) + 1 > char_limit:
                            lines += 1
                            current_line_len = len(word)
                        else:
                            current_line_len += len(word) + 1
                    if current_line_len > 0 or lines == 0:
                        lines += 1
                    header_lines_map[col] = lines
                    if lines > max_lines:
                        max_lines = lines

                max_header_height = max_lines * line_height

                def draw_table_header():
                    y_start = pdf.get_y()
                    for col in df.columns:
                        x_start = pdf.get_x()
                        text = sanitize_for_fpdf(str(col))
                        lines_needed = max_lines - header_lines_map[col]
                        if lines_needed > 0:
                            text += "\n" * lines_needed
                        pdf.multi_cell(col_widths[col], line_height, text, border=1, align='L')
                        pdf.set_xy(x_start + col_widths[col], y_start)
                    pdf.set_y(y_start + max_header_height)

                draw_table_header()

                current_prov_sigla = None
                current_region = None
                
                pdf.set_font("Arial", size=9)
                for _, row in df.iterrows():
                    if col_ufficio_sep:
                        prov_sigla = format_val(row[col_ufficio_sep]).upper()
                        if prov_sigla != current_prov_sigla:
                            current_prov_sigla = prov_sigla
                            region_name, prov_full_name = PROVINCE_DATA.get(prov_sigla, ("", prov_sigla))
                            
                            if pdf.get_y() + 20 > 190:
                                pdf.add_page()
                                draw_table_header()
                            
                            pdf.ln(4)
                            
                            if region_name and region_name != current_region:
                                current_region = region_name
                                pdf.set_font("Arial", 'B', 12) 
                                pdf.cell(0, 7, txt=sanitize_for_fpdf(region_name.upper()), ln=True, align='L')
                            
                            if prov_full_name:
                                pdf.set_font("Arial", 'B', 10)
                                pdf.cell(0, 6, txt=sanitize_for_fpdf(prov_full_name.upper()), ln=True, align='L')
                            
                            pdf.ln(2)
                            pdf.set_font("Arial", size=9)

                    if pdf.get_y() + 6 > 190:
                        pdf.add_page()
                        draw_table_header()
                        pdf.set_font("Arial", size=9)

                    for col in df.columns:
                        valore = sanitize_for_fpdf(format_val(row[col]))
                        char_lim = max(1, int(col_widths[col] / 2.0))
                        if len(valore) > char_lim:
                            valore = valore[:char_lim-3] + "..."
                        
                        align = 'R' if valore.replace('.', '', 1).replace(',', '', 1).replace('-', '', 1).isdigit() else 'L'
                        pdf.cell(col_widths[col], 6, valore, border=1, align=align)
                    pdf.ln(6)

            pdf.ln(8)
            trovato_almeno_uno = True
            
        except Exception as e:
            logger.error(f"Errore elaborazione file: {str(e)}")
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Errore interno durante l'elaborazione della classe {codice}."), ln=True)
            pdf.ln(5)

    if not trovato_almeno_uno:
        pdf.cell(0, 10, txt="Nessun dato disponibile per i filtri selezionati.", ln=True, align='C')

    pdf_string = pdf.output(dest='S')
    if isinstance(pdf_string, str):
        pdf_bytes = pdf_string.encode('latin-1')
    else:
        pdf_bytes = pdf_string

    import base64
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

    return jsonify({
        "pdf_base64": pdf_base64,
        "stats": stats_data
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)

from fpdf import FPDF
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
REPO_NAME = os.environ.get("REPO_NAME", "TuoUsernameGithub/dati-privati-pdf")

g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
if not g:
    logger.error("ATTENZIONE: GITHUB_TOKEN non trovato nelle variabili d'ambiente!")

CODICE_CLASSE_PATTERN = re.compile(r'^[A-Z0-9]{1,10}$')
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
    "VT": ("Lazio", "Viterbo")
}
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

# Dizionario delle scuole per il calcolo del grafico
SCUOLE_MUSICALI = {
    "Agrigento": 54, "Alessandria": 9, "Ancona": 18, "Aosta": 0, "Ascoli Piceno": 10,
    "Asti": 4, "Avellino": 65, "Bari": 44, "Barletta-Andria-Trani": 10, "Belluno": 13,
    "Benevento": 36, "Bergamo": 22, "Biella": 5, "Bologna": 23, "Bolzano": 3,
    "Brescia": 25, "Brindisi": 26, "Cagliari": 18, "Caltanissetta": 28, "Campobasso": 25,
    "Caserta": 63, "Catania": 61, "Catanzaro": 36, "Chieti": 15, "Como": 14,
    "Cosenza": 112, "Cremona": 15, "Crotone": 26, "Cuneo": 12, "Enna": 21,
    "Fermo": 13, "Ferrara": 7, "Firenze": 28, "Foggia": 43, "Forlì-Cesena": 0,
    "Frosinone": 38, "Genova": 16, "Gorizia": 0, "Grosseto": 9, "Imperia": 2,
    "Isernia": 16, "L'Aquila": 21, "La Spezia": 10, "Latina": 22, "Lecce": 57,
    "Lecco": 7, "Livorno": 12, "Lodi": 3, "Lucca": 17, "Macerata": 9,
    "Mantova": 9, "Massa-Carrara": 10, "Matera": 21, "Messina": 36, "Milano": 51,
    "Modena": 6, "Monza e della Brianza": 14, "Napoli": 116, "Novara": 10, "Nuoro": 10,
    "Oristano": 6, "Padova": 36, "Palermo": 107, "Parma": 10, "Pavia": 7,
    "Perugia": 18, "Pesaro e Urbino": 0, "Pescara": 20, "Piacenza": 0, "Pisa": 12,
    "Pistoia": 12, "Pordenone": 0, "Potenza": 38, "Prato": 13, "Ragusa": 23,
    "Ravenna": 5, "Reggio Calabria": 44, "Reggio Emilia": 4, "Rieti": 19, "Rimini": 5,
    "Roma": 69, "Rovigo": 25, "Salerno": 80, "Sassari": 40, "Savona": 4,
    "Siena": 9, "Siracusa": 23, "Sondrio": 11, "Taranto": 26, "Teramo": 15,
    "Terni": 5, "Torino": 49, "Trapani": 38, "Trento": 0, "Treviso": 51,
    "Trieste": 0, "Udine": 0, "Varese": 17, "Venezia": 29, "Verbano-Cusio-Ossola": 6,
    "Vercelli": 9, "Verona": 26, "Vibo Valentia": 38, "Vicenza": 43, "Viterbo": 18
}

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

def normalize_string(s):
    return re.sub(r'[\s_-]+', '', str(s)).upper()

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

    if not isinstance(province_nomi, list) or not isinstance(regioni_richieste, list):
        return jsonify({"error": "Formato regioni/province non valido."}), 400
    if not isinstance(classi_selezionate, list) or not classi_selezionate:
        return jsonify({"error": "Nessuna classe selezionata."}), 400
    if len(classi_selezionate) > MAX_CLASSI:
        return jsonify({"error": f"Numero massimo di classi consentito: {MAX_CLASSI}"}), 400

    province_sigle = []
    for prov in province_nomi:
        sigla = PROVINCE_SIGLE.get(prov)
        if sigla:
            province_sigle.append(sigla)
    # --- DEBUG 1: Vediamo cosa arriva dal frontend ---
    logger.info(f"DEBUG 1: Filtri ricevuti -> Classi: {classi_selezionate} | Province Nomi: {province_nomi} | Sigle generate: {province_sigle} | Fascia: '{fascia_richiesta}' (Normalizzata: '{normalize_string(fascia_richiesta)}')")
    codici_validi = []
    for codice in classi_selezionate:
        identificativo = codice.split(' - ')[0].strip()
        if not identificativo:
            return jsonify({"error": "Uno o più codici classe non sono validi."}), 400
        codici_validi.append(identificativo)

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, txt=sanitize_for_fpdf("Report Estrazione Dati Filtrati"), ln=True, align='C')
    pdf.set_font("Arial", size=10)
    
    safe_regioni = sanitize_for_fpdf(", ".join(regioni_richieste).upper() if regioni_richieste else 'TUTTE')
    safe_province = sanitize_for_fpdf(", ".join(province_nomi).upper() if province_nomi else 'TUTTE')
    filtro_luogo = f"Regioni: {safe_regioni} | Province: {safe_province}"
    pdf.cell(0, 10, txt=filtro_luogo, ln=True, align='C')
    pdf.ln(5)

    trovato_almeno_uno = False
    stats_data = {} 
    all_dfs = []
    
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = repo.get_contents("")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    for codice in codici_validi:
        fascia_norm = normalize_string(fascia_richiesta) if fascia_richiesta else ""
        codice_norm = normalize_string(codice)
        
        file_da_elaborare = []
        nomi_visti = set() # Fix per evitare duplicati
        for f in root_files:
            nome_file_norm = normalize_string(f.name)
            # --- DEBUG 2: Vediamo come matchano i file ---
            if codice_norm in nome_file_norm and nome_file_norm.endswith(".XLSX") and f.name not in nomi_visti:
                nomi_visti.add(f.name)
                logger.info(f"DEBUG 2: Trovato file pertinente: '{f.name}' (Normalizzato: '{nome_file_norm}')")
                
                # Se il tuo file si chiama solo "AM56_I_Fascia.xlsx", non contiene "RISULTATOESTRAZIONE"
                # e quindi il filtro originale lo scartava! Usiamo questo più permissivo:
                parte_dopo_codice = nome_file_norm.split(codice_norm)[-1]
                
                if fascia_norm:
                    if parte_dopo_codice == fascia_norm + ".XLSX":
                        logger.info(f"DEBUG 2: -> File AMMESSO per la fascia '{fascia_norm}'")
                        file_da_elaborare.append(f)
                    else:
                        logger.info(f"DEBUG 2: -> File SCARTATO. La parte dopo il codice è '{parte_dopo_codice}' ma la fascia cercata è '{fascia_norm}.XLSX'")
                else:
                    file_da_elaborare.append(f)
                if fascia_norm:
                    parte_dopo_codice = nome_file_norm.split(codice_norm)[1]
                    if parte_dopo_codice == fascia_norm + ".XLSX":
                        file_da_elaborare.append(f)
                else:
                    file_da_elaborare.append(f)

        if not file_da_elaborare:
            continue

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Classe di Concorso: {codice}"), ln=True)
        pdf.ln(2)

        try:
            # Scarichiamo tutti i file trovati
            lista_dati = []
            logger.info(f"DEBUG: File da elaborare per {codice}: {[f.name for f in file_da_elaborare]}")
            for file_trovato in file_da_elaborare:
                try:
                    file_content = repo.get_contents(file_trovato.path)
                    file_data = file_content.decoded_content
                    
                    if len(file_data) > 10 * 1024 * 1024: 
                        logger.warning(f"File {file_trovato.name} troppo grande. Salto.")
                        continue
                        
                    excel_io = io.BytesIO(file_data)
                    df_temp = pd.read_excel(excel_io, engine='openpyxl')
                    # --- DEBUG 3: Vediamo se l'Excel si legge e quante righe ha ---
                    logger.info(f"DEBUG 3: File '{file_trovato.name}' letto. Righe totali nel foglio Excel: {len(df_temp)}")
                    
                    # Estrai il nome della fascia dal nome del file
                    # Es: "Risultato_Estrazione_AM56_I fascia.xlsx" -> "I FASCIA"
                    fascia_nome = file_trovato.name.split(codice)[-1].replace("_", " ").replace(".xlsx", "").strip().upper()
                    if not fascia_nome:
                        fascia_nome = "DETTAGLI"
                        
                    lista_dati.append((df_temp, fascia_nome))
                except Exception as e:
                    logger.error(f"Errore lettura file {file_trovato.name}: {str(e)}")
            
            if not lista_dati:
                continue

            # Elaboriamo un file (e quindi una fascia) alla volta
            for df, nome_fascia in lista_dati:
                df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]
                logger.info(f"DEBUG: Inizio stampa PDF per fascia '{nome_fascia}' con {len(df)} righe.")

                if province_sigle:
                    col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                    
                    # --- DEBUG 4: Vediamo cosa contiene la colonna provincia ---
                    if col_ufficio:
                        valori_unici = df[col_ufficio].astype(str).str.strip().str.upper().unique()
                        logger.info(f"DEBUG 4: Colonna trovata: '{col_ufficio}'. Valori presenti nel file: {valori_unici}")
                        
                        df[col_ufficio] = df[col_ufficio].astype(str).str.strip().str.upper()
                        df = df[df[col_ufficio].isin(province_sigle)]
                        df = df[df[col_ufficio].str.len() == 2]
                        
                        logger.info(f"DEBUG 4: Righe rimaste dopo il filtro provincia (cercavi {province_sigle}): {len(df)}")
                    else:
                        logger.warning("DEBUG 4: Nessuna colonna 'UFFICIO' o 'PROVINCIA' trovata nel file Excel!")
                        df = pd.DataFrame()

                if df.empty:
                    continue

                # --- CALCOLO STATISTICHE RAPPORTO S/C ---
                col_ufficio_sep = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                if col_ufficio_sep:
                    counts = df[col_ufficio_sep].value_counts()
                    for sigla, count in counts.items():
                        sigla_str = str(sigla).upper()
                        region_name, nome_esteso = PROVINCE_DATA.get(sigla_str, ("", sigla_str))
                        
                        num_scuole = SCUOLE_MUSICALI.get(nome_esteso, 0)
                        num_candidati = int(count)
                        
                        if num_candidati > 0:
                            rapporto = round(num_scuole / num_candidati, 4)
                        else:
                            rapporto = 0
                            
                        if nome_esteso not in stats_data:
                            stats_data[nome_esteso] = {
                                "scuole": num_scuole,
                                "candidati": num_candidati,
                                "rapporto": rapporto
                            }
                        else:
                            stats_data[nome_esteso]["candidati"] += num_candidati
                            stats_data[nome_esteso]["rapporto"] = round(stats_data[nome_esteso]["scuole"] / stats_data[nome_esteso]["candidati"], 4)
                # ----------------------------------------

                # --- INTESTAZIONE FASCIA ---
                pdf.set_font("Arial", 'B', 12)
                pdf.cell(0, 10, txt=sanitize_for_fpdf(nome_fascia), ln=True, align='L')
                pdf.ln(2)

                if len(df) > MAX_ROWS_PDF:
                    df = df.head(MAX_ROWS_PDF)
                    pdf.set_font("Arial", 'I', 8)
                    pdf.cell(0, 6, txt=sanitize_for_fpdf(f"Avviso: Mostrati solo i primi {MAX_ROWS_PDF} record per motivi di spazio."), ln=True)

                def is_empty(val):
                    v = str(val).strip().lower()
                    return v in ['nan', '*', 'none', '', '-']
                
                cols_to_drop = []
                for col in df.columns:
                    unique_vals = [val for val in df[col].unique() if not is_empty(val)]
                    
                    # FIX: Non scartare mai la colonna UFFICIO/PROVINCIA, serve per i raggruppamenti nel PDF!
                    col_upper = str(col).upper()
                    is_ufficio_col = 'UFFICIO' in col_upper or 'PROVINCIA' in col_upper
                    
                    if len(unique_vals) <= 1 and not is_ufficio_col:
                        cols_to_drop.append(col)
                        
                    if 'pdf' in str(col).lower() or 'xls' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower():
                        cols_to_drop.append(col)
                        
                df = df.drop(columns=cols_to_drop, errors='ignore')

                def format_val(val):
                    s = str(val).strip()
                    if s.lower() in ['nan', 'none', ''] or s == '*':
                        return "-"
                    if s.endswith('.0'):
                        try:
                            f = float(s)
                            if f.is_integer():
                                return str(int(f))
                        except ValueError:
                            pass
                    return s

                col_widths = {}
                total_width = 0
                for col in df.columns:
                    max_len = len(str(col))
                    for val in df[col].head(100):
                        val_str = format_val(val)
                        if len(val_str) > max_len:
                            max_len = len(val_str)
                    
                    width = min(max_len * 2.2, 50)
                    if str(col).upper() in ['UFFICIO PROVINCIALE', 'UFFICIO', 'PROVINCIA']:
                        width = 20 
                    if str(col).upper() in ['COGNOME', 'NOME']:
                        width = max(width, 35)
                    if 'TOTALE' in str(col).upper() or 'PUNTEGGIO' in str(col).upper():
                        width = max(width, 25)
                    if 'POSIZIONE' in str(col).upper():
                        width = max(width, 20)
                        
                    width = max(width, 15)
                    col_widths[col] = width
                    total_width += width

                page_width = 277
                if total_width > page_width:
                    scale = page_width / total_width
                    for col in col_widths:
                        col_widths[col] *= scale

                pdf.set_font("Arial", 'B', 9)
                line_height = 5
                
                max_lines = 1
                header_lines_map = {}
                for col in df.columns:
                    char_limit = max(1, int(col_widths[col] / 1.8))
                    text = sanitize_for_fpdf(str(col))
                    lines = 0
                    current_line_len = 0
                    for word in text.split():
                        if current_line_len + len(word) + 1 > char_limit:
                            lines += 1
                            current_line_len = len(word)
                        else:
                            current_line_len += len(word) + 1
                    if current_line_len > 0 or lines == 0:
                        lines += 1
                    header_lines_map[col] = lines
                    if lines > max_lines:
                        max_lines = lines

                max_header_height = max_lines * line_height

                def draw_table_header():
                    y_start = pdf.get_y()
                    for col in df.columns:
                        x_start = pdf.get_x()
                        text = sanitize_for_fpdf(str(col))
                        lines_needed = max_lines - header_lines_map[col]
                        if lines_needed > 0:
                            text += "\n" * lines_needed
                        pdf.multi_cell(col_widths[col], line_height, text, border=1, align='L')
                        pdf.set_xy(x_start + col_widths[col], y_start)
                    pdf.set_y(y_start + max_header_height)

                draw_table_header()

                current_prov_sigla = None
                current_region = None
                
                pdf.set_font("Arial", size=9)
                for _, row in df.iterrows():
                    if col_ufficio_sep:
                        prov_sigla = format_val(row[col_ufficio_sep]).upper()
                        if prov_sigla != current_prov_sigla:
                            current_prov_sigla = prov_sigla
                            region_name, prov_full_name = PROVINCE_DATA.get(prov_sigla, ("", prov_sigla))
                            
                            if pdf.get_y() + 20 > 190:
                                pdf.add_page()
                                draw_table_header()
                            
                            pdf.ln(4)
                            
                            if region_name and region_name != current_region:
                                current_region = region_name
                                pdf.set_font("Arial", 'B', 12) 
                                pdf.cell(0, 7, txt=sanitize_for_fpdf(region_name.upper()), ln=True, align='L')
                            
                            if prov_full_name:
                                pdf.set_font("Arial", 'B', 10)
                                pdf.cell(0, 6, txt=sanitize_for_fpdf(prov_full_name.upper()), ln=True, align='L')
                            
                            pdf.ln(2)
                            pdf.set_font("Arial", size=9)

                    if pdf.get_y() + 6 > 190:
                        pdf.add_page()
                        draw_table_header()
                        pdf.set_font("Arial", size=9)

                    for col in df.columns:
                        valore = sanitize_for_fpdf(format_val(row[col]))
                        char_lim = max(1, int(col_widths[col] / 2.0))
                        if len(valore) > char_lim:
                            valore = valore[:char_lim-3] + "..."
                        
                        align = 'R' if valore.replace('.', '', 1).replace(',', '', 1).replace('-', '', 1).isdigit() else 'L'
                        pdf.cell(col_widths[col], 6, valore, border=1, align=align)
                    pdf.ln(6)

            pdf.ln(8)
            trovato_almeno_uno = True
            
        except Exception as e:
            logger.error(f"Errore elaborazione file: {str(e)}")
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Errore interno durante l'elaborazione della classe {codice}."), ln=True)
            pdf.ln(5)

    if not trovato_almeno_uno:
        pdf.cell(0, 10, txt="Nessun dato disponibile per i filtri selezionati.", ln=True, align='C')

    pdf_string = pdf.output(dest='S')
    if isinstance(pdf_string, str):
        pdf_bytes = pdf_string.encode('latin-1')
    else:
        pdf_bytes = pdf_string

    import base64
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

    return jsonify({
        "pdf_base64": pdf_base64,
        "stats": stats_data
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
