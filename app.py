from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key-12345-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB максимум

# Инициализация базы данных
db = SQLAlchemy(app)


# Модели базы данных
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<User {self.username}>'


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_name = db.Column(db.String(100))
    teacher_contacts = db.Column(db.Text)
    order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Subject {self.name}>'


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    material_type = db.Column(db.String(20), nullable=False)  # lectures, practices, tasks, other
    file_path = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связь
    subject = db.relationship('Subject', backref=db.backref('materials', lazy=True))

    def __repr__(self):
        return f'<Material {self.title}>'


class News(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Связь
    subject = db.relationship('Subject', backref=db.backref('news', lazy=True))

    def __repr__(self):
        return f'<News {self.title}>'


# Создаем папки
os.makedirs('templates', exist_ok=True)
os.makedirs('templates/admin', exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Создаем базу данных (БЕЗ тестовых данных)
with app.app_context():
    db.create_all()

    # Создаем администратора, если его нет
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            is_admin=True
        )
        db.session.add(admin)
        print("Создан администратор: admin / admin123")

    # Создаем тестового пользователя (опционально)
    if not User.query.filter_by(username='student').first():
        student = User(
            username='student',
            password=generate_password_hash('student123'),
            is_admin=False
        )
        db.session.add(student)
        print("Создан студент: student / student123")

    db.session.commit()
    print("База данных инициализирована!")
    print("Сайт пустой - добавьте предметы через админ-панель")


# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите в систему', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# Декоратор для проверки админских прав
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = db.session.get(User, session['user_id'])
        if not user or not user.is_admin:
            flash('Требуются права администратора', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


# Функция для получения текущего пользователя (для шаблонов)
@app.context_processor
def inject_user():
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        if user:
            return {'current_user': user}
    return {'current_user': None}


# Главная страница
@app.route('/')
@login_required
def index():
    subjects = Subject.query.order_by(Subject.order).all()
    news = News.query.order_by(News.created_at.desc()).limit(10).all()
    return render_template('index.html', subjects=subjects, news=news)


# Страница входа
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')

    return render_template('login.html')


# Выход из системы
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


# Страница предмета (ВЕСЬ ЭКРАН)
@app.route('/subject/<int:subject_id>')
@login_required
def subject(subject_id):
    subject = db.session.get(Subject, subject_id)
    if not subject:
        flash('Предмет не найден', 'danger')
        return redirect(url_for('index'))

    # Получаем материалы по типам
    lectures = Material.query.filter_by(subject_id=subject_id, material_type='lectures').order_by(
        Material.created_at.desc()).all()
    practices = Material.query.filter_by(subject_id=subject_id, material_type='practices').order_by(
        Material.created_at.desc()).all()
    tasks = Material.query.filter_by(subject_id=subject_id, material_type='tasks').order_by(
        Material.created_at.desc()).all()
    other = Material.query.filter_by(subject_id=subject_id, material_type='other').order_by(
        Material.created_at.desc()).all()

    return render_template('subject.html',
                           subject=subject,
                           lectures=lectures,
                           practices=practices,
                           tasks=tasks,
                           other=other)


# Страница материала (ВЕСЬ ЭКРАН)
@app.route('/material/<int:material_id>')
@login_required
def material(material_id):
    material = db.session.get(Material, material_id)
    if not material:
        flash('Материал не найден', 'danger')
        return redirect(url_for('index'))

    return render_template('material.html', material=material)


# АДМИН-ПАНЕЛЬ

# Главная страница админ-панели
@app.route('/admin')
@admin_required
def admin_dashboard():
    subjects = Subject.query.order_by(Subject.order).all()
    return render_template('admin/dashboard.html', subjects=subjects)


# Добавление предмета
@app.route('/admin/subject/add', methods=['POST'])
@admin_required
def add_subject():
    try:
        name = request.form['name']
        teacher_name = request.form['teacher_name']
        teacher_contacts = request.form['teacher_contacts']

        # Определяем порядок
        last_subject = Subject.query.order_by(Subject.order.desc()).first()
        order = (last_subject.order + 1) if last_subject else 0

        subject = Subject(
            name=name,
            teacher_name=teacher_name,
            teacher_contacts=teacher_contacts,
            order=order
        )

        db.session.add(subject)
        db.session.commit()

        flash(f'Предмет "{name}" успешно добавлен', 'success')
    except Exception as e:
        flash(f'Ошибка при добавлении предмета: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))


# Редактирование предмета
@app.route('/admin/subject/<int:subject_id>/edit', methods=['POST'])
@admin_required
def edit_subject(subject_id):
    try:
        subject = db.session.get(Subject, subject_id)
        if not subject:
            flash('Предмет не найден', 'danger')
            return redirect(url_for('admin_dashboard'))

        subject.name = request.form['name']
        subject.teacher_name = request.form['teacher_name']
        subject.teacher_contacts = request.form['teacher_contacts']

        db.session.commit()
        flash('Изменения сохранены', 'success')
    except Exception as e:
        flash(f'Ошибка при сохранении: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))


# Удаление предмета
@app.route('/admin/subject/<int:subject_id>/delete')
@admin_required
def delete_subject(subject_id):
    try:
        subject = db.session.get(Subject, subject_id)
        if not subject:
            flash('Предмет не найден', 'danger')
            return redirect(url_for('admin_dashboard'))

        # Удаляем все материалы предмета
        Material.query.filter_by(subject_id=subject_id).delete()
        # Удаляем все новости предмета
        News.query.filter_by(subject_id=subject_id).delete()
        # Удаляем предмет
        db.session.delete(subject)

        db.session.commit()
        flash('Предмет и все связанные материалы удалены', 'success')
    except Exception as e:
        flash(f'Ошибка при удалении: {str(e)}', 'danger')

    return redirect(url_for('admin_dashboard'))


# Добавление новости
@app.route('/admin/news/add', methods=['POST'])
@admin_required
def add_news():
    try:
        subject_id = request.form['subject_id']
        title = request.form['title']
        content = request.form['content']

        # Проверяем существование предмета
        subject = db.session.get(Subject, subject_id)
        if not subject:
            flash('Предмет не найден', 'danger')
            return redirect(url_for('index'))

        news = News(
            subject_id=subject_id,
            title=title,
            content=content
        )

        db.session.add(news)
        db.session.commit()

        flash('Новость добавлена', 'success')
    except Exception as e:
        flash(f'Ошибка при добавлении новости: {str(e)}', 'danger')

    return redirect(url_for('index'))


# Удаление новости
@app.route('/admin/news/<int:news_id>/delete')
@admin_required
def delete_news(news_id):
    try:
        news = db.session.get(News, news_id)
        if not news:
            flash('Новость не найдена', 'danger')
            return redirect(url_for('index'))

        db.session.delete(news)
        db.session.commit()

        flash('Новость удалена', 'success')
    except Exception as e:
        flash(f'Ошибка при удалении новости: {str(e)}', 'danger')

    return redirect(url_for('index'))


# Добавление материала
@app.route('/admin/material/add', methods=['POST'])
@admin_required
def add_material():
    try:
        subject_id = request.form['subject_id']
        title = request.form['title']
        content = request.form['content']
        material_type = request.form['material_type']

        # Проверяем существование предмета
        subject = db.session.get(Subject, subject_id)
        if not subject:
            flash('Предмет не найден', 'danger')
            return redirect(url_for('index'))

        material = Material(
            subject_id=subject_id,
            title=title,
            content=content,
            material_type=material_type
        )

        # Обработка загрузки файла
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                # Проверяем расширение файла
                allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'txt', 'pptx', 'zip'}
                filename = secure_filename(file.filename)
                if '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                    # Сохраняем файл
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    unique_filename = f"{subject_id}_{material_type}_{timestamp}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    material.file_path = unique_filename
                else:
                    flash('Недопустимый формат файла', 'warning')

        db.session.add(material)
        db.session.commit()

        flash('Материал добавлен', 'success')
    except Exception as e:
        flash(f'Ошибка при добавлении материала: {str(e)}', 'danger')

    return redirect(url_for('subject', subject_id=subject_id))


# Удаление материала
@app.route('/admin/material/<int:material_id>/delete')
@admin_required
def delete_material(material_id):
    try:
        material = db.session.get(Material, material_id)
        if not material:
            flash('Материал не найден', 'danger')
            return redirect(url_for('index'))

        subject_id = material.subject_id
        db.session.delete(material)
        db.session.commit()

        flash('Материал удален', 'success')
        return redirect(url_for('subject', subject_id=subject_id))
    except Exception as e:
        flash(f'Ошибка при удалении: {str(e)}', 'danger')
        return redirect(url_for('index'))


# Скачивание файла
@app.route('/uploads/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


# Регистрация нового пользователя
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Проверки
        if password != confirm_password:
            flash('Пароли не совпадают', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует', 'danger')
            return redirect(url_for('register'))

        # Создаем пользователя
        user = User(
            username=username,
            password=generate_password_hash(password),
            is_admin=False  # По умолчанию не админ
        )

        db.session.add(user)
        db.session.commit()

        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# Запуск приложения
if __name__ == '__main__':
    print("=" * 50)
    print("Учебный портал запущен!")
    print("Адрес: http://localhost:5000")
    print("Админ: admin / admin123")
    print("Студент: student / student123")
    print("Сайт пустой - создавайте предметы через админ-панель")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)