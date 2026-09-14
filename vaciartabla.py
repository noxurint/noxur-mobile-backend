# Podés ejecutar esto en Python para limpiar la tabla antes de la nueva prueba
import sqlite3
# conn = sqlite3.connect('tracking.db') 'QUITA EL COMENTARIO SI LO QUIERES USAR
cursor = conn.cursor()
cursor.execute("DELETE FROM ubicaciones;")
conn.commit()
conn.close()
print("Base de datos limpia para nuevas coordenadas.")

#npx localtunnel --port 5000 'forma rápida Para ver la url, no requiere cambiar políticas'

#Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned 'habilitar los scripts para tu usuario con este comando'
#lt --port 5000 'Para ver la url'
#npx localtunnel --port 5000
#lt --port 5000 --subdomain major-adults-lie

#flutter clean
#flutter pub get 'Para vaciar todo lo realizado'
#flutter run 'para correr la app, en el celular'
#flutter pub add http
#flutter build apk --release 'Para generar el apk de release'
#Ubicación: C:\Users\VitC\Downloads\NoxurMobileCel\build\app\outputs\flutter-apk\app-release.apk
#Remove-Item pubspec.lock -ErrorAction SilentlyContinue 'Eliminar el archivo de bloqueo cacheado'

#limpiá la caché de build de Android en PowerShell:
#cd android
#.\gradlew clean
#cd ..

#flutter run -v 'comando en la terminal para que Gradle nos diga la causa exacta del fallo'