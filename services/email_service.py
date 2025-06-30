import os
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# SendGrid 임포트 (선택적)
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment, FileContent, FileName, FileType, Disposition
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False

from config import (
    DEBUG, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL, SENDGRID_FROM_NAME,
    MAIL_SERVER, MAIL_PORT, MAIL_USE_TLS, MAIL_USERNAME, MAIL_PASSWORD, MAIL_DEFAULT_SENDER
)
from models import db, EmailLog, User

logger = logging.getLogger(__name__)

class EmailService:
    """이메일 서비스 (Mailtrap/SendGrid 통합)"""
    
    def __init__(self):
        self.debug_mode = DEBUG
        
        if self.debug_mode:
            # Mailtrap 설정
            logger.info("이메일 서비스 초기화: Mailtrap 모드")
            self.mail_server = MAIL_SERVER
            self.mail_port = MAIL_PORT
            self.mail_use_tls = MAIL_USE_TLS
            self.mail_username = MAIL_USERNAME
            self.mail_password = MAIL_PASSWORD
            self.from_email = MAIL_DEFAULT_SENDER
            self.from_name = "주식 분석 뉴스레터 (테스트)"
            self.sendgrid_client = None
        else:
            # SendGrid 설정
            logger.info("이메일 서비스 초기화: SendGrid 모드")
            self.api_key = SENDGRID_API_KEY
            self.from_email = SENDGRID_FROM_EMAIL
            self.from_name = SENDGRID_FROM_NAME
            
            if not self.api_key and SENDGRID_AVAILABLE:
                logger.warning("SendGrid API 키가 설정되지 않았습니다.")
                self.sendgrid_client = None
            elif SENDGRID_AVAILABLE:
                self.sendgrid_client = SendGridAPIClient(api_key=self.api_key)
            else:
                logger.warning("SendGrid 패키지가 설치되지 않았습니다.")
                self.sendgrid_client = None
    
    def send_newsletter(self, user, subject, html_content, text_content=None, attachments=None):
        """뉴스레터 이메일 발송"""
        try:
            if self.debug_mode:
                # Mailtrap 사용
                return self._send_via_smtp(user, subject, html_content, text_content, attachments)
            else:
                # SendGrid 사용
                return self._send_via_sendgrid(user, subject, html_content, text_content, attachments)
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"뉴스레터 이메일 발송 실패: {user.email} - {error_msg}")
            self._log_email(user.id, 'newsletter', subject, 'failed', error_msg)
            return False, error_msg
    
    def _send_via_smtp(self, user, subject, html_content, text_content=None, attachments=None):
        """SMTP를 통한 이메일 발송 (Mailtrap)"""
        try:
            # 메시지 생성
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = user.email
            
            # 텍스트 버전 추가
            if text_content:
                part1 = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(part1)
            
            # HTML 버전 추가
            part2 = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part2)
            
            # 첨부파일 추가
            if attachments:
                for attachment in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment['content'])
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        f'attachment; filename= {attachment["filename"]}'
                    )
                    msg.attach(part)
            
            # SMTP 서버 연결 및 발송
            server = smtplib.SMTP(self.mail_server, self.mail_port)
            if self.mail_use_tls:
                server.starttls()
            server.login(self.mail_username, self.mail_password)
            text = msg.as_string()
            server.sendmail(self.from_email, user.email, text)
            server.quit()
            
            # 로그 저장
            self._log_email(user.id, 'newsletter', subject, 'sent')
            
            logger.info(f"뉴스레터 이메일 발송 성공 (SMTP): {user.email} - {subject}")
            return True, "SMTP 발송 성공"
            
        except Exception as e:
            raise e
    
    def _send_via_sendgrid(self, user, subject, html_content, text_content=None, attachments=None):
        """SendGrid를 통한 이메일 발송"""
        try:
            if not self.sendgrid_client:
                raise ValueError("SendGrid 클라이언트가 초기화되지 않았습니다.")
            
            # 이메일 생성
            message = Mail(
                from_email=Email(self.from_email, self.from_name),
                to_emails=To(user.email),
                subject=subject,
                html_content=Content("text/html", html_content)
            )
            
            if text_content:
                message.content = Content("text/plain", text_content)
            
            # 첨부파일 추가
            if attachments:
                for attachment in attachments:
                    file_attachment = Attachment(
                        FileContent(attachment['content']),
                        FileName(attachment['filename']),
                        FileType(attachment['type']),
                        Disposition('attachment')
                    )
                    message.add_attachment(file_attachment)
            
            # 이메일 발송
            response = self.sendgrid_client.send(message)
            
            # 로그 저장
            self._log_email(user.id, 'newsletter', subject, 'sent')
            
            logger.info(f"뉴스레터 이메일 발송 성공 (SendGrid): {user.email} - {subject}")
            return True, response.status_code
            
        except Exception as e:
            raise e
    
    def send_analysis_notification(self, user, ticker, analysis_type, analysis_url):
        """분석 완료 알림 이메일 발송"""
        try:
            subject = f"[주식 분석] {ticker} {analysis_type} 분석 완료"
            
            html_content = f"""
            <html>
            <body>
                <h2>주식 분석 완료 알림</h2>
                <p>안녕하세요, {user.get_full_name()}님!</p>
                <p>요청하신 <strong>{ticker}</strong>의 {analysis_type} 분석이 완료되었습니다.</p>
                <p><a href="{analysis_url}" style="background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">분석 결과 보기</a></p>
                <p>감사합니다.</p>
            </body>
            </html>
            """
            
            text_content = f"""
            주식 분석 완료 알림
            
            안녕하세요, {user.get_full_name()}님!
            
            요청하신 {ticker}의 {analysis_type} 분석이 완료되었습니다.
            분석 결과 보기: {analysis_url}
            
            감사합니다.
            """
            
            return self.send_newsletter(user, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"분석 알림 이메일 발송 실패: {user.email} - {e}")
            return False, str(e)
    
    def send_welcome_email(self, user):
        """환영 이메일 발송"""
        try:
            subject = "주식 분석 뉴스레터에 오신 것을 환영합니다!"
            
            html_content = f"""
            <html>
            <body>
                <h2>환영합니다!</h2>
                <p>안녕하세요, {user.get_full_name()}님!</p>
                <p>주식 분석 뉴스레터 서비스에 가입해 주셔서 감사합니다.</p>
                <p>이제 다음과 같은 서비스를 이용하실 수 있습니다:</p>
                <ul>
                    <li>AI 기반 주식 분석</li>
                    <li>기술적 차트 분석</li>
                    <li>개인화된 뉴스레터</li>
                    <li>실시간 시장 정보</li>
                </ul>
                <p>언제든지 문의사항이 있으시면 연락해 주세요.</p>
                <p>감사합니다.</p>
            </body>
            </html>
            """
            
            text_content = f"""
            환영합니다!
            
            안녕하세요, {user.get_full_name()}님!
            
            주식 분석 뉴스레터 서비스에 가입해 주셔서 감사합니다.
            
            이제 다음과 같은 서비스를 이용하실 수 있습니다:
            - AI 기반 주식 분석
            - 기술적 차트 분석
            - 개인화된 뉴스레터
            - 실시간 시장 정보
            
            언제든지 문의사항이 있으시면 연락해 주세요.
            
            감사합니다.
            """
            
            return self.send_newsletter(user, subject, html_content, text_content)
            
        except Exception as e:
            logger.error(f"환영 이메일 발송 실패: {user.email} - {e}")
            return False, str(e)
    
    def _log_email(self, user_id, email_type, subject, status, error_message=None):
        """이메일 발송 로그 저장"""
        try:
            log = EmailLog(
                user_id=user_id,
                email_type=email_type,
                subject=subject,
                status=status,
                error_message=error_message
            )
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            logger.error(f"이메일 로그 저장 실패: {e}")

# 전역 이메일 서비스 인스턴스
email_service = EmailService() 