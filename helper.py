from filelock import FileLock
import json
import smtplib
from email.mime.text import MIMEText
from itsdangerous import URLSafeTimedSerializer


def enviar_mail(destinatario, asunto, cuerpo, remitente, password):
    msg = MIMEText(cuerpo)
    msg['Subject'] = asunto
    msg['From'] = remitente
    msg['To'] = destinatario

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(remitente, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Error al enviar correo:", e)
        return False

def generar_token(email, secret_key):
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps(email)

def verificar_token(token, secret_key, max_age=3600):
    s = URLSafeTimedSerializer(secret_key)
    try:
        email = s.loads(token, max_age=max_age)
        return email
    except Exception:
        return None


def load_json(path):
    lock = FileLock(f"{path}.lock")
    with lock:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

def save_json(path, data):
    lock = FileLock(f"{path}.lock")
    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
