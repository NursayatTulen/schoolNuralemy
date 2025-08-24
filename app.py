from flask import Flask, request, redirect, url_for, render_template, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import json
import random
import string
from datetime import datetime
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://schoolnuralemy_db_user:n9aonkgpphoHs1EeRWHx8etZ1mItwCHD@dpg-d2lgjdbipnbc7387bbgg-a/schoolnuralemy_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    is_open = db.Column(db.Boolean, default=False)
    access_code = db.Column(db.String(6))
    opened_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    questions = db.relationship('Question', backref='test', lazy=True, cascade="all, delete-orphan")
    results = db.relationship('Result', backref='test', lazy=True, cascade="all, delete-orphan")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), default='checkbox')
    options = db.Column(db.Text, default='[]')
    match_pairs = db.Column(db.Text, default='{}')
    correct = db.Column(db.Text, default='[]')
    image = db.Column(db.String(200))

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_name = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Integer)
    percentage = db.Column(db.Float)
    answers = db.Column(db.Text)

with app.app_context():
    db.create_all()

USERNAME = 'nuralemy'
PASSWORD = '123456'

def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return base64.b64encode(img_io.getvalue()).decode('utf-8')

@app.route('/', methods=['GET', 'POST'])
def index():
    if session.get('logged_in'):
        tests = Test.query.all()
        return render_template('dashboard.html', tests=tests)
    else:
        if request.method == 'POST' and 'username' in request.form:
            if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
                session['logged_in'] = True
                return redirect(url_for('index'))
            else:
                flash('Қате логин немесе пароль')
        return render_template('student.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/take_test', methods=['POST'])
def take_test():
    code = request.form.get('code')
    name = request.form.get('name')
    if not code or not name:
        flash('Қате код немесе аты-жөніңізді енгізіңіз')
        return redirect(url_for('index'))
    test = Test.query.filter_by(access_code=code, is_open=True).first()
    if test:
        for q in test.questions:
            if q.question_type == 'checkbox':
                q.options = json.loads(q.options or '[]')
            elif q.question_type == 'matching':
                q.match_pairs = json.loads(q.match_pairs or '{}')
                right_items = list(q.match_pairs.values())
                random.shuffle(right_items)
                q.right_items = right_items
                q.left_items = list(q.match_pairs.keys())
        session['test_id'] = test.id
        session['student_name'] = name
        session.pop('warning_shown', None)
        return render_template('take_test.html', test=test, student_name=name)
    else:
        flash('Қате код немесе тест қолжетімді емес')
        return redirect(url_for('index'))

@app.route('/warn_user', methods=['POST'])
def warn_user():
    if not session.get('warning_shown'):
        session['warning_shown'] = True
        return jsonify({'status': 'warned', 'message': 'Сайттан шықпаңыз! Қайта кіргенде тест басынан басталады.'})
    return jsonify({'status': 'already_warned'})

@app.route('/submit_test', methods=['POST'])
def submit_test():
    test_id = request.form.get('test_id')
    student_name = request.form.get('student_name')
    if not test_id or not student_name:
        flash('Тест ID немесе аты-жөніңіз жоқ')
        return redirect(url_for('index'))
    test_id = int(test_id)
    test = Test.query.get(test_id)
    if not test or not test.is_open:
        flash('Тест қолжетімді емес')
        return redirect(url_for('index'))
    
    questions = test.questions
    answers = {}
    score = 0
    for q in questions:
        if q.question_type == 'checkbox':
            selected = [int(x) for x in request.form.getlist(f'q{q.id}[]')]
            correct_list = json.loads(q.correct or '[]')
            if set(selected) == set(correct_list):
                score += 1
            answers[q.id] = selected
        elif q.question_type == 'matching':
            matched = {}
            for key in json.loads(q.match_pairs or '{}').keys():
                matched[key] = request.form.get(f'q{q.id}_{key}')
            correct_pairs = json.loads(q.match_pairs or '{}')
            if matched == correct_pairs:
                score += 1
            answers[q.id] = matched
    
    total_questions = len(questions)
    percentage = (score / total_questions * 100) if total_questions > 0 else 0
    result = Result(test_id=test_id, student_name=student_name, score=score, percentage=percentage, answers=json.dumps(answers))
    db.session.add(result)
    db.session.commit()
    
    session.pop('test_id', None)
    session.pop('student_name', None)
    session.pop('warning_shown', None)
    
    return render_template('result.html', test=test, score=score, total_questions=total_questions, percentage=percentage, student_name=student_name)

