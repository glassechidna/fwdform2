import logging
import os
import re
import requests
import secrets
import sys
from uuid import uuid4

from flask import Flask, abort, jsonify, redirect, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(dotenv_path)
except:
    pass

app = Flask(__name__)
cors = CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

if 'DYNO' in os.environ:
    app.logger.addHandler(logging.StreamHandler(sys.stdout))
    app.logger.setLevel(logging.ERROR)

mailgun_domain = os.environ['MAILGUN_DOMAIN']
mailgun_key = os.environ['MAILGUN_API_KEY']
mailgun_send_url = 'https://api.mailgun.net/v3/%s/messages' % mailgun_domain

registration_enabled = os.environ.get('REGISTRATION_ENABLED') in ['yes', 'true']
registration_password = os.environ['REGISTRATION_PASSWORD'] if registration_enabled else None
default_sender = os.environ.get('DEFAULT_SENDER') or ('fwdform@%s' % mailgun_domain)

ESCAPE_SEQUENCE_RE = re.compile(r"\\|%")
UNESCAPE_SEQUENCE_RE = re.compile(r"\\(\\|%)")
PARAM_RE = re.compile(r"(?<!\\)%((?:[^%]|\\%)*?(?:[^%\\]|\\%))%")


def escape(text):
    return re.sub(ESCAPE_SEQUENCE_RE, lambda m: '\\' + m.group(0), text)


def unescape(text):
    return re.sub(UNESCAPE_SEQUENCE_RE, lambda m: m.group(1), text)


def substitute_params(template, params):
    if not template:
        return None
    return unescape(re.sub(PARAM_RE, lambda m: escape(params[unescape(m.group(1))]), template))


def send_mail(to_address, from_address, subject, body, html_body=None, reply_to_address=None):
    message = {
        'to': [to_address],
        'from': from_address,
        'subject': subject,
        'text': body
    }
    if html_body:
        message['html'] = html_body
    if reply_to_address:
        message['h:Reply-To'] = reply_to_address

    result = requests.post(
        mailgun_send_url,
        auth=('api', mailgun_key),
        data=message
    )
    if result.status_code != requests.codes.ok:
        app.logger.error('Received %(status)d error while sending email to %(email)s: %(error)s', {'status': result.status_code, 'email': to_address, 'error': result.text})
        abort(500)


def falsey_to_none(value):
    return value if value else None


def request_wants_json():
    best = request.accept_mimetypes.best_match(['application/json', 'text/plain'])
    return best == 'application/json' and request.accept_mimetypes[best] > request.accept_mimetypes['text/plain']


class User(db.Model):

    def __init__(self, email):
        self.email = falsey_to_none(email)
        self.public_token = str(uuid4())
        self.private_token = secrets.token_urlsafe(16)

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(320), unique=True, nullable=False) # https://tools.ietf.org/html/rfc5321#page-63
    public_token = db.Column(db.String(36), unique=True, nullable=False)
    private_token = db.Column(db.String(32), nullable=False)


class Form(db.Model):

    def __init__(self, user_id, subject, body, html_body, response_subject, response_body, response_html_body, response_from, response_reply_to):
        self.user_id = user_id
        self.public_token = str(uuid4())
        self.subject = falsey_to_none(subject)
        self.body = falsey_to_none(body)
        self.html_body = falsey_to_none(html_body)
        self.response_subject = falsey_to_none(response_subject)
        self.response_body = falsey_to_none(response_body)
        self.response_html_body = falsey_to_none(response_html_body)
        self.response_from = falsey_to_none(response_from)
        self.response_reply_to = falsey_to_none(response_reply_to)

    id = db.Column(db.Integer, primary_key=True)
    public_token = db.Column(db.String(36), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.Text(), nullable=False)
    body = db.Column(db.Text(), nullable=False)
    html_body = db.Column(db.Text(), nullable=True)
    response_subject = db.Column(db.Text(), nullable=True)
    response_body = db.Column(db.Text(), nullable=True)
    response_html_body = db.Column(db.Text(), nullable=True)
    response_from = db.Column(db.String(320), nullable=True)
    response_reply_to = db.Column(db.String(320), nullable=True)


