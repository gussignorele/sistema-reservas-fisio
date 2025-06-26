import json
import os
from werkzeug.security import generate_password_hash

USERS_FILE = "data/users.json"

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def create_admin(username, password):
    users = load_json(USERS_FILE)
    hashed = generate_password_hash(password)
    users[username] = {
        "password": hashed,
        "is_admin": True
    }
    save_json(USERS_FILE, users)
    print(f"Usuario admin '{username}' creado/actualizado correctamente.")

if __name__ == "__main__":
    print("Crear usuario admin (solo usuario y contraseña)")
    username = input("Usuario: ").strip()
    password = input("Contraseña: ").strip()
    create_admin(username, password)
