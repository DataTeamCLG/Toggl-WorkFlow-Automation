import streamlit as st
import pandas as pd
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import base64
from datetime import datetime
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
    page_title="Notificador de Incidentes Toggl",
    page_icon="⚠️",
    layout="wide"
)

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

SMTP_SERVER = "smtp.office365.com"
SMTP_PORT = 587

URL_LOGO_GITHUB = "https://raw.githubusercontent.com/Iamnotmanolotaco/Inmigration-USCIS-Alerts-Automation/main/clgam.png"
URL_BANNER_GITHUB = "https://raw.githubusercontent.com/Iamnotmanolotaco/Inmigration-USCIS-Alerts-Automation/main/banner.png"

NOMBRE_EMPRESA = "Community Law Group, PLLC® "
DEPARTAMENTO = "Quality Control & Efficiency Department"
TELEFONO = "+1 (615) 913-5576"
EMAIL_CONTACTO = "executiveassistant2@communitylawgroup.com"
SITIO_WEB = "www.communitylawgroup.com"

TAMANO_LOGO = 190
LOGO_WIDTH = 180

ZONA_HORARIA = pytz.timezone('America/Bogota')

HOJA_NAMES = "Names"
HOJA_INCIDENTES = "TogglFilterDB"

# ============================================================
# RECURSOS (logo / banner)
# ============================================================

def get_image_from_github(url):
    try:
        r = requests.get(url, timeout=10)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def resize_logo(logo_bytes, target_width=LOGO_WIDTH):
    try:
        if logo_bytes is None:
            return None
        img = Image.open(BytesIO(logo_bytes))
        w, h = img.size
        target_height = int(target_width * (h / w))
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format='PNG', quality=95, optimize=True)
        out.seek(0)
        return out.getvalue()
    except Exception:
        return logo_bytes


def get_logo_bytes():
    b = get_image_from_github(URL_LOGO_GITHUB)
    return resize_logo(b, LOGO_WIDTH) if b else None


def get_banner_base64():
    b = get_image_from_github(URL_BANNER_GITHUB)
    if b:
        return f"data:image/png;base64,{base64.b64encode(b).decode('utf-8')}"
    return None

# ============================================================
# UTILIDADES
# ============================================================

def obtener_saludo():
    h = datetime.now(ZONA_HORARIA).hour
    if 6 <= h < 12:
        return "Buenos días"
    elif 12 <= h < 18:
        return "Buenas tardes"
    return "Buenas noches"


def obtener_hora_local():
    return datetime.now(ZONA_HORARIA)


def limpiar_emails(valor):
    """Convierte 'a@x.com; b@y.com, c@z.com' en lista limpia."""
    if pd.isna(valor) or valor is None:
        return []
    txt = str(valor).strip()
    if txt.lower() in ('disabled', 'n/a', ''):
        return []
    partes = re.split(r'[;,\n]+', txt)
    return [p.strip() for p in partes if p.strip() and '@' in p.strip()]


def normalizar_nombre(nombre):
    """Para hacer match tolerante entre NAME CORRECT y Corrected Name."""
    if pd.isna(nombre):
        return ""
    return re.sub(r'\s+', ' ', str(nombre).strip()).lower()


