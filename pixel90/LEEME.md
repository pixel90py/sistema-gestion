# PIXEL90 — Sistema de Gestión Comercial

## Instalación (una sola vez)

### 1. Instalá Python
- Descargá Python 3.11+ desde https://www.python.org/downloads/
- Durante la instalación: ✅ marcá "Add Python to PATH"

### 2. Instalá Flask
Abrí CMD o PowerShell y ejecutá:
```
pip install flask
```

### 3. Descargá/copiá la carpeta PIXEL90
Colocá la carpeta donde quieras (ej: `C:\pixel90\`)

---

## Uso diario

### Opción A — Doble clic
Hacé doble clic en `INICIAR_PIXEL90.bat`
→ Se abre el navegador automáticamente en http://localhost:5000

### Opción B — Manual
```
cd C:\pixel90
python app.py
```
Luego abrí Chrome/Firefox en http://localhost:5000

---

## Acceso desde el celular
1. El celular debe estar en la misma red WiFi que tu PC
2. Buscá la IP de tu PC: ejecutá `ipconfig` en CMD → buscá "IPv4 Address"
3. En el celular abrí el navegador y entrá a: `http://192.168.X.X:5000`

---

## Backup de datos
Todos los datos están en `db/pixel90.db`
Copiá ese archivo para hacer backup. Es todo lo que necesitás.

---

## Estructura de carpetas
```
pixel90/
├── app.py              ← Servidor principal
├── db.py               ← Base de datos
├── INICIAR_PIXEL90.bat ← Arranque con doble clic
├── db/
│   └── pixel90.db      ← TUS DATOS (hacer backup de este archivo)
├── static/
│   └── img/            ← Logos y mascota
└── templates/
    └── index.html      ← Interfaz
```
