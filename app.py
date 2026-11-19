import streamlit as st
import pandas as pd
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import base64
from datetime import datetime, time as dt_time, timedelta
import requests
from io import BytesIO
from PIL import Image
import pytz
import traceback
import re

# ============================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================

st.set_page_config(
    page_title="Toggl Compliance System",
    page_icon="💠",
    layout="wide"
)

# ============================================================
# CONFIGURACIÓN GENERAL Y SECRETS (SEGURO + DIAGNÓSTICO)
# ============================================================

try:
    SMTP_SERVER = st.secrets["SMTP"]["SERVER"]
    SMTP_PORT = int(st.secrets["SMTP"]["PORT"])
    SMTP_USERNAME = st.secrets["SMTP"]["EMAIL"]
    SMTP_PASSWORD = st.secrets["SMTP"]["PASSWORD"]
    SMTP_ERROR = None
except KeyError as e:
    SMTP_SERVER = None
    SMTP_PORT = None
    SMTP_USERNAME = None
    SMTP_PASSWORD = None
    SMTP_ERROR = f"Falta la llave {e} en los Secrets."
except Exception as e:
    SMTP_SERVER = None
    SMTP_PORT = None
    SMTP_USERNAME = None
    SMTP_PASSWORD = None
    SMTP_ERROR = f"Error leyendo Secrets: {str(e)}"

URL_LOGO_GITHUB = "https://raw.githubusercontent.com/DataTeamCLG/Toggl-WorkFlow-Automation/main/emailclg.png"
URL_BANNER_GITHUB = "https://raw.githubusercontent.com/Iamnotmanolotaco/Inmigration-USCIS-Alerts-Automation/main/banner.png"

NOMBRE_EMPRESA = "Community Law Group, PLLC® "
DEPARTAMENTO = "Quality Control & Efficiency Department"
EMAIL_CONTACTO = "data.analyst7@communitylawgroup.com"
SITIO_WEB = "www.communitylawgroup.com"

TAMANO_LOGO = 120
LOGO_WIDTH = 120
LOGO_MAX_BYTES = 8000  # 8 KB: Tamaño ultra-ligero a prueba de Outlook

ZONA_HORARIA = pytz.timezone('America/Bogota')

HOJA_NAMES = "Names"
HOJA_INCIDENTES = "TogglFilterDB"

# ============================================================
# RECURSOS (LOGO / BANNER)
# ============================================================

def get_image_from_github(url):
    try:
        r = requests.get(url, timeout=10)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def optimizar_logo(logo_bytes, target_width=LOGO_WIDTH, max_bytes=LOGO_MAX_BYTES):
    if logo_bytes is None:
        return None, None
    try:
        original = Image.open(BytesIO(logo_bytes))
        if original.mode in ('RGBA', 'LA', 'P'):
            original = original.convert('RGBA')
            rgb = Image.new("RGB", original.size, (255, 255, 255))
            rgb.paste(original, mask=original.split()[-1])
        else:
            rgb = original.convert("RGB")

        w, h = rgb.size
        target_height = int(target_width * (h / w))
        img = rgb.resize((target_width, target_height), Image.Resampling.LANCZOS)

        for quality in (85, 75, 65, 55, 45, 35):
            out = BytesIO()
            img.save(out, format='JPEG', quality=quality, optimize=True)
            data = out.getvalue()
            if len(data) <= max_bytes:
                return data, 'jpeg'

        for width in (100, 80):
            th = int(width * (h / w))
            small = img.resize((width, th), Image.Resampling.LANCZOS)
            out = BytesIO()
            small.save(out, format='JPEG', quality=75, optimize=True)
            data = out.getvalue()
            if len(data) <= max_bytes:
                return data, 'jpeg'
        return data, 'jpeg'
    except Exception:
        return logo_bytes, 'png'


def get_logo_bytes():
    raw = get_image_from_github(URL_LOGO_GITHUB)
    if not raw:
        return None, None
    return optimizar_logo(raw, LOGO_WIDTH, LOGO_MAX_BYTES)


