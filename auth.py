import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session

auth_bp = Blueprint('auth', __name__)


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('auth.login'))
        return view_func(*args, **kwargs)
    return wrapper


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if (username == os.getenv('ADMIN_USERNAME', 'admin') and
                password == os.getenv('ADMIN_PASSWORD', 'admin123')):
            session['admin'] = True
            return redirect(url_for('dashboard'))
        error = "Login yoki parol noto‘g‘ri!"
    return render_template('login.html', error=error)


@auth_bp.route('/logout')
@admin_required
def logout():
    session.pop('admin', None)
    return redirect(url_for('auth.login'))