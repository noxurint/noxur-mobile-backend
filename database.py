import sqlite3
from datetime import datetime

DB_NAME = "tracking.db"

def get_db_connection():
    """Abre y retorna la conexión a SQLite con soporte para diccionarios."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea la base de datos y las tablas relacionales si no existen."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Tabla de Dispositivos / Usuarios (Perfil Personal)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dispositivos (
            dispositivo_id TEXT PRIMARY KEY,
            nombres TEXT,
            apellidos TEXT,
            email TEXT,
            codigo_grupo TEXT,
            direccion TEXT,
            localidad TEXT,
            provincia TEXT,
            pais TEXT,
            foto TEXT,
            estado TEXT DEFAULT '😀 Disponible',
            ultima_conexion TEXT
        )
    ''')
    
    for col in ['foto', 'email', 'codigo_grupo', 'estado']:
        try:
            cursor.execute(f"ALTER TABLE dispositivos ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass

    # 2. Nueva Tabla Intermedia: Múltiples Grupos y Visibilidad (Puntos 4, 5 y 6)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dispositivo_grupos (
            dispositivo_id TEXT NOT NULL,
            codigo_grupo TEXT NOT NULL,
            activo INTEGER DEFAULT 1,
            fecha_union TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (dispositivo_id, codigo_grupo),
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (dispositivo_id)
        )
    ''')

    # Migración automática de grupos antiguos a la nueva tabla
    cursor.execute('''
        INSERT OR IGNORE INTO dispositivo_grupos (dispositivo_id, codigo_grupo, activo)
        SELECT dispositivo_id, UPPER(TRIM(codigo_grupo)), 1
        FROM dispositivos
        WHERE codigo_grupo IS NOT NULL AND TRIM(codigo_grupo) != ''
    ''')

    # 3. Tabla de Ubicaciones GPS
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ubicaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dispositivo_id TEXT NOT NULL,
            latitud REAL NOT NULL,
            longitud REAL NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (dispositivo_id) REFERENCES dispositivos (dispositivo_id)
        )
    ''')

    # 4. Tabla para mensajes de voz
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensajes_voz (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_grupo TEXT NOT NULL,
            emisor_dni TEXT NOT NULL,
            emisor_nombre TEXT NOT NULL,
            receptor_dni TEXT DEFAULT 'TODOS',
            audio_base64 TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE mensajes_voz ADD COLUMN receptor_dni TEXT DEFAULT 'TODOS'")
    except sqlite3.OperationalError:
        pass

    # 5. Tabla para mensajes de texto e imágenes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mensajes_texto (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_grupo TEXT NOT NULL,
            emisor_dni TEXT NOT NULL,
            emisor_nombre TEXT NOT NULL,
            receptor_dni TEXT DEFAULT 'TODOS',
            texto TEXT NOT NULL,
            tipo_msg TEXT DEFAULT 'texto',
            imagen_b64 TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    for col in [('tipo_msg', "TEXT DEFAULT 'texto'"), ('imagen_b64', 'TEXT')]:
        try:
            cursor.execute(f"ALTER TABLE mensajes_texto ADD COLUMN {col[0]} {col[1]}")
        except sqlite3.OperationalError:
            pass
    
    conn.commit()
    conn.close()
    print("💾 Base de datos relacional multi-grupo inicializada correctamente.")

def existe_dispositivo(disp_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM dispositivos WHERE UPPER(TRIM(dispositivo_id)) = ?', (str(disp_id).strip().upper(),))
    existe = cursor.fetchone() is not None
    conn.close()
    return existe

# --- FUNCIONES DE GESTIÓN MULTI-GRUPO ---

def agregar_usuario_a_grupo(disp_id, codigo_grupo, activo=1):
    """Agrega un usuario a un nuevo grupo o actualiza su estado (Activo/Inactivo)."""
    dni_limpio = str(disp_id or '').replace('.', '').replace('-', '').strip().upper()
    grupo_limpio = str(codigo_grupo or '').strip().upper()
    
    if not dni_limpio or not grupo_limpio:
        return False

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO dispositivo_grupos (dispositivo_id, codigo_grupo, activo)
            VALUES (?, ?, ?)
            ON CONFLICT(dispositivo_id, codigo_grupo) DO UPDATE SET
                activo = excluded.activo
        ''', (dni_limpio, grupo_limpio, 1 if activo else 0))
        
        # Opcional: mantener el último grupo registrado como principal en dispositivos
        cursor.execute('''
            UPDATE dispositivos SET codigo_grupo = ? WHERE UPPER(TRIM(dispositivo_id)) = ?
        ''', (grupo_limpio, dni_limpio))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error al asociar usuario a grupo: {e}")
        return False

def cambiar_estado_grupo_usuario(disp_id, codigo_grupo, activo):
    """Permite al usuario ponerse Activo (1) u Oculto/Inactivo (0) en un grupo específico."""
    dni_limpio = str(disp_id or '').replace('.', '').replace('-', '').strip().upper()
    grupo_limpio = str(codigo_grupo or '').strip().upper()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE dispositivo_grupos
            SET activo = ?
            WHERE UPPER(TRIM(dispositivo_id)) = ? AND UPPER(TRIM(codigo_grupo)) = ?
        ''', (1 if activo else 0, dni_limpio, grupo_limpio))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error cambiando estado de grupo: {e}")
        return False

def obtener_grupos_de_usuario(disp_id):
    """Retorna la lista de todos los grupos a los que pertenece el usuario y su estado."""
    dni_limpio = str(disp_id or '').replace('.', '').replace('-', '').strip().upper()
    if not dni_limpio:
        return []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT codigo_grupo, activo
            FROM dispositivo_grupos
            WHERE UPPER(TRIM(dispositivo_id)) = ?
            ORDER BY fecha_union DESC
        ''', (dni_limpio,))
        filas = cursor.fetchall()
        conn.close()
        return [dict(f) for f in filas]
    except Exception as e:
        print(f"❌ Error obteniendo grupos del usuario: {e}")
        return []

def guardar_perfil_usuario(data):
    disp_id = str(data.get('dni', '')).replace('.', '').replace('-', '').strip().upper()
    if not disp_id:
        return False

    tiempo_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    foto_nueva = data.get('foto', '')
    estado_nuevo = data.get('estado', '😀 Disponible')
    codigo_grupo = data.get('codigo_grupo', '').strip().upper()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO dispositivos (dispositivo_id, nombres, apellidos, email, codigo_grupo, direccion, localidad, provincia, pais, foto, estado, ultima_conexion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dispositivo_id) DO UPDATE SET
                nombres=excluded.nombres,
                apellidos=excluded.apellidos,
                email=excluded.email,
                codigo_grupo=excluded.codigo_grupo,
                direccion=excluded.direccion,
                localidad=excluded.localidad,
                provincia=excluded.provincia,
                pais=excluded.pais,
                foto=CASE WHEN excluded.foto != '' THEN excluded.foto ELSE dispositivos.foto END,
                estado=CASE WHEN excluded.estado != '' THEN excluded.estado ELSE dispositivos.estado END,
                ultima_conexion=excluded.ultima_conexion
        ''', (
            disp_id,
            data.get('nombres', ''),
            data.get('apellidos', ''),
            data.get('email', ''),
            codigo_grupo,
            data.get('direccion', ''),
            data.get('localidad', ''),
            data.get('provincia', ''),
            data.get('pais', ''),
            foto_nueva,
            estado_nuevo,
            tiempo_actual
        ))
        conn.commit()
        conn.close()

        # Si especificó un grupo, lo vinculamos automáticamente como activo
        if codigo_grupo:
            agregar_usuario_a_grupo(disp_id, codigo_grupo, activo=1)

        return True
    except Exception as e:
        print(f"❌ Error al guardar perfil en BD: {e}")
        return False

def obtener_amigos_por_grupo(codigo_grupo, mi_dni):
    """Obtiene los miembros del grupo que estén en estado ACTIVO (activo = 1)."""
    codigo_limpio = str(codigo_grupo or '').strip().upper()
    dni_limpio = str(mi_dni or '').replace('.', '').replace('-', '').strip().upper()

    if not codigo_limpio:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Filtra solo los miembros que estén con activo = 1 en la tabla de grupos
    cursor.execute('''
        SELECT d.dispositivo_id, d.nombres, d.apellidos, d.foto, d.estado, d.ultima_conexion
        FROM dispositivo_grupos dg
        JOIN dispositivos d ON UPPER(TRIM(REPLACE(REPLACE(d.dispositivo_id, '.', ''), '-', ''))) = UPPER(TRIM(REPLACE(REPLACE(dg.dispositivo_id, '.', ''), '-', '')))
        WHERE UPPER(TRIM(dg.codigo_grupo)) = ?
          AND dg.activo = 1
          AND UPPER(TRIM(REPLACE(REPLACE(d.dispositivo_id, '.', ''), '-', ''))) != ?
    ''', (codigo_limpio, dni_limpio))
    
    dispositivos = cursor.fetchall()
    amigos = []

    for d in dispositivos:
        disp_id = d["dispositivo_id"]
        disp_id_limpio = str(disp_id).replace('.', '').replace('-', '').strip().upper()

        cursor.execute('''
            SELECT latitud, longitud, timestamp
            FROM ubicaciones
            WHERE UPPER(TRIM(REPLACE(REPLACE(dispositivo_id, '.', ''), '-', ''))) = ?
            ORDER BY id DESC LIMIT 1
        ''', (disp_id_limpio,))
        
        ub = cursor.fetchone()

        amigos.append({
            "dispositivo_id": disp_id,
            "dni": disp_id,
            "nombres": d["nombres"] or "Amigo",
            "apellidos": d["apellidos"] or "",
            "foto_base64": d["foto"] or "",
            "estado": d["estado"] or "😀 Disponible",
            "latitud": ub["latitud"] if ub else 0.0,
            "longitud": ub["longitud"] if ub else 0.0,
            "timestamp": ub["timestamp"] if ub else (d["ultima_conexion"] or "")
        })

    conn.close()
    return amigos

def actualizar_estado_usuario(disp_id, nuevo_estado):
    dni_limpio = str(disp_id or '').strip().upper()
    estado_limpio = str(nuevo_estado or '😀 Disponible').strip()
    if not dni_limpio:
        return False

    tiempo_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE dispositivos 
            SET estado = ?, ultima_conexion = ?
            WHERE UPPER(TRIM(dispositivo_id)) = ?
        ''', (estado_limpio, tiempo_actual, dni_limpio))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error al actualizar estado en BD: {e}")
        return False

def guardar_ubicacion(disp_id, lat, lng):
    tiempo_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dni_limpio = str(disp_id or '').replace('.', '').replace('-', '').strip().upper()
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ubicaciones (dispositivo_id, latitud, longitud, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (dni_limpio, lat, lng, tiempo_actual))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error al guardar ubicación en BD: {e}")
        return False

def obtener_historial_con_perfil(disp_id=None, limite=100):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = '''
        SELECT u.latitud, u.longitud, u.timestamp, u.dispositivo_id,
               d.nombres, d.apellidos, d.email, d.localidad, d.foto, d.estado
        FROM ubicaciones u
        LEFT JOIN dispositivos d ON UPPER(TRIM(REPLACE(REPLACE(u.dispositivo_id, '.', ''), '-', ''))) = UPPER(TRIM(REPLACE(REPLACE(d.dispositivo_id, '.', ''), '-', '')))
    '''
    params = []
    if disp_id:
        dni_limpio = str(disp_id).replace('.', '').replace('-', '').strip().upper()
        query += " WHERE UPPER(TRIM(REPLACE(REPLACE(u.dispositivo_id, '.', ''), '-', ''))) = ?"
        params.append(dni_limpio)
        
    query += ' ORDER BY u.id DESC LIMIT ?'
    params.append(limite)
    
    cursor.execute(query, params)
    filas = cursor.fetchall()
    conn.close()
    
    resultado = []
    for f in reversed(filas):
        resultado.append({
            "lat": f["latitud"],
            "lng": f["longitud"],
            "timestamp": f["timestamp"],
            "dispositivo_id": f["dispositivo_id"],
            "nombres": f["nombres"] or "Sin registrar",
            "apellidos": f["apellidos"] or "",
            "email": f["email"] or "",
            "localidad": f["localidad"] or "",
            "foto": f["foto"] or "",
            "estado": f["estado"] or "😀 Disponible"
        })
    return resultado

# --- FUNCIONES DE MENSAJES DE VOZ Y TEXTO ---

def guardar_mensaje_voz(grupo, dni, nombre, receptor_dni, audio_b64):
    try:
        grupo_limpio = str(grupo or '').strip().upper()
        dni_limpio = str(dni or '').replace('.', '').replace('-', '').strip().upper()
        receptor_limpio = str(receptor_dni or 'TODOS').replace('.', '').replace('-', '').strip().upper()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO mensajes_voz (codigo_grupo, emisor_dni, emisor_nombre, receptor_dni, audio_base64)
            VALUES (?, ?, ?, ?, ?)
        ''', (grupo_limpio, dni_limpio, nombre or 'Móvil', receptor_limpio, audio_b64))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error guardando mensaje de voz: {e}")
        return False

def obtener_mensajes_voz_grupo(grupo, mi_dni=""):
    codigo_limpio = str(grupo or '').strip().upper()
    dni_limpio = str(mi_dni or '').replace('.', '').replace('-', '').strip().upper()

    if not codigo_limpio:
        return []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, codigo_grupo, emisor_dni, emisor_nombre, receptor_dni, audio_base64 AS audio, timestamp
            FROM mensajes_voz
            WHERE UPPER(TRIM(codigo_grupo)) = ?
              AND (
                receptor_dni = 'TODOS' 
                OR receptor_dni IS NULL 
                OR receptor_dni = '' 
                OR UPPER(TRIM(REPLACE(REPLACE(receptor_dni, '.', ''), '-', ''))) = ? 
                OR UPPER(TRIM(REPLACE(REPLACE(emisor_dni, '.', ''), '-', ''))) = ?
              )
            ORDER BY id DESC
            LIMIT 30
        ''', (codigo_limpio, dni_limpio, dni_limpio))

        filas = cursor.fetchall()
        conn.close()
        return [dict(f) for f in filas]
    except Exception as e:
        print(f"❌ Error obteniendo mensajes de voz: {e}")
        return []

def guardar_mensaje_texto(codigo_grupo, emisor_dni, emisor_nombre, receptor_dni, texto, tipo_msg='texto', imagen_b64=None):
    try:
        grupo_limpio = str(codigo_grupo or '').strip().upper()
        dni_limpio = str(emisor_dni or '').replace('.', '').replace('-', '').strip().upper()
        receptor_limpio = str(receptor_dni or 'TODOS').replace('.', '').replace('-', '').strip().upper()

        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO mensajes_texto (codigo_grupo, emisor_dni, emisor_nombre, receptor_dni, texto, tipo_msg, imagen_b64)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (grupo_limpio, dni_limpio, emisor_nombre or 'Móvil', receptor_limpio, texto, tipo_msg, imagen_b64))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error guardando mensaje de texto/imagen: {e}")
        return False

def obtener_mensajes_texto_grupo(grupo, mi_dni=""):
    codigo_limpio = str(grupo or '').strip().upper()
    dni_limpio = str(mi_dni or '').replace('.', '').replace('-', '').strip().upper()

    if not codigo_limpio:
        return []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, codigo_grupo, emisor_dni, emisor_nombre, receptor_dni, texto, tipo_msg, imagen_b64, timestamp
            FROM mensajes_texto
            WHERE UPPER(TRIM(codigo_grupo)) = ? 
              AND (
                receptor_dni = 'TODOS' 
                OR receptor_dni IS NULL 
                OR receptor_dni = '' 
                OR UPPER(TRIM(REPLACE(REPLACE(receptor_dni, '.', ''), '-', ''))) = ? 
                OR UPPER(TRIM(REPLACE(REPLACE(emisor_dni, '.', ''), '-', ''))) = ?
              )
            ORDER BY id DESC
            LIMIT 30
        ''', (codigo_limpio, dni_limpio, dni_limpio))

        filas = cursor.fetchall()
        conn.close()
        return [dict(f) for f in filas]
    except Exception as e:
        print(f"❌ Error obteniendo mensajes de texto: {e}")
        return []