def get_banner_base64():
    b = get_image_from_github(URL_BANNER_GITHUB)
    if b:
        return f"data:image/png;base64,{base64.b64encode(b).decode('utf-8')}"
    return None

# ============================================================
# UTILIDADES
# ============================================================

def obtener_saludo_en():
    h = datetime.now(ZONA_HORARIA).hour
    if 5 <= h < 12:
        return "Good morning"
    elif 12 <= h < 18:
        return "Good afternoon"
    return "Good evening"


def obtener_hora_local():
    return datetime.now(ZONA_HORARIA)


def limpiar_emails(valor):
    if pd.isna(valor) or valor is None:
        return []
    txt = str(valor).strip()
    if txt.lower() in ('disabled', 'n/a', ''):
        return []
    partes = re.split(r'[;,\n]+', txt)
    return [p.strip() for p in partes if p.strip() and '@' in p.strip()]


def normalizar_nombre(nombre):
    if pd.isna(nombre):
        return ""
    return re.sub(r'\s+', ' ', str(nombre).strip()).lower()


def formatear_duracion(valor):
    if pd.isna(valor):
        return "0:00:00"
    
    if isinstance(valor, dt_time):
        return f"{valor.hour}:{valor.minute:02d}:{valor.second:02d}"
        
    if isinstance(valor, timedelta):
        total_seg = int(valor.total_seconds())
        h, rem = divmod(total_seg, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}"

    s = str(valor).strip()
    
    if re.match(r'^\d+:\d{2}:\d{2}$', s):
        return s
    if re.match(r'^\d+:\d{2}$', s):
        return s + ":00"
    if "days" in s.lower() or "day" in s.lower():
        match = re.search(r'(\d+)', s)
        if match:
            h = int(match.group(1)) * 24
            return f"{h}:00:00"
            
    try:
        val_float = float(s)
        total_seg = int(round(val_float * 3600))
        h, rem = divmod(total_seg, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}"
    except ValueError:
        pass
        
    if isinstance(valor, (int, float)):
        total_seg = int(round(float(valor) * 3600))
        h, rem = divmod(total_seg, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}"

    return s


