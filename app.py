from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import subprocess
import zipfile
import psutil
import shutil
from datetime import datetime

app = Flask(__name__)

app.config['SECRET_KEY'] = 'sua_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'uploads'

os.makedirs('uploads', exist_ok=True)
os.makedirs('projetos', exist_ok=True)
os.makedirs('logs', exist_ok=True)


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

processos = {}

# ============================================================
# DATABASE
# ============================================================

class User(UserMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(100), unique=True)

    password = db.Column(db.String(300))

    plano = db.Column(db.String(20), default='free')


class Projeto(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    nome = db.Column(db.String(100))

    dono = db.Column(db.Integer)

    status = db.Column(db.String(20), default='offline')

    pid = db.Column(db.Integer, nullable=True)

    criado = db.Column(db.String(100))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================================================
# HOME
# ============================================================

@app.route('/')
def home():
    return render_template('index.html')

# ============================================================
# REGISTER
# ============================================================

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        username = request.form['username']

        password = generate_password_hash(request.form['password'])

        existe = User.query.filter_by(username=username).first()

        if existe:
            flash('Usuario ja existe')
            return redirect('/register')

        novo = User(
            username=username,
            password=password
        )

        db.session.add(novo)
        db.session.commit()

        flash('Conta criada')

        return redirect('/login')

    return render_template('register.html')

# ============================================================
# LOGIN
# ============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):

            login_user(user)

            return redirect('/dashboard')

        flash('Login invalido')

    return render_template('login.html')

# ============================================================
# LOGOUT
# ============================================================

@app.route('/logout')
@login_required
def logout():

    logout_user()

    return redirect('/')

# ============================================================
# DASHBOARD
# ============================================================

@app.route('/dashboard')
@login_required
def dashboard():

    projetos = Projeto.query.filter_by(
        dono=current_user.id
    ).all()

    return render_template(
        'dashboard.html',
        projetos=projetos
    )

# ============================================================
# UPLOAD
# ============================================================

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():

    if request.method == 'POST':

        arquivo = request.files['file']

        if not arquivo.filename.endswith('.zip'):
            flash('Envie ZIP')
            return redirect('/upload')

        nome = secure_filename(arquivo.filename)

        caminho_zip = os.path.join(
            app.config['UPLOAD_FOLDER'],
            nome
        )

        arquivo.save(caminho_zip)

        pasta_projeto = os.path.join(
            'projetos',
            f'{current_user.id}_{nome.replace(".zip", "")}'
        )

        os.makedirs(pasta_projeto, exist_ok=True)

        with zipfile.ZipFile(caminho_zip, 'r') as zip_ref:
            zip_ref.extractall(pasta_projeto)

        projeto = Projeto(
            nome=nome.replace('.zip', ''),
            dono=current_user.id,
            criado=datetime.now().strftime('%d/%m/%Y %H:%M')
        )

        db.session.add(projeto)
        db.session.commit()

        flash('Projeto enviado')

        return redirect('/dashboard')

    return render_template('upload.html')

# ============================================================
# START BOT
# ============================================================

@app.route('/start/<int:id>')
@login_required
def start_bot(id):

    projeto = Projeto.query.get(id)

    if not projeto:
        return redirect('/dashboard')

    pasta = os.path.join(
        'projetos',
        f'{current_user.id}_{projeto.nome}'
    )

    arquivo = None

    for root, dirs, files in os.walk(pasta):

        for f in files:

            if f in ['bot.py', 'main.py', 'app.py']:
                arquivo = os.path.join(root, f)
                break

    if not arquivo:
        flash('Arquivo principal nao encontrado')
        return redirect('/dashboard')

    log = open(
        f'logs/{projeto.nome}.log',
        'a',
        encoding='utf-8'
    )

    proc = subprocess.Popen(
        ['python', arquivo],
        stdout=log,
        stderr=log
    )

    projeto.pid = proc.pid
    projeto.status = 'online'

    db.session.commit()

    processos[proc.pid] = proc

    flash('Bot iniciado')

    return redirect('/dashboard')

# ============================================================
# STOP BOT
# ============================================================

@app.route('/stop/<int:id>')
@login_required
def stop_bot(id):

    projeto = Projeto.query.get(id)

    if projeto and projeto.pid:

        try:
            p = psutil.Process(projeto.pid)
            p.kill()
        except:
            pass

        projeto.pid = None
        projeto.status = 'offline'

        db.session.commit()

    flash('Bot parado')

    return redirect('/dashboard')

# ============================================================
# LOGS
# ============================================================

@app.route('/logs/<int:id>')
@login_required
def logs(id):

    projeto = Projeto.query.get(id)

    caminho = f'logs/{projeto.nome}.log'

    if not os.path.exists(caminho):
        return 'Sem logs'

    with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
        texto = f.read()

    return f'<pre>{texto[-5000:]}</pre>'

# ============================================================
# ADMIN
# ============================================================

@app.route('/admin')
@login_required
def admin():

    if current_user.id != 1:
        return redirect('/')

    users = User.query.all()
    projetos = Projeto.query.all()

    return render_template(
        'admin.html',
        users=users,
        projetos=projetos
    )

# ============================================================
# START
# ============================================================

if __name__ == '__main__':

    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', port=10000)
