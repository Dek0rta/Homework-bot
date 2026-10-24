import json
import os

from dotenv import load_dotenv

load_dotenv()  # на Replit ничего не делает — там секреты уже в env

BOT_TOKEN       = os.getenv("BOT_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ADMIN_USER_ID   = int(os.getenv("ADMIN_USER_ID", 0))
TIMEZONE        = os.getenv("TIMEZONE", "Europe/Moscow")

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Языковые модели ──────────────────────────────────────────────────────────
# Порядок провайдеров: первый — основной, остальные подхватывают при его сбое.
# Провайдер без ключа пропускается.
LLM_PROVIDERS = [
    p.strip().lower()
    for p in os.getenv("LLM_PROVIDERS", "gigachat,mistral").split(",")
    if p.strip()
]

# GigaChat: ключ авторизации из личного кабинета developers.sber.ru
GIGACHAT_CREDENTIALS  = os.getenv("GIGACHAT_CREDENTIALS")
GIGACHAT_SCOPE        = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_MODEL        = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max")      # личные ДЗ, расписание
GIGACHAT_FAST_MODEL   = os.getenv("GIGACHAT_FAST_MODEL", "GigaChat-2")     # переписка чата, только текст
GIGACHAT_VISION_MODEL = os.getenv("GIGACHAT_VISION_MODEL", "GigaChat-2-Pro")  # фото из чата класса
# Сертификаты Сбера выпущены НУЦ Минцифры — в стандартном наборе их нет
GIGACHAT_CA_BUNDLE    = os.getenv(
    "GIGACHAT_CA_BUNDLE",
    os.path.join(_ROOT_DIR, "certs", "russian_trusted_root_ca.pem"),
)

# Mistral: запасной провайдер. На бесплатном тарифе доступны только ministral-*
MISTRAL_MODEL      = os.getenv("MISTRAL_MODEL", "ministral-14b-latest")
MISTRAL_FAST_MODEL = os.getenv("MISTRAL_FAST_MODEL", MISTRAL_MODEL)

# Календарь выбирается на пользователя и хранится в user_calendar_tokens.
# TOKEN_PATH ниже остаётся только ради миграции старого общего токена.

# Директория для хранения данных.
# Приоритет: 1) env var DATA_DIR  2) автодетект /data (Railway Volume)  3) локальная ./data/
def _detect_data_dir() -> str:
    if explicit := os.getenv("DATA_DIR"):
        return explicit
    # Railway Volume автоматически монтируется в /data — используем без env var
    if os.path.isdir("/data") and os.access("/data", os.W_OK):
        return "/data"
    return "data"

_DATA_DIR = _detect_data_dir()

DB_PATH          = os.path.join(_DATA_DIR, "homework.db")
TOKEN_PATH       = os.path.join(_DATA_DIR, "token.json")
CREDENTIALS_PATH = os.path.join(_DATA_DIR, "credentials.json")
FSM_PATH         = os.path.join(_DATA_DIR, "fsm.json")

WEB_APP_URL      = os.getenv("WEB_APP_URL", "")

# Railway/Replit: credentials.json и token.json можно передать через переменные окружения
_creds_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
if _creds_env and not os.path.exists(CREDENTIALS_PATH):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as _f:
        _f.write(_creds_env if _creds_env.strip().startswith("{") else json.dumps(json.loads(_creds_env)))

_token_env = os.getenv("GOOGLE_TOKEN_JSON")
if _token_env and not os.path.exists(TOKEN_PATH):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as _f:
        _f.write(_token_env if _token_env.strip().startswith("{") else json.dumps(json.loads(_token_env)))
