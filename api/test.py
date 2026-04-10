from flask import Flask
app = Flask(__name__)

@app.route('/api/test')
def hello():
    import os
    token = os.getenv("BOT_TOKEN")
    mongo = os.getenv("MONGO_URI")
    return {
        "token_exists": bool(token),
        "token_prefix": token[:10] if token else None,
        "mongo_exists": bool(mongo),
        "mongo_prefix": mongo[:15] if mongo else None
    }
