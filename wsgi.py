from app import app

application = app  # For WSGI servers like gunicorn/uwsgi or PythonAnywhere

if __name__ == 'main':
    app.run()