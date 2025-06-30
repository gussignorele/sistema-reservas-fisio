from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os
import json
from filelock import FileLock
from helper import load_json, save_json
import csv
from io import StringIO
from flask import Response
import re
EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")
from helper import generar_token, enviar_mail, verificar_token


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

USERS_FILE = os.path.join(DATA_DIR, "users.json")
AVAIL_FILE = os.path.join(DATA_DIR, "availability.json")
BOOKINGS_FILE = os.path.join(DATA_DIR, "bookings.json")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        ADMIN_CODE = config.get("ADMIN_CODE")
        EMAIL_USER = config.get("EMAIL_USER")
        EMAIL_PASS = config.get("EMAIL_PASS")

except FileNotFoundError:
    ADMIN_CODE = None
    print(f"Advertencia: no se encontró {CONFIG_PATH}, ADMIN_CODE será None")


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or config.get("SECRET_KEY") or "cambiar-en-produccion"

@app.context_processor
def inject_config():
    return dict(ADMIN_CODE=ADMIN_CODE)


login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, username, is_admin=False, first_name=None, last_name=None, email=None, phone=None, categoria=None):
        self.id = username
        self.is_admin = is_admin
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.phone = phone
        self.categoria = categoria


@login_manager.user_loader
def load_user(user_id):
    users = load_json(USERS_FILE)
    if user_id in users:
        u = users[user_id]
        return User(
            user_id,
            is_admin=u.get("is_admin", False),
            first_name=u.get("first_name"),
            last_name=u.get("last_name"),
            email=u.get("email"),
            phone=u.get("phone"),
            categoria=u.get("categoria")
        )
    return None

def obtener_emails_administradores():
    users = load_json(USERS_FILE)
    return [info["email"] for info in users.values() if info.get("is_admin") and info.get("email")]


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        category = request.form.get("category", "").strip()

        if not username or not password or not first_name or not last_name or not phone or not category:
            flash("Los campos obligatorios no pueden estar vacíos", "error")
            return redirect(url_for("register"))

        if not EMAIL_REGEX.match(email):
            flash("El correo ingresado no parece válido", "error")
            return redirect(url_for("register"))

        users = load_json(USERS_FILE)
        if username in users:
            flash("El usuario ya existe", "error")
            return redirect(url_for("register"))

        users[username] = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": phone,
            "email": email,
            "categoria": category,
            "password": generate_password_hash(password),
            "is_admin": False,
            "confirmado": False
        }
        save_json(USERS_FILE, users)
        token = generar_token(email, app.secret_key)
        link = url_for("confirmar_email", token=token, _external=True)
        mensaje = f"""Hola {first_name},

        Gracias por registrarte. Para confirmar tu cuenta, hacé clic en el siguiente enlace:

        {link}

        Este enlace es válido por 1 hora.
        """
        enviar_mail(email, "Confirmá tu registro", mensaje, EMAIL_USER, EMAIL_PASS)
        flash("Registro exitoso. Te enviamos un correo para confirmar tu cuenta.", "info")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        users = load_json(USERS_FILE)
        user_data = users.get(username)
        if user_data and not user_data.get("confirmado", False):
            flash("Tenés que confirmar tu correo antes de iniciar sesión", "warning")
            return redirect(url_for("login"))

        if user_data and check_password_hash(user_data["password"], password):
            user = User(
                username=username,
                is_admin=user_data.get("is_admin", False),
                first_name=user_data.get("first_name"),
                last_name=user_data.get("last_name"),
                email=user_data.get("email"),
                phone=user_data.get("phone"),
                categoria=user_data.get("categoria")
            )
            login_user(user)
            return redirect(url_for("index"))
        else:
            flash("Credenciales inválidas", "error")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/admin/agenda")
