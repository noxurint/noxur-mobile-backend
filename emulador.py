import json
import time
import os
import socketio

# Creamos el cliente de WebSocket
sio = socketio.Client()

def cargar_coordenadas_geojson(archivo_path):
    """Abre el archivo GeoJSON y extrae la lista de coordenadas de forma flexible."""
    if not os.path.exists(archivo_path):
        print(f"❌ Error: No se encontró el archivo '{archivo_path}' en la carpeta.")
        print(f"Archivos actuales en la carpeta: {os.listdir('.')}")
        return []
    
    with open(archivo_path, 'r', encoding='utf-8') as f:
        try:
            datos = json.load(f)
        except Exception as e:
            print(f"❌ Error: El archivo no es un JSON válido: {e}")
            return []
        
    coordenadas_limpias = []
    
    def extraer_coords(objeto):
        if isinstance(objeto, dict):
            if objeto.get('type') in ['LineString', 'MultiLineString', 'Polygon'] and 'coordinates' in objeto:
                return objeto['coordinates']
            for clave, valor in objeto.items():
                resultado = extraer_coords(valor)
                if resultado: return resultado
        elif isinstance(objeto, list):
            for elemento in objeto:
                resultado = extraer_coords(elemento)
                if resultado: return resultado
        return None

    coords_raw = extraer_coords(datos)

    if coords_raw:
        if isinstance(coords_raw[0], list) and isinstance(coords_raw[0][0], list):
            coords_raw = coords_raw[0]
            
        for coord in coords_raw:
            if isinstance(coord, list) and len(coord) >= 2:
                coordenadas_limpias.append({
                    "lat": coord[1],  # El GeoJSON usa [Lng, Lat]
                    "lng": coord[0]
                })
    
    if coordenadas_limpias:
        print(f"✅ ¡Ruta cargada con éxito! {len(coordenadas_limpias)} puntos listos para emular.")
    else:
        print("❌ Error: No se encontraron geometrías de tipo línea o ruta en el archivo.")
        
    return coordenadas_limpias

@sio.event
def connect():
    print("⚡ Emulador conectado al servidor GatMobile.")

if __name__ == '__main__':
    nombre_archivo = "ruta.geojson"
    ruta_a_seguir = cargar_coordenadas_geojson(nombre_archivo)
    
    if not ruta_a_seguir:
        print("🛑 Saliendo del emulador por falta de datos válidos.")
        exit()

    try:
        sio.connect('http://localhost:5000')
        print("🚗 Iniciando viaje simulado...")
        
        for i, coordenada in enumerate(ruta_a_seguir):
            payload = {
                "dispositivo_id": "AUTO-FAMILIA-01",
                "lat": coordenada["lat"],
                "lng": coordenada["lng"]
            }
            
            sio.emit('actualizar_posicion', payload)
            progreso = (i + 1) / len(ruta_a_seguir) * 100
            print(f"[{progreso:.1f}%] Enviado -> Lat: {coordenada['lat']:.5f} | Lng: {coordenada['lng']:.5f}")
            time.sleep(2)
            
        print("🏁 ¡Destino alcanzado! Ruta finalizada.")
        sio.disconnect()
        
    except Exception as e:
        print(f"❌ Error en la transmisión: {e}")