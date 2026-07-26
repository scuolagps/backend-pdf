import os
import re
import io
import logging
from builtins import isinstance
from flask import Flask, request, send_file, jsonify
from fpdf import FPDF
import pandas as pd
from github import Github
from github.GithubException import UnknownObjectException

# Configurazione del logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Origini consentite per l'ambiente di sviluppo locale
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

# --- CONFIGURAZIONE GITHUB ---
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("dati-privati-pdf", "tonecraft17/dati-privati-pdf") # INSERISCI QUI IL NOME DELLA TUA REPO PRIVATA

# Inizializza il client Github
g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
if not g:
    logger.error("ATTENZIONE: GITHUB_TOKEN non trovato nelle variabili d'ambiente!")
# ----------------------------

CODICE_CLASSE_PATTERN = re.compile(r'^[A-Z0-9]{1,10}$')
MAX_CLASSI = 20
# Rimuoviamo MAX_FILE_SIZE_MB perché leggeremo in memoria, ma possiamo controllare la dimensione del file su github
MAX_ROWS_PDF = 500

# Dizionario con Sigla -> (Regione, Nome Esteso Provincia)
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
# Dizionario inverso
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

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

    codici_validi = []
    for codice in classi_selezionate:
        # Prende tutto quello che c'è prima del primo trattino (es. "AM56_I fascia")
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
    
    # Recupera la repository privata e l'elenco dei file in root
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = repo.get_contents("")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    for codice in codici_validi:
        # --- COSTRUISCI IL NOME DEL FILE IN BASE ALLA FASCIA SCELTA ---
        if fascia_richiesta:
            # Se l'utente ha scelto "I fascia", cerchiamo: Risultato_Estrazione_AM56_I fascia.xlsx
            prefix_da_cercare = f"Risultato_Estrazione_{codice}_{fascia_richiesta}"
        else:
            # Se "Tutte le fasce", cerchiamo qualsiasi file che inizia col codice
            prefix_da_cercare = f"Risultato_Estrazione_{codice}"

        # --- LOGICA: CERCA IL FILE BASANDOSI SUL PREFIX COSTRUITO ---
        file_trovato = None
        for f in root_files:
            # Controlla che il file inizi con il prefix e finisca con .xlsx
            if f.name.startswith(prefix_da_cercare) and f.name.endswith(".xlsx"):
                file_trovato = f
                break # Trovato il primo file corrispondente, esce dal ciclo
        
        if not file_trovato:
            logger.warning(f"ATTENZIONE: Nessun file trovato per {codice} (Fascia: {fascia_richiesta or 'Tutte'}). Salto.")
            continue

        nome_file = file_trovato.name 
        
        # --- NUOVA LOGICA: SCARICA FILE DA GITHUB ---
        try:
            logger.info(f"Tentativo di scaricare {nome_file} da GitHub...")
            file_content = repo.get_contents(nome_file)
            
            # Decodifica il contenuto del file (base64) in byte grezzi
            file_data = file_content.decoded_content
            
            # Opzionale: controllo dimensione in memoria
            if len(file_data) > 10 * 1024 * 1024: # 10 MB
                logger.warning(f"File {nome_file} troppo grande, superati i 10MB. Salto.")
                continue
                
        except UnknownObjectException:
            logger.warning(f"ATTENZIONE: File {nome_file} non trovato nella repository GitHub. Salto questa classe.")
            continue
        except Exception as e:
            logger.error(f"Errore nel download del file {nome_file} da GitHub: {str(e)}")
            continue
        # -------------------------------------------

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Classe di Concorso: {codice}"), ln=True)
        pdf.ln(2)

        try:
            # --- MODIFICA: Legge l'Excel dai byte in memoria (io.BytesIO) invece che dal disco ---
            excel_io = io.BytesIO(file_data)
            df = pd.read_excel(excel_io, engine='openpyxl')

            # 1. RIMUOVI COLONNE "Unnamed"
            df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]

            if province_sigle:
                col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                if col_ufficio:
                    df = df[df[col_ufficio].astype(str).str.strip().str.upper().isin(province_sigle)]
                    df = df[df[col_ufficio].astype(str).str.strip().str.len() == 2]
                    
                    df['TEMP_REGIONE'] = df[col_ufficio].astype(str).str.strip().str.upper().map(lambda x: PROVINCE_DATA.get(x, ("ZZZ", ""))[0])
                    df = df.sort_values(by=['TEMP_REGIONE', col_ufficio])
                    df = df.drop(columns=['TEMP_REGIONE'])
                else:
                    df = pd.DataFrame()

            if df.empty:
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Nessun risultato trovato per {codice} nelle province selezionate."), ln=True)
                pdf.ln(5)
                continue

            if len(df) > MAX_ROWS_PDF:
                df = df.head(MAX_ROWS_PDF)
                pdf.set_font("Arial", 'I', 8)
                pdf.cell(0, 6, txt=sanitize_for_fpdf(f"Avviso: Mostrati solo i primi {MAX_ROWS_PDF} record per motivi di spazio."), ln=True)

            # --- PULIZIA COLONNE INUTILI ---
            def is_empty(val):
                v = str(val).strip().lower()
                return v in ['nan', '*', 'none', '', '-']
            
            cols_to_drop = []
            for col in df.columns:
                unique_vals = [val for val in df[col].unique() if not is_empty(val)]
                if len(unique_vals) <= 1:
                    cols_to_drop.append(col)
                if 'pdf' in str(col).lower() or 'xls' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower():
                    cols_to_drop.append(col)
            df = df.drop(columns=cols_to_drop)

            # --- FUNZIONE FORMATTAZIONE VALORI ---
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

            # --- CALCOLO DINAMICO LARGHEZZE COLONNE ---
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

            # --- INTESTAZIONI TABELLA (Altezza Uniforme) ---
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

            # --- RIGHE DI DATI CON INTESTAZIONE REGIONE/PROVINCIA ---
            col_ufficio_sep = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
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
            logger.error(f"Errore elaborazione file {nome_file}: {str(e)}")
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
        
    output = io.BytesIO(pdf_bytes)
    output.seek(0)

    return send_file(
        output,
        download_name='Risultato_Estrazione_Filtrata.pdf',
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    from waitress import serve
    print(f"Avvio del server di produzione sulla porta {port}...")
    serve(app, host='0.0.0.0', port=port)
