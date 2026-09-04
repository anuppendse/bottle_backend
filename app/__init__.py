from flask import Flask, jsonify

from app.config import Config
from app.extensions import db, jwt, cors


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGIN"]}})

    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.products import products_bp
    from app.routes.categories import categories_bp
    from app.routes.batches import batches_bp
    from app.routes.labels import labels_bp
    from app.routes.dispatch import dispatch_bp
    from app.routes.recalls import recalls_bp
    from app.routes.csv_exports import csv_bp
    from app.routes.users import users_bp
    from app.routes.setup import setup_bp
    from app.routes.verify import verify_bp
    from app.routes.permissions import permissions_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.register_blueprint(products_bp, url_prefix="/api/products")
    app.register_blueprint(categories_bp, url_prefix="/api/categories")
    app.register_blueprint(batches_bp, url_prefix="/api/batches")
    app.register_blueprint(labels_bp, url_prefix="/api/labels")
    app.register_blueprint(dispatch_bp, url_prefix="/api/dispatch")
    app.register_blueprint(recalls_bp, url_prefix="/api/recalls")
    app.register_blueprint(csv_bp, url_prefix="/api/csv")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(setup_bp, url_prefix="/api/setup")
    app.register_blueprint(verify_bp, url_prefix="/api/verify")
    app.register_blueprint(permissions_bp, url_prefix="/api/permissions")

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found."}), 404

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    with app.app_context():
        db.create_all()
    return app

    return app
