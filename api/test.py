from flask import Flask
app = Flask(__name__)

@app.route('/api/test')
def hello():
    import bot
    return f"v2: Bot imported. Doc: {bot.__doc__[:20]}"
