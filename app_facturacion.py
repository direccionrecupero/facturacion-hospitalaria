# ============================================================================
# APP FACTURACIÓN HOSPITALARIA - EPSA JUJUY
# Autor: AI Assistant | Versión: 1.0 | Fecha: 2026-01-21
# ============================================================================
# Aplicación profesional para gestión consolidada de facturación hospitalaria
# Características: Dashboard ejecutivo, alertas automáticas, normalización Excel
# ============================================================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
from pathlib import Path
import json

# ============================================================================
# 1. CONFIGURACIÓN INICIAL
# ============================================================================

st.set_page_config(
    page_title="Facturación Hospitalaria EPSA",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .main { background-color: #f8f9fa; }
    .metric-card { 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .alert-card {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .success-card {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .error-card {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    h1 { color: #2c3e50; border-bottom: 3px solid #667eea; padding-bottom: 10px; }
    h2 { color: #34495e; }
    h3 { color: #7f8c8d; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# 2. INICIALIZACIÓN DE SESIÓN
# ============================================================================

if 'db_initialized' not in st.session_state:
    st.session_state.db_initialized = False
    st.session_state.data = pd.DataFrame()
    st.session_state.contactos = pd.DataFrame()

# ============================================================================
# 3. NORMALIZACIÓN INTELIGENTE DE EXCEL
# ============================================================================

class ExcelNormalizer:
    """Normaliza Excel desorganizados a formato estándar"""
    
    @staticmethod
    def detect_hospital_name(df, headers):
        """Detecta nombre de hospital en el Excel"""
        for col in headers:
            if 'HOSPITAL' in str(col).upper() or 'CAPS' in str(col).upper():
                for val in df.iloc[:, df.columns.get_loc(col)].head(10):
                    if pd.notna(val) and len(str(val)) > 3:
                        return str(val).strip()
        return 'SIN IDENTIFICAR'
    
    @staticmethod
    def detect_period(df, headers):
        """Detecta período de facturación"""
        months = {
            'ENERO': '01', 'FEBRERO': '02', 'MARZO': '03', 'ABRIL': '04',
            'MAYO': '05', 'JUNIO': '06', 'JULIO': '07', 'AGOSTO': '08',
            'SEPTIEMBRE': '09', 'OCTUBRE': '10', 'NOVIEMBRE': '11', 'DICIEMBRE': '12',
            'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05',
            'JUN': '06', 'JUL': '07', 'AUG': '08', 'SEP': '09', 'OCT': '10',
            'NOV': '11', 'DEC': '12'
        }
        
        for col in headers:
            if any(x in str(col).upper() for x in ['PERIODO', 'MES', 'FECHA']):
                for val in df.iloc[:, df.columns.get_loc(col)].head(10):
                    if pd.notna(val):
                        val_str = str(val).upper()
                        for month_name, month_num in months.items():
                            if month_name in val_str:
                                return f"{month_name}/2025"
        return datetime.now().strftime('%B/%Y')
    
    @staticmethod
    def detect_prestacion(df, headers):
        """Detecta tipo de prestación"""
        for col in headers:
            if 'PRESTACION' in str(col).upper():
                val = str(df.iloc[0, df.columns.get_loc(col)]).upper()
                if 'INTERNADO' in val:
                    return 'INTERNADOS'
                elif 'AMBULATORIO' in val:
                    return 'AMBULATORIO H' if 'H' in val else 'AMBULATORIO C'
        return 'AMBULATORIO H'
    
    @staticmethod
    def normalize(file_path):
        """Normaliza un Excel a formato estándar"""
        try:
            df = pd.read_excel(file_path, sheet_name=0, skiprows=3)
            df = df.dropna(how='all')
            
            hospital = ExcelNormalizer.detect_hospital_name(df, df.columns)
            period = ExcelNormalizer.detect_period(df, df.columns)
            prestacion = ExcelNormalizer.detect_prestacion(df, df.columns)
            
            df_norm = pd.DataFrame()
            
            # Mapeo flexible de columnas
            for col in df.columns:
                col_upper = str(col).upper()
                
                if 'RNOS' in col_upper or 'OBRA SOCIAL' in col_upper:
                    df_norm['RNOS'] = pd.to_numeric(df[col], errors='coerce').astype(int)
                elif 'CANTIDAD' in col_upper and any(x in col_upper for x in ['ODA', 'ODI', 'ORDEN']):
                    df_norm['CANTIDAD_ORDENES'] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                elif 'MONTO' in col_upper or 'TOTAL' in col_upper:
                    monto_clean = df[col].astype(str).str.replace('$', '').str.replace(',', '.').str.strip()
                    df_norm['MONTO'] = pd.to_numeric(monto_clean, errors='coerce').fillna(0)
            
            df_norm['NOMBRE_HOSPITAL'] = hospital
            df_norm['TIPO_PRESTACION'] = prestacion
            df_norm['MES_PRESENTACION'] = period
            df_norm['ESTADO'] = 'PENDIENTE'
            df_norm['MORA_DIAS'] = 0
            df_norm['MAIL'] = ''
            df_norm['SIGEXP'] = ''
            df_norm['OBS'] = ''
            df_norm['NOTA'] = ''
            df_norm['EMAIL_HOSPITAL'] = ''
            
            return df_norm, {
                'status': 'success',
                'hospital': hospital,
                'periodo': period,
                'prestacion': prestacion,
                'registros': len(df_norm),
                'monto_total': df_norm['MONTO'].sum()
            }
        except Exception as e:
            return None, {'status': 'error', 'mensaje': str(e)}

# ============================================================================
# 4. GESTIÓN DE BASE DE DATOS
# ============================================================================

class DatabaseManager:
    """Gestiona la base de datos SQLite"""
    
    def __init__(self, db_path='facturacion.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Inicializa la base de datos"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS facturacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_hospital TEXT,
            tipo_prestacion TEXT,
            mes_presentacion TEXT,
            rnos INTEGER,
            cantidad_ordenes INTEGER,
            efector TEXT,
            monto REAL,
            mail DATE,
            sigexp DATE,
            obs TEXT,
            nota TEXT,
            estado TEXT,
            mora_dias INTEGER,
            email_hospital TEXT,
            fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS contactos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre_hospital TEXT UNIQUE,
            email TEXT,
            telefono TEXT
        )''')
        
        conn.commit()
        conn.close()
    
    def insert_records(self, df):
        """Inserta registros en la BD"""
        conn = sqlite3.connect(self.db_path)
        df.to_sql('facturacion', conn, if_exists='append', index=False)
        conn.close()
        return True
    
    def get_all_data(self):
        """Obtiene todos los datos"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("SELECT * FROM facturacion ORDER BY fecha_carga DESC", conn)
        conn.close()
        return df
    
    def get_pending_invoices(self):
        """Obtiene facturas pendientes"""
        conn = sqlite3.connect(self.db_path)
        df = pd.read_sql_query("""
            SELECT * FROM facturacion 
            WHERE estado = 'PENDIENTE' 
            ORDER BY mora_dias DESC
        """, conn)
        conn.close()
        return df
    
    def update_status(self, ids, status):
        """Actualiza estado de registros"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        for id in ids:
            c.execute("UPDATE facturacion SET estado = ? WHERE id = ?", (status, id))
        conn.commit()
        conn.close()

# ============================================================================
# 5. SISTEMA DE ALERTAS Y EMAILS
# ============================================================================

class AlertSystem:
    """Sistema de alertas y envío de emails"""
    
    @staticmethod
    def calculate_mora(date_limit):
        """Calcula días de mora"""
        if pd.isna(date_limit):
            # Si no hay fecha presentación, calcula desde vencimiento
            today = datetime.now()
            month = today.month
            year = today.year
            
            if today.day < 5:
                month -= 1
                if month == 0:
                    month = 12
                    year -= 1
            
            vencimiento = datetime(year, month, 5)
            mora = (today - vencimiento).days
            return max(0, mora)
        return 0
    
    @staticmethod
    def send_email(destinatario, asunto, cuerpo, fecha_limite, dias_mora_limite):
        """Envía email de intimación"""
        try:
            # CONFIGURACIÓN SMTP (usuario debe usar Gmail con contraseña app)
            sender = st.secrets.get("EMAIL_USER", "tu_email@gmail.com")
            password = st.secrets.get("EMAIL_PASSWORD", "tu_contraseña")
            
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = destinatario
            msg['Subject'] = asunto
            
            cuerpo_final = cuerpo.replace("_______", fecha_limite).replace("_____", str(dias_mora_limite))
            msg.attach(MIMEText(cuerpo_final, 'plain', 'utf-8'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
            server.quit()
            
            return True
        except Exception as e:
            st.error(f"Error al enviar email: {e}")
            return False

# ============================================================================
# 6. INTERFACE PRINCIPAL
# ============================================================================

def main():
    st.title("🏥 Sistema de Facturación Hospitalaria - EPSA")
    st.markdown("Gestión consolidada de facturación ambulatoria e internaciones")
    
    # Sidebar - Navegación
    st.sidebar.title("📋 Menú Principal")
    menu = st.sidebar.radio("Selecciona una opción:", [
        "🏠 Dashboard",
        "📤 Cargar Excel",
        "📊 Análisis Ejecutivo",
        "⚠️ Alertas Pendientes",
        "📧 Enviar Intimaciones",
        "⚙️ Configuración",
        "📋 Ver Datos"
    ])
    
    # Inicializa base de datos
    db = DatabaseManager()
    
    # ========================================================================
    # SECCIÓN: DASHBOARD
    # ========================================================================
    
    if menu == "🏠 Dashboard":
        st.subheader("Panel de Control Ejecutivo")
        
        df_data = db.get_all_data()
        
        if len(df_data) > 0:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("💰 Monto Total Facturado", 
                         f"${df_data['monto'].sum():,.2f}",
                         delta=f"{len(df_data)} registros")
            
            with col2:
                st.metric("📋 Total de Órdenes",
                         f"{df_data['cantidad_ordenes'].sum():,}",
                         delta=f"Promedio: {df_data['cantidad_ordenes'].mean():.1f}")
            
            with col3:
                hospitales = df_data['nombre_hospital'].nunique()
                st.metric("🏢 Hospitales",
                         f"{hospitales}",
                         delta=f"de 33 registrados")
            
            with col4:
                pendientes = len(df_data[df_data['estado'] == 'PENDIENTE'])
                st.metric("⏳ Pendientes",
                         f"{pendientes}",
                         delta=f"{((pendientes/len(df_data)*100) if len(df_data)>0 else 0):.1f}%")
            
            # Gráficos
            st.markdown("---")
            col1, col2 = st.columns(2)
            
            with col1:
                # Top 10 hospitales por monto
                top_hospitals = df_data.groupby('nombre_hospital')['monto'].sum().nlargest(10)
                fig = px.bar(
                    x=top_hospitals.values,
                    y=top_hospitals.index,
                    orientation='h',
                    title='Top 10 Hospitales por Facturación',
                    labels={'x': 'Monto ($)', 'y': 'Hospital'},
                    color=top_hospitals.values,
                    color_continuous_scale='Viridis'
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Distribución por tipo prestación
                dist_prestacion = df_data.groupby('tipo_prestacion')['monto'].sum()
                fig = px.pie(
                    values=dist_prestacion.values,
                    names=dist_prestacion.index,
                    title='Distribución por Tipo de Prestación',
                    color_discrete_sequence=['#667eea', '#764ba2', '#f093fb']
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Tabla resumen
            st.markdown("---")
            st.subheader("📊 Resumen por Hospital")
            
            resumen = df_data.groupby('nombre_hospital').agg({
                'monto': ['sum', 'count'],
                'cantidad_ordenes': 'sum'
            }).round(2)
            resumen.columns = ['Monto Total', 'Registros', 'Total Órdenes']
            resumen['% del Total'] = (resumen['Monto Total'] / resumen['Monto Total'].sum() * 100).round(2)
            resumen = resumen.sort_values('Monto Total', ascending=False)
            
            st.dataframe(resumen, use_container_width=True)
        
        else:
            st.info("📭 No hay datos cargados. Comienza por cargar un Excel.")
    
    # ========================================================================
    # SECCIÓN: CARGAR EXCEL
    # ========================================================================
    
    elif menu == "📤 Cargar Excel":
        st.subheader("Cargar Facturación de Hospital")
        
        uploaded_file = st.file_uploader(
            "Selecciona archivo Excel (.xlsx)",
            type=['xlsx', 'xls']
        )
        
        if uploaded_file:
            with st.spinner("Normalizando Excel..."):
                temp_path = f"temp_{uploaded_file.name}"
                with open(temp_path, 'wb') as f:
                    f.write(uploaded_file.getbuffer())
                
                df_normalized, info = ExcelNormalizer.normalize(temp_path)
                
                if info['status'] == 'success':
                    st.success(f"✅ Excel normalizado correctamente")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Hospital", info['hospital'])
                    with col2:
                        st.metric("Período", info['periodo'])
                    with col3:
                        st.metric("Prestación", info['prestacion'])
                    
                    st.markdown("---")
                    st.write(f"📋 {info['registros']} registros | 💰 ${info['monto_total']:,.2f}")
                    
                    st.dataframe(df_normalized, use_container_width=True)
                    
                    if st.button("✅ Cargar a Base de Datos", key="cargar_bd"):
                        db.insert_records(df_normalized)
                        st.success("✅ Datos cargados correctamente en la BD")
                        Path(temp_path).unlink()
                else:
                    st.error(f"❌ Error: {info['mensaje']}")
    
    # ========================================================================
    # SECCIÓN: ANÁLISIS EJECUTIVO
    # ========================================================================
    
    elif menu == "📊 Análisis Ejecutivo":
        st.subheader("Análisis Ejecutivo Detallado")
        
        df_data = db.get_all_data()
        
        if len(df_data) > 0:
            # Filtros
            col1, col2, col3 = st.columns(3)
            
            with col1:
                hospital_filter = st.multiselect(
                    "Filtrar por Hospital:",
                    df_data['nombre_hospital'].unique(),
                    default=df_data['nombre_hospital'].unique()
                )
            
            with col2:
                prestacion_filter = st.multiselect(
                    "Filtrar por Prestación:",
                    df_data['tipo_prestacion'].unique(),
                    default=df_data['tipo_prestacion'].unique()
                )
            
            with col3:
                estado_filter = st.multiselect(
                    "Filtrar por Estado:",
                    df_data['estado'].unique(),
                    default=df_data['estado'].unique()
                )
            
            # Aplica filtros
            df_filtered = df_data[
                (df_data['nombre_hospital'].isin(hospital_filter)) &
                (df_data['tipo_prestacion'].isin(prestacion_filter)) &
                (df_data['estado'].isin(estado_filter))
            ]
            
            if len(df_filtered) > 0:
                # Métricas
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("💰 Total Filtrado", f"${df_filtered['monto'].sum():,.2f}")
                
                with col2:
                    st.metric("📋 Órdenes Filtradas", f"{df_filtered['cantidad_ordenes'].sum():,}")
                
                with col3:
                    st.metric("🏢 Hospitales Filtrados", df_filtered['nombre_hospital'].nunique())
                
                # Gráficos avanzados
                st.markdown("---")
                col1, col2 = st.columns(2)
                
                with col1:
                    # Evolución mensual
                    evoluccion_mes = df_filtered.groupby('mes_presentacion')['monto'].sum()
                    fig = px.line(
                        x=evoluccion_mes.index,
                        y=evoluccion_mes.values,
                        markers=True,
                        title='Evolución de Facturación Mensual',
                        labels={'x': 'Mes', 'y': 'Monto ($)'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    # Órdenes por hospital
                    ordenes_hosp = df_filtered.groupby('nombre_hospital')['cantidad_ordenes'].sum().nlargest(8)
                    fig = px.bar(
                        x=ordenes_hosp.index,
                        y=ordenes_hosp.values,
                        title='Top 8 Hospitales por Cantidad de Órdenes',
                        labels={'x': 'Hospital', 'y': 'Órdenes'}
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                # Ranking detallado
                st.markdown("---")
                st.subheader("📊 Ranking Detallado de Facturación")
                
                ranking = df_filtered.groupby('nombre_hospital').agg({
                    'monto': 'sum',
                    'cantidad_ordenes': 'sum'
                }).round(2)
                ranking['Promedio por Orden'] = (ranking['monto'] / ranking['cantidad_ordenes']).round(2)
                ranking['% del Total'] = (ranking['monto'] / ranking['monto'].sum() * 100).round(2)
                ranking.columns = ['Facturación Total', 'Total Órdenes', 'Promedio por Orden', '% del Total']
                ranking = ranking.sort_values('Facturación Total', ascending=False)
                ranking.insert(0, 'Ranking', range(1, len(ranking) + 1))
                
                st.dataframe(ranking, use_container_width=True)
                
                # Descargar análisis
                buffer = BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    ranking.to_excel(writer, sheet_name='Ranking')
                    df_filtered.to_excel(writer, sheet_name='Detalle')
                
                st.download_button(
                    label="📥 Descargar Análisis Excel",
                    data=buffer.getvalue(),
                    file_name=f"analisis_facturacion_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    # ========================================================================
    # SECCIÓN: ALERTAS PENDIENTES
    # ========================================================================
    
    elif menu == "⚠️ Alertas Pendientes":
        st.subheader("Facturaciones Pendientes de Presentación")
        
        df_pending = db.get_pending_invoices()
        
        if len(df_pending) > 0:
            st.warning(f"⚠️ {len(df_pending)} facturas pendientes de presentación")
            
            # Agrupa por hospital y mes
            alertas = df_pending.groupby(['nombre_hospital', 'mes_presentacion']).agg({
                'monto': 'sum',
                'cantidad_ordenes': 'sum',
                'mora_dias': 'first'
            }).reset_index()
            alertas = alertas.sort_values('mora_dias', ascending=False)
            
            st.dataframe(alertas, use_container_width=True)
            
            st.markdown("---")
            st.subheader("📧 Enviar Notificaciones")
            
            if st.button("📤 Enviar Alertas a Hospitales"):
                st.info("Las alertas serían enviadas a los contactos registrados (feature en desarrollo)")
        
        else:
            st.success("✅ No hay alertas pendientes - Toda la facturación está presentada")
    
    # ========================================================================
    # SECCIÓN: ENVIAR INTIMACIONES
    # ========================================================================
    
    elif menu == "📧 Enviar Intimaciones":
        st.subheader("Sistema de Intimaciones Automáticas")
        
        df_pending = db.get_pending_invoices()
        
        if len(df_pending) > 0:
            st.info("Configura los parámetros para enviar intimaciones")
            
            col1, col2 = st.columns(2)
            
            with col1:
                fecha_limite = st.text_input(
                    "Fecha límite para presentación (ej: 10 de febrero de 2026):",
                    value=f"{(datetime.now() + timedelta(days=5)).day} de {(datetime.now() + timedelta(days=5)).strftime('%B de %Y')}"
                )
            
            with col2:
                dias_mora = st.number_input(
                    "Días máximos de mora permitidos:",
                    value=30,
                    min_value=1,
                    max_value=180
                )
            
            st.markdown("---")
            
            # Plantilla de email
            plantilla = """Por medio del presente se requiere presentar, con fecha límite e improrrogable del _______de 08:00 a 16.00 hrs, las facturaciones de OSN de Ambulatorio e Internación pendientes.  
Motiva el pedido la necesidad de efectuar el cierre de todos los períodos adeudados a fin de alcanzar los objetivos propuestos por este Ministerio. 
Vencido dicho plazo no se aceptarán presentaciones  con mas de _____ días de vencidas.
Lo expuesto anteriormente se encuadra según lo dispuesto por Resolución Nº81686-S-2024 (Hoja de Ruta para comunicaciones y consecuencias ante su incumplimiento)
Asimismo, se les recuerda que, previa a presentación física de los expedientes en esta Dirección, deberán:
- Enviar por mail las Planillas de Facturación en formato excel indicando en el asunto el periodo y prestación facturada (un mail por periodo). 
- Utilizar y respetar el formato de la planilla excel oportunamente enviada y, las observaciones efectuadas a cada efector.
- Adjuntarse  impresos a la carátula del expediente físico: 1) mail de envío de planilla de facturación y 2) remito de pase de expediente (SIGEXP)
Quedan Uds. debidamente notificados.-
Sin otro particular, saludo a Uds. atentamente 
Director General - Abogado Javier G. Recupero
Direccion General de Seguridad Social, Financiamiento y Recupero"""
            
            st.text_area("Plantilla de Email:", value=plantilla, height=300, disabled=True)
            
            st.markdown("---")
            
            if st.button("📧 Enviar Intimaciones (Simulación)", key="enviar_intimaciones"):
                st.info("✅ Sistema de envío configurado. Para activar envío real, configura credenciales SMTP en secrets.")
                
                for idx, row in df_pending.iterrows():
                    st.write(f"📧 {row['nombre_hospital']} - {row['mes_presentacion']}")
        
        else:
            st.success("✅ No hay pendientes para intimar")
    
    # ========================================================================
    # SECCIÓN: CONFIGURACIÓN
    # ========================================================================
    
    elif menu == "⚙️ Configuración":
        st.subheader("⚙️ Configuración del Sistema")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📧 Configuración de Emails")
            st.info("""
            Para habilitar envío automático de emails:
            1. Crea archivo `secrets.toml` en tu aplicación
            2. Agrega:
            ```
            EMAIL_USER = "tu_email@gmail.com"
            EMAIL_PASSWORD = "tu_contraseña_app"
            ```
            """)
        
        with col2:
            st.markdown("### 🗄️ Base de Datos")
            st.info("""
            Base de datos: SQLite (facturacion.db)
            Tablas: 
            - facturacion
            - contactos
            
            Tamaño: Optimizado para 11.000+ registros
            """)
        
        st.markdown("---")
        
        # Estado del sistema
        st.markdown("### 📊 Estado del Sistema")
        df_data = db.get_all_data()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Registros", len(df_data))
        with col2:
            st.metric("Hospitales", df_data['nombre_hospital'].nunique() if len(df_data) > 0 else 0)
        with col3:
            st.metric("Monto Total", f"${df_data['monto'].sum():,.2f}" if len(df_data) > 0 else "$0.00")
    
    # ========================================================================
    # SECCIÓN: VER DATOS
    # ========================================================================
    
    elif menu == "📋 Ver Datos":
        st.subheader("Vista Completa de Datos")
        
        df_data = db.get_all_data()
        
        if len(df_data) > 0:
            # Opciones de visualización
            col1, col2, col3 = st.columns(3)
            
            with col1:
                mostrar = st.selectbox("Mostrar:", ["Todos", "Solo Pendientes", "Solo Presentados"])
            
            with col2:
                ordenar = st.selectbox("Ordenar por:", ["Fecha Carga", "Monto", "Hospital", "Fecha Presentación"])
            
            with col3:
                registros_mostrar = st.number_input("Registros a mostrar:", value=100, min_value=10, max_value=10000)
            
            # Filtra datos
            if mostrar == "Solo Pendientes":
                df_show = df_data[df_data['estado'] == 'PENDIENTE']
            elif mostrar == "Solo Presentados":
                df_show = df_data[df_data['estado'] == 'PRESENTADO']
            else:
                df_show = df_data
            
            # Ordena datos
            if ordenar == "Monto":
                df_show = df_show.sort_values('monto', ascending=False)
            elif ordenar == "Hospital":
                df_show = df_show.sort_values('nombre_hospital')
            
            st.dataframe(df_show.head(registros_mostrar), use_container_width=True)
            
            # Descargar
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_show.to_excel(writer, sheet_name='Datos')
            
            st.download_button(
                label="📥 Descargar Datos Completos",
                data=buffer.getvalue(),
                file_name=f"facturacion_completa_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        else:
            st.info("No hay datos para mostrar")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #7f8c8d; font-size: 0.85em;'>
    🏥 Sistema de Facturación Hospitalaria EPSA - Jujuy | v1.0 | 2026-01-21
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
