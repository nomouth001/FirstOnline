from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, TextAreaField, SelectField, TimeField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from models import User, StockList

class LoginForm(FlaskForm):
    """로그인 폼"""
    username = StringField('사용자명', validators=[DataRequired()])
    password = PasswordField('비밀번호', validators=[DataRequired()])
    remember_me = BooleanField('로그인 상태 유지')
    submit = SubmitField('로그인')

class RegistrationForm(FlaskForm):
    """회원가입 폼"""
    username = StringField('사용자명', validators=[DataRequired(), Length(min=3, max=25)])
    email = StringField('이메일', validators=[DataRequired(), Email()])
    first_name = StringField('이름', validators=[DataRequired(), Length(max=50)])
    last_name = StringField('성', validators=[DataRequired(), Length(max=50)])
    password = PasswordField('비밀번호', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('비밀번호 확인', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('회원가입')
    
    def validate_username(self, username):
        """사용자명 중복 확인"""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('이미 사용 중인 사용자명입니다.')
    
    def validate_email(self, email):
        """이메일 중복 확인"""
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('이미 사용 중인 이메일입니다.')

class ProfileForm(FlaskForm):
    """프로필 수정 폼"""
    first_name = StringField('이름', validators=[DataRequired(), Length(max=50)])
    last_name = StringField('성', validators=[DataRequired(), Length(max=50)])
    email = StringField('이메일', validators=[DataRequired(), Email()])
    submit = SubmitField('프로필 업데이트')
    
    def __init__(self, original_email, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
    
    def validate_email(self, email):
        """이메일 중복 확인 (자신 제외)"""
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('이미 사용 중인 이메일입니다.')

class ChangePasswordForm(FlaskForm):
    """비밀번호 변경 폼"""
    current_password = PasswordField('현재 비밀번호', validators=[DataRequired()])
    new_password = PasswordField('새 비밀번호', validators=[DataRequired(), Length(min=6)])
    new_password2 = PasswordField('새 비밀번호 확인', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('비밀번호 변경')

class StockListForm(FlaskForm):
    """종목 리스트 생성/수정 폼"""
    name = StringField('리스트 이름', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('설명')
    is_public = BooleanField('공개 리스트')
    submit = SubmitField('저장')
    
    def __init__(self, user_id=None, list_id=None, *args, **kwargs):
        super(StockListForm, self).__init__(*args, **kwargs)
        self.user_id = user_id
        self.list_id = list_id
    
    def validate_name(self, name):
        """리스트 이름 중복 확인"""
        if self.user_id:
            existing_list = StockList.query.filter_by(
                user_id=self.user_id, 
                name=name.data
            ).first()
            if existing_list and (not self.list_id or existing_list.id != self.list_id):
                raise ValidationError('이미 존재하는 리스트 이름입니다.')

class AddStockForm(FlaskForm):
    """종목 추가 폼"""
    ticker = StringField('종목 코드', validators=[DataRequired(), Length(max=20)])
    name = StringField('종목명', validators=[DataRequired(), Length(max=200)])
    submit = SubmitField('종목 추가') 