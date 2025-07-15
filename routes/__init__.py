# routes 패키지 

def register_blueprints(app):
    """모든 블루프린트를 Flask 앱에 등록합니다."""
    from routes.stock_routes import stock_bp
    from routes.analysis_routes import analysis_bp
    from routes.file_management_routes import file_management_bp
    from routes.auth_routes import auth_bp
    from routes.user_stock_routes import user_stock_bp
    from routes.admin_routes import admin_bp
    from routes.newsletter_routes import newsletter_bp

    # Blueprint 등록
    app.register_blueprint(stock_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(file_management_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(user_stock_bp, url_prefix='/user')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(newsletter_bp, url_prefix='/newsletter') 