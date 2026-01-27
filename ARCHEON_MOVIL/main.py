import flet as ft
import os
import sys
import time
import threading
import google.generativeai as genai
import json
import uuid
import yt_dlp
from pathlib import Path
from datetime import datetime
from gtts import gTTS

# --- CONFIGURACIÓN DE RUTAS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# --- IMPORTACIONES DEL NÚCLEO ---
try:
    from archeon_cloud import CloudManager
    from archeon_openrouter import OpenRouterAdapter
    from archeon_reasoner import ArcheonReasoner, Intent
    from archeon_context_memory import ContextMemory
except ImportError as e:
    print(f"⚠️ Módulos limitados: {e}")
    CloudManager = None
    OpenRouterAdapter = None
    ArcheonReasoner = None
    ContextMemory = None

# --- CREDENCIALES ---
os.environ["GOOGLE_API_KEY"] = "AIzaSyDzopiLUB2ZRLfu1vgFy5XpSoBgnZQXTzA"
os.environ["OPENROUTER_API_KEY"] = "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"

# Configurar Gemini
API_KEY = os.environ.get("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
    GEMINI_ACTIVO = True
else:
    GEMINI_ACTIVO = False

# --- ESTILOS ---
C_BG = "#050505"
C_PANEL = "#141419"
C_ACCENT = "#00f3ff"
C_TEXT = "#ffffff"
C_DIM = "#a1a1aa"
C_ERROR = "#ff2a6d"
C_SUCCESS = "#00ff88"
C_WARNING = "#ffaa00"
C_BG_CARD = "#1a1a2e"
C_BG_MAIN = "#050505"
C_BORDER = "#333333"
C_TEXT_DIM = "#a1a1aa"

# =================================================================
# CLASE: CONFIGURACIÓN PERSISTENTE (CON VOZ)
# =================================================================
class ConfigManager:
    def __init__(self):
        self.config_file = "archeon_mobile_config.json"
        self.default_config = {
            "asistente_nombre": "Archeon",
            "activacion_voz": False,
            "voz_comando": "oye archeon",
            "tts_activo": True,
            "tema_oscuro": True,
            "auto_conectar_pc": True,
            "ia_principal": "gemini",
            "volumen": 80,
            "notificaciones": True,
            "usuario_recordado": "",
            "recordar_usuario": False,
            "voz_rapida": False,
            "idioma_voz": "es",
            "limpiar_archivos": True
        }
        self.config = self.load_config()
    
    def load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # Merge manteniendo valores por defecto para nuevas claves
                    return {**self.default_config, **loaded}
            return self.default_config.copy()
        except Exception as e:
            print(f"⚠️ Error cargando configuración: {e}")
            return self.default_config.copy()
    
    def save_config(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"⚠️ Error guardando configuración: {e}")
            return False
    
    def get(self, key, default=None):
        val = self.config.get(key)
        if val is not None:
            return val
        return self.default_config.get(key, default)
    
    def set(self, key, value):
        self.config[key] = value
        return self.save_config()

# =================================================================
# CLASE RESPONSIVE HELPER
# =================================================================
class ResponsiveHelper:
    """Ayuda a determinar el tipo de dispositivo basado en el ancho"""
    
    @staticmethod
    def get_device_type(width):
        if width < 480:
            return "mobile"
        elif width < 768:
            return "phablet"
        elif width < 1024:
            return "tablet"
        else:
            return "desktop"
    
    @staticmethod
    def get_scaled_size(base_size, width):
        device_type = ResponsiveHelper.get_device_type(width)
        
        scale_factors = {
            "mobile": 0.9,
            "phablet": 1.0,
            "tablet": 1.2,
            "desktop": 1.4
        }
        
        factor = scale_factors.get(device_type, 1.0)
        return int(base_size * factor)
    
    @staticmethod
    def get_responsive_padding(width):
        device_type = ResponsiveHelper.get_device_type(width)
        
        if device_type == "mobile":
            return 10
        elif device_type == "phablet":
            return 15
        elif device_type == "tablet":
            return 20
        else:
            return 30

# =================================================================
# CEREBRO MÓVIL CON TTS Y YOUTUBE INTEGRADO - OPTIMIZADO
# =================================================================
class MobileNeuro:
    def __init__(self, cloud_manager, config_manager):
        self.cloud = cloud_manager
        self.config = config_manager
        self.memory = ContextMemory(max_messages=15) if ContextMemory else None
        self.reasoner = ArcheonReasoner(self.memory) if ArcheonReasoner else None
        self.router = OpenRouterAdapter() if OpenRouterAdapter else None
        self.audio_cache = {}
        self.music_playing = False
        self.current_music_url = None
        self.current_music_title = None
        self._ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'default_search': 'ytsearch1:',
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
        }
    
    def obtener_url_youtube(self, busqueda):
        """Busca en YouTube y obtiene el enlace directo de audio"""
        try:
            busqueda_limpia = busqueda.strip()
            if not busqueda_limpia:
                return None, None
                
            print(f"🔍 Buscando en YouTube: {busqueda_limpia}")
            
            with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{busqueda_limpia}", download=False)
                
                if 'entries' in info and info['entries']:
                    video = info['entries'][0]
                    formats = video.get('formats', [])
                    audio_formats = [f for f in formats if f.get('acodec') != 'none']
                    
                    if audio_formats:
                        audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                        return audio_formats[0]['url'], video.get('title', 'Desconocido')
                    elif 'url' in video:
                        return video['url'], video.get('title', 'Desconocido')
                
                elif 'url' in info:
                    return info['url'], info.get('title', 'Desconocido')
                    
        except Exception as e:
            print(f"❌ Error buscando música: {e}")
            import traceback
            traceback.print_exc()
            
        return None, None
    
    def generar_audio(self, texto, idioma="es", velocidad=False):
        """Convierte texto a voz y devuelve nombre del archivo"""
        try:
            texto_limpio = texto.replace("*", "").replace("#", "").replace("```", "")
            
            if len(texto_limpio) > 500:
                texto_limpio = texto_limpio[:497] + "..."
            
            filename = f"voz_{uuid.uuid4().hex[:10]}.mp3"
            assets_path = os.path.join(os.getcwd(), "assets", "voces")
            os.makedirs(assets_path, exist_ok=True)
            filepath = os.path.join(assets_path, filename)
            
            tts = gTTS(
                text=texto_limpio, 
                lang=idioma, 
                slow=not velocidad
            )
            tts.save(filepath)
            
            self.audio_cache[filename] = time.time()
            if len(self.audio_cache) > 5:
                self._limpiar_cache_antiguo()
            
            return filename
        except Exception as e:
            print(f"⚠️ Error TTS: {e}")
            return None
    
    def _limpiar_cache_antiguo(self):
        """Elimina archivos de voz antiguos del caché"""
        try:
            if len(self.audio_cache) <= 3:
                return
                
            archivos_ordenados = sorted(self.audio_cache.items(), key=lambda x: x[1])
            
            for filename, _ in archivos_ordenados[:-3]:
                try:
                    path = os.path.join(os.getcwd(), "assets", "voces", filename)
                    if os.path.exists(path):
                        os.remove(path)
                    del self.audio_cache[filename]
                except Exception as e:
                    print(f"⚠️ Error limpiando {filename}: {e}")
                    
        except Exception as e:
            print(f"❌ Error en limpieza de caché: {e}")
    
    def limpiar_archivos_voz(self):
        """Limpia todos los archivos de voz temporales"""
        try:
            voces_dir = os.path.join(os.getcwd(), "assets", "voces")
            if os.path.exists(voces_dir):
                for file in os.listdir(voces_dir):
                    if file.startswith("voz_") and file.endswith(".mp3"):
                        file_path = os.path.join(voces_dir, file)
                        try:
                            os.remove(file_path)
                        except:
                            pass
                self.audio_cache.clear()
                return True
        except Exception as e:
            print(f"⚠️ Error limpiando archivos de voz: {e}")
            return False
    
    def procesar(self, texto_usuario, imagen_path=None):
        """Procesa el mensaje del usuario"""
        response = {
            "texto": "", 
            "accion": None, 
            "dato": None, 
            "necesita_voz": True,
            "error": False
        }
        
        texto_usuario = texto_usuario.strip()
        txt_lower = texto_usuario.lower()
        
        # 1. Eliminar comando de activación
        if self.config.get("activacion_voz"):
            comando = self.config.get("voz_comando", "oye archeon").lower()
            if txt_lower.startswith(comando):
                texto_usuario = texto_usuario[len(comando):].strip()
                txt_lower = texto_usuario.lower()

        # 2. Detección de código o texto largo
        es_codigo_o_largo = False
        simbolos_codigo = ["{", "}", "function", "def ", "import ", "<html", "class ", "return ", "var ", "const ", "let "]
        
        if any(s in texto_usuario for s in simbolos_codigo):
            es_codigo_o_largo = True
            
        peticiones_ia = ["crea", "genera", "escribe", "corrige", "analiza", "explica", "resume", "dame", "haz"]
        if any(txt_lower.startswith(p) for p in peticiones_ia):
            es_codigo_o_largo = True

        if len(texto_usuario) > 60:
            es_codigo_o_largo = True
            
        # 3. VISIÓN (imagen)
        if imagen_path and GEMINI_ACTIVO:
            try:
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                with open(imagen_path, "rb") as f:
                    img_data = f.read()
                prompt = f"Analiza esta imagen. El usuario pregunta: '{texto_usuario}'. Responde en español de manera concisa."
                res = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": img_data}])
                response["texto"] = res.text
                return response
            except Exception as e:
                response["texto"] = f"⚠️ Error visual: {str(e)[:100]}"
                response["error"] = True
                return response
        
        # 4. COMANDOS ESPECIALES (sin voz)
        comandos_sin_voz = ["silenciar", "callate", "detente", "pausa", "stop"]
        if any(comando in txt_lower for comando in comandos_sin_voz):
            response["necesita_voz"] = False
        
        # 5. DETECCIÓN DE MÚSICA (Solo si NO es código/largo)
        intent = "unknown"
        
        if not es_codigo_o_largo:
            stop_keywords = ["detente", "detén", "para", "pausa", "stop", "alto"]
            if any(palabra in txt_lower for palabra in stop_keywords):
                if "música" in txt_lower or self.music_playing:
                    response["texto"] = "⏸️ Música detenida."
                    response["accion"] = "stop_music"
                    response["necesita_voz"] = False
                    self.music_playing = False
                    return response
            
            resume_keywords = ["continúa", "reanuda", "sigue", "resume", "play"]
            if any(palabra in txt_lower for palabra in resume_keywords):
                if self.current_music_url and not self.music_playing:
                    response["texto"] = "▶️ Reanudando música..."
                    response["accion"] = "resume_music"
                    response["necesita_voz"] = False
                    self.music_playing = True
                    return response

            if any(palabra in txt_lower for palabra in ["reproduce", "pon ", "escucha"]):
                if "código" not in txt_lower and "ejemplo" not in txt_lower:
                    intent = "play_music"

        # 6. EJECUCIÓN CON YOUTUBE
        if intent == "play_music":
            cancion = texto_usuario
            palabras_musica = ["reproduce", "pon", "música", "canción", "play", "escucha"]
            for palabra in palabras_musica:
                cancion = cancion.lower().replace(palabra, "")
            cancion = cancion.strip()
            
            # PC Check
            if "en la pc" in txt_lower:
                if self.cloud and hasattr(self.cloud, 'cloud_ready') and self.cloud.cloud_ready:
                    if hasattr(self.cloud, 'guardar_comando'):
                        self.cloud.guardar_comando(self.cloud.usuario_actual, "cmd_remoto", texto_usuario)
                    response["texto"] = f"📡 Enviando '{cancion}' a la PC..."
                    response["accion"] = "remote_pc"
                    response["necesita_voz"] = False
                else:
                    response["texto"] = "⚠️ No estoy conectado a la Base PC"
                return response
            
            # Búsqueda YouTube
            print(f"🎵 Buscando: {cancion}")
            url_real, titulo_real = self.obtener_url_youtube(cancion)
            
            if url_real:
                self.current_music_url = url_real
                self.current_music_title = titulo_real
                response["texto"] = f"🎵 Reproduciendo: {titulo_real}"
                response["accion"] = "play_music"
                response["dato"] = {
                    "url": url_real, 
                    "title": titulo_real, 
                    "volume": self.config.get("volumen")/100
                }
                self.music_playing = True
            else:
                response["texto"] = f"❌ No encontré '{cancion}'."
            
            return response
        
        # 7. COMANDOS PARA PC (Remote)
        if ("en la pc" in txt_lower or "en mi pc" in txt_lower) and self.cloud:
            if hasattr(self.cloud, 'cloud_ready') and self.cloud.cloud_ready:
                if hasattr(self.cloud, 'guardar_comando'):
                    self.cloud.guardar_comando(
                        self.cloud.usuario_actual, 
                        "cmd_remoto", 
                        texto_usuario
                    )
                    response["texto"] = f"📡 Comando enviado a la Base PC: {texto_usuario}"
                    response["accion"] = "remote_pc"
                    response["dato"] = texto_usuario
                    return response

        # 8. CHAT CON IA (GEMINI/OPENROUTER)
        historial = []
        if self.memory:
            try:
                historial = self.memory.get_history_for_llm()
            except: 
                historial = []
        
        sys_prompt = f"""
SYSTEM: Eres {self.config.get('asistente_nombre')}, un asistente inteligente TODO-TERRENO.

ROL GENERAL:
Ayudas en CUALQUIER TEMA: programación, tecnología, estudios, cocina, tareas diarias, explicación de conceptos, consejos prácticos y conversación general.

PRIORIDAD ABSOLUTA:
1. Comprender la INTENCIÓN REAL del usuario.
2. Responder de la forma MÁS ÚTIL y DIRECTA posible según esa intención.

DETECCIÓN DE INTENCIÓN (INTERNA):
Antes de responder, clasifica internamente la petición como UNA de estas:
- Conversación general / pregunta simple
- Explicación o aprendizaje
- Tarea práctica (cocinar, estudiar, usar algo)
- Programación / código
- Corrección o mejora de código

⚠️ REGLA CRÍTICA:
La detección de intención es SOLO INTERNA.
NUNCA expliques, menciones ni describas la intención del usuario en la respuesta.

COMPORTAMIENTO SEGÚN INTENCIÓN:

🟢 GENERAL (por defecto):
- Responde claro, natural y útil.
- Ve directo a la solución.
- Usa pasos o listas solo si aportan valor.
- Evita explicaciones innecesarias.

🟡 EXPLICACIÓN / APRENDIZAJE:
- Explica con ejemplos simples.
- Usa listas cuando ayuden a entender.
- Ajusta la profundidad al contexto.

🔵 PROGRAMACIÓN:
- Sé técnico y preciso.
- Usa buenas prácticas.
- Explica SOLO lo necesario para comprender o usar la solución.

🔴 CORRECCIÓN / MEJORA DE CÓDIGO:
(Solo si el usuario pide corregir, arreglar o mejorar)
- ZERO FLUFF.
- Diagnóstico breve en bullets.
- Código corregido OBLIGATORIO.
- Usa Markdown y separación de archivos si aplica.
- No des solo explicación: ENTREGA SOLUCIÓN.

REGLAS DE SALIDA (OBLIGATORIAS):
- Empieza directamente con la respuesta, no con introducciones.
- NO frases meta ("entiendo que…", "tu intención es…").
- NO expliques el proceso interno.
- NO nombres modos ni reglas.
- Saluda SOLO si el usuario saluda primero.
- Máximo 1 a 2 líneas antes de entrar al contenido real.

IDIOMA (REGLA CRÍTICA):
- Responde EXCLUSIVAMENTE en el idioma del último mensaje del usuario.
- Ignora el idioma del historial si difiere.
- Nunca cambies de idioma por iniciativa propia.

CONTEXTO:
Historial: {historial}
Usuario: {texto_usuario}
"""

        ia_seleccionada = self.config.get("ia_principal")
        respuesta = ""
        
        if ia_seleccionada == "gemini" and GEMINI_ACTIVO:
            try:
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                res = model.generate_content(sys_prompt)
                respuesta = res.text
            except Exception as e:
                respuesta = "⚠️ Error Gemini, cambiando a respaldo..."
                ia_seleccionada = "openrouter"

        if ia_seleccionada == "openrouter":
            if self.router and hasattr(self.router, 'ready') and self.router.ready:
                try:
                    res_obj = self.router.send_message(sys_prompt)
                    respuesta = res_obj.text if hasattr(res_obj, 'text') else str(res_obj)
                except Exception as e:
                    respuesta = f"⚠️ Error OpenRouter: {str(e)[:100]}"
            else:
                respuesta = "⚠️ IA no disponible."

        response["texto"] = respuesta
        
        # Guardar en memoria
        if self.memory:
            try:
                self.memory.add("user", texto_usuario)
                self.memory.add("assistant", respuesta)
            except Exception as e:
                print(f"⚠️ Error guardando en memoria: {e}")
                
        return response