def formatear_fecha(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime('%m/%d/%Y')
    try:
        return pd.to_datetime(valor).strftime('%m/%d/%Y')
    except Exception:
        return str(valor)

# ============================================================
# HTML DEL CORREO
# ============================================================

def generar_html_incidencias(usuario_info, df_usuario, logo_cid=None):
    saludo = obtener_saludo_en()
    prefix = usuario_info.get('prefix', '')
    nombre = usuario_info.get('nombre', '')
    saludo_completo = f"{saludo} {prefix} {nombre},".replace("  ", " ").strip()

    filas = ""
    for idx, (_, row) in enumerate(df_usuario.iterrows()):
        fecha = formatear_fecha(row.get('Date', ''))
        proyecto = row.get('Project (Activity)', '')
        cliente = row.get('Client Tag', '')
        descripcion = row.get('Description', '')
        duracion = formatear_duracion(row.get('Duration', ''))
        tipo = row.get('Type of incident', row.get('Type of Incident', ''))
        obs = row.get('Observations', '')
        
        bg_color = "#ffffff" if idx % 2 == 0 else "#f8fafc"
        
        filas += f"""
        <tr style="background-color: {bg_color};">
            <td style="padding: 12px 15px; color: #334155; font-size: 14px; font-weight: 700; white-space: nowrap;">{fecha}</td>
            <td style="padding: 12px 15px; color: #334155; font-size: 14px;">{proyecto}</td>
            <td style="padding: 12px 15px; font-size: 14px;">
                <span style="background-color: #e0f2fe; color: #0369a1; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; white-space: nowrap;">{cliente}</span>
            </td>
            <td style="padding: 12px 15px; color: #334155; font-size: 14px;">{descripcion}</td>
            <td style="padding: 12px 15px; color: #012338; font-size: 14px; font-weight: 700; white-space: nowrap;">{duracion}</td>
            <td style="padding: 12px 15px; color: #b91c1c; font-size: 14px; font-weight: 700;">{tipo}</td>
            <td style="padding: 12px 15px; color: #0f172a; font-size: 13px; font-weight: 700; font-style: italic;">{obs}</td>
        </tr>
        """

    logo_html = ""
    if logo_cid:
        logo_html = f"""
        <img src="cid:{logo_cid}" alt="{NOMBRE_EMPRESA}" width="{TAMANO_LOGO}"
             style="width: {TAMANO_LOGO}px; height: auto; border: none; display: block; margin: 0 auto 10px auto;">
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 0; background-color: #ffffff; font-family: 'Segoe UI', 'Calibri', Arial, sans-serif; line-height: 1.6; color: #1e293b;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #012338;">
            <tr>
                <td align="center" style="padding: 30px 20px;">
                    
                    <!-- Contenedor de ancho automático (se adapta al título) -->
                    <div style="display: inline-block; text-align: center;">
                        <!-- Línea decorativa superior (ancho exacto del título) -->
                        <div style="width: 100%; height: 3px; background-color: #7dd3fc; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                        
                        <h1 style="margin: 0; font-size: 26px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;">
                            <span style="font-size: 22px; vertical-align: middle; margin-right: 8px;">💠</span>
                            Toggl Time Entry Compliance System
                        </h1>
                        
                        <!-- Subtítulo con separador (ancho fijo) -->
                        <p style="margin: 10px 0 0 0; font-size: 14px; color: #7dd3fc; font-weight: 500; letter-spacing: 1px; text-transform: uppercase;">
                            Time Entries Incident Report
                        </p>
                        
                        <!-- Línea decorativa inferior (ancho fijo) -->
                        <div style="width: 40px; height: 3px; background-color: #7dd3fc; margin: 15px auto 0 auto; border-radius: 2px;"></div>
                    </div>
                    
                </td>
            </tr>
        </table>

        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #ffffff;">
            <tr>
                <td style="padding: 30px 20px;">
                    
                    <div style="background-color: #f0f9ff; padding: 15px 20px; border-radius: 6px; margin-bottom: 25px;">
                        <strong style="font-size: 18px; color: #012338;">{saludo_completo}</strong>
                    </div>

                    <p style="font-size: 15px; color: #334155; margin-bottom: 15px;">
                        As part of the training process for habits in Toggl — especially regarding the
                        Timers component — we are sending you the incident report on Time Entries
                        incidents detected in your account.
                    </p>
                    <p style="font-size: 15px; color: #334155; margin-bottom: 25px;">
                        The following <strong style="color: #ef4444; font-size: 16px;">{len(df_usuario)}</strong> incident(s) were identified and require your review:
                    </p>

                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="width: 100%; border-collapse: collapse; text-align: left; margin: 20px 0;">
                        <thead>
                            <tr style="background-color: #012338;">
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Date</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Project (Activity)</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Client Tag</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Description</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Duration</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Type of Incident</th>
                                <th style="background-color: #012338; color: #ffffff; font-weight: 700; padding: 14px 15px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; border: none;">Observations</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filas}
                        </tbody>
                    </table>

                    <div style="background-color: #eff6ff; border: 1px solid #bfdbfe; padding: 20px; border-radius: 6px; margin-top: 30px;">
                        <strong style="color: #012338; font-size: 15px; display: block; margin-bottom: 10px; text-transform: uppercase;">Action Required:</strong>
                        <span style="font-size: 14px; color: #1e3a8a;">
                            We expect team members to correct their time entries, activities, and activity descriptions within a maximum period of 24 hours.<br><br>
                            Should you have any questions regarding this report, please contact the Quality Control & Efficiency Department.<br>
                            Thank you for your attention and cooperation.
                        </span>
                    </div>

                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-top: 40px;">
                        <tr>
                            <td align="center" style="padding-top: 25px; border-top: 2px solid #e2e8f0; text-align: center;">
                                {logo_html}
                                <strong style="color: #012338; font-size: 16px; display: block; margin-bottom: 4px;">{NOMBRE_EMPRESA}</strong>
                                <span style="color: #0284c7; font-size: 14px; font-weight: 600; display: block; margin-bottom: 8px;">{DEPARTAMENTO}</span>
                                <span style="color: #64748b; font-size: 13px; display: inline-block;">
                                    ✉️ <a href="mailto:{EMAIL_CONTACTO}" style="color: #0284c7; text-decoration: none;">{EMAIL_CONTACTO}</a> &nbsp;|&nbsp; 🌐 <a href="https://{SITIO_WEB}" style="color: #0284c7; text-decoration: none;">{SITIO_WEB}</a>
                                </span>
                            </td>
                        </tr>
                    </table>

                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html

# ============================================================
# ENVÍO DE CORREO (BLINDADO Y SEGURO)
# ============================================================

def enviar_correo(smtp_server, smtp_port, smtp_username, smtp_password,
                  to_emails, cc_emails, subject, html_body, logo_bytes=None):
    try:
        msg = MIMEMultipart('related')
        msg['Subject'] = subject
        msg['From'] = smtp_username
        msg['To'] = ", ".join(to_emails)
        if cc_emails:
            msg['CC'] = ", ".join(cc_emails)
        msg['X-Priority'] = '1'

        msg_alt = MIMEMultipart('alternative')
        msg_alt.attach(MIMEText(html_body, 'html', 'utf-8'))
        msg.attach(msg_alt)

        if logo_bytes:
            try:
                cid = "company_logo_cid"
                img = MIMEImage(logo_bytes)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename='logo.jpeg')
                img.add_header('X-Attachment-Id', cid)
                img.add_header('Content-Transfer-Encoding', 'base64')
                msg.attach(img)
            except Exception as e:
                print(f"Error adjuntando logo: {e}")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=ctx)
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_username, to_emails + (cc_emails or []), msg.as_string())
        return True, "OK"
    except Exception as e:
        return False, str(e)

# ============================================================
# PROCESAMIENTO PRINCIPAL
# ============================================================

def cargar_hojas(uploaded_file):
    xls = pd.ExcelFile(uploaded_file, engine='openpyxl')
    hojas = {re.sub(r'\s+', '', h).lower(): h for h in xls.sheet_names}

    if re.sub(r'\s+', '', HOJA_NAMES).lower() not in hojas:
        raise ValueError(f"Sheet '{HOJA_NAMES}' not found. Available: {xls.sheet_names}")
    if re.sub(r'\s+', '', HOJA_INCIDENTES).lower() not in hojas:
        raise ValueError(f"Sheet '{HOJA_INCIDENTES}' not found. Available: {xls.sheet_names}")

    df_names = pd.read_excel(xls, sheet_name=hojas[re.sub(r'\s+', '', HOJA_NAMES).lower()])
    df_inc = pd.read_excel(xls, sheet_name=hojas[re.sub(r'\s+', '', HOJA_INCIDENTES).lower()])
    return df_names, df_inc


def construir_mapa_usuarios(df_names):
    mapa = {}
    for _, row in df_names.iterrows():
        nombre = row.get('NAME CORRECT')
        if pd.isna(nombre):
            continue
        status = str(row.get('USER STATUS', '')).strip().lower()
        if status != 'active':
            continue
        email = row.get('EMAIL')
        if pd.isna(email) or str(email).strip().lower() in ('disabled', ''):
            continue
        key = normalizar_nombre(nombre)
        cc = limpiar_emails(row.get('COPY_EMAIL_TG'))
        mapa[key] = {
            'nombre': str(nombre).strip(),
            'prefix': str(row.get('PREFIX', '')).strip() if not pd.isna(row.get('PREFIX')) else '',
            'email': str(email).strip(),
            'cc': cc,
        }
    return mapa


def procesar_y_enviar(df_names, df_inc, smtp_server, smtp_port, smtp_username, smtp_password,
                     test_mode=False, dry_run=False):
    resultados = []
    mapa_usuarios = construir_mapa_usuarios(df_names)

    if 'Member' not in df_inc.columns:
        return False, f"Sheet '{HOJA_INCIDENTES}' has no 'Member' column. Columns: {list(df_inc.columns)}", []

    logo_bytes, logo_mime = get_logo_bytes()
    logo_cid = "company_logo_cid" if logo_bytes else None

    df_inc = df_inc.copy()
    if 'Corrected Name' in df_inc.columns:
        df_inc['_match_name'] = df_inc['Corrected Name'].where(
            df_inc['Corrected Name'].notna() & (df_inc['Corrected Name'].astype(str).str.strip() != ''),
            df_inc['Member']
        )
    else:
        df_inc['_match_name'] = df_inc['Member']

    df_inc['_member_key'] = df_inc['_match_name'].apply(normalizar_nombre)
    df_inc = df_inc[df_inc['_member_key'] != '']

    grupos = df_inc.groupby('_member_key', sort=True)

    for member_key, df_usuario in grupos:
        info = mapa_usuarios.get(member_key)

        if info is None:
            nombre_original = df_usuario['_match_name'].iloc[0]
            resultados.append({
                'usuario': f"{nombre_original} (key: {member_key})",
                'estado': '⚠️ Not found in Names or not Active',
                'incidencias': len(df_usuario),
                'to': '-',
                'cc': '-'
            })
            continue

        if test_mode:
            to_emails = [smtp_username] if smtp_username else []
            cc_emails = []
        else:
            to_emails = [info['email']]
            cc_emails = info['cc']

        if not to_emails:
            resultados.append({
                'usuario': info['nombre'],
                'estado': '⚠️ No recipient',
                'incidencias': len(df_usuario),
                'to': '-',
                'cc': '-'
            })
            continue

        # Calcular fechas mínima y máxima para el asunto
        try:
            fechas_validas = pd.to_datetime(df_usuario['Date'], errors='coerce').dropna()
            if not fechas_validas.empty:
                min_date = fechas_validas.min().strftime('%m/%d/%Y')
                max_date = fechas_validas.max().strftime('%m/%d/%Y')
                if min_date == max_date:
                    date_str = min_date
                else:
                    date_str = f"{min_date} - {max_date}"
            else:
                date_str = ""
        except Exception:
            date_str = ""

        if date_str:
            asunto = f"Toggl Compliance Alert — {info['nombre']} — {date_str}"
        else:
            asunto = f"Toggl Compliance Alert — {info['nombre']}"
            
        if test_mode:
            asunto = f"[TEST] {asunto}"

        html = generar_html_incidencias(info, df_usuario, logo_cid)

        if dry_run:
            resultados.append({
                'usuario': info['nombre'],
                'estado': '🧪 Simulated',
                'incidencias': len(df_usuario),
                'to': ', '.join(to_emails),
                'cc': ', '.join(cc_emails) if cc_emails else '-'
            })
            continue

        ok, err = enviar_correo(smtp_server, smtp_port, smtp_username, smtp_password,
                                to_emails, cc_emails, asunto, html, logo_bytes)
        resultados.append({
            'usuario': info['nombre'],
            'estado': '✅ Sent' if ok else f'❌ {err[:80]}',
            'incidencias': len(df_usuario),
            'to': ', '.join(to_emails),
            'cc': ', '.join(cc_emails) if cc_emails else '-'
        })
        
        time.sleep(0.5)

    enviados = sum(1 for r in resultados if r['estado'].startswith('✅'))
    simulados = sum(1 for r in resultados if r['estado'].startswith('🧪'))
    advertencias = sum(1 for r in resultados if r['estado'].startswith('⚠️'))
    errores = len(resultados) - enviados - simulados - advertencias

    if dry_run:
        msg = f"🧪 Simulation: {simulados} emails would be sent | {advertencias} warnings | {errores} errors."
    else:
        msg = f"✅ {enviados} sent | ⚠️ {advertencias} warnings | ❌ {errores} errors."

    return True, msg, resultados

# ============================================================
# INTERFAZ STREAMLIT
# ============================================================

banner = get_banner_base64()
if banner:
    st.image(banner, use_container_width=True)
else:
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a3a5c, #4a7c9c);
        padding: 20px 30px; border-radius: 10px; margin-bottom: 20px;">
        <h1 style="color: white; margin: 0; font-size: 24px;">💠 Toggl Time Entry Compliance System</h1>
        <p style="color: rgba(255,255,255,0.9); margin: 4px 0 0 0;">
            Per-user incident detection and notification</p>
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📁 Data File")
    uploaded_file = st.file_uploader(
        "Upload the Excel file (sheets: Names + TogglFilterDB)",
        type=['xlsx', 'xls']
    )

    st.markdown("---")
    st.markdown("### 🧪 Test Mode")
    test_mode = st.checkbox("Test mode (send everything to my email)", value=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        btn_simular = st.button("📄 Simulate", use_container_width=True)
    with col2:
        btn_enviar = st.button("📨 Send", type="primary", use_container_width=True)

    st.caption("🔒 Secure TLS · No storage")

    # Validación visual de credenciales cargadas
    if SMTP_SERVER and SMTP_PORT and SMTP_USERNAME and SMTP_PASSWORD:
        st.success("✅ SMTP credentials loaded securely")
    else:
        st.error(f"⚠️ SMTP credentials not found. {SMTP_ERROR if SMTP_ERROR else 'Please check your Streamlit Secrets.'}")

if uploaded_file is not None:
    try:
        df_names, df_inc = cargar_hojas(uploaded_file)

        st.markdown("### 📊 Data Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Users (Names)", len(df_names))
        c2.metric("Incidents (TogglFilterDB)", len(df_inc))
        c3.metric("Users with incidents", df_inc['Member'].nunique() if 'Member' in df_inc.columns else 0)
        c4.metric("Today", obtener_hora_local().strftime('%m/%d/%Y'))

        with st.expander("👁️ Preview — Names (Active)"):
            if 'USER STATUS' in df_names.columns:
                df_active = df_names[df_names['USER STATUS'].astype(str).str.strip().str.lower() == 'active']
            else:
                df_active = df_names
            cols_prev = [c for c in ['NAME CORRECT', 'PREFIX', 'EMAIL', 'COPY_EMAIL_TG'] if c in df_active.columns]
            st.dataframe(df_active[cols_prev].head(20), use_container_width=True)

        with st.expander("👁️ Preview — TogglFilterDB"):
            st.dataframe(df_inc.head(20), use_container_width=True)

        faltantes = [c for c in ['Member', 'Date', 'Duration', 'Type of incident'] if c not in df_inc.columns]
        if faltantes:
            st.warning(f"⚠️ Missing columns in TogglFilterDB: {faltantes}. "
                       f"Current columns: {list(df_inc.columns)}")

        if btn_simular or btn_enviar:
            if not SMTP_SERVER or not SMTP_PORT or not SMTP_USERNAME or not SMTP_PASSWORD:
                st.error("⚠️ No SMTP credentials found. Please configure them in Streamlit Secrets.")
            else:
                if btn_enviar and not test_mode:
                    st.warning("🔴 REAL send enabled: emails will go to users and their CC.")
                with st.spinner("Processing..."):
                    ok, msg, resultados = procesar_y_enviar(
                        df_names, df_inc,
                        SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
                        test_mode=test_mode,
                        dry_run=btn_simular
                    )
                st.markdown("### 📋 Results")
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

                if resultados:
                    st.dataframe(pd.DataFrame(resultados), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error: {e}")
        st.code(traceback.format_exc())
else:
    st.info("📌 Upload the Excel file in the sidebar to begin.")
