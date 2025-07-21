import boto3
from botocore.exceptions import ClientError
import os
import uuid
from typing import Optional

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=os.getenv('S3_ENDPOINT'),
            aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
            aws_secret_access_key=os.getenv('S3_SECRET_KEY')
        )
        self.bucket = os.getenv('S3_BUCKET')
    
    async def upload_file(self, file_content: bytes, filename: str) -> Optional[str]:
        """Upload file to S3 and return URL"""
        try:
            # Generate unique filename
            ext = filename.split('.')[-1] if '.' in filename else 'jpg'
            unique_filename = f"uploads/{uuid.uuid4()}.{ext}"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=unique_filename,
                Body=file_content,
                ContentType=self._get_content_type(ext)
            )
            
            # Return public URL
            return f"{os.getenv('S3_ENDPOINT')}/{self.bucket}/{unique_filename}"
            
        except ClientError as e:
            print(f"Error uploading to S3: {e}")
            return None
    
    def _get_content_type(self, ext: str) -> str:
        """Get content type by file extension"""
        content_types = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        return content_types.get(ext.lower(), 'application/octet-stream')

# Глобальный экземпляр
s3_service = S3Service()