# =================================================================
# UI PRINCIPAL COMPLETA - OPTIMIZADA PARA FLET 0.24.1
# =================================================================
def main(page: ft.Page):
    page.title = "Archeon Mobile"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.bgcolor = C_BG
    page.window_width = 400
    page.window_height = 800
    page.window_min_width = 320
    page.window_min_height = 600
    ruta_imagen_pendiente = None
    modo_actual = "asistente"  # Variable para el modo actual
    
    # Configurar icono
    try:
        logo_path = os.path.join("assets", "logo_asistente.png")
        if os.path.exists(logo_path):
            page.window.icon = logo_path
    except:
        pass
    
    # Variables de estado
    current_width = page.width
    chat_lock = threading.Lock()
    
    def on_resize(e):
        nonlocal current_width
        current_width = page.width
        update_responsive_ui()
    
    page.on_resize = on_resize
    
    # Configuración
    config = ConfigManager()
    
    # Inicializar Nube
    print(">> [MÓVIL] Iniciando sistemas...")
    try:
        if CloudManager:
            cloud = CloudManager(supabase_config={
                "supabase_url": "https://rcgipowzivogyqbuwzlv.supabase.co",
                "supabase_key": "sb_publishable_V0kfZlDv6HKNudCl_vObeQ_pRbDU1RU"
            })
            print("✓ CloudManager inicializado")
        else:
            raise ImportError("CloudManager no disponible")
    except Exception as e:
        print(f"⚠️ CloudManager falló: {e}")
        class DummyCloud:
            def __init__(self): 
                self.cloud_ready = False
                self.usuario_actual = None
            
            def validar_login(self, u, p): 
                print(f"✓ Login simulado para {u}")
                return True
            
            def crear_usuario(self, email, username, password): 
                print(f"✓ Usuario simulado creado: {username}")
                return {"ok": True, "usuario": username}
            
            def actualizar_password(self, email, nueva_password):
                print(f"✓ Contraseña simulada actualizada para {email}")
                return True
            
            def guardar_comando(self, usuario, tipo, comando):
                print(f"✓ Comando simulado guardado: {comando}")
                return True
        
        cloud = DummyCloud()
    
    # Cerebro
    brain = MobileNeuro(cloud, config)
    
    # Componentes de audio
    audio_player = ft.Audio(
        src="https://luna-modelo-assets.s3.amazonaws.com/silence.mp3",
        autoplay=False,
        volume=config.get("volumen") / 100,
        on_state_changed=lambda e: None
    )
    page.overlay.append(audio_player)
    
    file_picker = ft.FilePicker(on_result=lambda e: procesar_imagen(e))
    page.overlay.append(file_picker)
    
    # File picker para archivos normales (para Archeon Cloud Drive)
    file_picker_drive = ft.FilePicker(on_result=lambda e: subir_archivo_nube(e))
    page.overlay.append(file_picker_drive)
    
    # --- NUGGET: Función para cancelar la imagen seleccionada ---
    def cancelar_imagen(e):
        nonlocal ruta_imagen_pendiente
        ruta_imagen_pendiente = None
        preview_container.visible = False
        page.update()

    # --- UI: Controles de previsualización de imagen ---
    img_preview_control = ft.Image(
        src="",
        width=80, height=80,
        fit=ft.ImageFit.COVER,
        border_radius=ft.border_radius.all(10)
    )
    
    btn_cerrar_preview = ft.IconButton(
        icon=ft.icons.CLOSE_ROUNDED,
        icon_color=C_TEXT_DIM,
        bgcolor=C_BG_CARD,
        width=30, height=30,
        on_click=cancelar_imagen
    )

    # Contenedor que agrupa la imagen y el botón de cerrar
    preview_stack = ft.Stack([
        img_preview_control,
        ft.Container(btn_cerrar_preview, right=-5, top=-5)
    ], width=90, height=90)

    # El contenedor principal que irá sobre la barra de texto (oculto por defecto)
    preview_container = ft.Container(
        content=ft.Row([preview_stack], scroll=ft.ScrollMode.AUTO),
        padding=ft.padding.only(left=20, right=20, top=10, bottom=5),
        bgcolor="transparent",
        visible=False,
        animate_opacity=300
    )
    
    # UI Components optimizados
    chat_list = ft.ListView(
        expand=True, 
        spacing=10, 
        padding=ft.padding.only(top=10, bottom=10),
        auto_scroll=True,
        controls=[]
    )
    
    # Lista para archivos del Cloud Drive (nuevo)
    archivos_list = ft.ListView(
        expand=True,
        spacing=10,
        padding=20,
        auto_scroll=True,
        controls=[]
    )
    
    txt_input = ft.TextField(
        hint_text="Escribe o di un comando...",
        bgcolor="#1a1a1a",
        border_color="transparent",
        focused_border_color=C_ACCENT,
        color="white",
        expand=True,
        border_radius=20,
        content_padding=15,
        on_submit=lambda e: enviar_mensaje(),
        text_size=14
    )
    
    btn_mic = ft.IconButton(
        icon=ft.icons.MIC_OFF,
        icon_color=C_DIM,
        tooltip="Activar voz",
        on_click=lambda e: toggle_voz_entrada()
    )
    
    btn_silencio = ft.IconButton(
        icon=ft.icons.VOLUME_UP if config.get("tts_activo") else ft.icons.VOLUME_OFF,
        icon_color=C_SUCCESS if config.get("tts_activo") else C_DIM,
        tooltip="Activar/desactivar voz del asistente",
        on_click=lambda e: toggle_voz_salida()
    )
    
    btn_music_control = ft.IconButton(
        icon=ft.icons.PLAY_ARROW,
        icon_color=C_DIM,
        tooltip="Control de música (detener/reanudar)",
        visible=False,
        on_click=lambda e: controlar_musica()
    )
    
    # =================================================================
    # FUNCIONES PARA ARCHEON CLOUD DRIVE
    # =================================================================
    
    def crear_item_archivo(id_file, nombre, tipo, tamano, url_path):
        """Crea un item visual optimizado para el explorador de Archeon"""
        # Icono según el tipo de archivo
        icon_map = {
            "pdf": ft.icons.PICTURE_AS_PDF,
            "png": ft.icons.IMAGE,
            "jpg": ft.icons.IMAGE,
            "jpeg": ft.icons.IMAGE,
            "gif": ft.icons.IMAGE,
            "mp3": ft.icons.AUDIO_FILE,
            "mp4": ft.icons.VIDEO_FILE,
            "zip": ft.icons.COMPRESS,
            "txt": ft.icons.DESCRIPTION,
            "py": ft.icons.CODE,
            "js": ft.icons.CODE,
        }
        
        # Aplicamos tus funciones responsive
        t_nombre = get_responsive_size(14)
        t_meta = get_responsive_size(11)

        return ft.Container(
            content=ft.Row([
                # Icono con tu color de acento
                ft.Icon(icon_map.get(tipo.lower(), ft.icons.INSERT_DRIVE_FILE), color=C_ACCENT),
                
                ft.Column([
                    # Nombre del archivo
                    ft.Text(nombre, color="white", weight="bold", size=t_nombre, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    # Tamaño convertido a MB para mejor lectura
                    ft.Text(f"{tipo.upper()} • {tamano / (1024*1024):.2f} MB", color=C_DIM, size=t_meta),
                ], expand=True, spacing=2),
                
                # Botones de acción
                ft.Row([
                    # Cambiamos 'nombre' por 'url_path' para que Supabase sepa qué descargar
                    ft.IconButton(ft.icons.DOWNLOAD_ROUNDED, icon_color=C_SUCCESS, on_click=lambda _: descargar_archivo(url_path)),
                    ft.IconButton(ft.icons.DELETE_OUTLINE_ROUNDED, icon_color=C_ERROR, on_click=lambda _: eliminar_archivo(id_file))
                ], spacing=0)
            ]),
            padding=get_responsive_size(15),
            bgcolor=C_PANEL,
            border_radius=12,
            border=ft.border.all(1, "#222")
        )
    
    def descargar_archivo(url_path):
        """Descarga real del archivo desde Supabase Storage"""
        # Obtenemos el nombre real del archivo desde la ruta de la nube
        nombre_archivo = os.path.basename(url_path)
        mostrar_notificacion(f"⏳ Descargando: {nombre_archivo}...", "info")
        
        def proceso_descarga():
            try:
                # 1. Definir y crear carpeta de descargas local
                descargas_dir = os.path.join(os.getcwd(), "assets", "descargas")
                os.makedirs(descargas_dir, exist_ok=True)
                local_path = os.path.join(descargas_dir, nombre_archivo)
                
                # 2. Bajar los bytes desde el bucket 'archeon-drive'
                # 'url_path' tiene el formato: {user_id}/{nombre_archivo}
                data_bytes = cloud.supabase.storage.from_('archeon-drive').download(url_path)
                
                # 3. Escribir el archivo en el almacenamiento del dispositivo
                with open(local_path, "wb") as f:
                    f.write(data_bytes)
                
                mostrar_notificacion(f"✅ Descargado en: assets/descargas/{nombre_archivo}", "success")
                
            except Exception as e:
                print(f"❌ Error en descarga: {e}")
                mostrar_notificacion("Error al obtener el archivo de la nube", "error")

        # Ejecutamos en un hilo separado para no bloquear la interfaz
        threading.Thread(target=proceso_descarga, daemon=True).start()
    
    def eliminar_archivo(id_file):
        """Eliminación permanente de Storage y Base de Datos SQL"""
        mostrar_notificacion("⚠️ Eliminando archivo de la nube...", "warning")
        
        def proceso_eliminacion():
            try:
                # 1. Obtener la ruta (url_path) antes de borrar el registro
                res = cloud.supabase.table('archivos').select("url_path").eq("id", id_file).execute()
                
                if not res.data:
                    mostrar_notificacion("No se encontró el archivo", "error")
                    return

                path_en_nube = res.data[0]['url_path']

                # 2. Borrar el archivo físico del Storage
                # Se envía como una lista aunque sea solo uno
                cloud.supabase.storage.from_('archeon-drive').remove([path_en_nube])

                # 3. Borrar el registro de la tabla SQL
                cloud.supabase.table('archivos').delete().eq("id", id_file).execute()

                # 4. Actualizar la interfaz
                actualizar_lista_archivos()
                mostrar_notificacion("Archivo eliminado exitosamente", "success")

            except Exception as e:
                print(f"❌ Error al eliminar: {e}")
                mostrar_notificacion("Error de conexión con la nube", "error")

        # Ejecutar en segundo plano para no congelar Archeon
        threading.Thread(target=proceso_eliminacion, daemon=True).start()
    
    def subir_archivo_nube(e: ft.FilePickerResultEvent):
        """Sube un archivo real a Supabase Storage y lo registra en la base de datos"""
        # 1. Verificación de seguridad: No permitir subidas a invitados
        if not e.files or cloud.usuario_actual == "guest":
            mostrar_notificacion("⚠️ Inicia sesión para subir archivos a la nube", "error")
            return
        
        archivo = e.files[0]
        user_id = cloud.usuario_actual #
        mostrar_notificacion(f"Subiendo {archivo.name}...", "info")
        
        def proceso_real_subida():
            try:
                # 2. Preparar metadatos para la base de datos
                nombre = archivo.name
                extension = nombre.split('.')[-1] if '.' in nombre else "unknown"
                # Ruta organizada por carpetas de usuario para privacidad
                path_destino = f"{user_id}/{nombre}"
                
                # 3. Subida física al Storage
                with open(archivo.path, "rb") as f:
                    # Usamos el bucket 'archeon-drive' definido en tus planes
                    cloud.supabase.storage.from_('archeon-drive').upload(
                        path=path_destino,
                        file=f,
                        file_options={"content-type": f"application/{extension}"}
                    )
                
                # 4. Registro en la tabla SQL 'archivos'
                datos_registro = {
                    "user_id": user_id,
                    "nombre_archivo": nombre,
                    "tipo_archivo": extension,
                    "tamano_bytes": archivo.size,
                    "url_path": path_destino
                }
                cloud.supabase.table('archivos').insert(datos_registro).execute()
                
                # 5. Actualización de la UI
                actualizar_lista_archivos()
                mostrar_notificacion(f"✅ {nombre} sincronizado correctamente", "success")
                
            except Exception as error:
                print(f"❌ Error en Archeon Cloud: {error}")
                mostrar_notificacion("Error al conectar con el servidor de archivos", "error")

        # Ejecución en segundo plano para mantener la fluidez de la app
        threading.Thread(target=proceso_real_subida, daemon=True).start()
    
    def actualizar_lista_archivos():
        """Consulta real a Supabase para obtener archivos del usuario"""
        # Obtenemos quién está usando la app
        user_id = cloud.usuario_actual
        archivos_list.controls.clear()

        # 1. BLOQUEO DE SEGURIDAD: Si es invitado, no mostramos nada
        if user_id == "guest" or not user_id:
            archivos_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.LOCK_PERSON_OUTLINED, size=50, color=C_DIM),
                        ft.Text("ACCESO RESTRINGIDO", weight="bold", color="white", size=16),
                        ft.Text("Inicia sesión para gestionar tus archivos en la nube", 
                                color=C_TEXT_DIM, text_align=ft.TextAlign.CENTER),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=50,
                    alignment=ft.alignment.center
                )
            )
            page.update()
            return

        # 2. CONSULTA A SUPABASE
        try:
            # Traemos los archivos que pertenecen a este user_id
            res = cloud.supabase.table('archivos').select("*").eq("user_id", user_id).execute()
            archivos_db = res.data if res.data else []
            
            # Calculamos estadísticas reales
            total_archivos = len(archivos_db)
            # Sumamos los bytes y convertimos a MB
            total_bytes = sum(f.get("tamano_bytes", 0) for f in archivos_db)
            total_mb = total_bytes / (1024 * 1024)
            
            # Encabezado visual
            archivos_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"{total_archivos} archivos en tu nube", color=C_TEXT_DIM, size=12),
                            ft.Text(f"{total_mb:.2f} MB utilizados", color=C_TEXT_DIM, size=12),
                        ], expand=True),
                        ft.ElevatedButton(
                            "Subir archivo",
                            icon=ft.icons.UPLOAD_FILE,
                            on_click=lambda _: file_picker_drive.pick_files(
                                allow_multiple=False,
                                allowed_extensions=["pdf", "jpg", "png", "txt", "zip", "mp3", "py", "js"]
                            ),
                            bgcolor=C_ACCENT,
                            color="black"
                        )
                    ]),
                    padding=ft.padding.only(bottom=20)
                )
            )

            # 3. LISTADO DE ARCHIVOS REALES
            if not archivos_db:
                archivos_list.controls.append(
                    ft.Container(
                        content=ft.Text("Tu Archeon Drive está vacío", color=C_DIM),
                        padding=20, alignment=ft.alignment.center
                    )
                )
            else:
                for f in archivos_db:
                    archivos_list.controls.append(
                        crear_item_archivo(
                            id_file=f["id"],           
                            nombre=f["nombre_archivo"], 
                            tipo=f["tipo_archivo"], 
                            tamano=f["tamano_bytes"],
                            url_path=f["url_path"]     # <-- IMPORTANTE: Pasa la ruta real
                        )
                    )
                    
        except Exception as e:
            print(f"❌ Error Cloud Drive: {e}")
            mostrar_notificacion("Error al conectar con la nube", "error")
        
        # Pie de página
        archivos_list.controls.append(
            ft.Container(
                content=ft.Text(
                    "🔒 Tus archivos están protegidos por cifrado Archeon",
                    color=C_TEXT_DIM, size=11, text_align=ft.TextAlign.CENTER
                ),
                padding=20
            )
        )
        page.update()
    
    def abrir_explorador_archivos():
        """Abre la pantalla del Cloud Drive"""
        # Primero actualizamos la lista de archivos
        actualizar_lista_archivos()
        
        # Cambiamos a la vista del Cloud Drive
        page.clean()
        
        # Header del Cloud Drive
        header_drive = ft.Container(
            padding=get_input_padding(),
            bgcolor="rgba(0,0,0,0.5)",
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#222")),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.IconButton(
                        ft.icons.ARROW_BACK,
                        icon_color="white",
                        tooltip="Volver al chat",
                        on_click=lambda e: ir_dashboard()
                    ),
                    ft.Column([
                        ft.Text("Cloud Drive", weight="bold", color="white", size=get_responsive_size(16)),
                        ft.Text("Almacenamiento seguro en la nube", color=C_TEXT_DIM, size=get_responsive_size(12))
                    ], spacing=0),
                    ft.IconButton(
                        ft.icons.REFRESH,
                        icon_color=C_ACCENT,
                        tooltip="Actualizar lista",
                        on_click=lambda e: actualizar_lista_archivos()
                    )
                ]
            )
        )
        
        page.add(
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    colors=["#121212", "#000000"],
                    begin=ft.alignment.top_center,
                    end=ft.alignment.bottom_center
                ),
                content=ft.Column(
                    expand=True,
                    controls=[
                        header_drive,
                        ft.Container(content=archivos_list, expand=True),
                    ]
                )
            )
        )
    
    # =================================================================
    # FUNCIONES RESPONSIVE OPTIMIZADAS
    # =================================================================
    def get_responsive_size(base_size):
        if current_width <= 0:
            return base_size
        
        device_type = ResponsiveHelper.get_device_type(current_width)
        
        if device_type == "mobile":
            return int(base_size * 0.85)
        elif device_type == "phablet":
            return base_size
        elif device_type == "tablet":
            return int(base_size * 1.15)
        else:
            return int(base_size * 1.3)
    
    def get_input_padding():
        if current_width <= 0:
            return 15
        
        return ResponsiveHelper.get_responsive_padding(current_width)
    
    def update_responsive_ui():
        try:
            page.update()
        except:
            pass
    
    # =================================================================
    # FUNCIONES DE AUTENTICACIÓN OPTIMIZADAS
    # =================================================================
    
    def crear_input(label, password=False, icon=None, value=""):
        responsive_width = get_responsive_size(280)
        return ft.TextField(
            label=label,
            password=password,
            can_reveal_password=password,
            color=C_TEXT,
            border_color="#333",
            focused_border_color=C_ACCENT,
            bgcolor="rgba(255,255,255,0.05)",
            border_radius=10,
            text_size=get_responsive_size(14),
            height=get_responsive_size(50),
            width=responsive_width,
            value=value,
            prefix_icon=icon,
            on_submit=lambda e: None
        )
    
    # Inputs
    inp_email = crear_input("Correo Electrónico", icon=ft.icons.EMAIL)
    inp_usuario = crear_input("Nombre de Usuario", icon=ft.icons.PERSON)
    inp_pass = crear_input("Contraseña", True, icon=ft.icons.LOCK)
    inp_pass_confirm = crear_input("Confirmar Contraseña", True, icon=ft.icons.LOCK)
    inp_pass_nueva = crear_input("Nueva Contraseña", True, icon=ft.icons.LOCK)
    
    # Visibilidad inicial
    inp_usuario.visible = False
    inp_pass_confirm.visible = False
    inp_pass_nueva.visible = False
    
    # Botón Principal responsivo
    btn_texto = ft.Text(
        "INICIAR SESIÓN", 
        weight=ft.FontWeight.BOLD, 
        color="black",
        size=get_responsive_size(14)
    )
    
    btn_accion_container = ft.Container(
        content=btn_texto,
        bgcolor=C_ACCENT,
        width=get_responsive_size(280),
        height=get_responsive_size(50),
        border_radius=12,
        alignment=ft.alignment.center,
        on_click=lambda e: accion_login(e)
    )
    
    def actualizar_form_auth(e):
        index = e.control.selected_index if hasattr(e.control, 'selected_index') else 0
        
        inp_usuario.visible = False
        inp_pass_confirm.visible = False
        inp_pass_nueva.visible = False
        inp_pass.visible = True
        inp_pass.label = "Contraseña"
        inp_pass_nueva.label = "Nueva Contraseña"
        
        if index == 0:  # Login
            btn_texto.value = "INICIAR SESIÓN"
            btn_accion_container.on_click = accion_login
            
        elif index == 1:  # Registro
            inp_usuario.visible = True
            inp_pass_confirm.visible = True
            btn_texto.value = "CREAR CUENTA"
            btn_accion_container.on_click = accion_registro
            
        elif index == 2:  # Recuperar
            inp_pass_nueva.visible = True
            inp_pass.label = "Contraseña Actual (si la recuerdas)"
            btn_texto.value = "ACTUALIZAR CLAVE"
            btn_accion_container.on_click = accion_recuperar
        
        try:
            page.update()
        except:
            pass
    
    def mostrar_notificacion(mensaje, tipo="info"):
        colores = {"info": C_ACCENT, "error": C_ERROR, "success": C_SUCCESS}
        
        icon_map = {
            "info": ft.icons.INFO,
            "error": ft.icons.ERROR,
            "success": ft.icons.CHECK_CIRCLE
        }
        
        snack = ft.SnackBar(
            content=ft.Row([
                ft.Icon(
                    icon_map.get(tipo, ft.icons.INFO),
                    color=colores.get(tipo, C_ACCENT)
                ),
                ft.Text(mensaje, color="white", size=get_responsive_size(14))
            ], spacing=10),
            bgcolor="#1a1a1a",
            duration=3000
        )
        
        page.snack_bar = snack
        snack.open = True
        try:
            page.update()
        except:
            pass
    
    def accion_login(e):
        if not inp_email.value or not inp_pass.value:
            mostrar_notificacion("Faltan datos", "error")
            return
        
        mostrar_notificacion("Verificando en la Nube...", "info")
        
        if cloud and hasattr(cloud, 'validar_login'):
            if cloud.validar_login(inp_email.value, inp_pass.value):
                cloud.usuario_actual = inp_email.value
                mostrar_notificacion(f"Bienvenido {inp_email.value}", "success")
                
                ir_dashboard(primer_inicio=True) 
            else:
                mostrar_notificacion("Credenciales incorrectas o usuario no existe", "error")
        else:
            mostrar_notificacion("Servicio no disponible", "error")
    
    def accion_registro(e):
        if not all([inp_email.value, inp_usuario.value, inp_pass.value, inp_pass_confirm.value]):
            mostrar_notificacion("Completa todos los campos", "error")
            return
        
        if inp_pass.value != inp_pass_confirm.value:
            mostrar_notificacion("Las contraseñas no coinciden", "error")
            return
        
        if len(inp_pass.value) < 6:
            mostrar_notificacion("La contraseña debe tener al menos 6 caracteres", "error")
            return
        
        mostrar_notificacion("Registrando usuario...", "info")
        
        if cloud and hasattr(cloud, 'crear_usuario'):
            resultado = cloud.crear_usuario(inp_email.value, inp_usuario.value, inp_pass.value)
            
            if isinstance(resultado, dict) and resultado.get("ok"):
                mostrar_notificacion("¡Cuenta creada! Iniciando...", "success")
                cloud.usuario_actual = inp_email.value
                
                # CORRECCIÓN: Pasamos primer_inicio=True para que Archeon se presente
                ir_dashboard(primer_inicio=True) 
            else:
                error_msg = resultado.get("error", "Error desconocido") if isinstance(resultado, dict) else "Error en el registro"
                mostrar_notificacion(f"Error: {error_msg}", "error")
        else:
            mostrar_notificacion("Servicio no disponible", "error")
    
    def accion_recuperar(e):
        if not inp_email.value or not inp_pass_nueva.value:
            mostrar_notificacion("Ingresa correo y nueva contraseña", "error")
            return
        
        if len(inp_pass_nueva.value) < 6:
            mostrar_notificacion("La nueva contraseña debe tener al menos 6 caracteres", "error")
            return
        
        if inp_pass.value and hasattr(cloud, 'validar_login'):
            if not cloud.validar_login(inp_email.value, inp_pass.value):
                mostrar_notificacion("Contraseña actual incorrecta", "error")
                return
        
        mostrar_notificacion("Actualizando base de datos...", "info")
        
        if cloud and hasattr(cloud, 'actualizar_password'):
            if cloud.actualizar_password(inp_email.value, inp_pass_nueva.value):
                mostrar_notificacion("Contraseña actualizada con éxito", "success")
                tabs_auth.selected_index = 0
                actualizar_form_auth(ft.ControlEvent(control=tabs_auth))
            else:
                mostrar_notificacion("No se pudo actualizar (¿Email correcto?)", "error")
        else:
            mostrar_notificacion("Servicio no disponible", "error")
    
    # Tabs de autenticación
    tabs_auth = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="INICIO DE SESION", icon=ft.icons.LOGIN),
            ft.Tab(text="REGISTRO", icon=ft.icons.PERSON_ADD),
            ft.Tab(text="RECUPERAR", icon=ft.icons.VPN_KEY),
        ],
        on_change=actualizar_form_auth
    )
    
    def cargar_logo():
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            full_path = os.path.join(script_dir, "assets", "logo_asitente.png")
            
            print(f"🔍 Buscando logo en: {full_path}")
            
            if os.path.exists(full_path):
                device_type = ResponsiveHelper.get_device_type(current_width)
                logo_size = get_responsive_size(100 if device_type == "tablet" else 80)
                
                return ft.Image(
                    src=full_path,
                    width=logo_size,
                    height=logo_size,
                    fit=ft.ImageFit.CONTAIN,
                    border_radius=10
                )
            else:
                print("⚠️ No se encontró el archivo de logo. Usando icono por defecto.")
                return ft.Icon(ft.icons.SMART_TOY, size=get_responsive_size(80), color=C_ACCENT)
                
        except Exception as e:
            print(f"❌ Error cargando logo: {e}")
            return ft.Icon(ft.icons.MEMORY, size=get_responsive_size(80), color=C_ACCENT)
    
    # =================================================================
    # FUNCIONES DEL DASHBOARD OPTIMIZADAS
    # =================================================================
    
    def agregar_mensaje(texto, es_usuario=False, es_imagen=False, es_sistema=False):
        with chat_lock:
            screen_width = current_width if current_width > 0 else 350
            
            if ResponsiveHelper.get_device_type(screen_width) == "tablet":
                max_width = screen_width * 0.65
            else:
                max_width = screen_width * 0.75
            
            align = ft.MainAxisAlignment.END if es_usuario else ft.MainAxisAlignment.START
            
            if es_sistema:
                bg = "#1a1a2e"
                border = ft.border.all(1, C_ACCENT)
            elif es_usuario:
                bg = ft.colors.with_opacity(0.2, C_ACCENT)
                border = ft.border.only(right=ft.border.BorderSide(3, C_ACCENT))
            else:
                bg = "#222222"
                border = ft.border.only(left=ft.border.BorderSide(3, C_SUCCESS))
            
            contenido = []
            texto_size = get_responsive_size(14)
            
            if es_imagen:
                img_width = min(300, screen_width * 0.6)
                contenido.append(
                    ft.Image(
                        src=texto, 
                        width=img_width, 
                        border_radius=10, 
                        fit=ft.ImageFit.CONTAIN
                    )
                )
            else:
                contenido.append(
                    ft.Markdown(
                        texto,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        code_theme="atom-one-dark",
                        code_style=ft.TextStyle(font_family="Roboto Mono", size=12),
                        on_tap_link=lambda e: page.launch_url(e.data),
                    )
                )
            
            mensaje_container = ft.Container(
                content=ft.Column(contenido, spacing=5),
                bgcolor=bg,
                padding=get_responsive_size(15),
                border_radius=12,
                border=border,
                margin=ft.margin.only(bottom=10),
                width=max_width if len(texto) > 30 or es_imagen else None
            )
            
            chat_list.controls.append(
                ft.Row([mensaje_container], alignment=align)
            )
        
        try:
            page.update()
        except:
            pass
    
    def toggle_voz_entrada():
        actual = config.get("activacion_voz")
        nuevo_valor = not actual
        config.set("activacion_voz", nuevo_valor)
        
        if nuevo_valor:
            btn_mic.icon = ft.icons.MIC
            btn_mic.icon_color = C_SUCCESS
            mostrar_notificacion(f"🎤 Voz activada - Di '{config.get('voz_comando')}'")
        else:
            btn_mic.icon = ft.icons.MIC_OFF
            btn_mic.icon_color = C_DIM
            mostrar_notificacion("🎤 Voz desactivada")
        
        try:
            page.update()
        except:
            pass
    
    def toggle_voz_salida():
        actual = config.get("tts_activo")
        nuevo_valor = not actual
        config.set("tts_activo", nuevo_valor)
        
        if nuevo_valor:
            btn_silencio.icon = ft.icons.VOLUME_UP
            btn_silencio.icon_color = C_SUCCESS
            mostrar_notificacion("🔊 Voz del asistente ACTIVADA")
        else:
            btn_silencio.icon = ft.icons.VOLUME_OFF
            btn_silencio.icon_color = C_DIM
            mostrar_notificacion("🔇 Voz del asistente DESACTIVADA")
            brain.limpiar_archivos_voz()
        
        try:
            page.update()
        except:
            pass
    
    def controlar_musica():
        if brain.music_playing:
            audio_player.pause()
            btn_music_control.icon = ft.icons.PLAY_ARROW
            btn_music_control.tooltip = "Reanudar música"
            brain.music_playing = False
            mostrar_notificacion("⏸️ Música pausada", "info")
        else:
            audio_player.resume()
            btn_music_control.icon = ft.icons.PAUSE
            btn_music_control.tooltip = "Pausar música"
            brain.music_playing = True
            mostrar_notificacion("▶️ Música reanudada", "info")
        
        try:
            page.update()
        except:
            pass
    
    def reproducir_voz(texto):
        if not config.get("tts_activo"):
            return False
        
        palabras_excluidas = ["error", "⚠️", "📡", "🎵", "❌", "http://", "https://"]
        if any(palabra in texto.lower() for palabra in palabras_excluidas):
            return False
        
        if len(texto) > 400:
            texto = texto[:397] + "..."
        
        try:
            archivo_voz = brain.generar_audio(
                texto, 
                idioma=config.get("idioma_voz", "es"),
                velocidad=config.get("voz_rapida", False)
            )
            
            if archivo_voz:
                voz_path = os.path.join("assets", "voces", archivo_voz)
                if os.path.exists(voz_path):
                    audio_player.src = voz_path
                else:
                    audio_player.src = f"/assets/voces/{archivo_voz}"
                
                audio_player.volume = config.get("volumen", 80) / 100
                audio_player.play()
                
                # Limpieza automática en hilo separado
                if config.get("limpiar_archivos", True):
                    def limpiar_async():
                        time.sleep(20)
                        try:
                            brain.limpiar_archivos_voz()
                        except:
                            pass
                    
                    threading.Thread(target=limpiar_async, daemon=True).start()
                
                return True
                
        except Exception as e:
            print(f"❌ Error reproduciendo voz: {e}")
        
        return False
    
    def procesar_imagen(e: ft.FilePickerResultEvent):
        nonlocal ruta_imagen_pendiente
        if not e.files:
            return
        
        path = e.files[0].path
        ruta_imagen_pendiente = path
        
        # --- ACTUALIZACIÓN VISUAL ---
        img_preview_control.src = path
        preview_container.opacity = 1
        preview_container.visible = True
        page.update()
    
    def enviar_mensaje():
        nonlocal ruta_imagen_pendiente
        texto = txt_input.value.strip()

        if not texto and not ruta_imagen_pendiente:
            return
        
        if ruta_imagen_pendiente:
            agregar_mensaje(ruta_imagen_pendiente, es_imagen=True, es_usuario=True)
            if texto:
                agregar_mensaje(texto, es_usuario=True)
            procesar_mixto(texto if texto else "Analiza esta imagen", ruta_imagen_pendiente)
            
            # --- LIMPIEZA VISUAL ---
            ruta_imagen_pendiente = None
            preview_container.visible = False
        
        else:
            agregar_mensaje(texto, es_usuario=True)
            procesar_mensaje(texto)
        
        txt_input.value = ""
        page.update()
        
    def procesar_mixto(texto, path):
        thinking = ft.Container(
            content=ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2, color=C_ACCENT),
                ft.Text("Analizando imagen y texto...", color=C_DIM, size=get_responsive_size(12))
            ], spacing=10),
            padding=10
        )
        
        with chat_lock:
            chat_list.controls.append(thinking)
        page.update()

        def hilo():
            resultado = brain.procesar(texto, path)
            
            with chat_lock:
                if thinking in chat_list.controls:
                    chat_list.controls.remove(thinking)
            
            if resultado["texto"]:
                agregar_mensaje(resultado["texto"], es_usuario=False)
                if resultado.get("necesita_voz", True):
                    reproducir_voz(resultado["texto"])
            page.update()

        threading.Thread(target=hilo, daemon=True).start()

    def procesar_mensaje(texto):
        thinking = ft.Container(
            content=ft.Row([
                ft.ProgressRing(width=20, height=20, stroke_width=2, color=C_ACCENT),
                ft.Text("Pensando...", color=C_DIM, size=get_responsive_size(12))
            ], spacing=10),
            padding=10
        )
        
        with chat_lock:
            chat_list.controls.append(thinking)
        
        try:
            page.update()
        except:
            pass
        
        def hilo_procesamiento():
            resultado = brain.procesar(texto)
            
            def remove_thinking():
                with chat_lock:
                    if thinking in chat_list.controls:
                        chat_list.controls.remove(thinking)
            
            remove_thinking()
            
            def process_result():
                if resultado["accion"] == "play_music":
                    if resultado.get("dato"):
                        if isinstance(resultado["dato"], dict):
                            url_cancion = resultado["dato"].get("url")
                            volumen = resultado["dato"].get("volume", 0.8)
                        else:
                            url_cancion = resultado["dato"]
                            volumen = config.get("volumen", 80) / 100
                        
                        if url_cancion:
                            audio_player.src = url_cancion
                            audio_player.autoplay = True
                            audio_player.volume = volumen
                            
                            btn_music_control.icon = ft.icons.PAUSE
                            btn_music_control.icon_color = C_SUCCESS
                            btn_music_control.tooltip = "Pausar música"
                            btn_music_control.visible = True
                            
                            mostrar_notificacion("🎵 Reproduciendo música", "success")
                
                elif resultado["accion"] == "stop_music":
                    audio_player.pause()
                    btn_music_control.icon = ft.icons.PLAY_ARROW
                    btn_music_control.icon_color = C_DIM
                    btn_music_control.tooltip = "Reanudar música"
                    brain.music_playing = False
                    
                elif resultado["accion"] == "resume_music":
                    if audio_player.src and audio_player.src != "https://luna-modelo-assets.s3.amazonaws.com/silence.mp3":
                        audio_player.resume()
                        btn_music_control.icon = ft.icons.PAUSE
                        btn_music_control.icon_color = C_SUCCESS
                        btn_music_control.tooltip = "Pausar música"
                        brain.music_playing = True
                
                elif resultado["accion"] == "remote_pc":
                    mostrar_notificacion("📡 Comando enviado a PC", "success")
                
                if resultado["texto"]:
                    agregar_mensaje(resultado["texto"], es_usuario=False)
                    
                    if resultado.get("necesita_voz", True):
                        reproducir_voz(resultado["texto"])
                
                try:
                    page.update()
                except:
                    pass
            
            process_result()
        
        threading.Thread(target=hilo_procesamiento, daemon=True).start()
    
    # =================================================================
    # PANTALLA DE CONFIGURACIÓN OPTIMIZADA
    # =================================================================
    def abrir_configuracion():
        config_dialog = None
        
        def guardar_config():
            nonlocal config_dialog
            if config_dialog:
                config_dialog.open = False
            
            mostrar_notificacion("✅ Configuración guardada", "success")
            
            btn_mic.icon = ft.icons.MIC if config.get("activacion_voz") else ft.icons.MIC_OFF
            btn_mic.icon_color = C_SUCCESS if config.get("activacion_voz") else C_DIM
            btn_silencio.icon = ft.icons.VOLUME_UP if config.get("tts_activo") else ft.icons.VOLUME_OFF
            btn_silencio.icon_color = C_SUCCESS if config.get("tts_activo") else C_DIM
            
            try:
                page.update()
            except:
                pass
        
        def cerrar_dialogo(e):
            nonlocal config_dialog
            if config_dialog:
                config_dialog.open = False
                try:
                    page.update()
                except:
                    pass

        # Tamaño responsivo
        dialog_width = min(400, current_width * 0.9)
        dialog_height = min(550, page.height * 0.8)
        
        # Contenido del diálogo
        contenido_dialogo = ft.Column(
            scroll="adaptive",
            spacing=get_responsive_size(12),
            tight=True,
            controls=[
                ft.Text("Nombre del Asistente", color="white", size=get_responsive_size(14)),
                ft.TextField(
                    value=config.get("asistente_nombre"),
                    on_change=lambda e: config.set("asistente_nombre", e.control.value),
                    border_color=C_ACCENT,
                    color="white",
                    hint_text="Ej: Archeon",
                    text_size=get_responsive_size(14)
                ),
                
                ft.Text("IA Principal", color="white", size=get_responsive_size(14)),
                ft.Dropdown(
                    value=config.get("ia_principal"),
                    options=[
                        ft.dropdown.Option("gemini", "Gemini (Google)"),
                        ft.dropdown.Option("openrouter", "OpenRouter")
                    ],
                    on_change=lambda e: config.set("ia_principal", e.control.value),
                    border_color=C_ACCENT,
                    color="white",
                    text_size=get_responsive_size(14)
                ),
                
                ft.Divider(height=10, color="#333"),
                
                ft.Text("🎤 VOZ DE ENTRADA", color=C_ACCENT, size=get_responsive_size(12)),
                ft.Row([
                    ft.Switch(
                        value=config.get("activacion_voz"),
                        active_color=C_ACCENT,
                        on_change=lambda e: config.set("activacion_voz", e.control.value)
                    ),
                    ft.Text("Reconocimiento de voz", color="white", expand=True),
                ]),
                
                ft.Text("Comando de activación", color="white", size=get_responsive_size(12)),
                ft.TextField(
                    value=config.get("voz_comando"),
                    on_change=lambda e: config.set("voz_comando", e.control.value),
                    border_color=C_ACCENT,
                    color="white",
                    hint_text="Ej: oye archeon",
                    text_size=get_responsive_size(14)
                ),
                
                ft.Divider(height=10, color="#333"),
                
                ft.Text("🔊 VOZ DEL ASISTENTE", color=C_ACCENT, size=get_responsive_size(12)),
                ft.Row([
                    ft.Switch(
                        value=config.get("tts_activo"),
                        active_color=C_ACCENT,
                        on_change=lambda e: config.set("tts_activo", e.control.value)
                    ),
                    ft.Text("Texto a voz (TTS)", color="white", expand=True),
                ]),
                
                ft.Row([
                    ft.Switch(
                        value=config.get("voz_rapida"),
                        active_color=C_ACCENT,
                        on_change=lambda e: config.set("voz_rapida", e.control.value)
                    ),
                    ft.Text("Voz rápida", color="white", expand=True),
                ]),
                
                ft.Text("Idioma de voz", color="white", size=get_responsive_size(12)),
                ft.Dropdown(
                    value=config.get("idioma_voz"),
                    options=[
                        ft.dropdown.Option("es", "Español"),
                        ft.dropdown.Option("en", "Inglés"),
                        ft.dropdown.Option("fr", "Francés")
                    ],
                    on_change=lambda e: config.set("idioma_voz", e.control.value),
                    border_color=C_ACCENT,
                    color="white",
                    width=get_responsive_size(150),
                    text_size=get_responsive_size(14)
                ),
                
                ft.Row([
                    ft.Switch(
                        value=config.get("limpiar_archivos"),
                        active_color=C_ACCENT,
                        on_change=lambda e: config.set("limpiar_archivos", e.control.value)
                    ),
                    ft.Text("Auto-limpiar archivos de voz", color="white", expand=True),
                ]),
                
                ft.Divider(height=10, color="#333"),
                
                ft.Text(f"Volumen: {config.get('volumen')}%", color="white"),
                ft.Slider(
                    min=0,
                    max=100,
                    divisions=10,
                    value=config.get("volumen"),
                    active_color=C_ACCENT,
                    on_change=lambda e: config.set("volumen", int(e.control.value)),
                    label="{value}%"
                ),
                
                ft.ElevatedButton(
                    "🧹 Limpiar archivos de voz",
                    on_click=lambda e: (
                        brain.limpiar_archivos_voz(),
                        mostrar_notificacion("Archivos de voz eliminados", "info")
                    ),
                    bgcolor="#333",
                    color="white",
                    width=get_responsive_size(200)
                )
            ]
        )

        config_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚙️ CONFIGURACIÓN", color=C_ACCENT, size=get_responsive_size(16)),
            content=ft.Container(
                width=dialog_width,
                height=dialog_height,
                content=contenido_dialogo
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=cerrar_dialogo),
                ft.TextButton("Guardar", on_click=lambda e: guardar_config()),
            ],
            actions_alignment=ft.MainAxisAlignment.END
        )
        
        page.dialog = config_dialog
        config_dialog.open = True
        try:
            page.update()
        except:
            pass
    
    # =================================================================
    # FUNCIÓN PARA MOSTRAR MENÚ DE MODOS (BOTTOM SHEET)
    # =================================================================
    def actualizar_icono_modo():
        """Actualiza el icono según el modo actual"""
        icon_map = {
            "asistente": ft.icons.SMART_TOY_OUTLINED,
            "programador": ft.icons.CODE,
            "traductor": ft.icons.TRANSLATE
        }
        return icon_map.get(modo_actual, ft.icons.SMART_TOY_OUTLINED)
    
    def mostrar_modos(e):
        # Función interna para cerrar el menú al elegir una opción
        def close_sheet(e):
            bottom_sheet.open = False
            page.update()

        # Función para cambiar modo y cerrar menú
        def cambiar_y_cerrar(nuevo_modo):
            nonlocal modo_actual
            modo_actual = nuevo_modo
            actualizar_icono_modo()
            close_sheet(None)
            mostrar_notificacion(f"Modo cambiado a: {nuevo_modo.capitalize()}", "success")

        # Creamos el contenido del menú
        modos_content = ft.Container(
            content=ft.Column([
                ft.Container(ft.Text("Selecciona un Modo", size=16, weight=ft.FontWeight.BOLD, color=C_TEXT), padding=10),
                ft.Divider(color=C_BORDER),
                # Creamos los ítems del menú usando ListTile para un look más nativo
                ft.ListTile(
                    leading=ft.Icon(ft.icons.SMART_TOY_OUTLINED, color=C_ACCENT),
                    title=ft.Text("Asistente (General)", color=C_TEXT),
                    on_click=lambda _: cambiar_y_cerrar("asistente")
                ),
                 ft.ListTile(
                    leading=ft.Icon(ft.icons.CODE, color=C_ACCENT),
                    title=ft.Text("Programador (Código)", color=C_TEXT),
                    on_click=lambda _: cambiar_y_cerrar("programador")
                ),
                 ft.ListTile(
                    leading=ft.Icon(ft.icons.TRANSLATE, color=C_ACCENT),
                    title=ft.Text("Traductor (Idiomas)", color=C_TEXT),
                    on_click=lambda _: cambiar_y_cerrar("traductor")
                ),
                ft.Container(height=10), # Espaciador inferior
                ft.ElevatedButton("Cancelar", on_click=close_sheet, bgcolor=C_BG_CARD, color=C_TEXT)
            ], tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            padding=20,
            bgcolor=C_BG_MAIN,
            border_radius=ft.border_radius.only(top_left=20, top_right=20)
        )

        # Configuramos y mostramos la hoja inferior
        bottom_sheet = ft.BottomSheet(
            modos_content,
            open=True,
            on_dismiss=lambda e: print("Menú cerrado"),
            bgcolor="transparent"
        )
        page.overlay.append(bottom_sheet)
        page.update()
    
    # =================================================================
    # VISTAS PRINCIPALES OPTIMIZADAS
    # =================================================================
    def vista_autenticacion():
        container_width = min(320, current_width * 0.9)
        
        return ft.Container(
            expand=True,
            alignment=ft.alignment.center,
            gradient=ft.RadialGradient(
                colors=["#1a1a2e", "#000000"],
                center=ft.alignment.center,
                radius=1.2
            ),
            content=ft.Container(
                width=container_width,
                padding=get_responsive_size(25),
                border_radius=20,
                border=ft.border.all(1, "rgba(255,255,255,0.1)"),
                bgcolor="rgba(20,20,25,0.95)",
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=get_responsive_size(20),
                    tight=True,
                    controls=[
                        cargar_logo(),
                        ft.Text("ARCHEON", 
                               size=get_responsive_size(30), 
                               weight=ft.FontWeight.W_200, 
                               color="white", 
                               style=ft.TextStyle(letter_spacing=5)),
                        ft.Text("MOBILE INTERFACE", 
                               size=get_responsive_size(10), 
                               color=C_ACCENT, 
                               style=ft.TextStyle(letter_spacing=2)),
                        tabs_auth,
                        ft.Divider(height=10, color="transparent"),
                        inp_email,
                        inp_usuario,
                        inp_pass,
                        inp_pass_confirm,
                        inp_pass_nueva,
                        ft.Divider(height=10, color="transparent"),
                        btn_accion_container,
                        ft.TextButton(
                            "MODO INVITADO", 
                            on_click=lambda _: (
                                setattr(cloud, 'usuario_actual', 'guest'),
                                ir_dashboard(primer_inicio=True)
                            )
                        ),
                        ft.Container(height=10),
                        ft.Row([
                            ft.Icon(
                                ft.icons.VOLUME_UP if config.get("tts_activo") else ft.icons.VOLUME_OFF,
                                color=C_SUCCESS if config.get("tts_activo") else C_DIM
                            ),
                            ft.Text(
                                "Voz: ON" if config.get("tts_activo") else "Voz: OFF",
                                color=C_DIM, 
                                size=get_responsive_size(10)
                            )
                        ], alignment=ft.MainAxisAlignment.CENTER)
                    ]
                )
            )
        )
    
    def ir_dashboard(primer_inicio=False):
        page.clean()
        
        # Creamos una columna para apilar la previsualización y la barra de entrada
        bottom_area_column = ft.Column(
            controls=[
                preview_container,
                ft.Container(
                    padding=get_input_padding(),
                    bgcolor="#111",
                    border_radius=ft.border_radius.only(top_left=20, top_right=20),
                    content=ft.Row([
                        ft.IconButton(
                            actualizar_icono_modo(),
                            icon_color=C_ACCENT,
                            tooltip="Cambiar modo",
                            on_click=mostrar_modos
                        ),
                        ft.IconButton(
                            ft.icons.CAMERA_ALT,
                            icon_color=C_ACCENT,
                            tooltip="Subir imagen",
                            on_click=lambda _: file_picker.pick_files(
                                allow_multiple=False,
                                allowed_extensions=["jpg", "jpeg", "png", "gif"]
                            )
                        ),
                        txt_input,
                        btn_mic,
                        ft.IconButton(
                            ft.icons.SEND,
                            icon_color=C_ACCENT,
                            tooltip="Enviar",
                            on_click=lambda _: enviar_mensaje()
                        )
                    ])
                )
            ],
            spacing=0,
            tight=True
        )
        
        header = ft.Container(
            padding=get_input_padding(),
            bgcolor="rgba(0,0,0,0.5)",
            border=ft.border.only(bottom=ft.border.BorderSide(1, "#222")),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.IconButton(
                        ft.icons.MENU,
                        icon_color="white",
                        tooltip="Menú",
                        on_click=lambda e: mostrar_menu()
                    ),
                    ft.Column([
                        ft.Text(
                            config.get("asistente_nombre"), 
                            weight="bold", 
                            color="white", 
                            size=get_responsive_size(16)
                        ),
                        ft.Row([
                            ft.Icon(
                                ft.icons.CIRCLE, 
                                color=C_SUCCESS if config.get("tts_activo") else C_DIM, 
                                size=get_responsive_size(8)
                            ),
                            ft.Text(
                                "VOZ ON" if config.get("tts_activo") else "VOZ OFF", 
                                color=C_SUCCESS if config.get("tts_activo") else C_DIM, 
                                size=get_responsive_size(10)
                            )
                        ], spacing=5)
                    ], spacing=0),
                    ft.Row([
                        btn_music_control,
                        btn_silencio,
                        ft.IconButton(
                            ft.icons.FOLDER_OPEN,
                            icon_color="white",
                            tooltip="Mis Archivos",
                            on_click=lambda e: abrir_explorador_archivos()
                        ),
                        ft.IconButton(
                            ft.icons.SETTINGS,
                            icon_color=C_ACCENT,
                            tooltip="Configuración",
                            on_click=lambda e: abrir_configuracion()
                        )
                    ], spacing=5)
                ]
            )
        )
        
        page.add(
            ft.Container(
                expand=True,
                gradient=ft.LinearGradient(
                    colors=["#121212", "#000000"],
                    begin=ft.alignment.top_center,
                    end=ft.alignment.bottom_center
                ),
                content=ft.Column(
                    expand=True,
                    controls=[
                        header,
                        ft.Container(content=chat_list, expand=True),
                        ft.Container(
                            content=bottom_area_column,
                            alignment=ft.alignment.bottom_center,
                            padding=ft.padding.only(bottom=10 if not page.web else 0),
                        )
                    ]
                )
            )
        )
        if primer_inicio:
            nombre = config.get("asistente_nombre")
            mensaje_bienvenida = (
                f"🤖 **{nombre.upper()} INICIADO**\n\n"
                f"• Usuario: {cloud.usuario_actual if cloud.usuario_actual else 'Invitado'}\n"
                f"• Voz Asistente: {'ACTIVADA 🔊' if config.get('tts_activo') else 'DESACTIVADA 🔇'}\n"
                f"• Voz Entrada: {'ACTIVADA 🎤' if config.get('activacion_voz') else 'DESACTIVADA'}\n"
                f"• Comando voz: '{config.get('voz_comando')}'\n"
                f"• Nube PC: {'Conectada ✅' if hasattr(cloud, 'cloud_ready') and cloud.cloud_ready else 'Desconectada ⚠️'}\n"
                f"• Modo actual: {modo_actual.capitalize()}\n"
                f"• Cloud Drive: {'Disponible 📁' if cloud.usuario_actual != 'guest' else 'Requiere cuenta'}\n\n"
                f"🎵 **CONTROLES DE MÚSICA:**\n"
                f"• 'Pon [canción]' - Reproduce una canción específica\n"
                f"• 'Pon música EN LA PC' - DJ automático en PC\n"
                f"• 'Detente' o 'Pausa' - Para la música\n"
                f"• 'Continúa' - Reanuda la música\n"
                f"• Botón ⏸️/▶️ arriba - Control manual\n\n"
                f"📱 **OTROS COMANDOS:**\n"
                f"• 'Sube una imagen' - Análisis con IA\n"
                f"• 'Configuración' - Ajustes de voz y más\n"
                f"• 'Ayuda' - Muestra todos los comandos\n"
                f"• Botón 🧠 - Cambiar modo (Asistente/Programador/Traductor)\n"
                f"• Botón 📁 - Acceder a Archeon Cloud Drive\n\n"
                f"💡 **TIP:** Di '{config.get('voz_comando')}' seguido de tu comando si activaste voz."
            )        
            agregar_mensaje(mensaje_bienvenida, es_sistema=True)
        
            if config.get("tts_activo") and cloud.usuario_actual and cloud.usuario_actual != "guest":
                reproducir_voz(f"Hola {cloud.usuario_actual}, soy {nombre}. Estoy en modo {modo_actual}. ¿En qué puedo ayudarte?")
    
    # =================================================================
    # FUNCIONES DEL MENÚ OPTIMIZADAS
    # =================================================================
    def detener_musica_desde_menu(e):
        if page.dialog and hasattr(page.dialog, 'open'):
            page.dialog.open = False
        
        audio_player.pause()
        brain.music_playing = False
        btn_music_control.icon = ft.icons.PLAY_ARROW
        btn_music_control.icon_color = C_DIM
        mostrar_notificacion("Música detenida", "info")
        
        try:
            page.update()
        except:
            pass
    
    def mostrar_menu():
        def accion_ayuda(e):
            if menu_dialog:
                menu_dialog.open = False
            
            agregar_mensaje(
                "📋 **COMANDOS DISPONIBLES:**\n\n"
                "🎵 **MÚSICA:**\n"
                "• pon [canción] - Reproduce una canción\n"
                "• detente / pausa - Para la música\n"
                "• continua / reanuda - Sigue reproduciendo\n"
                "• botón ⏸️/▶️ - Control manual\n\n"
                "📁 **CLOUD DRIVE:**\n"
                "• Botón 📁 - Accede a tus archivos en la nube\n"
                "• Subir archivo - Guarda documentos en la nube\n"
                "• Descargar - Obtén copias locales\n\n"
                "🤖 **GENERAL:**\n"
                "• ayuda - Muestra esta lista\n"
                "• configuración - Ajustes de voz y más\n"
                "• silenciar - Desactiva mi voz\n"
                "• sube una imagen - Analiza con IA\n"
                "• 🧠 - Cambiar modo (Asistente/Programador/Traductor)\n",
                es_sistema=True
            )

        def accion_prueba_voz(e):
            if menu_dialog:
                menu_dialog.open = False
            reproducir_voz("Hola, esta es una prueba de la voz del asistente móvil.")

        def accion_cloud_drive(e):
            if menu_dialog:
                menu_dialog.open = False
            abrir_explorador_archivos()

        def accion_logout(e):
            if menu_dialog:
                menu_dialog.open = False
            ir_login()

        menu_dialog = ft.AlertDialog(
            title=ft.Text("MENÚ", color=C_ACCENT, size=get_responsive_size(16)),
            content=ft.Column([
                ft.ListTile(
                    leading=ft.Icon(ft.icons.HELP, color=C_ACCENT),
                    title=ft.Text("Ayuda y comandos"),
                    on_click=accion_ayuda
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.VOLUME_UP, color=C_ACCENT),
                    title=ft.Text("Probar voz del asistente"),
                    on_click=accion_prueba_voz
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.CLOUD_UPLOAD, color=C_ACCENT),
                    title=ft.Text("Ir al Cloud Drive"),
                    on_click=accion_cloud_drive
                ),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.STOP, color=C_WARNING),
                    title=ft.Text("Detener música actual"),
                    on_click=detener_musica_desde_menu
                ),
                ft.Divider(),
                ft.ListTile(
                    leading=ft.Icon(ft.icons.LOGOUT, color=C_ERROR),
                    title=ft.Text("Cerrar sesión", color=C_ERROR),
                    on_click=accion_logout
                ),
            ], height=min(300, page.height * 0.6), tight=True),
            actions=[ft.TextButton("Cerrar", on_click=lambda e: setattr(menu_dialog, 'open', False))]
        )
        
        page.dialog = menu_dialog
        menu_dialog.open = True
        try:
            page.update()
        except:
            pass
    
    def ir_login():
        page.clean()
        audio_player.pause()
        brain.music_playing = False
        if cloud:
            cloud.usuario_actual = None
        page.add(vista_autenticacion())

    
    # Iniciar con autenticación
    current_width = page.width
    page.add(vista_autenticacion())

if __name__ == "__main__":
    # Crear carpetas necesarias
    os.makedirs("assets", exist_ok=True)
    os.makedirs(os.path.join("assets", "voces"), exist_ok=True)
    
    # Ejecutar como APP NATIVA optimizada para Flet 0.24.1
    ft.app(
        target=main,
        assets_dir="assets",
        view=ft.AppView.FLET_APP
    )