def formatear_duracion(valor):
    """Duration viene como 'H:MM:SS' o como fracción de día (Excel time)."""
    if pd.isna(valor):
        return ""
    if isinstance(valor, (int, float)):
        total_seg = int(round(valor * 86400))
        h, rem = divmod(total_seg, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    s = str(valor).strip()
    if re.match(r'^\d+:\d{2}:\d{2}$', s):
        return s
    if re.match(r'^\d+:\d{2}$', s):
        return s + ":00"
    return s


def formatear_fecha(valor):
    if pd.isna(valor):
        return ""
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.strftime('%d/%m/%Y')
    try:
        return pd.to_datetime(valor).strftime('%d/%m/%Y')
    except Exception:
        return str(valor)

# ============================================================
# HTML DEL CORREO
# ============================================================

def generar_html_incidencias(usuario_info, df_usuario, logo_cid=None):
    saludo = obtener_saludo()
    prefix = usuario_info.get('prefix', '')
    nombre = usuario_info.get('nombre', '')
    saludo_completo = f"{saludo} {prefix} {nombre},".replace("  ", " ").strip()

    filas = ""
    for _, row in df_usuario.iterrows():
        fecha = formatear_fecha(row.get('Date', ''))
        proyecto = row.get('Project (Activity)', '')
        cliente = row.get('Client Tag', '')
        descripcion = row.get('Description', '')
        duracion = formatear_duracion(row.get('Duration', ''))
        tipo = row.get('Type of incident', row.get('Type of Incident', ''))
        obs = row.get('Observations', '')

        filas += f"""
        <tr class="fila-normal">
            <td class="col-fecha">{fecha}</td>
            <td class="col-proyecto">{proyecto}</td>
            <td class="col-cliente">{cliente}</td>
            <td class="col-desc">{descripcion}</td>
            <td class="col-dur">{duracion}</td>
            <td class="col-tipo">{tipo}</td>
            <td class="col-obs">{obs}</td>
        </tr>
        """

    logo_html = ""
    if logo_cid:
        logo_html = f"""
        <div style="text-align: center; margin-bottom: 15px;">
            <img src="cid:{logo_cid}" alt="{NOMBRE_EMPRESA}" width="{TAMANO_LOGO}"
                 style="width: {TAMANO_LOGO}px; height: auto; border: none; display: block; margin: 0 auto;">
        </div>
        """

    firma_html = f"""
    <div style="margin-top: 30px; padding-top: 20px; border-top: 2px solid #b8d1e8; font-family: 'Segoe UI', 'Calibri', Arial, sans-serif;">
        {logo_html}
        <div style="text-align: center;">
            <strong style="color: #1a3a5c; font-size: 14px;">{NOMBRE_EMPRESA}</strong><br>
            <span style="color: #4a7c9c; font-size: 12px;">{DEPARTAMENTO}</span><br>
            <span style="color: #666666; font-size: 11px;">
                📞 {TELEFONO} | ✉️ <a href="mailto:{EMAIL_CONTACTO}" style="color: #4a7c9c; text-decoration: none;">{EMAIL_CONTACTO}</a> | 🌐 <a href="https://{SITIO_WEB}" style="color: #4a7c9c; text-decoration: none;">{SITIO_WEB}</a>
            </span>
        </div>
    </div>
    """

    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Segoe UI', 'Calibri', Arial, sans-serif;
                line-height: 1.5; color: #000000; margin: 0; padding: 0;
                background-color: #f5f7fa;
            }}
            .container {{
                max-width: 950px; margin: 0 auto; padding: 25px;
                background-color: #ffffff; border: 1px solid #dce4ec;
            }}
            .header {{
                background-color: #e8f0f8; padding: 20px;
                border-bottom: 2px solid #b8d1e8; text-align: center;
            }}
            .header h1 {{ margin: 0; font-size: 22px; font-weight: bold; color: #1a3a5c; }}
            .header p {{ margin: 4px 0 0 0; font-size: 13px; color: #4a7c9c; }}
            .saludo {{
                background-color: #f0f6fc; border-left: 3px solid #4a7c9c;
                padding: 12px 18px; margin: 20px 0; font-size: 15px; color: #000000;
            }}
            .saludo strong {{ color: #1a3a5c; font-weight: bold; }}
            .tabla-resumen {{
                margin: 25px 0; border: 1px solid #dce4ec;
                background-color: #ffffff; border-radius: 4px; overflow: hidden;
            }}
            .tabla-resumen table {{
                width: 100%; border-collapse: collapse; font-size: 12px;
            }}
            .tabla-resumen th {{
                background-color: #e8f0f8; color: #1a3a5c; font-weight: bold;
                padding: 10px 8px; text-align: left; border-bottom: 2px solid #b8d1e8;
            }}
            .tabla-resumen td {{
                padding: 10px 8px; color: #000000;
                border-bottom: 1px solid #e8edf2; vertical-align: top;
            }}
            .tabla-resumen tr:last-child td {{ border-bottom: none; }}
            .fila-normal:hover {{ background-color: #f8fafc; }}
            .agradecimiento {{
                background-color: #f0f6fc; padding: 12px 18px; margin-top: 25px;
                text-align: center; font-size: 13px; color: #000000;
                border-top: 1px solid #dce4ec; border-radius: 4px;
            }}
            .badge-count {{
                display: inline-block; background-color: #1a3a5c; color: #ffffff;
                padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚠️ Notificación de Incidentes — Toggl</h1>
                <p>Registro de incidencias detectadas</p>
            </div>
            <div class="saludo">
                <strong>{saludo_completo}</strong><br>
                Se han detectado <span class="badge-count">{len(df_usuario)}</span>
                incidencia(s) en tu registro de horas de Toggl. A continuación el detalle:
            </div>
            <div class="tabla-resumen">
                <table>
                    <thead>
                        <tr>
                            <th>Fecha</th>
                            <th>Proyecto (Activity)</th>
                            <th>Client Tag</th>
                            <th>Descripción</th>
                            <th>Duración</th>
                            <th>Tipo de Incidente</th>
                            <th>Observaciones</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filas}
                    </tbody>
                </table>
            </div>
            <div class="agradecimiento">
                Por favor revisa y corrige las incidencias. Si tienes dudas, contacta al departamento de Quality Control.<br>
                Gracias por tu atención.
            </div>
            {firma_html}
        </div>
    </body>
    </html>
    """
    return html

# ============================================================
# ENVÍO DE CORREO
# ============================================================

def enviar_correo(smtp_username, smtp_password, to_emails, cc_emails,
                  subject, html_body, logo_bytes=None):
    try:
        msg = MIMEMultipart('related')
        msg['Subject'] = subject
        msg['From'] = smtp_username
        msg['To'] = ", ".join(to_emails)
        if cc_emails:
            msg['CC'] = ", ".join(cc_emails)
        msg['X-Priority'] = '1'

        msg.attach(MIMEText(html_body, 'html'))

        if logo_bytes:
            try:
                cid = "company_logo_cid"
                img = MIMEImage(logo_bytes)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename='logo.png')
                img.add_header('X-Attachment-Id', cid)
                msg.attach(img)
            except Exception as e:
                print(f"Error logo: {e}")

        ctx = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
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
    """Carga Names y TogglFilterDB del Excel subido."""
    xls = pd.ExcelFile(uploaded_file, engine='openpyxl')

    hojas = {re.sub(r'\s+', '', h).lower(): h for h in xls.sheet_names}

    if re.sub(r'\s+', '', HOJA_NAMES).lower() not in hojas:
        raise ValueError(f"No se encontró la hoja '{HOJA_NAMES}'. Hojas disponibles: {xls.sheet_names}")
    if re.sub(r'\s+', '', HOJA_INCIDENTES).lower() not in hojas:
        raise ValueError(f"No se encontró la hoja '{HOJA_INCIDENTES}'. Hojas disponibles: {xls.sheet_names}")

    df_names = pd.read_excel(xls, sheet_name=hojas[re.sub(r'\s+', '', HOJA_NAMES).lower()])
    df_inc = pd.read_excel(xls, sheet_name=hojas[re.sub(r'\s+', '', HOJA_INCIDENTES).lower()])
    return df_names, df_inc


def construir_mapa_usuarios(df_names):
    """
    Devuelve dict {nombre_normalizado: {nombre, prefix, email, cc}}.
    Solo incluye usuarios con USER STATUS == 'Active'.
    """
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


def procesar_y_enviar(df_names, df_inc, smtp_user, smtp_pass,
                     test_mode=False, dry_run=False):
    """Devuelve (ok, mensaje, resumen_lista)."""
    resultados = []

    mapa_usuarios = construir_mapa_usuarios(df_names)

    if 'Member' not in df_inc.columns:
        return False, f"La hoja '{HOJA_INCIDENTES}' no tiene columna 'Member'. Columnas: {list(df_inc.columns)}", []

    logo_bytes = get_logo_bytes()
    logo_cid = "company_logo_cid" if logo_bytes else None

    df_inc = df_inc.copy()

    # ============================================================
    # MATCH: usamos 'Corrected Name' con fallback a 'Member'
    # ============================================================
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
                'estado': '⚠️ No encontrado en Names o no está Active',
                'incidencias': len(df_usuario),
                'to': '-',
                'cc': '-'
            })
            continue

        if test_mode:
            to_emails = [smtp_user] if smtp_user else []
            cc_emails = []
        else:
            to_emails = [info['email']]
            cc_emails = info['cc']

        if not to_emails:
            resultados.append({
                'usuario': info['nombre'],
                'estado': '⚠️ Sin destinatario',
                'incidencias': len(df_usuario),
                'to': '-',
                'cc': '-'
            })
            continue

        asunto = f"⚠️ Incidentes Toggl — {info['nombre']}"
        if test_mode:
            asunto = f"[PRUEBA] {asunto}"

        html = generar_html_incidencias(info, df_usuario, logo_cid)

        if dry_run:
            resultados.append({
                'usuario': info['nombre'],
                'estado': '🧪 Simulado',
                'incidencias': len(df_usuario),
                'to': ', '.join(to_emails),
                'cc': ', '.join(cc_emails) if cc_emails else '-'
            })
            continue

        ok, err = enviar_correo(smtp_user, smtp_pass, to_emails, cc_emails,
                                asunto, html, logo_bytes)
        resultados.append({
            'usuario': info['nombre'],
            'estado': '✅ Enviado' if ok else f'❌ {err[:80]}',
            'incidencias': len(df_usuario),
            'to': ', '.join(to_emails),
            'cc': ', '.join(cc_emails) if cc_emails else '-'
        })

    enviados = sum(1 for r in resultados if r['estado'].startswith('✅'))
    simulados = sum(1 for r in resultados if r['estado'].startswith('🧪'))
    advertencias = sum(1 for r in resultados if r['estado'].startswith('⚠️'))
    errores = len(resultados) - enviados - simulados - advertencias

    if dry_run:
        msg = f"🧪 Simulación: {simulados} correos se enviarían | {advertencias} advertencias | {errores} errores."
    else:
        msg = f"✅ {enviados} enviados | ⚠️ {advertencias} advertencias | ❌ {errores} errores."

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
        <h1 style="color: white; margin: 0; font-size: 24px;">⚠️ Notificador de Incidentes Toggl</h1>
        <p style="color: rgba(255,255,255,0.9); margin: 4px 0 0 0;">
            Detección y notificación de incidencias por usuario</p>
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 📧 Configuración SMTP")
    smtp_username = st.text_input("Correo de Outlook", value="", placeholder="tu@email.com")
    smtp_password = st.text_input("Contraseña", type="password", placeholder="••••••••")

    st.markdown("---")
    st.markdown("### 📁 Archivo de Datos")
    uploaded_file = st.file_uploader(
        "Sube el Excel (hojas: Names + TogglFilterDB)",
        type=['xlsx', 'xls']
    )

    st.markdown("---")
    st.markdown("### 🧪 Modo prueba")
    test_mode = st.checkbox("Modo prueba (envía todo a tu correo)", value=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        btn_simular = st.button("📄 Simular", use_container_width=True)
    with col2:
        btn_enviar = st.button("📨 Enviar", type="primary", use_container_width=True)

    st.caption("🔒 TLS seguro · Sin almacenamiento")

if uploaded_file is not None:
    try:
        df_names, df_inc = cargar_hojas(uploaded_file)

        st.markdown("### 📊 Resumen de datos")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Usuarios (Names)", len(df_names))
        c2.metric("Incidencias (TogglFilterDB)", len(df_inc))
        c3.metric("Usuarios con incidencia", df_inc['Member'].nunique() if 'Member' in df_inc.columns else 0)
        c4.metric("Hoy", obtener_hora_local().strftime('%d/%m/%Y'))

        with st.expander("👁️ Vista previa — Names (Active)"):
            if 'USER STATUS' in df_names.columns:
                df_active = df_names[df_names['USER STATUS'].astype(str).str.strip().str.lower() == 'active']
            else:
                df_active = df_names
            cols_prev = [c for c in ['NAME CORRECT', 'PREFIX', 'EMAIL', 'COPY_EMAIL_TG'] if c in df_active.columns]
            st.dataframe(df_active[cols_prev].head(20), use_container_width=True)

        with st.expander("👁️ Vista previa — TogglFilterDB"):
            st.dataframe(df_inc.head(20), use_container_width=True)

        faltantes = [c for c in ['Member', 'Date', 'Duration', 'Type of incident'] if c not in df_inc.columns]
        if faltantes:
            st.warning(f"⚠️ Faltan columnas en TogglFilterDB: {faltantes}. "
                       f"Columnas actuales: {list(df_inc.columns)}")

        if btn_simular or btn_enviar:
            if btn_enviar and (not smtp_username or not smtp_password):
                st.error("⚠️ Ingresa credenciales SMTP para enviar.")
            else:
                if btn_enviar and not test_mode:
                    st.warning("🔴 Envío REAL activado: los correos irán a los usuarios y sus CC.")
                with st.spinner("Procesando..."):
                    ok, msg, resultados = procesar_y_enviar(
                        df_names, df_inc,
                        smtp_username, smtp_password,
                        test_mode=test_mode,
                        dry_run=btn_simular
                    )
                st.markdown("### 📋 Resultados")
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
    st.info("📌 Sube el archivo Excel en la barra lateral para comenzar.")