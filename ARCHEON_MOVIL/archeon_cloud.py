# archeon_cloud.py (VERSIÓN SUPABASE DEFINITIVA) - OPTIMIZADA v10.0
import uuid
import hashlib
import os
import hmac
import base64
import time
import threading
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Union

# Importamos Supabase de forma segura
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("!! [CLOUD] Librería supabase no instalada. Ejecutando en MODO OFFLINE.")

class CloudManager:
    """
    Gestor de la nube (Supabase + Postgres) BLINDADO Y AUTOMATIZADO.
    Versión optimizada v10.0 con Caché + Async + Conexión Supabase
    """
    
    # ==========================================================
    # 🔧 INICIALIZACIÓN Y CONFIGURACIÓN (OPTIMIZADO v10.0)
    # ==========================================================
    def __init__(self, supabase_config: Dict[str, str] = None, secret_key: str = None):
        """Inicializa Supabase con múltiples métodos de autenticación"""
        self.cloud_ready = False 
        self.supabase = None
        self.client = None
        
        # ✅ MEJORA v10.0: SISTEMA DE CACHÉ INTELIGENTE (RAM)
        self._config_cache = {}  # {'email': {'data': {...}, 'timestamp': 12345678}}
        self._gustos_cache = {}
        self._comandos_cache = {}
        self.CACHE_TTL = 300  # 5 minutos de vida para la caché

        if SUPABASE_AVAILABLE:
            self._initialize_supabase(supabase_config)

        key_source = secret_key or os.getenv("AR_SECRET_KEY", "AR_Default_Development_Key_2025")
        self.secret_key = key_source.encode()
        
    def _initialize_supabase(self, supabase_config: Union[Dict, str, None]):
        """✅ MEJORA v10.0: Inicialización Supabase en memoria"""
        try:
            config = None
            
            # Método 1: Diccionario de credenciales
            if isinstance(supabase_config, dict):
                print(">> [CLOUD] Configurando Supabase con diccionario...")
                url = supabase_config.get("supabase_url")
                key = supabase_config.get("supabase_key")
                if url and key:
                    config = {"url": url, "key": key}
                    
            # Método 2: Variables de entorno
            elif supabase_config is None:
                print(">> [CLOUD] Intentando inicializar desde variables de entorno...")
                url = os.getenv("SUPABASE_URL")
                key = os.getenv("SUPABASE_KEY")
                if url and key:
                    config = {"url": url, "key": key}
                    print("🔥 [CLOUD] Supabase configurado desde ENV")
                    
            # Método 3: String JSON
            elif isinstance(supabase_config, str):
                try:
                    config = json.loads(supabase_config)
                    print(">> [CLOUD] Configurando Supabase desde JSON string...")
                except:
                    # Intentar como archivo
                    if os.path.exists(supabase_config):
                        with open(supabase_config, 'r') as f:
                            config = json.load(f)
                        print(f">> [CLOUD] Configurando Supabase desde archivo: {supabase_config}")
            
            if config and config.get("url") and config.get("key"):
                self.supabase = create_client(config["url"], config["key"])
                self.cloud_ready = True
                print("🔥 [CLOUD] Supabase CONECTADO correctamente (Async Ready)")
                self._iniciar_mantenimiento()
            else:
                print("❌ [CLOUD] No se pudo inicializar Supabase: configuración incompleta")
                self.cloud_ready = False
                
        except Exception as e:
            print(f"❌ [CLOUD] Error inicializando Supabase: {e}")
            self.cloud_ready = False
    
    def _run_async(self, target_func, *args):
        """✅ MEJORA v10.0: Ejecuta una función en segundo plano para no bloquear"""
        if not self.cloud_ready: 
            return
        t = threading.Thread(target=target_func, args=args, daemon=True)
        t.start()
            
    def _get_user_doc_id(self, email: str) -> str:
        """ID único e irreversible por usuario."""
        return hashlib.sha256(email.encode()).hexdigest()

    # ==========================================================
    # 🧹 MANTENIMIENTO AUTOMÁTICO (LIMPIEZA DE SESSIONES)
    # ==========================================================
    def _iniciar_mantenimiento(self):
        """Lanza un hilo que limpia la base de datos cada 12 horas."""
        def tarea_limpieza():
            while True:
                time.sleep(60)  # Espera inicial
                try:
                    if self.cloud_ready:
                        self.limpiar_sesiones_expiradas()
                except Exception as e:
                    print(f"!! Error en tarea de limpieza: {e}")
                time.sleep(43200)  # Esperar 12 horas (12 * 60 * 60)

        t = threading.Thread(target=tarea_limpieza, daemon=True)
        t.start()

    def limpiar_sesiones_expiradas(self):
        """Borra de la base de datos los tokens que ya no sirven."""
        if not self.cloud_ready: 
            return
            
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            
            # Consultar sesiones expiradas
            response = self.supabase.table("sessions") \
                .select("*") \
                .lt("expira", now_iso) \
                .execute()
            
            expired_sessions = response.data
            
            if expired_sessions:
                # Eliminar en lotes de 100
                batch_size = 100
                for i in range(0, len(expired_sessions), batch_size):
                    batch = expired_sessions[i:i + batch_size]
                    token_ids = [session["token"] for session in batch]
                    
                    self.supabase.table("sessions") \
                        .delete() \
                        .in_("token", token_ids) \
                        .execute()
                
                print(f"🧹 [MANTENIMIENTO] Se eliminaron {len(expired_sessions)} sesiones expiradas.")
                
        except Exception as e:
            print(f"!! Error en limpieza: {e}")

    # ==========================================================
    # 🔐 HASH DE PASSWORD
    # ==========================================================
    def hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple:
        """Genera hash seguro de contraseña usando PBKDF2-HMAC-SHA256."""
        if not salt: 
            salt = os.urandom(16)
        else:
            try: 
                salt = bytes.fromhex(salt)
            except: 
                salt = os.urandom(16)
                
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300000)
        return hashed.hex(), salt.hex()

    # ==========================================================
    # 🔐 GESTIÓN DE USUARIOS
    # ==========================================================
    def crear_usuario(self, email: str, username: str, password: str) -> Dict[str, Any]:
        """Crea un nuevo usuario en Supabase."""
        if not self.cloud_ready: 
            return {"ok": False, "error": "Modo offline. No se puede crear usuario."}
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            # Verificar si el usuario ya existe
            response = self.supabase.table("users") \
                .select("*") \
                .eq("id", doc_id) \
                .execute()
            
            if response.data:
                return {"ok": False, "error": "El usuario ya existe."}

            hashed, salt = self.hash_password(password)
            now_iso = datetime.now(timezone.utc).isoformat()

            # Insertar nuevo usuario
            user_data = {
                "id": doc_id,
                "email": email,
                "username": username,
                "password_hash": hashed,
                "salt": salt,
                "creado": now_iso,
                "ultimo_login": now_iso,
                "config": json.dumps({
                    "nombre": "Archeon", 
                    "tema": "dark",
                    "voz_id": "",
                    "user_name": username
                })
            }
            
            self.supabase.table("users").insert(user_data).execute()
            
            print(f">> [CLOUD] Usuario creado: {email} | Nombre: {username}")
            return {"ok": True, "msg": "Usuario creado exitosamente."}
            
        except Exception as e:
            print(f"!! [CLOUD] Error creando usuario: {e}")
            return {"ok": False, "error": str(e)}
        
    def validar_login(self, email: str, password: str) -> bool:
        """Valida credenciales de usuario."""
        if not self.cloud_ready: 
            return False
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            # Obtener usuario
            response = self.supabase.table("users") \
                .select("*") \
                .eq("id", doc_id) \
                .execute()
            
            if not response.data:
                return False
                
            user_data = response.data[0]
            
            # Verificar que tenemos los datos necesarios
            if not user_data or "salt" not in user_data or "password_hash" not in user_data: 
                return False 
                
            # Calcular hash con la sal almacenada
            hashed_calculado, _ = self.hash_password(password, user_data["salt"])
            
            # Comparar de forma segura
            if hmac.compare_digest(hashed_calculado, user_data["password_hash"]):
                # ✅ MEJORA v10.0: Actualizar último login en segundo plano
                self._run_async(self._update_login_time, doc_id)
                return True
                
            return False
            
        except Exception as e:
            print(f"!! [CLOUD] Error validando login: {e}")
            return False
    
    def _update_login_time(self, doc_id: str):
        """✅ MEJORA v10.0: Actualiza el login en segundo plano."""
        try:
            self.supabase.table("users") \
                .update({"ultimo_login": datetime.now(timezone.utc).isoformat()}) \
                .eq("id", doc_id) \
                .execute()
        except Exception as e:
            print(f"!! Error actualizando login time: {e}")

    def actualizar_password(self, email: str, nueva_password: str) -> bool:
        """Actualiza la contraseña del usuario."""
        if not self.cloud_ready: 
            return False
            
        try:
            doc_id = self._get_user_doc_id(email)
            hashed, salt = self.hash_password(nueva_password)
            
            self.supabase.table("users") \
                .update({
                    "password_hash": hashed, 
                    "salt": salt,
                    "actualizado": datetime.now(timezone.utc).isoformat()
                }) \
                .eq("id", doc_id) \
                .execute()
            
            print(f">> [CLOUD] Contraseña actualizada para: {email}")
            return True
            
        except Exception as e:
            print(f"!! [CLOUD] Error actualizando contraseña: {e}")
            return False

    # ==========================================================
    # 🔐 SESIONES
    # ==========================================================
    def firmar_token(self, token: str) -> str:
        """Firma un token con HMAC-SHA256."""
        firma = hmac.new(self.secret_key, token.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(firma).decode().rstrip("=")

    def crear_sesion(self, email: str) -> str:
        """Crea una sesión/token para el usuario."""
        if email == "guest":
            # 🟢 FIX: Genera un ID de sesión único y temporal para el modo invitado.
            return f"guest_{uuid.uuid4().hex}"
            
        if not self.cloud_ready:
            # Modo offline - token temporal
            return f"offline_{uuid.uuid4().hex}"
            
        try:
            token = uuid.uuid4().hex
            firma = self.firmar_token(token)
            exp = datetime.now(timezone.utc) + timedelta(hours=24)

            # Guardar sesión en Supabase
            session_data = {
                "token": token,
                "email": email,
                "firma_almacenada": firma,
                "creado": datetime.now(timezone.utc).isoformat(),
                "expira": exp.isoformat()
            }
            
            self.supabase.table("sessions").insert(session_data).execute()
            
            print(f">> [CLOUD] Sesión creada para: {email}")
            return f"{token}:{firma}"
            
        except Exception as e:
            print(f"!! [CLOUD] Error creando sesión: {e}")
            # Fallback a token offline
            return f"fallback_{uuid.uuid4().hex}"

    def obtener_usuario_por_token(self, full_token: str) -> Optional[str]:
        """Obtiene el email del usuario a partir del token."""
        if not full_token: 
            return None
            
        # 🟢 FIX CRÍTICO: Devolver el ID ÚNICO completo para que el sistema
        # pueda usarlo para cargar/guardar la configuración local temporal.
        if full_token.startswith("guest_"):
            return full_token 
            
        # Token offline/fallback
        if full_token.startswith("offline_") or full_token.startswith("fallback_"):
            return "offline_user"
            
        # Token de Supabase
        if ":" not in full_token: 
            return None

        try:
            token, firma_cliente = full_token.split(":", 1)
            
            # Validación criptográfica local (RÁPIDA) antes de ir a la nube
            firma_real = hmac.new(self.secret_key, token.encode(), hashlib.sha256).digest()
            firma_real_b64 = base64.urlsafe_b64encode(firma_real).decode().rstrip("=")
            
            if not hmac.compare_digest(firma_real_b64, firma_cliente):
                return None
            
            # Obtener sesión de Supabase
            response = self.supabase.table("sessions") \
                .select("*") \
                .eq("token", token) \
                .execute()
            
            if not response.data:
                return None
                
            session_data = response.data[0]
            
            # Verificar expiración
            exp = datetime.fromisoformat(session_data["expira"].replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                # Token expirado - eliminar en segundo plano
                self._run_async(lambda: self.supabase.table("sessions").delete().eq("token", token).execute())
                return None

            return session_data["email"]
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo usuario por token: {e}")
            return None

    # ==========================================================
    # 🗑️ ELIMINACIÓN DE DATOS (GDPR / DERECHO AL OLVIDO)
    # ==========================================================
    def eliminar_usuario_total(self, email: str) -> bool:
        """Borra ABSOLUTAMENTE TODO de un usuario. Irreversible."""
        if not self.cloud_ready: 
            return False
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            # 1. Borrar subcolecciones
            tables_to_clean = [
                "memoria", "gustos", "comandos", "chats_mensajes"
            ]
            
            for table in tables_to_clean:
                try:
                    self.supabase.table(table).delete().eq("user_id", doc_id).execute()
                except Exception as e:
                    print(f"!! Error eliminando {table}: {e}")
            
            # 2. Borrar configuraciones
            try:
                self.supabase.table("configuraciones").delete().eq("user_id", doc_id).execute()
            except:
                pass
            
            # 3. Borrar sesiones activas
            try:
                self.supabase.table("sessions").delete().eq("email", email).execute()
            except:
                pass
            
            # 4. Borrar códigos de verificación
            try:
                self.supabase.table("verification_codes").delete().eq("email", email).execute()
            except:
                pass
            
            # 5. Borrar usuario principal
            self.supabase.table("users").delete().eq("id", doc_id).execute()
            
            print(f"☠️ [CLOUD] Usuario {email} eliminado permanentemente.")
            return True
            
        except Exception as e:
            print(f"!! [CLOUD] Error eliminando usuario: {e}")
            return False

    # ==========================================================
    # ⚡ MEMORIA Y CONFIGURACIÓN OPTIMIZADA (CACHE + ASYNC)
    # ==========================================================
    def obtener_config(self, email: str) -> Dict[str, Any]:
        """✅ MEJORA v10.0: Obtiene configuración usando Caché para velocidad extrema."""
        if not self.cloud_ready: 
            return self._default_config(email)

        # 1. Revisar Caché RAM
        cached = self._config_cache.get(email)
        if cached:
            age = time.time() - cached['timestamp']
            if age < self.CACHE_TTL:  # Si tiene menos de 5 minutos
                return cached['data']

        # 2. Si no hay caché o expiró, buscar en Nube
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("users") \
                .select("config") \
                .eq("id", doc_id) \
                .execute()
            
            if response.data:
                config_str = response.data[0].get("config", "{}")
                config = json.loads(config_str) if config_str else {}
                # Asegurar que tenemos valores por defecto
                full_config = {**self._default_config(email), **config}
                
                # ✅ MEJORA: Actualizar Caché
                self._config_cache[email] = {
                    'data': full_config,
                    'timestamp': time.time()
                }
                return full_config
            return self._default_config(email)
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo config: {e}")
            return self._default_config(email)
    
    def _default_config(self, email: str) -> Dict[str, Any]:
        """Configuración por defecto."""
        name = email.split('@')[0] if '@' in email else "Usuario"
        return {
            "nombre": "Archeon",
            "tema": "dark",
            "voz_id": "",
            "user_name": name
        }

    def guardar_config(self, email: str, config: Dict[str, Any]):
        """✅ MEJORA v10.0: Guarda y actualiza la caché inmediatamente."""
        if not self.cloud_ready: 
            return
            
        # 1. Actualizar caché local (para que la UI se sienta instantánea)
        if email in self._config_cache:
            current = self._config_cache[email]['data']
            self._config_cache[email]['data'] = {**current, **config}
            self._config_cache[email]['timestamp'] = time.time()  # Refrescar TTL
        else:
            # Si no hay caché, crear una nueva
            self._config_cache[email] = {
                'data': {**self._default_config(email), **config},
                'timestamp': time.time()
            }

        # ✅ MEJORA v10.0: Guardar en Nube en Segundo Plano (Fire & Forget)
        self._run_async(self._guardar_config_cloud, email, config)
    
    def _guardar_config_cloud(self, email: str, config: Dict[str, Any]):
        """✅ MEJORA v10.0: Guarda la configuración en la nube en segundo plano."""
        try:
            doc_id = self._get_user_doc_id(email)
            
            # Obtener configuración actual
            response = self.supabase.table("users") \
                .select("config") \
                .eq("id", doc_id) \
                .execute()
            
            if response.data:
                current_config_str = response.data[0].get("config", "{}")
                current_config = json.loads(current_config_str) if current_config_str else {}
                
                # Fusionar configuraciones
                merged_config = {**current_config, **config}
                
                # Guardar actualizado
                self.supabase.table("users") \
                    .update({
                        "config": json.dumps(merged_config),
                        "actualizado": datetime.now(timezone.utc).isoformat()
                    }) \
                    .eq("id", doc_id) \
                    .execute()
            else:
                # Crear nuevo usuario con configuración
                user_data = {
                    "id": doc_id,
                    "email": email,
                    "config": json.dumps(config),
                    "creado": datetime.now(timezone.utc).isoformat()
                }
                self.supabase.table("users").insert(user_data).execute()
                
            print(f">> [CLOUD] Configuración sincronizada: {email}")
            
        except Exception as e:
            print(f"!! [CLOUD] Error guardando config async: {e}")

    def guardar_recuerdo(self, email: str, categoria: str, contenido: str, importancia: int = 1):
        """✅ MEJORA v10.0: Fire & Forget - No espera a que termine."""
        self._run_async(self._guardar_recuerdo_cloud, email, categoria, contenido, importancia)
    
    def _guardar_recuerdo_cloud(self, email: str, categoria: str, contenido: str, importancia: int):
        """✅ MEJORA v10.0: Guarda recuerdos en la nube en segundo plano."""
        if not self.cloud_ready: 
            return
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            recuerdo_data = {
                "user_id": doc_id,
                "categoria": categoria,
                "contenido": contenido,
                "importancia": importancia,
                "fecha": datetime.now(timezone.utc).isoformat()
            }
            
            self.supabase.table("memoria").insert(recuerdo_data).execute()
            
        except Exception as e:
            print(f"!! [CLOUD] Error guardando recuerdo async: {e}")

    def obtener_recuerdos(self, email: str, min_importancia: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """Obtiene recuerdos del usuario."""
        if not self.cloud_ready: 
            return []
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("memoria") \
                .select("*") \
                .eq("user_id", doc_id) \
                .gte("importancia", min_importancia) \
                .order("fecha", desc=True) \
                .limit(limit) \
                .execute()
                
            return response.data
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo recuerdos: {e}")
            return []

    # ==========================================================
    # ❤️ GUSTOS Y COMANDOS CON CACHÉ
    # ==========================================================
    def guardar_gusto(self, email: str, gusto: str, valor: bool = True):
        """✅ MEJORA v10.0: Actualiza caché y guarda en segundo plano."""
        if not self.cloud_ready: 
            return
            
        # Update Cache
        if email not in self._gustos_cache:
            self._gustos_cache[email] = {}
        self._gustos_cache[email][gusto] = valor
        
        # ✅ MEJORA: Async Cloud
        self._run_async(self._guardar_gusto_cloud, email, gusto, valor)
    
    def _guardar_gusto_cloud(self, email: str, gusto: str, valor: bool):
        """✅ MEJORA v10.0: Guarda gustos en la nube en segundo plano."""
        try:
            doc_id = self._get_user_doc_id(email)
            
            gusto_data = {
                "user_id": doc_id,
                "gusto": gusto,
                "activo": valor,
                "fecha": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert (insert or update)
            self.supabase.table("gustos").upsert(gusto_data).execute()
            
        except Exception as e:
            print(f"!! [CLOUD] Error guardando gusto async: {e}")

    def obtener_gustos(self, email: str) -> Dict[str, bool]:
        """✅ MEJORA v10.0: Obtiene gustos usando caché."""
        # Check Cache
        if email in self._gustos_cache:
            return self._gustos_cache[email]
        
        if not self.cloud_ready: 
            return {}
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("gustos") \
                .select("*") \
                .eq("user_id", doc_id) \
                .execute()
            
            gustos = {item["gusto"]: item["activo"] for item in response.data}
            
            # ✅ MEJORA: Fill Cache
            self._gustos_cache[email] = gustos
            return gustos
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo gustos: {e}")
            return {}

    def guardar_comando(self, email: str, comando: str, accion: str):
        """✅ MEJORA v10.0: Guarda comandos en segundo plano."""
        if not self.cloud_ready: 
            return
            
        # Update Cache
        if email not in self._comandos_cache:
            self._comandos_cache[email] = {}
        self._comandos_cache[email][comando] = accion
        
        # ✅ MEJORA: Ejecutar en segundo plano
        self._run_async(self._guardar_comando_cloud, email, comando, accion)
    
    def _guardar_comando_cloud(self, email: str, comando: str, accion: str):
        """✅ MEJORA v10.0: Guarda comando en la nube en segundo plano."""
        try:
            doc_id = self._get_user_doc_id(email)
            
            comando_data = {
                "user_id": doc_id,
                "comando": comando,
                "accion": accion,
                "fecha": datetime.now(timezone.utc).isoformat(),
                "usos": 1
            }
            
            # Incrementar usos si existe
            response = self.supabase.table("comandos") \
                .select("usos") \
                .eq("user_id", doc_id) \
                .eq("comando", comando) \
                .execute()
            
            if response.data:
                current_uses = response.data[0].get("usos", 0)
                comando_data["usos"] = current_uses + 1
            
            self.supabase.table("comandos").upsert(comando_data).execute()
            
        except Exception as e:
            print(f"!! [CLOUD] Error guardando comando async: {e}")

    def obtener_comandos(self, email: str) -> Dict[str, str]:
        """Obtiene comandos personalizados del usuario."""
        if not self.cloud_ready: 
            return {}
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("comandos") \
                .select("*") \
                .eq("user_id", doc_id) \
                .execute()
            
            comandos = {item["comando"]: item["accion"] for item in response.data}
            return comandos
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo comandos: {e}")
            return {}

    # ==========================================================
    # 💬 CHAT (ASÍNCRONO)
    # ==========================================================
    def guardar_mensaje_chat(self, email: str, contacto: str, texto: str, autor: str, leido: bool = False):
        """✅ MEJORA v10.0: Guarda mensajes en segundo plano."""
        if not self.cloud_ready: 
            return
            
        # ✅ MEJORA: Ejecutar en segundo plano
        self._run_async(self._guardar_mensaje_chat_cloud, email, contacto, texto, autor, leido)
    
    def _guardar_mensaje_chat_cloud(self, email: str, contacto: str, texto: str, autor: str, leido: bool):
        """✅ MEJORA v10.0: Guarda mensaje en la nube en segundo plano."""
        try:
            doc_id = self._get_user_doc_id(email)
            
            mensaje_data = {
                "user_id": doc_id,
                "contacto": contacto,
                "texto": texto,
                "autor": autor,
                "leido": leido,
                "fecha": datetime.now(timezone.utc).isoformat()
            }
            
            self.supabase.table("chats_mensajes").insert(mensaje_data).execute()
            
        except Exception as e:
            print(f"!! [CLOUD] Error guardando mensaje async: {e}")

    def obtener_chat(self, email: str, contacto: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene historial de chat con un contacto."""
        if not self.cloud_ready: 
            return []
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("chats_mensajes") \
                .select("*") \
                .eq("user_id", doc_id) \
                .eq("contacto", contacto) \
                .order("fecha", desc=True) \
                .limit(limit) \
                .execute()
            
            # Ordenar cronológicamente
            mensajes = response.data
            mensajes.reverse()
            return mensajes
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo chat: {e}")
            return []

    def mensajes_sin_leer(self, email: str) -> List[str]:
        """Obtiene lista de contactos con mensajes sin leer."""
        if not self.cloud_ready: 
            return []
            
        try:
            doc_id = self._get_user_doc_id(email)
            
            response = self.supabase.table("chats_mensajes") \
                .select("contacto") \
                .eq("user_id", doc_id) \
                .neq("autor", "yo") \
                .eq("leido", False) \
                .execute()
            
            # Obtener contactos únicos
            contactos = list(set([msg["contacto"] for msg in response.data]))
            return contactos
            
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo mensajes sin leer: {e}")
            return []
        
    # ==========================================================
    # 🔐 GESTIÓN DE CÓDIGOS (ESTRICTO BASE DE DATOS)
    # ==========================================================
    def guardar_codigo_verificacion(self, email: str, codigo: str) -> bool:
        """Guarda en Supabase y CONFIRMA que se escribió correctamente."""
        if not self.cloud_ready: 
            print("!! [CLOUD] Error: Nube no disponible para guardar código.")
            return False

        try:
            # 1. Normalización
            email_clean = str(email).lower().strip()
            doc_id = hashlib.sha256(f"code_{email_clean}".encode()).hexdigest()
            
            print(f">> [CLOUD] Intentando escribir en DB | ID: {doc_id[:8]}...")

            datos = {
                "id": doc_id,
                "email": email_clean,
                "codigo": str(codigo).strip(),
                "expira": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                "creado": datetime.now(timezone.utc).isoformat()
            }

            # 2. ESCRITURA SINCRÓNICA (Bloqueante)
            self.supabase.table("verification_codes").upsert(datos).execute()
            
            # 3. AUTO-VERIFICACIÓN DE INTEGRIDAD (La prueba de fuego)
            response = self.supabase.table("verification_codes") \
                .select("*") \
                .eq("id", doc_id) \
                .execute()
            
            if response.data:
                print(f"✅ [CLOUD] Escritura CONFIRMADA en base de datos. El documento existe.")
                return True
            else:
                print(f"❌ [CLOUD CRÍTICO] Se ejecutó inserción pero el documento NO aparece. Error de persistencia.")
                return False

        except Exception as e:
            print(f"!! [CLOUD ERROR] La base de datos rechazó la escritura: {e}")
            return False

    def validar_codigo_verificacion(self, email: str, codigo_usuario: str) -> Dict[str, Any]:
        """Verifica directamente contra la base de datos."""
        if not self.cloud_ready: 
            return {"ok": False, "error": "Nube desconectada"}

        try:
            email_clean = str(email).lower().strip()
            doc_id = hashlib.sha256(f"code_{email_clean}".encode()).hexdigest()
            code_user = str(codigo_usuario).strip()
            
            print(f">> [CLOUD] Consultando DB para ID: {doc_id[:8]}...")
            
            # Forzamos lectura fresca del servidor
            response = self.supabase.table("verification_codes") \
                .select("*") \
                .eq("id", doc_id) \
                .execute()
            
            if not response.data:
                print(f"!! [CLOUD] Documento {doc_id[:8]} NO ENCONTRADO en la consulta de validación.")
                return {"ok": False, "error": "Código no encontrado (Error de DB)."}

            data = response.data[0]
            print(f">> [CLOUD] Datos recuperados: {data.get('codigo')} vs Ingresado: {code_user}")
            
            # Verificar expiración
            try:
                expira = datetime.fromisoformat(data["expira"])
                if datetime.now(timezone.utc) > expira:
                    return {"ok": False, "error": "El código ha expirado."}
            except: 
                pass

            # Comparar
            if str(data["codigo"]).strip() == code_user:
                # Borrar tras uso
                try:
                    self.supabase.table("verification_codes").delete().eq("id", doc_id).execute()
                except: 
                    pass
                return {"ok": True}
            else:
                return {"ok": False, "error": "Código incorrecto."}

        except Exception as e:
            print(f"!! [CLOUD] Error validando: {e}")
            return {"ok": False, "error": f"Error técnico: {e}"}

    # ==========================================================
    # 🛠️ UTILIDADES ADICIONALES
    # ==========================================================
    def flush_cache(self, email: str = None):
        """Limpia la caché para un usuario específico o toda la caché."""
        if email:
            self._config_cache.pop(email, None)
            self._gustos_cache.pop(email, None)
            self._comandos_cache.pop(email, None)
            print(f">> [CLOUD] Caché limpiada para: {email}")
        else:
            self._config_cache.clear()
            self._gustos_cache.clear()
            self._comandos_cache.clear()
            print(">> [CLOUD] Caché completamente limpiada")

    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado del gestor de nube."""
        return {
            "cloud_ready": self.cloud_ready,
            "supabase_available": SUPABASE_AVAILABLE,
            "config_cache_size": len(self._config_cache),
            "gustos_cache_size": len(self._gustos_cache),
            "comandos_cache_size": len(self._comandos_cache)
        }

# ==========================================================
# 📝 EJEMPLO DE USO
# ==========================================================
if __name__ == "__main__":
    # Configuración de ejemplo
    config = {
        "supabase_url": "https://tu-proyecto.supabase.co",
        "supabase_key": "tu-clave-supabase"
    }
    
    cloud = CloudManager(config)
    
    if cloud.cloud_ready:
        print("✅ Supabase conectado correctamente")
        
        # Ejemplo de creación de usuario
        result = cloud.crear_usuario("test@example.com", "TestUser", "Password123")
        print(f"Crear usuario: {result}")
        
        # Ejemplo de login
        if cloud.validar_login("test@example.com", "Password123"):
            token = cloud.crear_sesion("test@example.com")
            print(f"Token de sesión: {token}")
            
            # Obtener usuario del token
            email = cloud.obtener_usuario_por_token(token)
            print(f"Usuario del token: {email}")
    else:
        print("❌ Supabase no disponible")

# ==========================================================
    # ⚡ SKILL STUDIO (MACROS AVANZADAS)
    # ==========================================================
    def guardar_skill(self, email: str, trigger: str, actions: List[Dict]):
        """Guarda una macro compleja (secuencia de pasos)."""
        # Validar caché y modo offline...
        if not self.cloud_ready: return
        
        self._run_async(self._guardar_skill_cloud, email, trigger, actions)

    def _guardar_skill_cloud(self, email: str, trigger: str, actions: List[Dict]):
        try:
            doc_id = self._get_user_doc_id(email)
            # Upsert basado en user_id y trigger sería ideal, 
            # pero por simplicidad insertamos o actualizamos buscando por trigger
            
            # Primero borramos si existe para ese usuario (para sobrescribir)
            self.supabase.table("skills").delete().eq("user_id", doc_id).eq("trigger", trigger).execute()
            
            data = {
                "user_id": doc_id,
                "trigger": trigger,
                "actions": json.dumps(actions) # Guardamos el JSON de pasos
            }
            self.supabase.table("skills").insert(data).execute()
            print(f">> [CLOUD] Skill guardada: {trigger}")
        except Exception as e:
            print(f"!! [CLOUD] Error guardando skill: {e}")

    # ==========================================================
    # ⚡ SKILL STUDIO (MACROS)
    # ==========================================================
    def obtener_skills(self, email: str) -> List[Dict]:
        """Descarga las macros guardadas por el usuario."""
        if not self.cloud_ready: return []
        try:
            doc_id = self._get_user_doc_id(email)
            # Seleccionamos * de la tabla skills
            response = self.supabase.table("skills").select("*").eq("user_id", doc_id).execute()
            
            # Procesar datos
            skills = []
            for item in response.data:
                # Supabase a veces devuelve el JSON como string, a veces como dict
                actions_data = item.get("actions")
                if isinstance(actions_data, str):
                    try: actions_data = json.loads(actions_data)
                    except: actions_data = []
                
                skills.append({
                    "id": item.get("id"),
                    "trigger": item.get("trigger"),
                    "actions": actions_data
                })
            return skills
        except Exception as e:
            print(f"!! [CLOUD] Error obteniendo skills: {e}")
            return []

    def guardar_skill(self, email: str, trigger: str, actions: List[Dict]):
        """Guarda una nueva macro."""
        if not self.cloud_ready: return
        
        # Ejecutamos en segundo plano para no congelar la UI
        self._run_async(self._guardar_skill_internal, email, trigger, actions)

    def _guardar_skill_internal(self, email: str, trigger: str, actions: List[Dict]):
        try:
            doc_id = self._get_user_doc_id(email)
            
            # Preparamos los datos
            data = {
                "user_id": doc_id,
                "trigger": trigger,
                "actions": json.dumps(actions) # Convertimos lista a JSON string para guardar
            }
            
            self.supabase.table("skills").insert(data).execute()
            print(f">> [CLOUD] Skill guardada: {trigger}")
        except Exception as e:
            print(f"!! [CLOUD] Error guardando skill: {e}")
    
    def borrar_skill(self, skill_id: int):
        """Elimina una macro por su ID numérico."""
        if not self.cloud_ready: return
        try:
            self.supabase.table("skills").delete().eq("id", skill_id).execute()
            print(f">> [CLOUD] Skill eliminada: ID {skill_id}")
        except Exception as e:
            print(f"!! [CLOUD] Error borrando skill: {e}")