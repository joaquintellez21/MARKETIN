# Polymarket Trading Bot

Bot automatizado para trading en [Polymarket](https://polymarket.com) usando la API CLOB.

## Características

- **3 Estrategias de trading:**
  - **Momentum** – Compra tokens con precio bajo y tendencia alcista, vende cuando sube
  - **Market Making** – Coloca órdenes bid/ask alrededor del precio medio para capturar el spread
  - **Value** – Compra mercados con alto volumen y precio bajo (potencialmente infravalorados)
- **Gestión de riesgo** – Stop-loss, take-profit, límites de exposición
- **Modo dry-run** – Simula operaciones sin ejecutar trades reales
- **Scanner de mercados** – Filtra mercados por volumen y liquidez
- **Logging completo** – Consola + archivo de log

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/joaquintellez21/marketin.git
cd marketin

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Configuración

```bash
# Copiar el archivo de ejemplo y editar con tus credenciales
cp .env.example .env
```

Variables de entorno requeridas:

| Variable | Descripción |
|---|---|
| `POLYMARKET_API_KEY` | API key de Polymarket |
| `POLYMARKET_SECRET` | Secret de la API |
| `POLYMARKET_PASSPHRASE` | Passphrase de la API |
| `PRIVATE_KEY` | Clave privada de tu wallet |
| `DRY_RUN` | `true` para simular (default), `false` para trading real |

## Uso

```bash
# Ejecutar el bot (modo dry-run por defecto)
python bot.py

# Escanear mercados disponibles
python -c "from scanner import MarketScanner; from config import Config; MarketScanner(Config()).scan()"
```

## Estructura del Proyecto

```
├── bot.py          # Motor principal del bot
├── client.py       # Wrapper del cliente Polymarket CLOB
├── config.py       # Configuración desde variables de entorno
├── strategies.py   # Estrategias de trading
├── risk.py         # Gestión de riesgo (stop-loss, position sizing)
├── scanner.py      # Scanner de mercados
├── logger.py       # Configuración de logging
├── requirements.txt
├── .env.example
└── .gitignore
```

## Advertencia

⚠️ **Este bot es para fines educativos.** El trading en mercados de predicción conlleva riesgo de pérdida de capital. Usa siempre el modo `DRY_RUN=true` primero para entender el comportamiento antes de operar con dinero real.