@app.route('/')
def index():
    return redirect('https://github.com/glassechidna/fwdform2')

@app.route('/register', methods=['POST'])
def register():
    if not registration_enabled:
        abort(500)
    if registration_password and request.form['password'] != registration_password:
        abort(403)

    user = User.query.filter_by(email=request.form['email']).first()
    if user:
        return ('Email already registered', 403)

    user = User(request.form['email'])
    db.session.add(user)
    db.session.commit()

    if request_wants_json():
        return jsonify(
            public_token=user.public_token,
            private_token=user.private_token
        )
    else:
        return f"Public token: {user.public_token}, Private token: {user.private_token}"

@app.route('/user/<public_token>', methods=['DELETE'])
def deregister(public_token):
    user = User.query.filter_by(public_token=public_token).first()
    if not user:
        return ('User not found', 404)

    token = request.form['token']
    if user.private_token != token:
        return ('Token invalid', 403)

    email = user.email
    Form.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()

    if request_wants_json():
        return jsonify()
    else:
        return f"Registration for {email} deleted"

@app.route('/user/<public_token>', methods=['POST'])
def forward_message(public_token):
    user = User.query.filter_by(public_token=public_token).first()
    if not user:
        return ('User not found', 404)

    subject = request.form.get('name') or request.form.get('email') or 'Anonymous'
    send_mail(
        to_address=user.email,
        from_address=default_sender,
        subject=f"Message from {subject}",
        body=request.form['message'],
        reply_to_address=request.form.get('email'),
    )

    if 'redirect' in request.form:
        return redirect(request.form['redirect'])

    return jsonify() if request_wants_json() else 'Message submitted'

@app.route('/user/<public_token>/form', methods=['POST'])
def register_form(public_token):
    user = User.query.filter_by(public_token=public_token).first()
    if not user:
        return ('User not found', 404)

    token = request.form['token']
    if user.private_token != token:
        return ('Token invalid', 403)

    form = Form(
        user_id=user.id,
        subject=request.form['subject'],
        body=request.form['body'],
        html_body=request.form.get('html_body'),
        response_subject=request.form.get('response_subject'),
        response_body=request.form.get('response_body'),
        response_html_body=request.form.get('response_html_body'),
        response_from=request.form.get('response_from'),
        response_reply_to=request.form.get('response_reply_to')
    )
    db.session.add(form)
    db.session.commit()

    if request_wants_json():
        return jsonify(
            form_token=form.public_token
        )
    else:
        return f"Form token: {form.public_token}"

@app.route('/form/<form_token>', methods=['DELETE'])
def deregister_form(form_token):
    form = Form.query.filter_by(public_token=form_token).first()
    if not form:
        return ('Form not found', 404)

    user = User.query.filter_by(id=form.user_id).first()
    if not user:
        return ('User not found', 404)

    token = request.form['token']
    if user.private_token != token:
        return ('Token invalid', 403)

    subject = form.subject
    db.session.delete(form)
    db.session.commit()

    return jsonify() if request_wants_json() else f"Form '{subject}' deleted"

@app.route('/form/<form_token>', methods=['POST'])
def forward_form(form_token):
    form = Form.query.filter_by(public_token=form_token).first()
    if not form:
        return ('Form not found', 404)

    user = User.query.filter_by(id=form.user_id).first()
    if not user:
        return ('User not found', 404)

    submitter_email = request.form.get('email')

    send_mail(
        to_address=user.email,
        from_address=default_sender,
        subject=substitute_params(form.subject, request.form),
        body=substitute_params(form.body, request.form),
        reply_to_address=submitter_email,
    )

    if submitter_email and form.response_body:
        send_mail(
            to_address=submitter_email,
            from_address=form.response_from or default_sender,
            subject=substitute_params(form.response_subject, request.form) or 'Your confirmation',
            body=substitute_params(form.response_body, request.form),
            html_body=substitute_params(form.response_html_body, request.form),
            reply_to_address=form.response_reply_to
        )

    if 'redirect' in request.form:
        return redirect(request.form['redirect'])

    return jsonify() if request_wants_json() else 'Form submitted'
