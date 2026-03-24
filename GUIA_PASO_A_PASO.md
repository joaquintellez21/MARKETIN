# GUIA PASO A PASO - Bot de Trading para Polymarket

Sigue cada paso en orden. No te saltes ninguno.

---

## PASO 1: Instalar Python

Necesitas Python 3.10 o superior en tu computadora.

**En Windows:**
1. Abre tu navegador
2. Ve a https://www.python.org/downloads/
3. Haz clic en el boton amarillo grande que dice "Download Python 3.x.x"
4. Abre el archivo descargado
5. **MUY IMPORTANTE**: Marca la casilla que dice "Add Python to PATH" abajo del instalador
6. Haz clic en "Install Now"
7. Espera a que termine y cierra el instalador

**En Mac:**
1. Abre la Terminal (busca "Terminal" en Spotlight con Cmd+Espacio)
2. Escribe esto y presiona Enter:
```
brew install python
```
(Si no tienes brew, ve a https://brew.sh y sigue las instrucciones primero)

---

## PASO 2: Descargar el bot

1. Abre la terminal / linea de comandos:
   - **Windows**: Busca "cmd" en el menu de inicio y abrelo
   - **Mac**: Abre Terminal
2. Escribe estos comandos uno por uno, presionando Enter despues de cada uno:

```
git clone https://github.com/joaquintellez21/marketin.git
```

```
cd marketin
```

Si no tienes git, descarga el ZIP desde https://github.com/joaquintellez21/marketin y descomprimelo. Luego en la terminal navega a la carpeta:
```
cd ruta/donde/descomprimiste/marketin
```

---

## PASO 3: Crear entorno virtual

Esto aisla las dependencias del bot para no afectar tu computadora.

**Windows:**
```
python -m venv .venv
```
```
.venv\Scripts\activate
```

**Mac / Linux:**
```
python3 -m venv .venv
```
```
source .venv/bin/activate
```

Sabras que funciono porque veras `(.venv)` al inicio de la linea en tu terminal.

---

## PASO 4: Instalar dependencias

Con el entorno virtual activado (ves `(.venv)` en la terminal), escribe:

```
pip install -r requirements.txt
```

Espera a que termine. Veran varias lineas de texto. Esto es normal.

---

## PASO 5: Crear tu cuenta en Polymarket y obtener credenciales

### 5a. Crear cuenta en Polymarket
1. Ve a https://polymarket.com
2. Crea una cuenta (puedes conectar una wallet de MetaMask o crear una con email)
3. Deposita fondos (USDC en la red Polygon) -- puedes empezar con poco, como $10

### 5b. Obtener tus credenciales de la API
1. Ve a https://polymarket.com
2. Inicia sesion
3. Ve a la seccion de developer / API de tu perfil
4. Genera una API Key -- te daran 3 valores:
   - **API Key** (una cadena larga de letras y numeros)
   - **Secret** (otra cadena larga)
   - **Passphrase** (otra cadena)
5. Guarda estos 3 valores en un lugar seguro. Los necesitaras en el siguiente paso.

### 5c. Tu clave privada (Private Key)
- Si usas MetaMask: Haz clic en los 3 puntos > Detalles de cuenta > Exportar clave privada
- **NUNCA compartas tu clave privada con nadie**
- **NUNCA la subas a internet**

---

## PASO 6: Configurar el bot

1. En la carpeta del proyecto, busca el archivo `.env.example`
2. Haz una copia y renombrala a `.env`:

**Windows:**
```
copy .env.example .env
```

**Mac / Linux:**
```
cp .env.example .env
```

3. Abre el archivo `.env` con cualquier editor de texto (Notepad, TextEdit, VS Code, etc.)

4. Reemplaza los valores. El archivo se vera asi:

```
# Polymarket API Configuration
POLYMARKET_API_KEY=aqui_pega_tu_api_key
POLYMARKET_SECRET=aqui_pega_tu_secret
POLYMARKET_PASSPHRASE=aqui_pega_tu_passphrase
PRIVATE_KEY=aqui_pega_tu_clave_privada

# Chain Configuration (NO TOQUES ESTO)
CHAIN_ID=137

# Trading Configuration
MAX_POSITION_SIZE=100
STOP_LOSS_PERCENT=10
TAKE_PROFIT_PERCENT=20
ORDER_SIZE=10
DRY_RUN=true

# Logging
LOG_LEVEL=INFO
```

5. **Guarda el archivo**

### Que significa cada valor de trading:

| Valor | Que hace | Ejemplo |
|---|---|---|
| `MAX_POSITION_SIZE` | Maximo de dolares que el bot puede tener invertidos al mismo tiempo | `100` = maximo $100 |
| `STOP_LOSS_PERCENT` | Si pierdes este % en una posicion, el bot vende automaticamente | `10` = vende si pierde 10% |
| `TAKE_PROFIT_PERCENT` | Si ganas este % en una posicion, el bot vende automaticamente | `20` = vende si gana 20% |
| `ORDER_SIZE` | Cuantos dolares pone el bot en cada operacion | `10` = $10 por trade |
| `DRY_RUN` | `true` = SIMULACION (no gasta dinero real). `false` = dinero real | Empieza con `true` |

---

## PASO 7: Ejecutar el bot en MODO SIMULACION (recomendado primero)

Asegurate de que `DRY_RUN=true` en tu archivo `.env` (asi viene por defecto).

En la terminal, con el entorno virtual activado, escribe:

```
python bot.py
```

Veras algo como esto en pantalla:

```
============================================================
Polymarket Trading Bot starting
Dry run: True
Strategies: 3
Max position size: $100.00
============================================================
--- Tick ---
Fetched 20 markets
Signal: BUY abc123... 10.00 @ $0.3500 – Momentum: price $0.35 < buy_below $0.40
[DRY RUN] Order: BUY 10.00 @ $0.3500 on abc123...
Sleeping 60s until next tick...
```

**[DRY RUN]** significa que NO esta gastando dinero real. Solo simula.

### Para detener el bot:
Presiona `Ctrl + C` en la terminal.

---

## PASO 8: Ejecutar con DINERO REAL (cuando estes listo)

**ADVERTENCIA: Solo haz esto cuando entiendas como funciona el bot y estes dispuesto a arriesgar dinero.**

1. Abre el archivo `.env`
2. Cambia esta linea:
```
DRY_RUN=false
```
3. Guarda el archivo
4. Ejecuta el bot:
```
python bot.py
```

Ahora el bot comprara y vendera con dinero real.

---

## PASO 9: Ajustar la configuracion (opcional)

### Quieres ser mas conservador (menos riesgo):
```
MAX_POSITION_SIZE=50
STOP_LOSS_PERCENT=5
ORDER_SIZE=5
```

### Quieres ser mas agresivo (mas riesgo):
```
MAX_POSITION_SIZE=500
STOP_LOSS_PERCENT=15
TAKE_PROFIT_PERCENT=30
ORDER_SIZE=25
```

Despues de cambiar valores, guarda el archivo `.env` y reinicia el bot (`Ctrl+C` y luego `python bot.py`).

---

## RESOLUCION DE PROBLEMAS

### "python no se reconoce como comando"
- Windows: Reinstala Python y asegurate de marcar "Add to PATH"
- Mac: Usa `python3` en vez de `python`

### "No module named py_clob_client"
- Asegurate de tener el entorno virtual activado (ves `(.venv)` en la terminal)
- Ejecuta: `pip install -r requirements.txt`

### "Error de conexion / API key invalid"
- Revisa que copiaste bien los valores en el archivo `.env`
- No debe haber espacios antes o despues del `=`
- Ejemplo correcto: `POLYMARKET_API_KEY=abc123`
- Ejemplo INCORRECTO: `POLYMARKET_API_KEY = abc123`

### El bot no hace nada / no compra
- Es normal si esta en modo `DRY_RUN=true`
- Si esta en modo real, puede que no encuentre mercados que cumplan los criterios de las estrategias
- Revisa el archivo `bot.log` para ver que esta pasando

### Quiero parar el bot
- Presiona `Ctrl + C` en la terminal
- El bot se detendra de forma segura

---

## RESUMEN RAPIDO (para los impacientes)

```bash
# 1. Descargar
git clone https://github.com/joaquintellez21/marketin.git
cd marketin

# 2. Preparar
python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# 3. Configurar
cp .env.example .env
# Editar .env con tus credenciales de Polymarket

# 4. Ejecutar (simulacion)
python bot.py

# 5. Ejecutar (dinero real) - cambiar DRY_RUN=false en .env
python bot.py
```
