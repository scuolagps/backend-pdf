import os
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

def sanitize_for_fpdf(text):
    if not isinstance(text, str):
        text = str(text)
    return text.encode('latin-1', 'replace').decode('latin-1')

# --- FUNZIONE MAGICA PER NORMALIZZARE I NOMI ---
def normalize_string(s):
    # Rimuove TUTTI gli spazi, trattini bassi _, trattini normali - e converte in maiuscolo
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

    logger.info("="*50)
    logger.info(f"DEBUG RICHIESTA RICEVUTA:")
    logger.info(f"Classi: {classi_selezionate}")
    logger.info(f"Regioni: {regioni_richieste}")
    logger.info(f"Province (Nomi): {province_nomi}")
    logger.info(f"Fascia richiesta: '{fascia_richiesta}'")
    logger.info("="*50)

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
    
    logger.info(f"DEBUG: Sigle province da cercare nell'Excel: {province_sigle}")

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
    
    try:
        repo = g.get_repo(REPO_NAME)
        root_files = repo.get_contents("")
    except Exception as e:
        return jsonify({"error": f"Impossibile accedere alla repository: {str(e)}"}), 500

    for codice in codici_validi:
               # --- NUOVA LOGICA DI RICERCA INFALLIBILE E PRECISA ---
        fascia_norm = normalize_string(fascia_richiesta) if fascia_richiesta else ""
        codice_norm = normalize_string(codice)
        
        file_da_elaborare = []
        for f in root_files:
            nome_file_norm = normalize_string(f.name)
            # Cerca "RISULTATOESTRAZIONEAM56" e ".XLSX"
            if f"RISULTATOESTRAZIONE{codice_norm}" in nome_file_norm and nome_file_norm.endswith(".XLSX"):
                if fascia_norm:
                    # MAGIA LOGICA: Dividiamo il nome del file usando il codice (es. "AM56")
                    # la parte a destra sarà "IFASCIA.XLSX" o "IIFASCIA.XLSX"
                    # e verifico che sia ESATTAMENTE uguale a "FASCIA.XLSX"
                    parte_dopo_codice = nome_file_norm.split(codice_norm)[1]
                    if parte_dopo_codice == fascia_norm + ".XLSX":
                        file_da_elaborare.append(f)
                else:
                    # Se "Tutte le fasce", prende tutti i file di quel codice
                    file_da_elaborare.append(f)
        
        logger.info(f"DEBUG RICERCA FILE per codice {codice} e fascia '{fascia_richiesta}':")
        if file_da_elaborare:
            logger.info(f"Trovati {len(file_da_elaborare)} file: {[f.name for f in file_da_elaborare]}")
        else:
            logger.warning(f"NESSUN file trovato per codice {codice} e fascia '{fascia_richiesta}'")

        if not file_da_elaborare:
            continue

        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Classe di Concorso: {codice}"), ln=True)
        pdf.ln(2)

        try:
            lista_df = []
            for file_trovato in file_da_elaborare:
                try:
                    logger.info(f"DEBUG: Tentativo download {file_trovato.name}...")
                    file_content = repo.get_contents(file_trovato.path)
                    file_data = file_content.decoded_content
                    
                    if len(file_data) > 10 * 1024 * 1024: 
                        logger.warning(f"File {file_trovato.name} troppo grande. Salto.")
                        continue
                        
                    excel_io = io.BytesIO(file_data)
                    df_temp = pd.read_excel(excel_io, engine='openpyxl')
                    
                    logger.info(f"DEBUG: Colonne trovate in {file_trovato.name}: {list(df_temp.columns)}")
                    logger.info(f"DEBUG: Numero righe totali lette: {len(df_temp)}")
                    
                    lista_df.append(df_temp)
                except Exception as e:
                    logger.error(f"Errore lettura file {file_trovato.name}: {str(e)}")
            
            if not lista_df:
                continue
                
            df = pd.concat(lista_df, ignore_index=True)
            df = df.loc[:, ~df.columns.astype(str).str.contains('^Unnamed')]

            if province_sigle:
                col_ufficio = next((col for col in df.columns if 'UFFICIO' in str(col).upper() or 'PROVINCIA' in str(col).upper()), None)
                logger.info(f"DEBUG: Colonna Ufficio/Provincia identificata: '{col_ufficio}'")
                
                if col_ufficio:
                    df[col_ufficio] = df[col_ufficio].astype(str).str.strip().str.upper()
                    logger.info(f"DEBUG: Valori unici in {col_ufficio}: {df[col_ufficio].unique()[:20]}")
                    
                    df = df[df[col_ufficio].isin(province_sigle)]
                    df = df[df[col_ufficio].str.len() == 2]
                    logger.info(f"DEBUG: Righe rimaste dopo il filtro provincia ({province_sigle}): {len(df)}")
                else:
                    logger.warning("DEBUG: Colonna Ufficio/Provincia NON trovata! Il filtro provincia non può essere applicato.")
                    df = pd.DataFrame()
            else:
                logger.info("DEBUG: Nessuna provincia richiesta, salto il filtro provincia.")

            if df.empty:
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Nessun risultato trovato per {codice} nelle province selezionate."), ln=True)
                pdf.ln(5)
                logger.warning(f"DEBUG: DataFrame vuoto dopo i filtri per {codice}. Salto stampa tabella.")
                continue

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
                if len(unique_vals) <= 1:
                    cols_to_drop.append(col)
                if 'pdf' in str(col).lower() or 'xls' in str(col).lower() or 'elenco' in str(col).lower() or 'allegato' in str(col).lower():
                    cols_to_drop.append(col)
            df = df.drop(columns=cols_to_drop)

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
            logger.error(f"Errore elaborazione file: {str(e)}")
            pdf.set_font("Arial", 'I', 10)
            pdf.cell(0, 10, txt=sanitize_for_fpdf(f"Errore interno durante l'elaborazione della classe {codice}."), ln=True)
            pdf.ln(5)

    if not trovato_almeno_uno:
        pdf.cell(0, 10, txt="Nessun dato disponibile per i filtri selezionati.", ln=True, align='C')
        logger.warning("DEBUG: PDF generato vuoto (nessun dato trovato in nessuna classe elaborata).")

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