@app.route('/teacher/create', methods=['GET', 'POST'])
def create_test():
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Тест атауын енгізіңіз')
            return redirect(url_for('create_test'))
        test = Test(name=name)
        db.session.add(test)
        db.session.commit()
        return redirect(url_for('edit_test', id=test.id))
    return render_template('create_test.html')

@app.route('/teacher/edit/<int:id>', methods=['GET', 'POST'])
def edit_test(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name')
        if not name:
            flash('Тест атауын енгізіңіз')
            return redirect(url_for('edit_test', id=id))
        test.name = name
        db.session.commit()
        return redirect(url_for('edit_test', id=id))
    return render_template('edit_test.html', test=test)

@app.route('/teacher/add_question/<int:test_id>', methods=['GET', 'POST'])
def add_question(test_id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(test_id)
    json_questions = None

    if request.method == 'POST':
        # JSON текстін өңдеу
        json_text = request.form.get('json_text')
        if json_text:
            try:
                json_data = json.loads(json_text)
                if not isinstance(json_data, list):
                    flash('JSON массиві болуы керек')
                    return redirect(url_for('add_question', test_id=test_id))
                json_questions = json_data  # JSON сұрақтарын шаблонға жіберу
                for q in json_data:
                    text = q.get('text')
                    question_type = q.get('question_type')
                    if not text or not question_type:
                        flash('JSON-да сұрақ мәтіні немесе түрі жоқ')
                        return redirect(url_for('add_question', test_id=test_id))
                    
                    image = None
                    if 'image' in request.files and request.files['image'].filename:
                        file = request.files['image']
                        filename = secure_filename(file.filename)
                        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                        image = filename

                    if question_type == 'checkbox':
                        options = q.get('options', [])
                        correct = q.get('correct', [])
                        if not options or not correct:
                            flash('JSON-да нұсқалар немесе дұрыс жауаптар жоқ')
                            return redirect(url_for('add_question', test_id=test_id))
                        question = Question(
                            test_id=test_id,
                            text=text,
                            question_type='checkbox',
                            options=json.dumps(options),
                            correct=json.dumps(correct),
                            image=image
                        )
                    elif question_type == 'matching':
                        match_pairs = q.get('match_pairs', {})
                        if not match_pairs:
                            flash('JSON-да сәйкестендіру жұптары жоқ')
                            return redirect(url_for('add_question', test_id=test_id))
                        question = Question(
                            test_id=test_id,
                            text=text,
                            question_type='matching',
                            match_pairs=json.dumps(match_pairs),
                            correct=json.dumps(match_pairs),
                            image=image
                        )
                    else:
                        flash('Қате сұрақ түрі JSON-да')
                        return redirect(url_for('add_question', test_id=test_id))
                    
                    db.session.add(question)
                db.session.commit()
                flash('JSON-дан сұрақтар сәтті қосылды')
                return redirect(url_for('edit_test', id=test_id))
            except json.JSONDecodeError:
                flash('Қате JSON форматы')
                return redirect(url_for('add_question', test_id=test_id))

        # JSON файлын өңдеу
        if 'json_file' in request.files and request.files['json_file'].filename:
            json_file = request.files['json_file']
            if json_file and json_file.filename.endswith('.json'):
                try:
                    json_data = json.load(json_file)
                    json_questions = json_data
                    for q in json_data:
                        text = q.get('text')
                        question_type = q.get('question_type')
                        if not text or not question_type:
                            flash('JSON файлында сұрақ мәтіні немесе түрі жоқ')
                            return redirect(url_for('add_question', test_id=test_id))
                        
                        image = None
                        if 'image' in request.files and request.files['image'].filename:
                            file = request.files['image']
                            filename = secure_filename(file.filename)
                            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                            image = filename

                        if question_type == 'checkbox':
                            options = q.get('options', [])
                            correct = q.get('correct', [])
                            if not options or not correct:
                                flash('JSON файлында нұсқалар немесе дұрыс жауаптар жоқ')
                                return redirect(url_for('add_question', test_id=test_id))
                            question = Question(
                                test_id=test_id,
                                text=text,
                                question_type='checkbox',
                                options=json.dumps(options),
                                correct=json.dumps(correct),
                                image=image
                            )
                        elif question_type == 'matching':
                            match_pairs = q.get('match_pairs', {})
                            if not match_pairs:
                                flash('JSON файлында сәйкестендіру жұптары жоқ')
                                return redirect(url_for('add_question', test_id=test_id))
                            question = Question(
                                test_id=test_id,
                                text=text,
                                question_type='matching',
                                match_pairs=json.dumps(match_pairs),
                                correct=json.dumps(match_pairs),
                                image=image
                            )
                        else:
                            flash('Қате сұрақ түрі JSON файлында')
                            return redirect(url_for('add_question', test_id=test_id))
                        
                        db.session.add(question)
                    db.session.commit()
                    flash('JSON файлынан сұрақтар сәтті қосылды')
                    return redirect(url_for('edit_test', id=test_id))
                except json.JSONDecodeError:
                    flash('Қате JSON форматы')
                    return redirect(url_for('add_question', test_id=test_id))
            else:
                flash('JSON файлы болуы керек')
                return redirect(url_for('add_question', test_id=test_id))
        
        # Қолмен сұрақ қосу
        text = request.form.get('text')
        question_type = request.form.get('question_type')
        if not text or not question_type:
            flash('Сұрақ мәтінін немесе түрін енгізіңіз')
            return redirect(url_for('add_question', test_id=test_id))
        image = None
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename
        if question_type == 'checkbox':
            options = request.form.getlist('option[]')
            correct = [int(i) for i in request.form.getlist('correct[]') if i]
            if not options or not correct:
                flash('Нұсқалар немесе дұрыс жауаптар енгізіңіз')
                return redirect(url_for('add_question', test_id=test_id))
            question = Question(
                test_id=test_id,
                text=text,
                question_type='checkbox',
                options=json.dumps(options),
                correct=json.dumps(correct),
                image=image
            )
        elif question_type == 'matching':
            match_left = request.form.getlist('match_left[]')
            match_right = request.form.getlist('match_right[]')
            if not match_left or not match_right:
                flash('Сәйкестендіру жұптарын енгізіңіз')
                return redirect(url_for('add_question', test_id=test_id))
            match_pairs = dict(zip(match_left, match_right))
            question = Question(
                test_id=test_id,
                text=text,
                question_type='matching',
                match_pairs=json.dumps(match_pairs),
                correct=json.dumps(match_pairs),
                image=image
            )
        else:
            flash('Қате сұрақ түрі')
            return redirect(url_for('add_question', test_id=test_id))
        
        db.session.add(question)
        db.session.commit()
        flash('Сұрақ сәтті қосылды')
        return redirect(url_for('edit_test', id=test_id))
    
    return render_template('add_question.html', test_id=test_id, json_questions=json_questions)

@app.route('/teacher/edit_question/<int:q_id>', methods=['GET', 'POST'])
def edit_question(q_id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    question = Question.query.get_or_404(q_id)
    if request.method == 'POST':
        text = request.form.get('text')
        question_type = request.form.get('question_type')
        if not text or not question_type:
            flash('Сұрақ мәтінін немесе түрін енгізіңіз')
            return redirect(url_for('edit_question', q_id=q_id))
        question.text = text
        question.question_type = question_type
        if 'image' in request.files:
            file = request.files['image']
            if file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                question.image = filename
        if question_type == 'checkbox':
            options = request.form.getlist('option[]')
            correct = [int(i) for i in request.form.getlist('correct[]') if i]
            if not options or not correct:
                flash('Нұсқалар немесе дұрыс жауаптар енгізіңіз')
                return redirect(url_for('edit_question', q_id=q_id))
            question.options = json.dumps(options)
            question.correct = json.dumps(correct)
            question.match_pairs = None
        elif question_type == 'matching':
            match_left = request.form.getlist('match_left[]')
            match_right = request.form.getlist('match_right[]')
            if not match_left or not match_right:
                flash('Сәйкестендіру жұптарын енгізіңіз')
                return redirect(url_for('edit_question', q_id=q_id))
            match_pairs = dict(zip(match_left, match_right))
            question.match_pairs = json.dumps(match_pairs)
            question.correct = json.dumps(match_pairs)
            question.options = None
        db.session.commit()
        flash('Сұрақ сәтті өзгертілді')
        return redirect(url_for('edit_test', id=question.test_id))
    if question.question_type == 'checkbox':
        options = json.loads(question.options or '[]')
        correct = json.loads(question.correct or '[]')
        match_pairs = None
    elif question.question_type == 'matching':
        match_pairs = json.loads(question.match_pairs or '{}')
        options = None
        correct = None
    return render_template('edit_question.html', question=question, options=options, correct=correct, match_pairs=match_pairs)

@app.route('/teacher/delete_question/<int:q_id>')
def delete_question(q_id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    question = Question.query.get_or_404(q_id)
    test_id = question.test_id
    db.session.delete(question)
    db.session.commit()
    flash('Сұрақ жойылды')
    return redirect(url_for('edit_test', id=test_id))

@app.route('/teacher/delete/<int:id>')
def delete_test(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    db.session.delete(test)
    db.session.commit()
    flash('Тест жойылды')
    return redirect(url_for('index'))

@app.route('/teacher/open/<int:id>')
def open_test(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    test.access_code = generate_code()
    test.is_open = True
    test.opened_at = datetime.utcnow()
    test.closed_at = None
    test.results.clear()
    db.session.commit()
    flash(f'Тест ашылды, код: {test.access_code}')
    return redirect(url_for('invite_student', id=id))

@app.route('/teacher/close/<int:id>')
def close_test(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    test.is_open = False
    test.closed_at = datetime.utcnow()
    db.session.commit()
    return render_template('results.html', test=test, results=test.results)

@app.route('/teacher/results/<int:id>')
def view_results(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    return render_template('results.html', test=test, results=test.results)

@app.route('/teacher/invite/<int:id>')
def invite_student(id):
    if not session.get('logged_in'):
        return redirect(url_for('index'))
    test = Test.query.get_or_404(id)
    invite_url = f"{request.url_root}take_test_direct/{test.id}/{test.access_code}"
    qr_code = generate_qr_code(invite_url)
    return render_template('invite.html', test=test, invite_url=invite_url, qr_code=qr_code, access_code=test.access_code)

@app.route('/take_test_direct/<int:test_id>/<string:invite_code>')
def take_test_direct(test_id, invite_code):
    test = Test.query.get_or_404(test_id)
    if test.is_open and invite_code == test.access_code:
        session['test_id'] = test.id
        session.pop('student_name', None)
        return render_template('enter_name.html', test=test, invite_code=invite_code)
    flash('Тест қолжетімді емес немесе шақыру қате')
    return redirect(url_for('index'))

@app.route('/submit_name', methods=['POST'])
def submit_name():
    test_id = request.form.get('test_id')
    student_name = request.form.get('student_name')
    invite_code = request.form.get('invite_code')
    if not test_id or not student_name or not invite_code:
        flash('Тест ID, аты-жөніңіз немесе шақыру коды жоқ')
        return redirect(url_for('index'))
    test_id = int(test_id)
    test = Test.query.get(test_id)
    if test and test.is_open and invite_code == test.access_code and student_name:
        session['test_id'] = test.id
        session['student_name'] = student_name
        for q in test.questions:
            if q.question_type == 'checkbox':
                q.options = json.loads(q.options or '[]')
            elif q.question_type == 'matching':
                q.match_pairs = json.loads(q.match_pairs or '{}')
                right_items = list(q.match_pairs.values())
                random.shuffle(right_items)
                q.right_items = right_items
                q.left_items = list(q.match_pairs.keys())
        return render_template('take_test.html', test=test, student_name=student_name)
    flash('Аты-жөніңізді дұрыс енгізіңіз немесе тест қолжетімді емес')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)