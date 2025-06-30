import boto3
import os
import io
import logging
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

class S3Service:
    """AWS S3를 사용한 파일 저장 서비스"""
    
    def __init__(self):
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                region_name=os.getenv('AWS_REGION', 'ap-northeast-2')
            )
            self.bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
            self.base_url = f"https://{self.bucket_name}.s3.ap-northeast-2.amazonaws.com"
            
            if not self.bucket_name:
                raise ValueError("AWS_S3_BUCKET_NAME 환경변수가 설정되지 않았습니다.")
                
        except NoCredentialsError:
            logging.error("AWS 자격 증명이 설정되지 않았습니다.")
            raise
        except Exception as e:
            logging.error(f"S3 클라이언트 초기화 실패: {e}")
            raise
    
    def upload_chart(self, fig, ticker, chart_type='daily'):
        """차트를 S3에 업로드하고 공개 URL 반환"""
        try:
            # 메모리 버퍼에 차트 저장
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            buffer.seek(0)
            
            # 파일 경로 생성 (폴더 구조)
            date_str = datetime.now().strftime('%Y/%m/%d')
            timestamp = datetime.now().strftime('%H%M%S')
            file_key = f"charts/{date_str}/{ticker}_{chart_type}_{timestamp}.png"
            
            # S3에 업로드
            self.s3_client.upload_fileobj(
                buffer,
                self.bucket_name,
                file_key,
                ExtraArgs={
                    'ContentType': 'image/png',
                    'CacheControl': 'max-age=86400',  # 24시간 캐시
                    'ACL': 'public-read'  # 공개 읽기 권한
                }
            )
            
            # 공개 URL 생성
            url = f"{self.base_url}/{file_key}"
            
            logging.info(f"차트 업로드 성공: {url}")
            return url
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logging.error(f"S3 업로드 실패 ({error_code}): {e}")
            return None
        except Exception as e:
            logging.error(f"차트 업로드 실패: {e}")
            return None
        finally:
            if 'buffer' in locals():
                buffer.close()
            # matplotlib 메모리 정리
            import matplotlib.pyplot as plt
            plt.close(fig)
    
    def upload_analysis(self, analysis_text, ticker):
        """분석 결과를 S3에 업로드하고 공개 URL 반환"""
        try:
            date_str = datetime.now().strftime('%Y/%m/%d')
            timestamp = datetime.now().strftime('%H%M%S')
            file_key = f"analysis/{date_str}/{ticker}_analysis_{timestamp}.txt"
            
            # 텍스트를 bytes로 변환
            analysis_bytes = analysis_text.encode('utf-8')
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=analysis_bytes,
                ContentType='text/plain; charset=utf-8',
                CacheControl='max-age=86400',
                ACL='public-read'
            )
            
            url = f"{self.base_url}/{file_key}"
            logging.info(f"분석 결과 업로드 성공: {url}")
            return url
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logging.error(f"분석 결과 S3 업로드 실패 ({error_code}): {e}")
            return None
        except Exception as e:
            logging.error(f"분석 결과 업로드 실패: {e}")
            return None
    
    def delete_old_files(self, days_old=7):
        """오래된 파일 정리 (비용 절약)"""
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            # 파일 목록 조회
            response = self.s3_client.list_objects_v2(Bucket=self.bucket_name)
            
            deleted_count = 0
            if 'Contents' in response:
                for obj in response['Contents']:
                    # 시간대 정보 제거하여 비교
                    obj_date = obj['LastModified'].replace(tzinfo=None)
                    if obj_date < cutoff_date:
                        self.s3_client.delete_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        deleted_count += 1
                        logging.debug(f"삭제된 파일: {obj['Key']}")
            
            logging.info(f"오래된 파일 {deleted_count}개 삭제 완료")
            return deleted_count
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logging.error(f"파일 정리 실패 ({error_code}): {e}")
            return 0
        except Exception as e:
            logging.error(f"파일 정리 실패: {e}")
            return 0
    
    def health_check(self):
        """S3 연결 상태 확인"""
        try:
            # 버킷 존재 확인
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logging.error(f"버킷 '{self.bucket_name}'을 찾을 수 없습니다.")
            elif error_code == '403':
                logging.error("버킷 접근 권한이 없습니다.")
            else:
                logging.error(f"S3 연결 실패 ({error_code}): {e}")
            return False
        except Exception as e:
            logging.error(f"S3 Health Check 실패: {e}")
            return False

# 전역 인스턴스 생성 (지연 초기화)
s3_service = None

def get_s3_service():
    """S3 서비스 싱글톤 인스턴스 반환"""
    global s3_service
    if s3_service is None:
        try:
            s3_service = S3Service()
            if not s3_service.health_check():
                logging.warning("S3 서비스 Health Check 실패")
        except Exception as e:
            logging.error(f"S3 서비스 초기화 실패: {e}")
            s3_service = None
    return s3_service 