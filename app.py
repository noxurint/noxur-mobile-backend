import functools
import sqlite3
import traceback
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import database

# Librería de traducción
try:
    from googletrans import Translator
    translator = Translator()
except ImportError:
    translator = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'noxurmobile_secret_key_2026'

# 1. SEGURIDAD: Limitar el tamaño máximo del Payload a 16 MB (para imágenes/audios Base64)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# 2. SEGURIDAD: Configuración de CORS estricto
CORS(app, resources={r"/api/*": {"origins": "*"}})

# 3. SEGURIDAD: Configuración de Rate Limiting por IP para evitar saturación/DDoS
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per day", "100 per hour"],
    storage_uri="memory://"
)

socketio = SocketIO(app, cors_allowed_origins="*")

# Inicializa las tablas al arrancar la aplicación
database.init_db()

# Clave de API para autenticar peticiones de la app móvil
CLAVE_SECRETA_APP = "Noxur_Token_Seguro_2026_x89A!"

def requerir_api_key(f):
    """Decorador opcional para validar la clave secreta en la cabecera x-api-key."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        token_recibido = request.headers.get('x-api-key')
        # Si la app envía la cabecera, se valida obligatoriamente
        if token_recibido and token_recibido != CLAVE_SECRETA_APP:
            return json_response({"exito": False, "mensaje": "No autorizado. Clave de API inválida."}, 401)
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def aplicar_headers_seguridad(response):
    """4. SEGURIDAD: Inyección de cabeceras de protección HTTP."""
    response.headers["bypass-tunnel-reminder"] = "true"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def json_response(data, status_code=200):
    """Auxiliar para crear respuestas JSON estandarizadas."""
    resp = app.make_response((jsonify(data), status_code))
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp

@app.route('/')
def index():
    return render_template('mapa.html')

# --- ENDPOINT TRADUCTOR LIVE ---

import requests
from flask import jsonify, request


@app.route("/api/traductor/traducir", methods=["POST"])
def traducir_texto():
  try:
    data = request.get_json() or {}
    texto = data.get("texto", "").strip()
    origen = data.get("origen", "es").strip()
    destino = data.get("destino", "en").strip()

    if not texto:
      return jsonify({"error": "No se proporcionó texto para traducir"}), 400

    # Petición directa y ultra rápida a la API gratuita de Google Translate
    url_gt = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={origen}&tl={destino}&dt=t&q={requests.utils.quote(texto)}"
    res = requests.get(url_gt, timeout=5)

    if res.status_code == 200:
      res_json = res.json()
      # Extraer el texto traducido
      traduccion = "".join([segmento[0] for segmento in res_json[0]])
      return jsonify({"traducido": traduccion, "origen": origen, "destino": destino}), 200
    else:
      return jsonify({"error": "Falla en servicio de traducción"}), 500

  except Exception as e:
    print(f"Error en /api/traductor/traducir: {e}")
    return jsonify({"error": str(e)}), 500

# --- RUTAS DE GESTIÓN DE PERFIL ---

@app.route('/api/perfil', methods=['POST'])
@limiter.limit("20 per minute")
@requerir_api_key
def registrar_perfil():
    datos = request.get_json(silent=True) or request.form.to_dict()
    
    if datos and datos.get('dni'):
        dni_limpio = str(datos.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
        datos['dni'] = dni_limpio
        es_nuevo = datos.get('es_nuevo', False)

        if es_nuevo and database.existe_dispositivo(dni_limpio):
            return json_response({
                "status": "duplicado", 
                "mensaje": f"El DNI {dni_limpio} ya se encuentra registrado. Si es tuyo, podés modificar tus datos."
            }, 400)

        exito = database.guardar_perfil_usuario(datos)
        if exito:
            mensaje_confirmacion = "✅ Perfil registrado con éxito en la base de datos" if es_nuevo else "✅ Datos actualizados en la base de datos correctamente"
            print(f"👤 [PERFIL ACTUALIZADO] DNI: {dni_limpio} - Grupo: {datos.get('codigo_grupo')}")
            return json_response({"status": "ok", "mensaje": mensaje_confirmacion}, 200)

    return json_response({"status": "error", "mensaje": "DNI requerido"}, 400)

# --- RUTAS DE GESTIÓN MULTI-GRUPO ---

@app.route('/api/grupos/usuario', methods=['GET'])
@limiter.limit("60 per minute")
def obtener_grupos_usuario():
    mi_dni = str(request.args.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    if not mi_dni:
        return json_response([], 200)

    grupos = database.obtener_grupos_de_usuario(mi_dni)
    return json_response(grupos, 200)

@app.route('/api/grupos/estado', methods=['POST'])
@limiter.limit("30 per minute")
@requerir_api_key
def cambiar_estado_grupo():
    datos = request.get_json(silent=True) or request.form.to_dict() or {}
    dni = str(datos.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    codigo_grupo = str(datos.get('codigo_grupo', '')).strip().upper()
    activo = datos.get('activo', True)

    if not dni or not codigo_grupo:
        return json_response({'exito': False, 'mensaje': 'DNI y codigo_grupo son requeridos'}, 400)

    exito = database.cambiar_estado_grupo_usuario(dni, codigo_grupo, activo)
    if exito:
        estado_str = "ACTIVO" if activo else "INACTIVO"
        print(f"👁️ [VISIBILIDAD CAMBIADA] DNI: {dni} -> Grupo: {codigo_grupo} ({estado_str})")
        return json_response({'exito': True, 'mensaje': f'Estado en grupo {codigo_grupo} actualizado'}, 200)
    else:
        return json_response({'exito': False, 'mensaje': 'Error al actualizar visibilidad en BD'}, 500)

@app.route('/api/grupos/unirse', methods=['POST'])
@limiter.limit("15 per minute")
@requerir_api_key
def unirse_a_grupo():
    datos = request.get_json(silent=True) or request.form.to_dict() or {}
    dni = str(datos.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    codigo_grupo = str(datos.get('codigo_grupo', '')).strip().upper()

    if not dni or not codigo_grupo:
        return json_response({'exito': False, 'mensaje': 'DNI y código de grupo requeridos'}, 400)

    exito = database.agregar_usuario_a_grupo(dni, codigo_grupo, activo=1)
    if exito:
        print(f"👥 [NUEVO GRUPO] DNI: {dni} se unió a: {codigo_grupo}")
        return json_response({'exito': True, 'mensaje': f'Unido con éxito al grupo {codigo_grupo}'}, 200)
    return json_response({'exito': False, 'mensaje': 'Error al vincular con el grupo'}, 500)

@app.route('/api/estado/actualizar', methods=['POST'])
@limiter.limit("30 per minute")
@requerir_api_key
def actualizar_estado():
    datos = request.get_json(silent=True) or request.form.to_dict() or {}
    dni = str(datos.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    estado = str(datos.get('estado', '😀 Disponible')).strip()

    if not dni:
        return json_response({'exito': False, 'mensaje': 'DNI requerido'}, 400)

    exito = database.actualizar_estado_usuario(dni, estado)
    if exito:
        print(f"📌 [ESTADO ACTUALIZADO] DNI: {dni} -> Estado: {estado}")
        return json_response({'exito': True, 'mensaje': 'Estado actualizado correctamente'}, 200)
    else:
        return json_response({'exito': False, 'mensaje': 'Error al actualizar estado en la BD'}, 500)

@app.route('/api/amigos', methods=['GET'])
@limiter.limit("60 per minute")
def obtener_amigos():
    grupo = request.args.get('grupo', '').strip().upper()
    mi_dni = str(request.args.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()

    if not grupo or not mi_dni:
        return json_response([], 200)

    amigos = database.obtener_amigos_por_grupo(grupo, mi_dni)
    return json_response(amigos, 200)

@app.route('/api/celular', methods=['GET', 'POST'])
@limiter.limit("120 per minute")
def recibir_ubicacion_celular():
    lat = request.args.get('lat') or request.form.get('lat')
    lng = request.args.get('lon') or request.args.get('lng') or request.form.get('lon')
    disp_id = request.args.get('id') or request.form.get('id')
    estado = request.args.get('estado') or request.form.get('estado')

    if not lat or not lng:
        datos_json = request.get_json(silent=True)
        if datos_json:
            lat = datos_json.get('lat')
            lng = datos_json.get('lon') or datos_json.get('lng')
            disp_id = datos_json.get('id')
            estado = datos_json.get('estado')

    disp_id = str(disp_id).replace('.', '').replace('-', '').replace(' ', '').strip() if disp_id else 'SIN-DNI'

    if lat and lng:
        try:
            lat_f = float(lat)
            lng_f = float(lng)
            
            database.guardar_ubicacion(disp_id, lat_f, lng_f)

            if estado:
                database.actualizar_estado_usuario(disp_id, str(estado).strip())

            historial = database.obtener_historial_con_perfil(disp_id=disp_id, limite=1)
            
            nombres = "Familiar"
            apellidos = ""
            email = ""
            foto = ""
            estado_actual = "😀 Disponible"
            
            if historial and len(historial) > 0:
                nombres = historial[0].get('nombres', 'Familiar')
                apellidos = historial[0].get('apellidos', '')
                email = historial[0].get('email', '')
                foto = historial[0].get('foto', '')
                estado_actual = historial[0].get('estado', '😀 Disponible')

            payload = {
                "dispositivo_id": disp_id,
                "lat": lat_f,
                "lng": lng_f,
                "nombres": nombres,
                "apellidos": apellidos,
                "email": email,
                "foto": foto,
                "estado": estado_actual
            }
            socketio.emit('posicion_actualizada', payload)
            
            return json_response({"status": "OK"}, 200)
        except ValueError:
            pass

    return json_response({"error": "Datos inválidos"}, 400)

@app.route('/api/historial')
@limiter.limit("30 per minute")
def get_historial():
    ruta_historial = database.obtener_historial_con_perfil(limite=100)
    return json_response(ruta_historial, 200)

# --- RUTAS DE MENSAJES DE VOZ ---

@app.route('/api/voz/enviar', methods=['POST'])
@limiter.limit("20 per minute")
@requerir_api_key
def enviar_voz():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    grupo = str(data.get('codigo_grupo', '')).strip().upper()
    dni = str(data.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    nombre = str(data.get('nombre', 'Móvil')).strip()
    receptor_dni = str(data.get('receptor_dni', 'TODOS')).replace('.', '').replace('-', '').replace(' ', '').strip()
    audio_b64 = data.get('audio', '')

    if not grupo or not dni or not audio_b64:
        return json_response({'exito': False, 'mensaje': 'Faltan datos obligatorios (grupo, dni o audio)'}, 400)

    exito = database.guardar_mensaje_voz(grupo, dni, nombre, receptor_dni, audio_b64)
    if exito:
        socketio.emit('nuevo_mensaje_voz', {
            'codigo_grupo': grupo,
            'emisor_dni': dni,
            'emisor_nombre': nombre,
            'receptor_dni': receptor_dni
        })
        return json_response({'exito': True, 'mensaje': 'Audio transmitido con éxito'}, 200)
    else:
        return json_response({'exito': False, 'mensaje': 'Error al guardar el audio en la BD'}, 500)

@app.route('/api/voz/obtener', methods=['GET'])
@limiter.limit("60 per minute")
def obtener_voz():
    grupo = request.args.get('grupo', '').strip().upper()
    mi_dni = str(request.args.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
    
    if not grupo:
        return json_response([], 200)
        
    mensajes = database.obtener_mensajes_voz_grupo(grupo, mi_dni)
    return json_response(mensajes, 200)

# --- RUTAS DE MENSAJES DE TEXTO E IMÁGENES ---

@app.route('/api/texto/enviar', methods=['POST'])
@limiter.limit("30 per minute")
@requerir_api_key
def enviar_mensaje_texto():
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        grupo = str(data.get('codigo_grupo', '')).strip().upper()
        dni = str(data.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
        nombre = str(data.get('nombre', 'Móvil')).strip()
        texto = str(data.get('texto', '')).strip()
        receptor_dni = str(data.get('receptor_dni', 'TODOS')).replace('.', '').replace('-', '').replace(' ', '').strip()
        tipo_msg = str(data.get('tipo_msg', 'texto')).strip()
        imagen_b64 = data.get('imagen_b64')

        if not grupo or not dni:
            return json_response({'exito': False, 'mensaje': 'Faltan datos obligatorios (codigo_grupo o dni)'}, 400)

        if tipo_msg == 'texto' and not texto:
            return json_response({'exito': False, 'mensaje': 'El texto del mensaje no puede estar vacío'}, 400)

        exito = database.guardar_mensaje_texto(grupo, dni, nombre, receptor_dni, texto, tipo_msg, imagen_b64)
        if exito:
            payload = {
                'codigo_grupo': grupo,
                'emisor_dni': dni,
                'emisor_nombre': nombre,
                'receptor_dni': receptor_dni,
                'texto': texto,
                'tipo_msg': tipo_msg,
                'imagen_b64': imagen_b64
            }
            socketio.emit('nuevo_mensaje_texto', payload)
            return json_response({'exito': True, 'mensaje': 'Transmitido con éxito'}, 200)
        else:
            return json_response({'exito': False, 'mensaje': 'Error al guardar en BD'}, 500)
    except Exception as e:
        print(f"❌ Error en /api/texto/enviar: {e}")
        traceback.print_exc()
        return json_response({'exito': False, 'mensaje': str(e)}, 500)

@app.route('/api/texto/obtener', methods=['GET'])
@limiter.limit("60 per minute")
def obtener_mensajes_texto():
    grupo = request.args.get('grupo', '').strip().upper()
    mi_dni = str(request.args.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()

    if not grupo:
        return json_response([], 200)

    mensajes = database.obtener_mensajes_texto_grupo(grupo, mi_dni)
    return json_response(mensajes, 200)

# --- ENDPOINTS PARA EVENTOS Y ALERTAS ---

@app.route('/api/eventos/crear', methods=['POST'])
@limiter.limit("10 per minute")
@requerir_api_key
def crear_evento():
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        codigo_grupo = str(data.get('codigo_grupo', '')).strip().upper()
        creador_dni = str(data.get('dni', '')).replace('.', '').replace('-', '').replace(' ', '').strip()
        creador_nombre = str(data.get('nombre', 'Amigo')).strip()
        tipo = str(data.get('tipo', 'alerta')).strip()
        titulo = str(data.get('titulo', 'Alerta')).strip()
        lat = float(data.get('lat', 0.0))
        lng = float(data.get('lng', 0.0))

        if not codigo_grupo or not creador_dni:
            return json_response({'exito': False, 'mensaje': 'Datos incompletos'}, 400)

        conn = database.get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS eventos_grupo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_grupo TEXT,
                creador_dni TEXT,
                creador_nombre TEXT,
                tipo TEXT,
                titulo TEXT,
                lat REAL,
                lng REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        c.execute('''
            INSERT INTO eventos_grupo (codigo_grupo, creador_dni, creador_nombre, tipo, titulo, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (codigo_grupo, creador_dni, creador_nombre, tipo, titulo, lat, lng))
        
        conn.commit()
        conn.close()

        prefijo = "🚨 ALERTA:" if tipo == 'alerta' else "🎉 EVENTO:"
        msg_texto = f"{prefijo} {titulo}"
        database.guardar_mensaje_texto(codigo_grupo, creador_dni, creador_nombre, 'TODOS', msg_texto)

        socketio.emit('nuevo_evento', {
            'codigo_grupo': codigo_grupo,
            'tipo': tipo,
            'titulo': titulo,
            'lat': lat,
            'lng': lng
        })

        return json_response({'exito': True, 'mensaje': 'Evento/Alerta reportado con éxito'}, 200)
    except Exception as e:
        print(f"❌ Error creando evento: {e}")
        traceback.print_exc()
        return json_response({'exito': False, 'mensaje': str(e)}, 500)

@app.route('/api/eventos/obtener', methods=['GET'])
@limiter.limit("60 per minute")
def obtener_eventos():
    try:
        codigo_grupo = request.args.get('grupo', '').strip().upper()
        if not codigo_grupo:
            return json_response([], 200)

        conn = database.get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS eventos_grupo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_grupo TEXT,
                creador_dni TEXT,
                creador_nombre TEXT,
                tipo TEXT,
                titulo TEXT,
                lat REAL,
                lng REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        c.execute('''
            SELECT id, creador_dni, creador_nombre, tipo, titulo, lat, lng, timestamp
            FROM eventos_grupo
            WHERE codigo_grupo = ? AND timestamp >= datetime('now', '-12 hours')
            ORDER BY id DESC
        ''', (codigo_grupo,))
        
        filas = c.fetchall()
        conn.close()

        eventos = [dict(f) for f in filas]
        return json_response(eventos, 200)
    except Exception as e:
        print(f"❌ Error obteniendo eventos: {e}")
        return json_response([], 200)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)