@login_required
def admin_agenda():
    if not current_user.is_authenticated or not current_user.is_admin:
        flash("Acceso denegado", "error")
        return redirect(url_for("index"))

    bookings = load_json(BOOKINGS_FILE)
    users = load_json(USERS_FILE)

    full_bookings = {}
    for date, hours in bookings.items():
        full_bookings[date] = {}
        for hour, users_dict in hours.items():
            user_infos = []
            for username, meta in users_dict.items():
                info = users.get(username, {})
                full_name = f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                phone = info.get('phone', 'Sin celular')
                categoria = info.get('categoria', 'Sin categoría')
                pagado = meta.get("pagado", False)
                pagado_checked = "checked" if pagado else ""
                btn = f'''
                    <form method="post" action="{url_for('toggle_paid', date=date, hour=hour, username=username)}" style="display:inline">
                        <input type="checkbox" onChange="this.form.submit()" {pagado_checked}>
                    </form>
                '''
                user_infos.append(
                    f"{full_name} ({phone}) - Categoría: {categoria} - Pagado: {btn}"
                )
            full_bookings[date][hour] = user_infos

    return render_template("admin_agenda.html", bookings=full_bookings)

@app.route("/admin/toggle_paid/<date>/<hour>/<username>", methods=["POST"])
@login_required
def toggle_paid(date, hour, username):
    if not current_user.is_admin:
        flash("Acceso denegado", "error")
        return redirect(url_for("index"))

    bookings = load_json(BOOKINGS_FILE)

    if date in bookings and hour in bookings[date] and username in bookings[date][hour]:
        pagado_actual = bookings[date][hour][username].get("pagado", False)
        bookings[date][hour][username]["pagado"] = not pagado_actual
        save_json(BOOKINGS_FILE, bookings)
        flash(f"Estado de pago actualizado para {username} en {date} {hour}", "success")
    else:
        flash("No se encontró la reserva", "error")

    return redirect(url_for("admin_agenda"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada", "info")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    if not getattr(current_user, "is_admin", False):
        flash("Acceso denegado", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        date_str = request.form.get("date")
        start = request.form.get("start")
        end = request.form.get("end")
        if not date_str or not start or not end:
            flash("Todos los campos son obligatorios", "danger")
            return redirect(url_for("admin"))
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            h_start = datetime.strptime(start, "%H:%M").time()
            h_end = datetime.strptime(end, "%H:%M").time()
            if h_end <= h_start:
                flash("La hora fin debe ser posterior a la hora inicio", "error")
                return redirect(url_for("admin"))
        except ValueError:
            flash("Formato de fecha u hora inválido", "error")
            return redirect(url_for("admin"))
        slots = []
        current = datetime.combine(date_obj, h_start)
        end_dt = datetime.combine(date_obj, h_end)
        while current + timedelta(hours=1) <= end_dt:
            slots.append(current.strftime("%H:%M"))
            current += timedelta(hours=1)
        av = load_json(AVAIL_FILE)
        av[date_str] = slots
        save_json(AVAIL_FILE, av)
        flash(f"Disponibilidad establecida para {date_str}: {', '.join(slots)}", "success")
        return redirect(url_for("admin"))
    av = load_json(AVAIL_FILE)
    dates = sorted(av.keys())
    return render_template("admin.html", availability=av, dates=dates)

@app.route("/availability", methods=["GET", "POST"])
@login_required
def availability():
    av = load_json(AVAIL_FILE)
    if request.method == "POST":
        date_str = request.form.get("date")
        hour = request.form.get("hour")
        if not date_str or not hour:
            flash("Seleccione fecha y hora", "error")
            return redirect(url_for("availability"))
        if date_str not in av or hour not in av[date_str]:
            flash("Slot no disponible", "error")
            return redirect(url_for("availability"))

        bookings = load_json(BOOKINGS_FILE)

        # --- Control: impedir múltiples reservas futuras ---
        now = datetime.now()
        for d, hs in bookings.items():
            for h, us in hs.items():
                if current_user.id in us:
                    try:
                        dt = datetime.strptime(f"{d} {h}", "%Y-%m-%d %H:%M")
                        if dt > now:
                            flash("Ya tenés una reserva activa a futuro. Solo se permite una.", "error")
                            return redirect(url_for("availability"))
                    except ValueError:
                        continue  # en caso de error de formato, ignorar

        day_bookings = bookings.get(date_str, {})
        users_dict = day_bookings.get(hour, {})

        if current_user.id in users_dict:
            flash("Ya reservaste ese turno", "error")
            return redirect(url_for("availability"))

        if len(users_dict) >= 2:
            flash("Ese slot ya está completo", "error")
            return redirect(url_for("availability"))

        users_dict[current_user.id] = {"pagado": False}
        day_bookings[hour] = users_dict
        bookings[date_str] = day_bookings
        save_json(BOOKINGS_FILE, bookings)
        flash(f"Turno reservado: {date_str} {hour}", "success")
        admin_emails = obtener_emails_administradores()
        usuario = f"{current_user.first_name} {current_user.last_name}"
        msg = f"{usuario} ha reservado un turno para el {date_str} a las {hour}."
        for email in admin_emails:
            enviar_mail(email, "Nueva reserva registrada", msg, EMAIL_USER, EMAIL_PASS)
        return redirect(url_for("my_bookings"))

    bookings = load_json(BOOKINGS_FILE)
    avail_display = {}
    for date_str, slots in av.items():
        free_hours = []
        for hour in slots:
            booked = bookings.get(date_str, {}).get(hour, {})
            if len(booked) < 2:
                free_hours.append(hour)
        if free_hours:
            avail_display[date_str] = free_hours
    dates = sorted(avail_display.keys())
    return render_template("view_availability.html", availability=avail_display, dates=dates)


@app.route("/my_bookings")
@login_required
def my_bookings():
    bookings = load_json(BOOKINGS_FILE)
    my = []
    for date_str, hours_map in bookings.items():
        for hour, users_map in hours_map.items():
            if current_user.id in users_map:
                pagado = users_map[current_user.id].get("pagado", False)
                my.append((date_str, hour, pagado))
    my_sorted = sorted(my, key=lambda x: (x[0], x[1]))
    return render_template("my_bookings.html", bookings=my_sorted)

@app.route("/cancel/<date_str>/<hour>", methods=["POST"])
@login_required
def cancel(date_str, hour):
    bookings = load_json(BOOKINGS_FILE)
    day_bookings = bookings.get(date_str, {})
    users_dict = day_bookings.get(hour, {})
    if current_user.id in users_dict:
        users_dict.pop(current_user.id)
        if users_dict:
            day_bookings[hour] = users_dict
        else:
            day_bookings.pop(hour, None)
        if day_bookings:
            bookings[date_str] = day_bookings
        else:
            bookings.pop(date_str, None)
        save_json(BOOKINGS_FILE, bookings)
        flash(f"Reserva cancelada: {date_str} {hour}", "info")
        admin_emails = obtener_emails_administradores()
        usuario = f"{current_user.first_name} {current_user.last_name}"
        msg = f"{usuario} ha cancelado un turno para el {date_str} a las {hour}."
        for email in admin_emails:
            enviar_mail(email, "Cancelación registrada", msg, EMAIL_USER, EMAIL_PASS)
    else:
        flash("No tienes esa reserva", "error")
    return redirect(url_for("my_bookings"))

@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    users = load_json(USERS_FILE)
    user_data = users.get(current_user.id, {})

    if request.method == "POST":
        nombre = request.form.get("first_name", "").strip()
        apellido = request.form.get("last_name", "").strip()
        celular = request.form.get("phone", "").strip()
        direccion = request.form.get("direccion", "").strip()
        email = request.form.get("email", "").strip()
        categoria = request.form.get("categoria", "").strip()

        if not nombre or not apellido or not celular or not categoria:
            flash("Nombre, apellido, celular y categoría son obligatorios", "danger")
            return redirect(url_for("perfil"))

        user_data.update({
            "first_name": nombre,
            "last_name": apellido,
            "phone": celular,
            "direccion": direccion,
            "email": email,
            "categoria": categoria
        })
        users[current_user.id] = user_data
        save_json(USERS_FILE, users)
        flash("Datos actualizados correctamente", "success")
        return redirect(url_for("perfil"))

    return render_template("perfil.html", user=user_data)


@app.route("/admin/historial", methods=["GET", "POST"])
@login_required
def admin_historial():
    if not current_user.is_admin:
        flash("Acceso denegado", "error")
        return redirect(url_for("index"))

    bookings = load_json(BOOKINGS_FILE)
    users = load_json(USERS_FILE)

    filtro = request.form.get("filtro")
    fecha = request.form.get("fecha")
    resultados = []

    def agregar_resultado(fecha_str, hora, username, meta):
        user = users.get(username, {})
        nombre = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        telefono = user.get('phone', 'Sin celular')
        categoria = user.get('categoria', 'Sin categoría')
        pagado = "Sí" if meta.get("pagado") else "No"
        resultados.append((fecha_str, hora, nombre, telefono, categoria, pagado))

    for date_str, horas in bookings.items():
        for hora, usuarios in horas.items():
            for username, meta in usuarios.items():
                try:
                    dt = datetime.strptime(f"{date_str} {hora}", "%Y-%m-%d %H:%M")
                except ValueError:
                    continue

                if filtro == "dia" and fecha:
                    if date_str == fecha:
                        agregar_resultado(date_str, hora, username, meta)

                elif filtro == "semana" and fecha:
                    try:
                        inicio_semana = datetime.strptime(fecha, "%Y-%m-%d") - timedelta(days=datetime.strptime(fecha, "%Y-%m-%d").weekday())
                        fin_semana = inicio_semana + timedelta(days=6)
                        if inicio_semana.date() <= dt.date() <= fin_semana.date():
                            agregar_resultado(date_str, hora, username, meta)
                    except ValueError:
                        continue

                elif filtro == "mes" and fecha:
                    if dt.strftime("%Y-%m") == fecha:
                        agregar_resultado(date_str, hora, username, meta)

                elif not filtro:
                    agregar_resultado(date_str, hora, username, meta)

    resultados.sort(key=lambda x: (x[0], x[1]))  # ordenar por fecha y hora
    return render_template("admin_historial.html", resultados=resultados, filtro=filtro, fecha=fecha)

@app.route("/admin/historial/export", methods=["POST"])
@login_required
def export_historial_csv():
    if not current_user.is_admin:
        flash("Acceso denegado", "error")
        return redirect(url_for("index"))

    filtro = request.form.get("filtro")
    fecha = request.form.get("fecha")

    bookings = load_json(BOOKINGS_FILE)
    users = load_json(USERS_FILE)

    filas = [("Fecha", "Hora", "Usuario", "Teléfono", "Categoría", "Pagado")]

    def agregar_fila(date_str, hour, username, meta):
        user = users.get(username, {})
        nombre = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
        telefono = user.get('phone', 'Sin celular')
        categoria = user.get('categoria', 'Sin categoría')
        pagado = "Sí" if meta.get("pagado") else "No"
        filas.append((date_str, hour, nombre, telefono, categoria, pagado))

    for date_str, horas in bookings.items():
        for hora, usuarios in horas.items():
            for username, meta in usuarios.items():
                try:
                    dt = datetime.strptime(f"{date_str} {hora}", "%Y-%m-%d %H:%M")
                except ValueError:
                    continue

                if filtro == "dia" and fecha:
                    if date_str == fecha:
                        agregar_fila(date_str, hora, username, meta)

                elif filtro == "semana" and fecha:
                    try:
                        inicio = datetime.strptime(fecha, "%Y-%m-%d") - timedelta(days=datetime.strptime(fecha, "%Y-%m-%d").weekday())
                        fin = inicio + timedelta(days=6)
                        if inicio.date() <= dt.date() <= fin.date():
                            agregar_fila(date_str, hora, username, meta)
                    except ValueError:
                        continue

                elif filtro == "mes" and fecha:
                    if dt.strftime("%Y-%m") == fecha:
                        agregar_fila(date_str, hora, username, meta)

                elif not filtro:
                    agregar_fila(date_str, hora, username, meta)

    # Crear CSV
    si = StringIO()
    cw = csv.writer(si)
    cw.writerows(filas)

    output = si.getvalue()
    si.close()

    filename = f"historial_reservas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.route("/confirmar/<token>")
def confirmar_email(token):
    email = verificar_token(token, app.secret_key)
    if not email:
        flash("Enlace inválido o expirado", "danger")
        return redirect(url_for("login"))

    users = load_json(USERS_FILE)
    actualizado = False
    for username, data in users.items():
        if data.get("email") == email:
            if data.get("confirmado"):
                flash("La cuenta ya estaba confirmada", "info")
            else:
                data["confirmado"] = True
                users[username] = data
                save_json(USERS_FILE, users)
                flash("Cuenta confirmada. Ahora podés iniciar sesión.", "success")
            actualizado = True
            break

    if not actualizado:
        flash("No se encontró el usuario", "danger")
    return redirect(url_for("login"))



@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        users = load_json(USERS_FILE)
        for username, data in users.items():
            if data.get("email") == email:
                token = generar_token(email, app.secret_key)
                link = url_for("nuevo_password", token=token, _external=True)
                mensaje = f"""Hola,

Se solicitó un restablecimiento de contraseña para tu cuenta.

Para crear una nueva contraseña, hacé clic en el siguiente enlace:

{link}

Este enlace vence en 1 hora.
Si no solicitaste este cambio, ignorá este mensaje.
"""
                enviar_mail(email, "Restablecer contraseña", mensaje, EMAIL_USER, EMAIL_PASS)
                flash("Si el correo está registrado, se envió un enlace para restablecer la contraseña.", "info")
                return redirect(url_for("login"))
        flash("Si el correo está registrado, se envió un enlace para restablecer la contraseña.", "info")
        return redirect(url_for("login"))
    return render_template("reset_password.html")


@app.route("/nuevo_password/<token>", methods=["GET", "POST"])
def nuevo_password(token):
    email = verificar_token(token, app.secret_key)
    if not email:
        flash("El enlace es inválido o expiró", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password")
        if not password:
            flash("La contraseña no puede estar vacía", "error")
            return redirect(request.url)

        users = load_json(USERS_FILE)
        for username, data in users.items():
            if data.get("email") == email:
                data["password"] = generate_password_hash(password)
                users[username] = data
                save_json(USERS_FILE, users)
                flash("Contraseña actualizada correctamente. Ahora podés iniciar sesión.", "success")
                return redirect(url_for("login"))
        flash("No se encontró el usuario asociado al correo", "error")
        return redirect(url_for("login"))

    return render_template("nuevo_password.html")
"""
if __name__ == "__main__":
    app.run(debug=True)
"""


# /admin/ver_json/users
#
# /admin/ver_json/bookings
@app.route("/admin/ver_json/<archivo>")
@login_required
def ver_json(archivo):
    if not current_user.is_admin:
        abort(403)

    nombre_archivo = f"{archivo}.json"

    try:
        datos = load_json(nombre_archivo)
        return render_template("ver_json.html", archivo=archivo, datos=datos)
    except FileNotFoundError:
        flash(f"Archivo {nombre_archivo} no encontrado", "error")
        return redirect(url_for("admin"))
    except Exception as e:
        return f"Error al leer {nombre_archivo}: {e}", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))